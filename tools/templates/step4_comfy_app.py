# @title 4. Launch Web Studio {display-mode: "form"}
import json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
from urllib.parse import urlsplit

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

# 2. Start Web Studio server (127.0.0.1:8188, loopback only)
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
    "env": env_overrides,
}, sort_keys=True)
app_is_up = app_ready() or (process_running(APP_PROCESS_PATTERN) and app_ready(timeout=15))
if app_is_up and read_text(APP_LAUNCH_CONFIG) != app_fingerprint:
    print("Web Studio configuration changed; restarting...")
    stop_processes(APP_PROCESS_PATTERN, 30)
    app_is_up = False

if app_is_up:
    print("[OK] Web Studio server already running (127.0.0.1:8188).")
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
