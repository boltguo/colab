"""Path symlink safety checks and optional Bearer/Header API Key auth."""
import hmac
import hashlib
import json
import os
import secrets
import tempfile
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


def create_session(access_password: str) -> str:
    payload = f"{int(time.time()) + SESSION_TTL}.{secrets.token_urlsafe(24)}"
    signature = hmac.new(access_password.encode(), b"colab-session:" + payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def valid_session(cookie: str, access_password: str) -> bool:
    if not cookie or not access_password or len(cookie) > 256:
        return False
    try:
        expires, nonce, signature = cookie.split(".")
        if not nonce or not time.time() < int(expires) <= time.time() + SESSION_TTL:
            return False
        expected = hmac.new(access_password.encode(), f"colab-session:{expires}.{nonce}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


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


class AuthState:
    """Separate browser access from the API key configured inside the application."""

    def __init__(self, access_password: str, data_dir: Path, api_key: str = ""):
        self.access_password = access_password
        self.key_path = ensure_safe_path(data_dir / "api_key.json", stop_at=data_dir)
        self.key_digest = hashlib.sha256(api_key.encode()).hexdigest() if api_key else ""
        if self.key_path.exists():
            data = json.loads(self.key_path.read_text(encoding="utf-8"))
            digest = data.get("sha256", "")
            if not isinstance(digest, str) or (digest and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest))):
                raise RuntimeError("API Key 配置损坏，请检查 api_key.json。")
            self.key_digest = digest

    @property
    def api_key_configured(self) -> bool:
        return bool(self.key_digest)

    @property
    def api_required(self) -> bool:
        return self.api_key_configured

    def browser_authenticated(self, request) -> bool:
        return valid_session(request.cookies.get(SESSION_COOKIE, ""), self.access_password)

    def has_api_key(self, request) -> bool:
        provided = extract_token(request.headers.get("authorization"), request.headers.get("x-api-key"))
        provided = provided or request.query_params.get("api_key", "").strip()
        return bool(provided and self.key_digest) and hmac.compare_digest(
            hashlib.sha256(provided.encode()).hexdigest(), self.key_digest
        )

    def allows_api(self, request) -> bool:
        return not self.api_required or self.browser_authenticated(request) or self.has_api_key(request)

    def set_api_key(self, key: str) -> None:
        if key and (not 8 <= len(key) <= 512 or not key.isascii() or any(c.isspace() or not c.isprintable() for c in key)):
            raise ValueError("API Key 请使用 8～512 位字母、数字或符号，不含空格。")
        digest = hashlib.sha256(key.encode()).hexdigest() if key else ""
        ensure_safe_path(self.key_path, stop_at=self.key_path.parent)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.key_path.parent, encoding="utf-8", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                os.chmod(tmp_path, 0o600)
                json.dump({"sha256": digest}, tmp)
                tmp.close()
                tmp_path.replace(self.key_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        self.key_digest = digest


def make_auth_dependency(auth: AuthState):
    async def verify_request_auth(
        request: Request,
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        api_key_query: Optional[str] = Query(default=None, alias="api_key"),
    ) -> None:
        if not auth.allows_api(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key 无效或缺失，请在 Authorization: Bearer <API_KEY> 或 X-API-Key 请求头中提供。",
            )

    return verify_request_auth


def verify_ws_auth(websocket: WebSocket, auth: AuthState) -> bool:
    if not auth.api_required:
        return True
    return auth.has_api_key(websocket) or (
        same_origin(websocket) and auth.browser_authenticated(websocket)
    )
