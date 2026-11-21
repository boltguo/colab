"""Path symlink safety checks and same-origin request verification."""
from pathlib import Path
import sys
from typing import Iterable, Optional

_MACOS_SYSTEM_ROOT_SYMLINKS = {Path("/var"), Path("/tmp"), Path("/etc")}
_LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _is_loopback_host(host: str) -> bool:
    clean = host.strip().lower()
    if clean.startswith("[") and "]" in clean:
        hostname = clean[1 : clean.index("]")]
    elif clean.count(":") == 1:
        hostname = clean.split(":", 1)[0]
    else:
        hostname = clean
    return hostname in {"127.0.0.1", "localhost", "::1"}


def same_origin(request, extra_origins: Iterable[str] = ()) -> bool:
    """Verify request Origin matches the active host or Colab proxy origin."""
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        return True

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    scheme = "https" if (forwarded_proto in {"https", "wss"} or request.url.scheme in {"https", "wss"}) else "http"

    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    host = forwarded_host or (request.headers.get("host") or request.url.netloc or "").strip()

    allowed = {item.strip().rstrip("/") for item in extra_origins if item and item.strip()}
    if host:
        allowed.add(f"{scheme}://{host}")
        if not forwarded_proto and not _is_loopback_host(host):
            # Colab's managed proxy may terminate TLS at the edge and forward plain HTTP locally.
            allowed.add(f"https://{host}")
    return origin in allowed


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
