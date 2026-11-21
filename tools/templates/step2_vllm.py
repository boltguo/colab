# @title 2. Install vLLM Engine & App Bundle {display-mode: "form"}
import hashlib, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path

VLLM_VERSION = "0.32.0"

APP_DIR = Path("/content/app")
RELEASE_REPO = "{{RELEASE_REPO}}"
RELEASE_TAG = "{{RELEASE_TAG}}"
APP_ARCHIVE = "{{APP_ARCHIVE}}"
APP_SHA256 = "{{APP_SHA256}}"

APP_SERVER_PACKAGES = [
    f"vllm=={VLLM_VERSION}",
    "fastapi>=0.115.0,<1.0.0",
    "uvicorn[standard]>=0.30.0,<1.0.0",
    "python-multipart>=0.0.9,<1.0.0",
    "pydantic>=2.7.0,<3.0.0",
    "huggingface_hub>=0.23.0",
    "hf_xet",
    "openai",
]

def run(args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)

def ensure_not_symlink(path, label):
    for p in [path, *path.parents]:
        if p == Path("/content"):
            break
        if p.is_symlink():
            raise RuntimeError(f"{label} path contains a symlink; start a fresh runtime: {p}")

def install_release_app():
    ensure_not_symlink(APP_DIR, "App directory")
    stamp_file = APP_DIR / ".release_sha256"
    if (
        stamp_file.is_file()
        and not stamp_file.is_symlink()
        and stamp_file.read_text(encoding="utf-8").strip() == f"{RELEASE_TAG}:{APP_SHA256}"
        and (APP_DIR / "backend/run_server.py").is_file()
    ):
        print(f"App bundle already up to date: {APP_ARCHIVE} ({RELEASE_TAG})")
        return

    local_archive = Path(f"/content/{APP_ARCHIVE}")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        if local_archive.is_file() and not local_archive.is_symlink():
            print(f"Using pre-staged app archive: {local_archive}")
            payload = local_archive.read_bytes()
        else:
            url = f"https://github.com/{RELEASE_REPO}/releases/download/{RELEASE_TAG}/{APP_ARCHIVE}"
            print(f"Downloading app bundle: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "colab-release-fetcher"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read()
        actual_sha = hashlib.sha256(payload).hexdigest()
        if actual_sha != APP_SHA256:
            raise RuntimeError(
                f"App bundle SHA256 mismatch! Expected {APP_SHA256}, got {actual_sha}"
            )
        tmp_path.write_bytes(payload)

        staging = APP_DIR.with_name("app.staging")
        if staging.is_symlink():
            raise RuntimeError("Staging directory is a symlink; aborting.")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        staging_root = staging.resolve()

        with tarfile.open(tmp_path, "r:gz") as tf:
            for member in tf.getmembers():
                if member.issym() or member.islnk():
                    raise RuntimeError(f"Refusing symlink/hardlink archive entry: {member.name}")
                target = (staging / member.name).resolve()
                if target != staging_root and not str(target).startswith(str(staging_root) + "/"):
                    raise RuntimeError(f"Archive path escapes staging root: {member.name}")
            tf.extractall(staging)

        (staging / ".release_sha256").write_text(f"{RELEASE_TAG}:{APP_SHA256}\n", encoding="utf-8")
        if APP_DIR.exists():
            shutil.rmtree(APP_DIR)
        staging.replace(APP_DIR)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

run([sys.executable, "-m", "pip", "install", "-q", *APP_SERVER_PACKAGES])
install_release_app()

vllm_ver = subprocess.check_output([sys.executable, "-c", "import vllm; print(vllm.__version__)"], text=True).strip()
print(f"Engine: vLLM {vllm_ver} | app: {RELEASE_TAG} ({APP_SHA256[:12]})")
print("[OK] vLLM engine and Web Studio bundle installed.")
