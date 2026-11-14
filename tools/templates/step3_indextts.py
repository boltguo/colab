# @title 3. 下载 IndexTTS 2.5 模型权重 {display-mode: "form"}
import os, shutil, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
os.environ.setdefault("HF_XET_CHUNK_CACHE_SIZE_BYTES", "0")
from huggingface_hub import hf_hub_download

MODEL_DIR = Path("/content/models/IndexTTS-2.5")
INDEXTTS_DIR = Path("/content/index-tts")
{{MODEL_SOURCES}}
MODEL_FILES = [
{{MODEL_FILES}}]

def local_directory(path):
    path = Path(path)
    for parent in [path, *path.parents]:
        if parent == Path("/content"):
            break
        if parent.is_symlink():
            raise RuntimeError(f"目录是软链接，请使用新的 runtime：{parent}")
    path.mkdir(parents=True, exist_ok=True)

def model_ready(target, size):
    return target.is_file() and not target.is_symlink() and target.stat().st_size == size

def download_model(repo, revision, _folder, file, size):
    target = MODEL_DIR / file
    local_directory(target.parent)
    started = time.time()
    result = Path(
        hf_hub_download(
            repo_id=repo,
            filename=file,
            revision=revision,
            local_dir=str(MODEL_DIR),
            force_download=target.exists(),
            token=False,
        )
    )
    if result.resolve() != target.resolve() or not model_ready(target, size):
        raise RuntimeError(f"模型下载不完整：{target}")
    print(f"已下载：{file}（{size / 1024**3:.2f} GB，{time.time() - started:.0f} 秒）")

def download_models():
    local_directory(MODEL_DIR)
    pending = []
    for item in MODEL_FILES:
        target = MODEL_DIR / item[3]
        if target.is_symlink():
            raise RuntimeError(f"模型文件是软链接：{target}")
        if model_ready(target, item[4]):
            print("已存在：", item[3])
        else:
            pending.append(item)
    if pending:
        missing = sum(item[4] for item in pending)
        free = shutil.disk_usage(MODEL_DIR).free
        if free < missing + 2 * 1024**3:
            raise RuntimeError(
                f"磁盘空间不足：还需 {missing / 1024**3:.1f} GB，可用 {free / 1024**3:.1f} GB。"
            )
        started = time.time()
        pool = ThreadPoolExecutor(max_workers=3)
        try:
            futures = [pool.submit(download_model, *item) for item in sorted(pending, key=lambda x: -x[4])]
            for future in as_completed(futures):
                future.result()
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        elapsed = time.time() - started
        print(
            f"主权重下载完成：{missing / 1024**3:.1f} GB，用时 {elapsed:.0f} 秒（{missing / 1024**2 / max(elapsed, 1):.0f} MB/s）"
        )

    if str(INDEXTTS_DIR) not in sys.path:
        sys.path.insert(0, str(INDEXTTS_DIR))
    from indextts.utils.model_download import ensure_models_available
    ensure_models_available(str(MODEL_DIR))

download_models()
print("[OK] IndexTTS 2.5 全部主模型与辅助声码器准备完成。")
