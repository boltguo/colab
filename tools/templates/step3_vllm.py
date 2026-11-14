# @title 3. 下载并校验 Qwen3.8-27B 模型权重 {display-mode: "form"}
import os, shutil, time, torch
from pathlib import Path

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
            raise RuntimeError(f"拒绝访问软链接模型路径：{p}")

vram_gib = torch.cuda.get_device_properties(0).total_memory / 1024**3
precision = "BF16" if vram_gib >= 70 else "FP8"
spec = MODEL_SPECS[precision]
target_dir = spec["local_dir"]
ensure_not_symlink(target_dir)
target_dir.parent.mkdir(parents=True, exist_ok=True)

free_gb = shutil.disk_usage(target_dir.parent).free / 1024**3
if not (target_dir / "config.json").is_file() and free_gb < spec["min_free_gb"]:
    raise RuntimeError(f"磁盘空间不足：{spec['repo_id']} 需 {spec['min_free_gb']} GB，可用 {free_gb:.1f} GB。")

print(f"下载：{spec['repo_id']}（{precision}，显存 {vram_gib:.1f} GiB，commit {spec['revision'][:12]}）")
started = time.time()
snapshot_download(
    repo_id=spec["repo_id"],
    revision=spec["revision"],
    local_dir=str(target_dir),
)
if target_dir.is_symlink() or (target_dir / "config.json").is_symlink():
    raise RuntimeError("模型目录校验异常（检测到软链接）。")

SELECTED_QWEN38_DIR = str(target_dir)
marker = Path("/content/models/.selected_qwen38_dir")
if not marker.is_symlink():
    marker.write_text(SELECTED_QWEN38_DIR, encoding="utf-8")
print(f"[OK] 模型准备完成：{target_dir}（用时 {time.time() - started:.0f} 秒）")
