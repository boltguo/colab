"""Shared-password gate for the Studio, API docs, and private media."""
import asyncio
from html import escape
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .security import SESSION_COOKIE, SESSION_TTL, create_session, matches_key, request_has_key, same_origin, valid_session

_LOGIN_STYLE = Path(__file__).with_name("login.css").read_text(encoding="utf-8")
_LOGIN_ART = Path(__file__).with_name("login_art.svg").read_text(encoding="utf-8")


def login_page(error: str = "") -> HTMLResponse:
    return HTMLResponse("""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>访问验证</title>
<style>""" + _LOGIN_STYLE + """</style></head>
<body><main><div class="artwork" aria-hidden="true">""" + _LOGIN_ART + """</div>
<section class="access-form" aria-labelledby="access-title"><h1 id="access-title">访问密码</h1>
<form method="post" action="/auth/login">
<input id="password" name="password" type="password" aria-label="访问密码" autocomplete="current-password" maxlength="4096" required autofocus>
""" + (f'<p class="error" role="alert">{escape(error)}</p>' if error else "") + """
<button type="submit">进入</button></form></section></main></body></html>""", status_code=401 if error else 200,
        headers={"Cache-Control": "no-store, no-transform", "X-Frame-Options": "DENY",
                 "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})


def install_web_access(app: FastAPI, api_key: str) -> None:
    @app.middleware("http")
    async def access_gate(request: Request, call_next):
        public_route = request.url.path in {"/api/v1/health", "/auth/login"} or (
            request.url.path == "/auth/logout" and request.method == "POST"
        )
        if api_key and request.method != "OPTIONS" and not public_route:
            explicit_key = request_has_key(request, api_key)
            browser_session = valid_session(request.cookies.get(SESSION_COOKIE, ""), api_key)
            if not explicit_key and not browser_session:
                if request.method in {"GET", "HEAD"} and not request.url.path.startswith(("/api/", "/v1/")):
                    return RedirectResponse("/auth/login", status_code=303)
                return JSONResponse({"detail": "请先输入访问密码，或使用 Bearer API Key。"}, status_code=401,
                                    headers={"X-Colab-Login-Required": "1"})
            if browser_session and not explicit_key and request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request):
                return JSONResponse({"detail": "不允许跨站操作。"}, status_code=403)
        return await call_next(request)

    @app.get("/auth/login", include_in_schema=False)
    async def get_login(request: Request):
        if not api_key or valid_session(request.cookies.get(SESSION_COOKIE, ""), api_key):
            return RedirectResponse("/", status_code=303)
        return login_page()

    @app.post("/auth/login", include_in_schema=False)
    async def post_login(request: Request):
        if not same_origin(request):
            return JSONResponse({"detail": "不允许跨站登录。"}, status_code=403)
        if not api_key:
            return RedirectResponse("/", status_code=303)
        form = await request.form()
        password = form.get("password", "")
        if not isinstance(password, str) or len(password) > 4096 or not matches_key(password, api_key):
            await asyncio.sleep(0.25)
            return login_page("密码不正确，请重试。")
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(SESSION_COOKIE, create_session(api_key), max_age=SESSION_TTL,
                            httponly=True, secure=request.url.scheme == "https", samesite="strict")
        return response

    @app.post("/auth/logout", include_in_schema=False)
    async def logout(request: Request):
        if not same_origin(request):
            return JSONResponse({"detail": "不允许跨站操作。"}, status_code=403)
        response = RedirectResponse("/auth/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, httponly=True, secure=request.url.scheme == "https", samesite="strict")
        return response
