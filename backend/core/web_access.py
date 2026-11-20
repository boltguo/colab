"""Browser password gate and browser-only API key configuration."""
import asyncio
from html import escape
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .security import AuthState, SESSION_COOKIE, SESSION_TTL, create_session, matches_key, same_origin

_LOGIN_STYLE = Path(__file__).with_name("login.css").read_text(encoding="utf-8")
_LOGIN_ART = Path(__file__).with_name("login_art.svg").read_text(encoding="utf-8")


def _detect_request_locale(request: Optional[Request]) -> Literal["en", "zh"]:
    if request is None:
        return "en"
    raw = request.headers.get("accept-language", "")
    if not raw.strip():
        return "en"
    weighted: list[tuple[float, int, str]] = []
    for idx, part in enumerate(raw.split(",")):
        piece = part.strip()
        if not piece:
            continue
        segments = [seg.strip() for seg in piece.split(";")]
        tag = segments[0].lower()
        if not tag:
            continue
        q = 1.0
        invalid_q = False
        for param in segments[1:]:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:].strip())
                except ValueError:
                    invalid_q = True
                break
        if invalid_q or q <= 0.0:
            continue
        weighted.append((q, -idx, tag))
    weighted.sort(reverse=True)
    for _, _, tag in weighted:
        if tag.startswith("zh"):
            return "zh"
        if tag.startswith("en"):
            return "en"
    return "en"


def login_page(error: str = "", locale: str = "en") -> HTMLResponse:
    if locale == "zh":
        html_lang = "zh-CN"
        title = "访问验证"
        heading = "访问密码"
        submit = "进入"
    else:
        html_lang = "en"
        title = "Access Verification"
        heading = "Access Password"
        submit = "Sign in"
    return HTMLResponse(
        f"""<!doctype html><html lang="{html_lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>"""
        + _LOGIN_STYLE
        + f"""</style></head>
<body><main aria-labelledby="access-title"><div class="artwork" aria-hidden="true">"""
        + _LOGIN_ART
        + f"""</div>
<h1 id="access-title">{heading}</h1>
<form method="post" action="/auth/login">
<input id="password" name="password" type="password" aria-label="{heading}" autocomplete="current-password" maxlength="4096" required autofocus>
"""
        + (f'<p class="error" role="alert">{escape(error)}</p>' if error else "")
        + f"""
<button type="submit">{submit}</button></form></main></body></html>""",
        status_code=401 if error else 200,
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        },
    )


class ApiKeyUpdate(BaseModel):
    api_key: str = Field(max_length=512)


def install_web_access(app: FastAPI, auth: AuthState) -> None:
    @app.middleware("http")
    async def access_gate(request: Request, call_next):
        public_route = request.url.path in {"/api/v1/health", "/auth/login"} or (
            request.url.path == "/auth/logout" and request.method == "POST"
        )
        if request.method != "OPTIONS" and not public_route:
            is_api = request.url.path.startswith(("/api/", "/v1/"))
            browser_session = auth.browser_authenticated(request)
            allowed = auth.allows_api(request) if is_api else not auth.access_password or browser_session
            if not allowed:
                if request.method in {"GET", "HEAD"} and not is_api:
                    return RedirectResponse("/auth/login", status_code=303)
                detail = "API Key 无效或缺失，请提供配置的 API Key。" if is_api else "请先输入应用访问密码。"
                return JSONResponse(
                    {"detail": detail},
                    status_code=401,
                    headers={"X-Colab-Login-Required": "1"},
                )
            if browser_session and not (is_api and auth.has_api_key(request)) and request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request):
                return JSONResponse({"detail": "不允许跨站操作。"}, status_code=403)
        return await call_next(request)

    @app.get("/auth/login", include_in_schema=False)
    async def get_login(request: Request):
        if not auth.access_password or auth.browser_authenticated(request):
            return RedirectResponse("/", status_code=303)
        return login_page(locale=_detect_request_locale(request))

    @app.post("/auth/login", include_in_schema=False)
    async def post_login(request: Request):
        if not same_origin(request):
            return JSONResponse({"detail": "不允许跨站登录。"}, status_code=403)
        if not auth.access_password:
            return RedirectResponse("/", status_code=303)
        form = await request.form()
        password = form.get("password", "")
        if not isinstance(password, str) or len(password) > 4096 or not matches_key(password, auth.access_password):
            await asyncio.sleep(0.25)
            locale = _detect_request_locale(request)
            error_msg = "密码不正确，请重试。" if locale == "zh" else "Incorrect password. Please try again."
            return login_page(error_msg, locale=locale)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            create_session(auth.access_password),
            max_age=SESSION_TTL,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
        )
        return response

    @app.post("/auth/api-key", include_in_schema=False)
    async def set_api_key(payload: ApiKeyUpdate, request: Request):
        if not auth.browser_authenticated(request):
            raise HTTPException(status_code=401, detail="请先使用应用访问密码登录。")
        try:
            auth.set_api_key(payload.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"configured": auth.api_key_configured}

    @app.post("/auth/logout", include_in_schema=False)
    async def logout(request: Request):
        if not same_origin(request):
            return JSONResponse({"detail": "不允许跨站操作。"}, status_code=403)
        response = RedirectResponse("/auth/login", status_code=303)
        response.delete_cookie(
            SESSION_COOKIE,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
        )
        return response
