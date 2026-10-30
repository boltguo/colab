# @title 2. 安装 vLLM 推理引擎 {display-mode: "form"}
import subprocess, sys, urllib.request
from pathlib import Path

VLLM_VERSION = "0.32.0"
CLOUDFLARED_VERSION = "2026.10.6"

def run(args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)

run([sys.executable, "-m", "pip", "install", "-q", f"vllm=={VLLM_VERSION}", "huggingface_hub", "hf_xet", "openai"])

{{CLOUDFLARED}}
vllm_ver = subprocess.check_output([sys.executable, "-c", "import vllm; print(vllm.__version__)"], text=True).strip()
print(f"vLLM: {vllm_ver} | cloudflared: {CLOUDFLARED_VERSION}")
print("[OK] vLLM 安装完成。")
