"""Unified CLI entrypoint to run a single-feature FastAPI Web Studio server."""
import argparse
import os
from pathlib import Path
import sys

# Ensure repository/release root is importable when invoked directly as a script
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uvicorn  # noqa: E402

from backend.core.app_factory import create_feature_app  # noqa: E402
from backend.core.config import AppSettings  # noqa: E402
from backend.features.registry import get_feature_plugin  # noqa: E402


def build_app(feature: str = ""):
    target_feature = feature or os.environ.get("COLAB_FEATURE", "indextts-2.5")
    plugin = get_feature_plugin(target_feature)
    settings = AppSettings.from_env(feature_override=plugin.name)
    return create_feature_app(plugin, settings=settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Colab Feature Web Studio Server")
    parser.add_argument("--feature", default=os.environ.get("COLAB_FEATURE", "indextts-2.5"))
    parser.add_argument("--host", default=os.environ.get("COLAB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("COLAB_PORT", "8188")))
    parser.add_argument("--dist-dir", default=os.environ.get("COLAB_DIST_DIR", ""))
    parser.add_argument("--data-dir", default=os.environ.get("COLAB_DATA_DIR", ""))
    parser.add_argument("--mock", action="store_true", help="Enable mock inference mode for UI/API testing")
    args = parser.parse_args()

    os.environ["COLAB_FEATURE"] = args.feature
    os.environ["COLAB_HOST"] = args.host
    os.environ["COLAB_PORT"] = str(args.port)
    if args.dist_dir:
        os.environ["COLAB_DIST_DIR"] = args.dist_dir
    if args.data_dir:
        os.environ["COLAB_DATA_DIR"] = args.data_dir
    if args.mock:
        os.environ["COLAB_MOCK_INFERENCE"] = "1"

    app = build_app(args.feature)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
