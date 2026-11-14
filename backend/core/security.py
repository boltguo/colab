"""Path symlink safety checks and optional Bearer/Header API Key auth."""
import hmac
from pathlib import Path
import sys
from typing import Optional

from fastapi import Header, HTTPException, Query, Request, WebSocket, status

_MACOS_SYSTEM_ROOT_SYMLINKS = {Path("/var"), Path("/tmp"), Path("/etc")}


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
        if not provided or not hmac.compare_digest(provided, expected_api_key):
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
    return bool(provided) and hmac.compare_digest(provided, expected_api_key)
