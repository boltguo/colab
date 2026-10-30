# @title 2. 安装 ComfyUI {display-mode: "form"}
import re, subprocess, sys, urllib.request
from pathlib import Path

COMFY_DIR = Path("/content/ComfyUI")
COMFY_REPO = "https://github.com/Comfy-Org/ComfyUI"
COMFY_VERSION = "v0.43.2"
COMFY_REVISION = "423cbd20511becb1f16122ab518e92e58bfa03d9"
CLOUDFLARED_VERSION = "2026.10.6"
{{NODE_CONSTANTS}}EXTRA_PACKAGES = {{EXTRA_PACKAGES}}

def run(args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)

def git(path, *args):
    return subprocess.check_output(["git", *args], cwd=path, text=True).strip()

def checkout_repo(path, repo_url, revision, label, allow_local_changes=False):
    if path.is_symlink():
        raise RuntimeError(f"{label} 目录是软链接，请使用新的 runtime。")
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
run([sys.executable, "-m", "pip", "install", "-q", "-r", str(requirements), *EXTRA_PACKAGES, "huggingface_hub", "hf_xet"])

{{CLOUDFLARED}}
print(f"ComfyUI: {COMFY_VERSION} ({COMFY_REVISION[:12]}){{NODE_SUMMARY}} | cloudflared: {CLOUDFLARED_VERSION}")
print("[OK] ComfyUI 安装完成。")
