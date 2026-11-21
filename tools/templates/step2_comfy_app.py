# @title 2. Install Inference Engine & App Bundle {display-mode: "form"}
import hashlib, re, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path

COMFY_DIR = Path("/content/ComfyUI")
COMFY_REPO = "https://github.com/Comfy-Org/ComfyUI"
COMFY_VERSION = "v0.43.2"
COMFY_REVISION = "423cbd20511becb1f16122ab518e92e58bfa03d9"

APP_DIR = Path("/content/app")
RELEASE_REPO = "{{RELEASE_REPO}}"
RELEASE_TAG = "{{RELEASE_TAG}}"
APP_ARCHIVE = "{{APP_ARCHIVE}}"
APP_SHA256 = "{{APP_SHA256}}"
BUNDLED_NODES_REL = "{{BUNDLED_NODES_REL}}"

{{NODE_CONSTANTS}}EXTRA_PACKAGES = {{EXTRA_PACKAGES}}
APP_SERVER_PACKAGES = [
    "fastapi>=0.115.0,<1.0.0",
    "uvicorn[standard]>=0.30.0,<1.0.0",
    "python-multipart>=0.0.9,<1.0.0",
    "pydantic>=2.7.0,<3.0.0",
    "huggingface_hub>=0.23.0",
    "hf_xet",
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
            raise RuntimeError(f"{label} path contains a symlink; start a fresh runtime: {p}")

def checkout_repo(path, repo_url, revision, label, allow_local_changes=False):
    ensure_not_symlink(path, label)
    fresh = not path.exists()
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--no-checkout", repo_url + ".git", str(path)])
    if not (path / ".git").is_dir():
        raise RuntimeError(f"{label} is not a git repository; please use a clean runtime: {path}")
    if git(path, "remote", "get-url", "origin").rstrip("/").removesuffix(".git") != repo_url:
        raise RuntimeError(f"Unexpected remote origin in {label}; please use a clean runtime.")
    if not fresh and not allow_local_changes and git(path, "status", "--porcelain"):
        raise RuntimeError(f"{label} has uncommitted local changes; please use a clean runtime.")
    if fresh or git(path, "rev-parse", "HEAD") != revision:
        run(["git", "fetch", "--depth", "1", "origin", revision], cwd=path)
        run(["git", "checkout", "--force", "--detach", revision], cwd=path)

def sync_bundled_custom_nodes():
    if not BUNDLED_NODES_REL:
        return
    src_root = APP_DIR / BUNDLED_NODES_REL
    if not src_root.is_dir():
        return
    custom_nodes_dir = COMFY_DIR / "custom_nodes"
    ensure_not_symlink(custom_nodes_dir, "ComfyUI custom_nodes")
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)
    for node_dir in sorted(p for p in src_root.iterdir() if p.is_dir()):
        if node_dir.is_symlink() or any(child.is_symlink() for child in node_dir.rglob("*")):
            raise RuntimeError(f"Refusing symlink inside bundled custom nodes: {node_dir}")
        dest = custom_nodes_dir / node_dir.name
        if dest.is_symlink():
            raise RuntimeError(f"Destination custom node path is a symlink: {dest}")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(node_dir, dest, symlinks=False)
        print(f"Synced bundled ComfyUI node pack: {node_dir.name}")

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

checkout_repo(COMFY_DIR, COMFY_REPO, COMFY_REVISION, "ComfyUI")
{{NODE_INSTALL}}
skip = {"torch", "torchvision", "torchaudio", "xformers"}
lines = []
for req_file in REQUIREMENT_FILES:
    for line in req_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[;\s]", s, maxsplit=1)[0].strip().lower()
        if name not in skip:
            lines.append(s)
requirements = Path("/content/comfy_requirements.txt")
requirements.write_text("\n".join(lines) + "\n", encoding="utf-8")
run([sys.executable, "-m", "pip", "install", "-q", "-r", str(requirements), *EXTRA_PACKAGES, *APP_SERVER_PACKAGES])

install_release_app()
sync_bundled_custom_nodes()

print(f"Engine: ComfyUI {COMFY_VERSION} ({COMFY_REVISION[:12]}){{NODE_SUMMARY}} | app: {RELEASE_TAG} ({APP_SHA256[:12]})")
print("[OK] Internal inference engine and Web Studio bundle installed.")
