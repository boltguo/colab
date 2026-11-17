"""Path symlink safety checks and optional Bearer/Header API Key auth."""
import hmac
import hashlib
import secrets
import time
from pathlib import Path
import sys
from typing import Optional

from fastapi import Header, HTTPException, Query, Request, WebSocket, status

_MACOS_SYSTEM_ROOT_SYMLINKS = {Path("/var"), Path("/tmp"), Path("/etc")}
SESSION_COOKIE = "colab_session"
SESSION_TTL = 12 * 60 * 60


def matches_key(provided: str, expected: str) -> bool:
    return bool(provided and expected) and hmac.compare_digest(provided.encode(), expected.encode())


def create_session(api_key: str) -> str:
    payload = f"{int(time.time()) + SESSION_TTL}.{secrets.token_urlsafe(24)}"
    signature = hmac.new(api_key.encode(), b"colab-session:" + payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def valid_session(cookie: str, api_key: str) -> bool:
    if not cookie or not api_key or len(cookie) > 256:
        return False
    try:
        expires, nonce, signature = cookie.split(".")
        if not nonce or not time.time() < int(expires) <= time.time() + SESSION_TTL:
            return False
        expected = hmac.new(api_key.encode(), f"colab-session:{expires}.{nonce}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def request_has_key(request, api_key: str) -> bool:
    provided = extract_token(request.headers.get("authorization"), request.headers.get("x-api-key"))
    return matches_key(provided or request.query_params.get("api_key", "").strip(), api_key)


def same_origin(request) -> bool:
    origin = request.headers.get("origin")
    scheme = "https" if request.url.scheme in {"https", "wss"} else "http"
    return not origin or origin.rstrip("/") == f"{scheme}://{request.url.netloc}"


def ensure_safe_path(path: Path, stop_at: Optional[Path] = None) -> Path:
    """Reject any symlink along path or its ancestors up to stop_at."""
    target = Path(path)
    if target.is_symlink():
        raise RuntimeError(f"拒绝访问软链接路径：{target}")
    boundary = Path(stop_at).resolve() if stop_at and stop_at.exists() else None
    for candidate in [target, *target.parents]:
        if (
            candidate != target
            and sys.platform == "darwin"
            and candidate in _MACOS_SYSTEM_ROOT_SYMLINKS
        ):
            continue
        if candidate.is_symlink():
            raise RuntimeError(f"拒绝访问软链接路径：{candidate}")
        if boundary is not None and candidate.exists():
            try:
                if candidate.resolve() == boundary:
                    break
            except OSError:
                pass
    return target


def ensure_safe_dir(path: Path, stop_at: Optional[Path] = None) -> Path:
    ensure_safe_path(path, stop_at=stop_at)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError(f"目录不能为软链接：{path}")
    return path


def extract_token(authorization: Optional[str], x_api_key: Optional[str]) -> str:
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    if x_api_key:
        return x_api_key.strip()
    return ""


def make_auth_dependency(expected_api_key: str):
    async def verify_request_auth(
        request: Request,
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        api_key_query: Optional[str] = Query(default=None, alias="api_key"),
    ) -> None:
        if not expected_api_key:
            return
        provided = extract_token(authorization, x_api_key) or (api_key_query or "").strip()
        if not matches_key(provided, expected_api_key) and not valid_session(request.cookies.get(SESSION_COOKIE, ""), expected_api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key 无效或缺失，请在 Authorization: Bearer <API_KEY> 或 X-API-Key 请求头中提供。",
            )

    return verify_request_auth


def verify_ws_auth(websocket: WebSocket, expected_api_key: str) -> bool:
    if not expected_api_key:
        return True
    auth_header = websocket.headers.get("authorization")
    x_key = websocket.headers.get("x-api-key")
    q_key = websocket.query_params.get("api_key", "")
    provided = extract_token(auth_header, x_key) or q_key.strip()
    return matches_key(provided, expected_api_key) or (
        same_origin(websocket) and valid_session(websocket.cookies.get(SESSION_COOKIE, ""), expected_api_key)
    )
