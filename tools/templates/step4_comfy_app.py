# @title 4. Launch Web Studio & API Service {display-mode: "form"}
TUNNEL_MODE = "Quick Tunnel (ephemeral)"  # @param ["Quick Tunnel (ephemeral)", "Custom Tunnel (CF_TUNNEL_TOKEN)"]
ACCESS_PASSWORD = ""  # @param {type:"string"}
USE_CF_TUNNEL_TOKEN = TUNNEL_MODE.startswith("Custom")
import hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

FEATURE_NAME = "{{FEATURE_NAME}}"
BUNDLED_NODES_REL = "{{BUNDLED_NODES_REL}}"
COMFY_DIR = Path("/content/ComfyUI")
COMFY_PORT = 8189
COMFY_BASE = f"http://127.0.0.1:{COMFY_PORT}"
COMFY_LOG = Path("/content/comfyui-worker.log")
COMFY_LAUNCHER = Path("/content/comfy_userdata_compat.py")
COMFY_LAUNCH_CONFIG = Path("/content/comfyui-worker.launch.json")
COMFY_PROCESS_PATTERN = r"comfy_userdata_compat\.py|ComfyUI/main\.py"
COMFY_LAUNCH_ARGS = [
    "--output-directory", str(COMFY_DIR / "output"),
    "--disable-all-custom-nodes",
{{LAUNCH_ARGS}}    "--disable-partner-nodes",
]
REQUIRED_NODES = {{REQUIRED_NODES}}

APP_DIR = Path("/content/app")
DATA_DIR = Path(f"/content/app_data/{FEATURE_NAME}")
PORT = 8188
BASE = f"http://127.0.0.1:{PORT}"
APP_LOG = Path(f"/content/{FEATURE_NAME}-web.log")
APP_LAUNCH_CONFIG = Path(f"/content/{FEATURE_NAME}.launch.json")
APP_PROCESS_PATTERN = r"backend/run_server\.py|backend\.run_server"

{{HELPERS}}
if not (COMFY_DIR / "main.py").is_file():
    raise RuntimeError("Internal engine /content/ComfyUI not found; please run Step 2 first.")
if APP_DIR.is_symlink() or not (APP_DIR / "backend/run_server.py").is_file():
    raise RuntimeError("App directory /content/app not found; please run Step 2 first.")

if FEATURE_NAME in ("minimax-h3", "seedvr2", "h3-character-swap"):
    missing_media_tools = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing_media_tools:
        raise RuntimeError(f"Missing required media tools: {', '.join(missing_media_tools)}. Run !apt-get -qq update && apt-get -qq install -y ffmpeg first.")

if BUNDLED_NODES_REL:
    bundled_nodes_src = APP_DIR / BUNDLED_NODES_REL
    if bundled_nodes_src.is_dir():
        custom_nodes_dir = COMFY_DIR / "custom_nodes"
        custom_nodes_dir.mkdir(parents=True, exist_ok=True)
        for node_dir in sorted(p for p in bundled_nodes_src.iterdir() if p.is_dir()):
            if node_dir.is_symlink() or any(c.is_symlink() for c in node_dir.rglob("*")):
                raise RuntimeError(f"Refusing symlink inside bundled custom nodes: {node_dir}")
            dest = custom_nodes_dir / node_dir.name
            if dest.is_symlink():
                raise RuntimeError(f"Destination custom node path is a symlink: {dest}")
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(node_dir, dest, symlinks=False)

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

LAUNCHER_SOURCE = r'''{{LAUNCHER_SOURCE}}'''

def comfy_get_json(route, timeout=5):
    with urllib.request.urlopen(COMFY_BASE + route, timeout=timeout) as response:
        return json.load(response)

def comfy_ready(timeout=5):
    try:
        comfy_get_json("/system_stats", timeout)
        return True
    except Exception:
        return False

# 1. Start internal headless ComfyUI worker (127.0.0.1:8189, loopback only)
comfy_cfg_str = json.dumps({"launcher": LAUNCHER_SOURCE, "args": COMFY_LAUNCH_ARGS, "port": COMFY_PORT})
comfy_running = comfy_ready() or (process_running(COMFY_PROCESS_PATTERN) and comfy_ready(timeout=30))
if comfy_running and read_text(COMFY_LAUNCH_CONFIG) != comfy_cfg_str:
    print("Restarting internal ComfyUI worker with updated launch configuration...")
    stop_processes(COMFY_PROCESS_PATTERN, 60)
    comfy_running = False

