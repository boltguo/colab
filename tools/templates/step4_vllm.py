# @title 4. 启动现代 Web 工作台与 OpenAI / Claude Code API 服务 {display-mode: "form"}
TUNNEL_MODE = "Quick Tunnel (临时链接)"  # @param ["Quick Tunnel (临时链接)", "自有 Tunnel (读取 Secrets 中 CF_TUNNEL_TOKEN)"]
REQUIRE_API_KEY = True  # @param {type:"boolean"}
ACCESS_PASSWORD = ""  # @param {type:"string"}
USE_CF_TUNNEL_TOKEN = TUNNEL_MODE.startswith("自有")
import hashlib, json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

FEATURE_NAME = "qwen3.8-27b"
VLLM_PORT = 8189
VLLM_BASE = f"http://127.0.0.1:{VLLM_PORT}"
VLLM_LOG = Path("/content/vllm-worker.log")
VLLM_LAUNCH_CONFIG = Path("/content/vllm-worker.launch.json")
VLLM_PROCESS_PATTERN = r"vllm serve|vllm\.entrypoints"

APP_DIR = Path("/content/app")
DATA_DIR = Path(f"/content/app_data/{FEATURE_NAME}")
UPLOADS_DIR = DATA_DIR / "uploads"
PORT = 8188
BASE = f"http://127.0.0.1:{PORT}"
APP_LOG = Path(f"/content/{FEATURE_NAME}-web.log")
APP_LAUNCH_CONFIG = Path(f"/content/{FEATURE_NAME}.launch.json")
APP_PROCESS_PATTERN = r"backend/run_server\.py|backend\.run_server"

{{HELPERS}}
if APP_DIR.is_symlink() or not (APP_DIR / "backend/run_server.py").is_file():
    raise RuntimeError("未找到应用服务目录 /content/app，请先运行第 2 步。")

marker = Path("/content/models/.selected_qwen38_dir")
model_dir = (
    globals().get("SELECTED_QWEN38_DIR")
    or (marker.read_text(encoding="utf-8").strip() if marker.is_file() and not marker.is_symlink() else "")
    or ("/content/models/Qwen3.8-27B" if Path("/content/models/Qwen3.8-27B/config.json").is_file() else "/content/models/Qwen3.8-27B-FP8")
)
if Path(model_dir).is_symlink() or not (Path(model_dir) / "config.json").is_file():
    raise RuntimeError(f"未找到模型目录 {model_dir}，请先运行第 3 步下载模型。")

def resolve_app_api_key():
    if ACCESS_PASSWORD.strip():
        return ACCESS_PASSWORD.strip()
    key = ""
    try:
        from google.colab import userdata
        key = (userdata.get("APP_API_KEY") or "").strip()
    except Exception:
        key = ""
    if not key:
        key = os.environ.get("APP_API_KEY", "").strip()
    return key

app_api_key = resolve_app_api_key() if REQUIRE_API_KEY else ""
if REQUIRE_API_KEY and not app_api_key:
    raise RuntimeError(
        "请在 ACCESS_PASSWORD 填写访问密码，或在 Colab 左侧 🔑 Secrets 配置 APP_API_KEY。"
    )

if DATA_DIR.is_symlink() or UPLOADS_DIR.is_symlink():
    raise RuntimeError("数据目录包含软链接，拒绝启动。")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 1. 启动内部 vLLM 引擎 (127.0.0.1:8189，不对公网直接暴露)
