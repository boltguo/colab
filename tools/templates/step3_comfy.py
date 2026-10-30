# @title 3. 下载模型与工作流 {display-mode: "form"}
import json, os, shutil, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
os.environ.setdefault("HF_XET_CHUNK_CACHE_SIZE_BYTES", "0")
from huggingface_hub import hf_hub_download

COMFY_DIR = Path("/content/ComfyUI")
MODEL_DIR = COMFY_DIR / "models"
WORKFLOW_DIR = COMFY_DIR / "user/default/workflows"
WORKFLOW_URL = "https://raw.githubusercontent.com/boltguo/colab/main/{{WORKFLOW_FOLDER}}"
WORKFLOW_FILES = [
{{WORKFLOW_FILES}}]
{{MODEL_SOURCES}}
MODEL_FILES = [
{{MODEL_FILES}}]
LOADER_DIRS = {
    "UNETLoader": "diffusion_models",
    "CLIPLoader": "text_encoders",
    "VAELoader": "vae",
    "LoraLoader": "loras",
    "LoraLoaderModelOnly": "loras",
}

def local_directory(path):
    path = Path(path)
    for parent in [path, *path.parents]:
        if parent == COMFY_DIR.parent:
            break
        if parent.is_symlink():
            raise RuntimeError(f"目录是软链接，请使用新的 runtime：{parent}")
    path.mkdir(parents=True, exist_ok=True)

def model_ready(target, size):
    return target.is_file() and not target.is_symlink() and target.stat().st_size == size

def download_model(repo, revision, folder, file, size):
    base = MODEL_DIR / folder
    target = base / file
    local_directory(target.parent)
    started = time.time()
    result = Path(hf_hub_download(repo_id=repo, filename=file, revision=revision, local_dir=str(base), force_download=target.exists()))
    if result.resolve() != target.resolve() or not model_ready(target, size):
        raise RuntimeError(f"模型下载不完整：{target}")
    print(f"已下载：{file}（{size / 1024**3:.1f} GB，{time.time() - started:.0f} 秒）")

def download_models():
    pending = []
    for item in MODEL_FILES:
        target = MODEL_DIR / item[2] / item[3]
        if target.is_symlink():
            raise RuntimeError(f"模型文件是软链接：{target}")
        if model_ready(target, item[4]):
            print("已存在：", item[3])
        else:
            pending.append(item)
    if not pending:
        return
    missing = sum(item[4] for item in pending)
    free = shutil.disk_usage(MODEL_DIR).free
    if free < missing + 2 * 1024**3:
        raise RuntimeError(f"磁盘空间不足：还需 {missing / 1024**3:.1f} GB，可用 {free / 1024**3:.1f} GB。")
    started = time.time()
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        futures = [pool.submit(download_model, *item) for item in sorted(pending, key=lambda item: -item[4])]
        for future in as_completed(futures):
            future.result()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    elapsed = time.time() - started
    print(f"模型下载完成：{missing / 1024**3:.1f} GB，用时 {elapsed:.0f} 秒（{missing / 1024**2 / max(elapsed, 1):.0f} MB/s）")

def check_workflow(data):
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) or not data["nodes"]:
        raise ValueError("工作流 JSON 缺少 nodes。")
    for graph in [data, *data.get("definitions", {}).get("subgraphs", [])]:
        for node in graph.get("nodes", []):
            if not isinstance(node, dict) or not isinstance(node.get("type"), str):
                raise ValueError("工作流节点结构无效。")
            folder = LOADER_DIRS.get(node["type"])
            values = node.get("widgets_values")
            name = values[0] if isinstance(values, list) and values else None
            if folder and not (isinstance(name, str) and Path(name).name == name and (MODEL_DIR / folder / name).is_file()):
                raise ValueError(f"{node['type']} 引用的模型不存在：{name}")

def download_workflows():
    local_directory(WORKFLOW_DIR)
    for name in WORKFLOW_FILES:
        try:
            request = urllib.request.Request(f"{WORKFLOW_URL}/{quote(name)}", headers={"User-Agent": "colab-workflow-sync"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read())
            check_workflow(data)
            target = WORKFLOW_DIR / name
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError(f"目标是软链接或目录：{target}")
            fd, temporary = tempfile.mkstemp(prefix=".workflow-", dir=WORKFLOW_DIR)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump(data, file, ensure_ascii=False, indent=2)
                    file.write("\n")
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except Exception as error:
            raise RuntimeError(f"工作流同步失败：{name}：{error}") from error
        print("工作流：", name)

for path in [MODEL_DIR, COMFY_DIR / "input", COMFY_DIR / "output"]:
    local_directory(path)
download_models()
{{POST_DOWNLOAD}}download_workflows()
print("[OK] 模型与工作流准备完成。")