if comfy_running:
    print("[OK] Internal ComfyUI worker already running (127.0.0.1:8189).")
else:
    stop_processes(COMFY_PROCESS_PATTERN, 60)
    COMFY_LAUNCHER.write_text(LAUNCHER_SOURCE, encoding="utf-8")
    rotate_log(COMFY_LOG)
    with COMFY_LOG.open("w") as log:
        comfy_proc = subprocess.Popen(
            [sys.executable, str(COMFY_LAUNCHER), "--listen", "127.0.0.1", "--port", str(COMFY_PORT), *COMFY_LAUNCH_ARGS],
            cwd=COMFY_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    COMFY_LAUNCH_CONFIG.write_text(comfy_cfg_str, encoding="utf-8")
    print("Starting internal GPU inference engine...")
    deadline = time.time() + 600
    while time.time() < deadline:
        if comfy_proc.poll() is not None:
            print(tail(COMFY_LOG))
            raise RuntimeError(f"Internal engine failed to start (exit code {comfy_proc.returncode}); see logs above.")
        if comfy_ready():
            print("[OK] Internal GPU inference engine ready (127.0.0.1:8189).")
            break
        time.sleep(2)
    else:
        print(tail(COMFY_LOG))
        raise TimeoutError("Internal engine did not become ready within 10 minutes; check logs.")

missing = sorted(REQUIRED_NODES - set(comfy_get_json("/object_info", timeout=60)))
if missing:
    print(tail(COMFY_LOG))
    raise RuntimeError(f"Missing required ComfyUI nodes: {', '.join(missing)}. Re-run Step 2.")

# 2. Start public FastAPI gateway & static Web Studio (127.0.0.1:8188)
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
    "COMFY_BASE_URL": COMFY_BASE,
    "COMFY_DIR": str(COMFY_DIR),
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
    print("Web/API configuration changed; restarting...")
    stop_processes(APP_PROCESS_PATTERN, 30)
    app_is_up = False

if app_is_up:
    print("[OK] Web Studio and API service already running (127.0.0.1:8188).")
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
    print("Starting Web Studio and API service...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if app_proc.poll() is not None:
            print(tail(APP_LOG))
            raise RuntimeError(f"Web/API service failed to start (exit code {app_proc.returncode}); see logs above.")
        if app_ready():
            print("[OK] Web Studio and API service started.")
            break
        time.sleep(1.5)
    else:
        print(tail(APP_LOG))
        raise TimeoutError("Web/API service did not become ready within 2 minutes; check logs.")

# 3. Expose via Cloudflare Tunnel & persist live URL metadata
verify_web_password(BASE, APP_PROCESS_PATTERN)
host_url = start_cf_tunnel(cf_token)
tunnel_mode_key = "custom" if cf_token else "quick"
if not DATA_DIR.is_symlink():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tunnel_info_path = DATA_DIR / "tunnel_info.json"
    if not tunnel_info_path.is_symlink():
        tunnel_info_path.write_text(
            json.dumps({"public_url": host_url, "tunnel_mode": tunnel_mode_key}, ensure_ascii=False),
            encoding="utf-8",
        )
check_public_url(host_url, "/api/v1/health")

sample_body = json.dumps({{SAMPLE_REQUEST_JSON}}, ensure_ascii=False)
auth_note = ' -H "Authorization: Bearer YOUR_API_KEY"'
tunnel_tip = (
    "WARNING: Quick Tunnel provides a temporary URL that expires when the runtime stops. Select Custom Tunnel above for a permanent domain."
    if tunnel_mode_key == "quick"
    else "INFO: Using your custom fixed Cloudflare Tunnel domain."
)
print(f"""
=== Endpoints ===
Web Studio   : {host_url}
API Docs     : {host_url}/docs
System Stats : {host_url}/api/v1/system
{tunnel_tip}
API Key      : Open by default; configure an optional key in the Web Studio header.

=== Quick API Example ===
curl -X POST "{host_url}/api/v1/generate" \\
  -H "Content-Type: application/json"{auth_note} \\
  -d '{sample_body}'
""")