def vllm_ready(timeout=5):
    try:
        with urllib.request.urlopen(VLLM_BASE + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

vllm_cmd = [
    "vllm", "serve", model_dir,
    "--served-model-name", "Qwen/Qwen3.8-27B", "qwen3.8-27b",
    "--host", "127.0.0.1",
    "--port", str(VLLM_PORT),
    "--max-model-len", "262144",
    "--gpu-memory-utilization", "0.93",
    "--enable-prefix-caching",
    "--reasoning-parser", "qwen3",
    "--enable-auto-tool-choice",
    "--tool-call-parser", "qwen3_coder",
    "--allowed-local-media-path", str(UPLOADS_DIR),
    "--trust-remote-code",
    "--speculative-config", '{"method":"mtp","num_speculative_tokens":3}',
]

vllm_cfg_str = json.dumps(vllm_cmd)
vllm_is_up = vllm_ready() or (process_running(VLLM_PROCESS_PATTERN) and vllm_ready(timeout=30))
if vllm_is_up and read_text(VLLM_LAUNCH_CONFIG) != vllm_cfg_str:
    print("vLLM 启动参数已变化，正在按新参数重启...")
    stop_processes(VLLM_PROCESS_PATTERN, 120)
    vllm_is_up = False

if vllm_is_up:
    print("[OK] 内部 vLLM 推理引擎已在运行 (127.0.0.1:8189)。")
else:
    stop_processes(VLLM_PROCESS_PATTERN, 120)
    rotate_log(VLLM_LOG)
    with VLLM_LOG.open("w") as log:
        vllm_proc = subprocess.Popen(
            vllm_cmd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    VLLM_LAUNCH_CONFIG.write_text(vllm_cfg_str, encoding="utf-8")
    print("正在加载 27B 权重并初始化 256K KV Cache（约需 1~3 分钟）...")
    deadline = time.time() + 900
    while time.time() < deadline:
        if vllm_proc.poll() is not None:
            print(tail(VLLM_LOG))
            raise RuntimeError(f"vLLM 启动失败（退出码 {vllm_proc.returncode}），请查看上方日志。")
        if vllm_ready():
            print("[OK] 内部 vLLM 推理引擎启动成功 (127.0.0.1:8189)。")
            break
        time.sleep(3)
    else:
        print(tail(VLLM_LOG))
        raise TimeoutError("vLLM 15 分钟内未就绪，请查看上方日志。")

# 2. 启动对外 FastAPI + 现代多模态前端工作台 + OpenAI/Anthropic 网关 (127.0.0.1:8188)
def app_ready(timeout=5):
    try:
        with urllib.request.urlopen(BASE + "/api/v1/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

env_overrides = {
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "COLAB_FEATURE": FEATURE_NAME,
    "COLAB_HOST": "127.0.0.1",
    "COLAB_PORT": str(PORT),
    "COLAB_DATA_DIR": str(DATA_DIR),
    "COLAB_DIST_DIR": str(APP_DIR / "dist" / FEATURE_NAME),
    "COLAB_API_KEY": app_api_key,
    "VLLM_BASE_URL": VLLM_BASE,
    "VLLM_ALLOW_LOCAL_MEDIA": "1",
}

app_cmd = [
    sys.executable,
    str(APP_DIR / "backend/run_server.py"),
    "--feature",
    FEATURE_NAME,
    "--host",
    "127.0.0.1",
    "--port",
    str(PORT),
    "--dist-dir",
    str(APP_DIR / "dist" / FEATURE_NAME),
]

app_fingerprint = json.dumps({
    "cmd": app_cmd,
    "release": read_text(APP_DIR / ".release_sha256").strip(),
    "auth_sha256": hashlib.sha256(app_api_key.encode("utf-8")).hexdigest(),
    "env": {key: value for key, value in env_overrides.items() if key != "COLAB_API_KEY"},
}, sort_keys=True)
app_is_up = app_ready() or (process_running(APP_PROCESS_PATTERN) and app_ready(timeout=15))
if app_is_up and read_text(APP_LAUNCH_CONFIG) != app_fingerprint:
    print("Web/API 网关配置已变更，正在重启...")
    stop_processes(APP_PROCESS_PATTERN, 30)
    app_is_up = False

if app_is_up:
    print("[OK] 现代 Web 工作台与 OpenAI/Anthropic API 网关已在运行 (127.0.0.1:8188)。")
else:
    stop_processes(APP_PROCESS_PATTERN, 30)
    rotate_log(APP_LOG)
    child_env = {**os.environ, **env_overrides}
    with APP_LOG.open("w") as log:
        app_proc = subprocess.Popen(
            app_cmd,
            cwd=APP_DIR,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    APP_LAUNCH_CONFIG.write_text(app_fingerprint, encoding="utf-8")
    print("正在启动现代多模态 Web 工作台与 API 网关...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if app_proc.poll() is not None:
            print(tail(APP_LOG))
            raise RuntimeError(f"Web/API 服务启动失败（退出码 {app_proc.returncode}），详见上方日志。")
        if app_ready():
            print("[OK] 现代 Web 工作台与 API 网关启动成功。")
            break
        time.sleep(1.5)
    else:
        print(tail(APP_LOG))
        raise TimeoutError("Web/API 服务 2 分钟内未就绪，请检查日志。")

# 3. 挂载 Cloudflare Tunnel 并同步隧道元数据
host_url = start_cf_tunnel(cf_token)
tunnel_mode_key = "custom" if cf_token else "quick"
tunnel_info_path = DATA_DIR / "tunnel_info.json"
if not tunnel_info_path.is_symlink():
    tunnel_info_path.write_text(
        json.dumps({"public_url": host_url, "tunnel_mode": tunnel_mode_key}, ensure_ascii=False),
        encoding="utf-8",
    )
check_public_url(host_url, "/api/v1/health")

key_display = "$APP_API_KEY" if app_api_key else "EMPTY"
tunnel_tip = (
    "⚠️ 提示：当前使用 Cloudflare Quick Tunnel 临时公网域名，实例关闭或重连隧道后地址即失效；如需固定域名请在上方选择「自有 Tunnel」。"
    if tunnel_mode_key == "quick"
    else "✅ 当前使用自有 Cloudflare Tunnel 固定域名。"
)
print(f"""
=== 访问入口 ===
🌐 现代多模态 Web 工作台 : {host_url}
📖 在线 API 文档         : {host_url}/docs
🩺 机器与显存实时状态    : {host_url}/api/v1/system
{tunnel_tip}

=== 1. Claude Code (cc) 直连配置（Anthropic /v1/messages 原生协议）===
export ANTHROPIC_BASE_URL="{host_url}"
export ANTHROPIC_AUTH_TOKEN="{key_display}"
export ANTHROPIC_API_KEY="{key_display}"
export ANTHROPIC_MODEL="qwen3.8-27b"
export ANTHROPIC_SMALL_FAST_MODEL="qwen3.8-27b"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
claude --model qwen3.8-27b

=== 2. OpenAI 兼容接口配置（/v1/chat/completions）===
Base URL : {host_url}/v1
Model    : qwen3.8-27b （或 Qwen/Qwen3.8-27B）
API Key  : {key_display}
""")
