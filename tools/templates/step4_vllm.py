# @title 4. Launch Web Studio {display-mode: "form"}
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
from urllib.parse import urlsplit

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

# 2. Start FastAPI Web Playground server (127.0.0.1:8188, loopback only)
def app_ready(timeout=5):
    try:
        with urllib.request.urlopen(BASE + "/api/v1/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

proxy_url, access_mode = resolve_colab_proxy_url(PORT)
proxy_origin = f"{urlsplit(proxy_url).scheme}://{urlsplit(proxy_url).netloc}" if access_mode == "colab" else ""

env_overrides = {
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "COLAB_FEATURE": FEATURE_NAME,
    "COLAB_HOST": "127.0.0.1",
    "COLAB_PORT": str(PORT),
    "COLAB_DATA_DIR": str(DATA_DIR),
    "COLAB_DIST_DIR": str(APP_DIR / "dist" / FEATURE_NAME),
    "COLAB_PROXY_ORIGIN": proxy_origin,
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
    "env": env_overrides,
}, sort_keys=True)
app_is_up = app_ready() or (process_running(APP_PROCESS_PATTERN) and app_ready(timeout=15))
if app_is_up and read_text(APP_LAUNCH_CONFIG) != app_fingerprint:
    print("Web Studio configuration changed; restarting...")
    stop_processes(APP_PROCESS_PATTERN, 30)
    app_is_up = False

if app_is_up:
    print("[OK] Web Studio already running (127.0.0.1:8188).")
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
    print("Starting Web Studio...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if app_proc.poll() is not None:
            print(tail(APP_LOG))
            raise RuntimeError(f"Web Studio failed to start (exit code {app_proc.returncode}); see logs above.")
        if app_ready():
            print("[OK] Web Studio started.")
            break
        time.sleep(1.5)
    else:
        print(tail(APP_LOG))
        raise TimeoutError("Web Studio did not become ready within 2 minutes; check logs.")

# 3. Expose via Google Colab native proxy & persist live URL metadata
if not DATA_DIR.is_symlink():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    proxy_info_path = DATA_DIR / "proxy_info.json"
    if not proxy_info_path.is_symlink():
        proxy_info_path.write_text(
            json.dumps({"public_url": proxy_url, "access_mode": access_mode}, ensure_ascii=False),
            encoding="utf-8",
        )
open_colab_proxy(PORT, proxy_url, access_mode)
