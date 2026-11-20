# @title 4. Launch Web Studio & OpenAI / Claude Code API Service {display-mode: "form"}
TUNNEL_MODE = "Quick Tunnel (ephemeral)"  # @param ["Quick Tunnel (ephemeral)", "Custom Tunnel (CF_TUNNEL_TOKEN)"]
ACCESS_PASSWORD = ""  # @param {type:"string"}
USE_CF_TUNNEL_TOKEN = TUNNEL_MODE.startswith("Custom")
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
    raise RuntimeError("App directory /content/app not found; please run Step 2 first.")

marker = Path("/content/models/.selected_qwen38_dir")
model_dir = (
    globals().get("SELECTED_QWEN38_DIR")
    or (marker.read_text(encoding="utf-8").strip() if marker.is_file() and not marker.is_symlink() else "")
    or ("/content/models/Qwen3.8-27B" if Path("/content/models/Qwen3.8-27B/config.json").is_file() else "/content/models/Qwen3.8-27B-FP8")
)
if Path(model_dir).is_symlink() or not (Path(model_dir) / "config.json").is_file():
    raise RuntimeError(f"Model directory not found: {model_dir}; please run Step 3 first.")

def resolve_access_password():
    if ACCESS_PASSWORD.strip():
        return ACCESS_PASSWORD.strip()
    key = ""
    try:
        from google.colab import userdata
        key = (userdata.get("ACCESS_PASSWORD") or "").strip()
    except Exception:
        key = ""
    if not key:
        key = os.environ.get("ACCESS_PASSWORD", "").strip()
    return key

access_password = resolve_access_password()
if not access_password:
    raise RuntimeError(
        "Set ACCESS_PASSWORD above or configure Colab Secret `ACCESS_PASSWORD`."
    )

if DATA_DIR.is_symlink() or UPLOADS_DIR.is_symlink():
    raise RuntimeError("Symlink detected in data directory; aborting launch.")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Start internal vLLM engine (127.0.0.1:8189, loopback only)
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
    # Single-GPU interactive use: avoid the throughput default exceeding hybrid-model cache blocks.
    "--max-num-seqs", "8",
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
    print("vLLM launch configuration changed; restarting engine...")
    stop_processes(VLLM_PROCESS_PATTERN, 120)
    vllm_is_up = False

if vllm_is_up:
    print("[OK] Internal vLLM engine already running (127.0.0.1:8189).")
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
    print("Loading 27B weights and initializing vLLM engine (256K context, max_num_seqs=8)...")
    deadline = time.time() + 900
    while time.time() < deadline:
        if vllm_proc.poll() is not None:
            print(tail(VLLM_LOG))
            raise RuntimeError(f"vLLM failed to start (exit code {vllm_proc.returncode}); see logs above.")
        if vllm_ready():
            print("[OK] Internal vLLM engine ready (127.0.0.1:8189).")
            break
        time.sleep(3)
    else:
        print(tail(VLLM_LOG))
        raise TimeoutError("vLLM did not become ready within 15 minutes; see logs above.")

# 2. Start public FastAPI + Web Studio + OpenAI/Anthropic gateway (127.0.0.1:8188)
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
    "COLAB_ACCESS_PASSWORD": access_password,
    "COLAB_API_KEY": "",
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
    "web_auth_sha256": hashlib.sha256(access_password.encode("utf-8")).hexdigest(),
    "env": {key: value for key, value in env_overrides.items() if key not in {"COLAB_ACCESS_PASSWORD", "COLAB_API_KEY"}},
}, sort_keys=True)
app_is_up = app_ready() or (process_running(APP_PROCESS_PATTERN) and app_ready(timeout=15))
if app_is_up and read_text(APP_LAUNCH_CONFIG) != app_fingerprint:
    print("Web/API gateway configuration changed; restarting...")
    stop_processes(APP_PROCESS_PATTERN, 30)
    app_is_up = False

if app_is_up:
    print("[OK] Web Studio and OpenAI/Anthropic gateway already running (127.0.0.1:8188).")
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
    print("Starting Web Studio and API gateway...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if app_proc.poll() is not None:
            print(tail(APP_LOG))
            raise RuntimeError(f"Web/API service failed to start (exit code {app_proc.returncode}); see logs above.")
        if app_ready():
            print("[OK] Web Studio and API gateway started.")
            break
        time.sleep(1.5)
    else:
        print(tail(APP_LOG))
        raise TimeoutError("Web/API service did not become ready within 2 minutes; check logs.")

# 3. Expose via Cloudflare Tunnel & persist live URL metadata
verify_web_password(BASE, APP_PROCESS_PATTERN)
host_url = start_cf_tunnel(cf_token)
tunnel_mode_key = "custom" if cf_token else "quick"
tunnel_info_path = DATA_DIR / "tunnel_info.json"
if not tunnel_info_path.is_symlink():
    tunnel_info_path.write_text(
        json.dumps({"public_url": host_url, "tunnel_mode": tunnel_mode_key}, ensure_ascii=False),
        encoding="utf-8",
    )
check_public_url(host_url, "/api/v1/health")

key_display = "YOUR_API_KEY"
tunnel_tip = (
    "WARNING: Quick Tunnel provides a temporary URL that expires when the runtime stops. Select Custom Tunnel above for a permanent domain."
    if tunnel_mode_key == "quick"
    else "INFO: Using your custom fixed Cloudflare Tunnel domain."
)
print(f"""
=== Endpoints ===
Web Playground : {host_url}
API Docs       : {host_url}/docs
System Stats   : {host_url}/api/v1/system
{tunnel_tip}
API Key        : Open by default; configure an optional key in the Web Studio header.

=== 1. Claude Code (Anthropic /v1/messages) ===
export ANTHROPIC_BASE_URL="{host_url}"
export ANTHROPIC_AUTH_TOKEN="{key_display}"
export ANTHROPIC_API_KEY="{key_display}"
export ANTHROPIC_MODEL="qwen3.8-27b"
export ANTHROPIC_SMALL_FAST_MODEL="qwen3.8-27b"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
claude --model qwen3.8-27b

=== 2. OpenAI-Compatible Endpoint (/v1/chat/completions) ===
Base URL : {host_url}/v1
Model    : qwen3.8-27b (or Qwen/Qwen3.8-27B)
API Key  : {key_display}
""")
