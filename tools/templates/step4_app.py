# @title 4. Launch Web Studio {display-mode: "form"}
import json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
from urllib.parse import urlsplit

FEATURE_NAME = "{{FEATURE_NAME}}"
APP_DIR = Path("/content/app")
DATA_DIR = Path(f"/content/app_data/{FEATURE_NAME}")
PORT = 8188
BASE = f"http://127.0.0.1:{PORT}"
LOG = Path(f"/content/{FEATURE_NAME}-web.log")
LAUNCH_CONFIG = Path(f"/content/{FEATURE_NAME}.launch.json")
PROCESS_PATTERN = r"backend/run_server\.py|backend\.run_server"

{{HELPERS}}
if APP_DIR.is_symlink() or not (APP_DIR / "backend/run_server.py").is_file():
    raise RuntimeError("App directory /content/app not found; please run Step 2 first.")

if FEATURE_NAME == "indextts-2.5":
    missing_media_tools = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing_media_tools:
        raise RuntimeError(f"Missing required media tools: {', '.join(missing_media_tools)}. Run !apt-get -qq update && apt-get -qq install -y ffmpeg first.")

def ready(timeout=5):
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
{{EXTRA_ENV}}}

cmd = [
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

launch_fingerprint = json.dumps({
    "cmd": cmd,
    "release": read_text(APP_DIR / ".release_sha256").strip(),
    "env": env_overrides,
}, sort_keys=True)
running = ready() or (process_running(PROCESS_PATTERN) and ready(timeout=15))
if running and read_text(LAUNCH_CONFIG) != launch_fingerprint:
    print("Service configuration changed; restarting Web Studio...")
    stop_processes(PROCESS_PATTERN, 30)
    running = False

if running:
    print("[OK] Web Studio server already running.")
else:
    stop_processes(PROCESS_PATTERN, 30)
    rotate_log(LOG)
    child_env = {**os.environ, **env_overrides}
    with LOG.open("w") as log:
        process = subprocess.Popen(
            cmd,
            cwd=APP_DIR,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    LAUNCH_CONFIG.write_text(launch_fingerprint, encoding="utf-8")
    print("Starting FastAPI Web Studio...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if process.poll() is not None:
            print(tail(LOG))
            raise RuntimeError(f"App server failed to start (exit code {process.returncode}); see logs above.")
        if ready():
            print("[OK] Web Studio server started.")
            break
        time.sleep(1.5)
    else:
        print(tail(LOG))
        raise TimeoutError("App server did not become ready within 2 minutes; see logs above.")

if not DATA_DIR.is_symlink():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    proxy_info_path = DATA_DIR / "proxy_info.json"
    if not proxy_info_path.is_symlink():
        proxy_info_path.write_text(
            json.dumps({"public_url": proxy_url, "access_mode": access_mode}, ensure_ascii=False),
            encoding="utf-8",
        )
open_colab_proxy(PORT, proxy_url, access_mode)
