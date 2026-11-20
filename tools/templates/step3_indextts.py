# @title 3. Download IndexTTS 2.5 Model Weights {display-mode: "form"}
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
            raise RuntimeError(f"Directory is a symlink; please start a fresh runtime: {parent}")
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
        raise RuntimeError(f"Incomplete model download: {target}")
    print(f"Downloaded: {file} ({size / 1024**3:.2f} GiB in {time.time() - started:.0f}s)")

def download_models():
    local_directory(MODEL_DIR)
    pending = []
    for item in MODEL_FILES:
        target = MODEL_DIR / item[3]
        if target.is_symlink():
            raise RuntimeError(f"Refusing symlink model file: {target}")
        if model_ready(target, item[4]):
            print("Verified:", item[3])
        else:
            pending.append(item)
    if pending:
        missing = sum(item[4] for item in pending)
        free = shutil.disk_usage(MODEL_DIR).free
        if free < missing + 2 * 1024**3:
            raise RuntimeError(
                f"Insufficient disk space: need {missing / 1024**3:.1f} GiB more, free {free / 1024**3:.1f} GiB."
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
            f"Primary weights ready: {missing / 1024**3:.1f} GiB in {elapsed:.0f}s ({missing / 1024**2 / max(elapsed, 1):.0f} MB/s)"
        )

    if str(INDEXTTS_DIR) not in sys.path:
        sys.path.insert(0, str(INDEXTTS_DIR))
    from indextts.utils.model_download import ensure_models_available
    ensure_models_available(str(MODEL_DIR))

download_models()
print("[OK] IndexTTS 2.5 weights and auxiliary vocoders ready.")
