"""Build per-feature frontend dist and package deterministic GitHub Release tarballs.

Usage:
  python3 tools/build_release.py --tag v0.1.0
  python3 tools/build_release.py --feature indextts-2.5 --tag v0.1.0 --skip-frontend-build
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
RELEASE_DIR = ROOT / "release_artifacts"
MANIFEST_PATH = ROOT / "tools" / "release_manifest.json"

# Map public feature slug -> backend python module folder name
FEATURE_SPECS: Dict[str, Dict[str, str]] = {
    "indextts-2.5": {
        "npm_pkg": "@colab/app-indextts-2.5",
        "backend_module": "indextts_2_5",
    },
    "qwen-image-2.1": {
        "npm_pkg": "@colab/app-qwen-image-2.1",
        "backend_module": "qwen_image_2_1",
    },
    "qwen3.8-27b": {
        "npm_pkg": "@colab/app-qwen3.8-27b",
        "backend_module": "qwen3_8_27b",
    },
    "minimax-h3": {
        "npm_pkg": "@colab/app-minimax-h3",
        "backend_module": "minimax_h3",
    },
    "seedvr2": {
        "npm_pkg": "@colab/app-seedvr2",
        "backend_module": "seedvr2",
    },
    "h3-character-swap": {
        "npm_pkg": "@colab/app-h3-character-swap",
        "backend_module": "h3_character_swap",
    },
}

SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".pyd"}


def _should_skip(path: Path) -> bool:
    if path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
        return True
    return False


def _collect_files(feature: str, backend_mod: str) -> List[Tuple[Path, str]]:
    dist_dir = FRONTEND_DIR / "dist" / feature
    if not (dist_dir / "index.html").is_file():
        raise FileNotFoundError(
            f"未找到前端构建产物 {dist_dir / 'index.html'}，请先构建前端。"
        )

    entries: List[Tuple[Path, str]] = []

    def add_tree(src_root: Path, arc_prefix: str) -> None:
        for p in sorted(src_root.rglob("*")):
            if _should_skip(p) or any(part in SKIP_NAMES for part in p.parts):
                continue
            if p.is_symlink():
                raise RuntimeError(f"拒绝打包软链接文件：{p}")
            if p.is_file():
                rel = p.relative_to(src_root).as_posix()
                entries.append((p, f"{arc_prefix}/{rel}"))

    # 1. Compiled SPA static assets
    add_tree(dist_dir, f"dist/{feature}")

    # 2. Shared FastAPI backend core & launcher
    for top_file in ("__init__.py", "requirements.txt", "run_server.py"):
        src = ROOT / "backend" / top_file
        if not src.is_file() or src.is_symlink():
            raise FileNotFoundError(f"缺少后端核心文件：{src}")
        entries.append((src, f"backend/{top_file}"))

    add_tree(ROOT / "backend" / "core", "backend/core")

    # 3. Feature registry + only this feature's backend module
    for feat_file in ("__init__.py", "registry.py"):
        src = ROOT / "backend" / "features" / feat_file
        entries.append((src, f"backend/features/{feat_file}"))

    add_tree(ROOT / "backend" / "features" / backend_mod, f"backend/features/{backend_mod}")

    return sorted(entries, key=lambda pair: pair[1])


def build_deterministic_tarball(feature: str, out_dir: Path) -> Tuple[Path, str, int]:
    spec = FEATURE_SPECS[feature]
    files = _collect_files(feature, spec["backend_module"])
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"app-{feature}.tar.gz"
    archive_path = out_dir / archive_name

    raw_buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw_buf, compresslevel=9, mtime=0) as gz:
        with tarfile.open(mode="w", fileobj=gz, format=tarfile.PAX_FORMAT) as tf:
            for src_path, arcname in files:
                data = src_path.read_bytes()
                info = tarfile.TarInfo(name=arcname)
                info.size = len(data)
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mode = 0o755 if arcname.endswith("run_server.py") else 0o644
                tf.addfile(info, io.BytesIO(data))

    payload = raw_buf.getvalue()
    archive_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    return archive_path, digest, len(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build release tarballs for Colab Feature Apps")
    parser.add_argument(
        "--feature",
        default="all",
        help="Feature name (e.g., indextts-2.5) or 'all'",
    )
    parser.add_argument("--tag", default="v0.1.0", help="Target GitHub Release tag")
    parser.add_argument("--repo", default="boltguo/colab", help="GitHub owner/repo")
    parser.add_argument("--skip-frontend-build", action="store_true")
    args = parser.parse_args()

    targets = (
        list(FEATURE_SPECS.keys())
        if args.feature == "all"
        else [args.feature]
    )
    for feat in targets:
        if feat not in FEATURE_SPECS:
            raise ValueError(f"未知的 feature: {feat}，支持：{list(FEATURE_SPECS.keys())}")

    if not args.skip_frontend_build:
        for feat in targets:
            pkg = FEATURE_SPECS[feat]["npm_pkg"]
            print(f"[Build Frontend] {feat} ({pkg})...")
            subprocess.run(["pnpm", "--filter", pkg, "build"], cwd=FRONTEND_DIR, check=True)

    manifest: Dict[str, object] = {}
    if MANIFEST_PATH.is_file():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    manifest["repo"] = args.repo
    manifest["release_tag"] = args.tag
    apps_map = dict(manifest.get("apps", {})) if isinstance(manifest.get("apps"), dict) else {}

    checksum_lines: List[str] = []
    for feat in targets:
        archive_path, sha256_hex, size_bytes = build_deterministic_tarball(feat, RELEASE_DIR)
        checksum_lines.append(f"{sha256_hex}  {archive_path.name}")
        apps_map[feat] = {
            "archive": archive_path.name,
            "sha256": sha256_hex,
            "size_bytes": size_bytes,
        }
        print(
            f"[OK] {archive_path.name} ({size_bytes / 1024:.1f} KiB) sha256={sha256_hex}"
        )

    (RELEASE_DIR / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    manifest["apps"] = apps_map
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] 已更新 {MANIFEST_PATH.relative_to(ROOT)} 与 {RELEASE_DIR.relative_to(ROOT)}/SHA256SUMS")


if __name__ == "__main__":
    main()
