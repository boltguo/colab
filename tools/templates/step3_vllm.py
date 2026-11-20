# @title 3. Download & Verify Qwen3.8-27B Weights {display-mode: "form"}
import os, shutil, time, torch
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
os.environ.setdefault("HF_XET_CHUNK_CACHE_SIZE_BYTES", "0")
from huggingface_hub import snapshot_download

MODEL_SPECS = {
    "BF16": {
        "repo_id": "Qwen/Qwen3.8-27B",
        "revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
        "local_dir": Path("/content/models/Qwen3.8-27B"),
        "min_free_gb": 58,
    },
    "FP8": {
        "repo_id": "Qwen/Qwen3.8-27B-FP8",
        "revision": "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a",
        "local_dir": Path("/content/models/Qwen3.8-27B-FP8"),
        "min_free_gb": 31,
    },
}

def ensure_not_symlink(path: Path) -> None:
    for p in [path, *path.parents]:
        if p == Path("/content"):
            break
        if p.is_symlink():
            raise RuntimeError(f"Refusing symlink model path: {p}")

vram_gib = torch.cuda.get_device_properties(0).total_memory / 1024**3
precision = "BF16" if vram_gib >= 70 else "FP8"
spec = MODEL_SPECS[precision]
target_dir = spec["local_dir"]
ensure_not_symlink(target_dir)
target_dir.parent.mkdir(parents=True, exist_ok=True)

free_gb = shutil.disk_usage(target_dir.parent).free / 1024**3
if not (target_dir / "config.json").is_file() and free_gb < spec["min_free_gb"]:
    raise RuntimeError(f"Insufficient disk space: {spec['repo_id']} requires {spec['min_free_gb']} GB, available {free_gb:.1f} GB.")

print(f"Downloading: {spec['repo_id']} ({precision}, VRAM {vram_gib:.1f} GiB, commit {spec['revision'][:12]})")
started = time.time()
snapshot_download(
    repo_id=spec["repo_id"],
    revision=spec["revision"],
    local_dir=str(target_dir),
    token=False,
)
if target_dir.is_symlink() or (target_dir / "config.json").is_symlink():
    raise RuntimeError("Invalid model directory: symlink detected.")

SELECTED_QWEN38_DIR = str(target_dir)
marker = Path("/content/models/.selected_qwen38_dir")
if not marker.is_symlink():
    marker.write_text(SELECTED_QWEN38_DIR, encoding="utf-8")
print(f"[OK] Model ready: {target_dir} ({time.time() - started:.0f}s)")
