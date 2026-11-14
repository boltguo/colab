"""Environment and path configuration for a single-feature runtime."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _default_data_dir(feature: str) -> Path:
    content_root = Path("/content")
    if content_root.is_dir() and not content_root.is_symlink() and os.access(content_root, os.W_OK):
        return content_root / "app_data" / feature
    return Path.cwd() / ".runtime_data" / feature


def _resolve_dist_dir(feature: str, repo_root: Path) -> Optional[Path]:
    explicit = os.environ.get("COLAB_DIST_DIR", "").strip()
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_dir() else None

    candidates = [
        repo_root / "dist" / feature,
        repo_root / "dist",
        repo_root / "frontend" / "apps" / feature / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


@dataclass(frozen=True)
class AppSettings:
    feature: str
    host: str
    port: int
    data_dir: Path
    dist_dir: Optional[Path]
    api_key: str
    mock_inference: bool
    repo_root: Path

    @classmethod
    def from_env(cls, feature_override: Optional[str] = None) -> "AppSettings":
        repo_root = Path(__file__).resolve().parent.parent.parent
        feature = (feature_override or os.environ.get("COLAB_FEATURE") or "indextts-2.5").strip()
        host = os.environ.get("COLAB_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = int(os.environ.get("COLAB_PORT", "8188"))
        raw_data_dir = os.environ.get("COLAB_DATA_DIR", "").strip()
        data_dir = Path(raw_data_dir) if raw_data_dir else _default_data_dir(feature)
        dist_dir = _resolve_dist_dir(feature, repo_root)
        api_key = os.environ.get("COLAB_API_KEY", "").strip()
        mock_raw = os.environ.get("COLAB_MOCK_INFERENCE", "").strip().lower()
        mock_inference = mock_raw in {"1", "true", "yes", "on"}
        return cls(
            feature=feature,
            host=host,
            port=port,
            data_dir=data_dir,
            dist_dir=dist_dir,
            api_key=api_key,
            mock_inference=mock_inference,
            repo_root=repo_root,
        )
