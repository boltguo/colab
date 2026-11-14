# @title 2. 安装 IndexTTS 2.5 引擎与应用服务包 {display-mode: "form"}
import hashlib, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path

INDEXTTS_DIR = Path("/content/index-tts")
INDEXTTS_REPO = "https://github.com/index-tts/index-tts"
INDEXTTS_REVISION = "d9e41aac89fd00b3d71497fddb287b7f24613712"

APP_DIR = Path("/content/app")
RELEASE_REPO = "{{RELEASE_REPO}}"
RELEASE_TAG = "{{RELEASE_TAG}}"
APP_ARCHIVE = "{{APP_ARCHIVE}}"
APP_SHA256 = "{{APP_SHA256}}"
CLOUDFLARED_VERSION = "2026.10.6"

RUNTIME_PACKAGES = [
    "transformers==4.52.1",
    "tokenizers>=0.21.0",
    "accelerate>=1.8.0",
    "safetensors>=0.4.3",
    "huggingface_hub>=0.23.0",
    "hf_xet",
    "librosa>=0.10.2",
    "soundfile>=0.10.0",
    "scipy>=1.10.0",
    "omegaconf>=2.3.0",
    "einops>=0.8.1",
    "sentencepiece>=0.2.1",
    "tiktoken>=0.5.0",
    "openai-whisper>=20231117",
    "modelscope>=1.27.0",
    "munch>=4.0.0",
    "json5>=0.9.16",
    "textstat>=0.7.10",
    "jieba>=0.42.1",
    "cn2an>=0.5.22",
    "g2p-en>=2.1.0",
    "ffmpeg-python>=0.2.0",
    "descript-audiotools>=0.7.2",
    "PyYAML>=6.0",
    "wetext>=0.0.9",
    "fugashi>=1.2.0",
    "unidic-lite>=1.0.0",
    "fastapi>=0.115.0,<1.0.0",
    "uvicorn[standard]>=0.30.0,<1.0.0",
    "python-multipart>=0.0.9,<1.0.0",
    "pydantic>=2.7.0,<3.0.0",
]

def run(args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)

def git(path, *args):
    return subprocess.check_output(["git", *args], cwd=path, text=True).strip()

def ensure_not_symlink(path, label):
    for p in [path, *path.parents]:
        if p == Path("/content"):
            break
        if p.is_symlink():
            raise RuntimeError(f"{label} 路径包含软链接，请使用新的 runtime：{p}")

def checkout_repo(path, repo_url, revision, label, allow_local_changes=False):
    ensure_not_symlink(path, label)
    fresh = not path.exists()
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--no-checkout", repo_url + ".git", str(path)])
    if not (path / ".git").is_dir():
        raise RuntimeError(f"{label} 目录不是 Git 仓库，请使用新的 runtime。")
    if git(path, "remote", "get-url", "origin").rstrip("/").removesuffix(".git") != repo_url:
        raise RuntimeError(f"现有 {label} 不是指定仓库，请使用新的 runtime。")
    if not fresh and not allow_local_changes and git(path, "status", "--porcelain"):
        raise RuntimeError(f"现有 {label} 有未提交修改，请使用新的 runtime。")
    if fresh or git(path, "rev-parse", "HEAD") != revision:
        run(["git", "fetch", "--depth", "1", "origin", revision], cwd=path)
        run(["git", "checkout", "--force", "--detach", revision], cwd=path)

def install_release_app():
    ensure_not_symlink(APP_DIR, "应用目录")
    stamp_file = APP_DIR / ".release_sha256"
    if (
        stamp_file.is_file()
        and not stamp_file.is_symlink()
        and stamp_file.read_text(encoding="utf-8").strip() == f"{RELEASE_TAG}:{APP_SHA256}"
        and (APP_DIR / "backend/run_server.py").is_file()
    ):
        print(f"应用包已是最新：{APP_ARCHIVE} ({RELEASE_TAG})")
        return

    local_archive = Path(f"/content/{APP_ARCHIVE}")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        if local_archive.is_file() and not local_archive.is_symlink():
            print(f"检测到本地预置应用包：{local_archive}")
            payload = local_archive.read_bytes()
        else:
            url = f"https://github.com/{RELEASE_REPO}/releases/download/{RELEASE_TAG}/{APP_ARCHIVE}"
            print(f"正在拉取应用包：{url}")
            req = urllib.request.Request(url, headers={"User-Agent": "colab-release-fetcher"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read()
        actual_sha = hashlib.sha256(payload).hexdigest()
        if actual_sha != APP_SHA256:
            raise RuntimeError(
                f"应用包 SHA256 校验失败！预期 {APP_SHA256}，实际 {actual_sha}"
            )
        tmp_path.write_bytes(payload)

        staging = APP_DIR.with_name("app.staging")
        if staging.is_symlink():
            raise RuntimeError("staging 目录为软链接，拒绝写入。")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        staging_root = staging.resolve()

        with tarfile.open(tmp_path, "r:gz") as tf:
            for member in tf.getmembers():
                if member.issym() or member.islnk():
                    raise RuntimeError(f"拒绝解压含链接的归档条目：{member.name}")
                target = (staging / member.name).resolve()
                if target != staging_root and not str(target).startswith(str(staging_root) + "/"):
                    raise RuntimeError(f"归档路径越界：{member.name}")
            tf.extractall(staging)

        (staging / ".release_sha256").write_text(f"{RELEASE_TAG}:{APP_SHA256}\n", encoding="utf-8")
        if APP_DIR.exists():
            shutil.rmtree(APP_DIR)
        staging.replace(APP_DIR)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

checkout_repo(INDEXTTS_DIR, INDEXTTS_REPO, INDEXTTS_REVISION, "index-tts", allow_local_changes=True)

# 让 Linux 也走预编译的 wetext 文本规范化，避免现场编译 pynini
front_py = INDEXTTS_DIR / "indextts/utils/front.py"
front_py.write_text(
    front_py.read_text(encoding="utf-8").replace('if platform.system() != "Linux":', "if True:"),
    encoding="utf-8",
)

run([sys.executable, "-m", "pip", "install", "-q", *RUNTIME_PACKAGES])
# descript-audiotools 声明了过旧的 protobuf<3.20 约束，安装后恢复现代 protobuf 以兼容 Colab Python 3.13 / TF
run([sys.executable, "-m", "pip", "install", "-q", "-U", "protobuf>=5.28.0,<7.0.0"])
install_release_app()

{{CLOUDFLARED}}
print(f"index-tts: {INDEXTTS_REVISION[:12]} | app: {RELEASE_TAG} ({APP_SHA256[:12]}) | cloudflared: {CLOUDFLARED_VERSION}")
print("[OK] IndexTTS 2.5 引擎与 Web/API 应用包安装完成（零 ComfyUI 依赖）。")
