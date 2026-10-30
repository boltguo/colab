# @title 4. 启动并挂载 API 服务 {display-mode: "form"}
import json, os, re, subprocess, time, urllib.request
from pathlib import Path

PORT = 8188
BASE = f"http://127.0.0.1:{PORT}"
LOG = Path("/content/vllm.log")
LAUNCH_CONFIG = Path("/content/vllm.launch.json")
PROCESS_PATTERN = "vllm serve|vllm.entrypoints"

{{HELPERS}}
model_dir = globals().get("SELECTED_QWEN38_DIR") or "/content/models/Qwen3.8-27B"
if not (Path(model_dir) / "config.json").is_file():
    raise RuntimeError(f"未找到模型目录 {model_dir}，请先运行第 3 步下载模型。")

def ready(timeout=5):
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

cmd = [
    "vllm", "serve", model_dir,
    "--served-model-name", "Qwen/Qwen3.8-27B", "qwen3.8-27b",
    "--host", "127.0.0.1",
    "--port", str(PORT),
    "--max-model-len", "262144",
    "--gpu-memory-utilization", "0.93",
    "--enable-prefix-caching",
    "--reasoning-parser", "qwen3",
    "--enable-auto-tool-choice",
    "--tool-call-parser", "qwen3_coder",
    "--trust-remote-code",
    "--speculative-config", '{"method":"mtp","num_speculative_tokens":3}',
]

launch_config = json.dumps(cmd)
running = ready() or (process_running(PROCESS_PATTERN) and ready(timeout=30))
if running and read_text(LAUNCH_CONFIG) != launch_config:
    print("启动参数已变化，正在按新参数重启 vLLM 服务...")
    stop_processes(PROCESS_PATTERN, 120)
    running = False

if running:
    print("[OK] vLLM 服务已经在运行。")
else:
    stop_processes(PROCESS_PATTERN, 120)
    rotate_log(LOG)
    with LOG.open("w") as log:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    LAUNCH_CONFIG.write_text(launch_config)
    print("正在加载 27B 权重并初始化 KV Cache（约需 1~3 分钟）...")
    deadline = time.time() + 900
    while time.time() < deadline:
        if process.poll() is not None:
            print(tail(LOG))
            raise RuntimeError(f"vLLM 启动失败（退出码 {process.returncode}），请查看上方日志。")
        if ready():
            print("[OK] vLLM 服务启动成功。")
            break
        time.sleep(3)
    else:
        print(tail(LOG))
        raise TimeoutError("vLLM 15 分钟内未就绪，请查看上方日志。")

host_url = start_cf_tunnel(cf_token)
check_public_url(host_url, "/health")

print(f"""
=== 1. Claude Code (cc) 直连配置（Anthropic /v1/messages 原生协议）===
export ANTHROPIC_BASE_URL="{host_url}"
export ANTHROPIC_AUTH_TOKEN="EMPTY"
export ANTHROPIC_API_KEY="EMPTY"
export ANTHROPIC_MODEL="qwen3.8-27b"
export ANTHROPIC_SMALL_FAST_MODEL="qwen3.8-27b"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
claude --model qwen3.8-27b

=== 2. OpenAI 兼容接口配置（/v1/chat/completions）===
Base URL : {host_url}/v1
Model    : qwen3.8-27b （或 Qwen/Qwen3.8-27B）
API Key  : EMPTY
""")
