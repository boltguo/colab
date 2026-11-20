# @title 4. Launch Web Studio & API Service {display-mode: "form"}
TUNNEL_MODE = "Quick Tunnel (ephemeral)"  # @param ["Quick Tunnel (ephemeral)", "Custom Tunnel (CF_TUNNEL_TOKEN)"]
ACCESS_PASSWORD = ""  # @param {type:"string"}
USE_CF_TUNNEL_TOKEN = TUNNEL_MODE.startswith("Custom")
import hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

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

def ready(timeout=5):
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
    "web_auth_sha256": hashlib.sha256(access_password.encode("utf-8")).hexdigest(),
    "env": {key: value for key, value in env_overrides.items() if key not in {"COLAB_ACCESS_PASSWORD", "COLAB_API_KEY"}},
}, sort_keys=True)
running = ready() or (process_running(PROCESS_PATTERN) and ready(timeout=15))
if running and read_text(LAUNCH_CONFIG) != launch_fingerprint:
    print("Service configuration changed; restarting web server...")
    stop_processes(PROCESS_PATTERN, 30)
    running = False

if running:
    print("[OK] Web Studio and API server already running.")
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
    print("Starting FastAPI server and Web Studio...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if process.poll() is not None:
            print(tail(LOG))
            raise RuntimeError(f"App server failed to start (exit code {process.returncode}); see logs above.")
        if ready():
            print("[OK] Web Studio and API server started.")
            break
        time.sleep(1.5)
    else:
        print(tail(LOG))
        raise TimeoutError("App server did not become ready within 2 minutes; see logs above.")

verify_web_password(BASE, PROCESS_PATTERN)
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

sample_body = json.dumps(
    {"text": "Hello, welcome to IndexTTS 2.5 API!", "speaker_audio": "preset:ref_audio", "language": "en"},
    ensure_ascii=False,
)
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
