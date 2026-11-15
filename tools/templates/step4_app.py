# @title 4. 启动现代 Web 工作台与 API 服务 {display-mode: "form"}
TUNNEL_MODE = "Quick Tunnel (临时链接)"  # @param ["Quick Tunnel (临时链接)", "自有 Tunnel (读取 Secrets 中 CF_TUNNEL_TOKEN)"]
REQUIRE_API_KEY = False  # @param {type:"boolean"}
USE_CF_TUNNEL_TOKEN = TUNNEL_MODE.startswith("自有")
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
    raise RuntimeError("未找到应用服务目录 /content/app，请先运行第 2 步。")

if FEATURE_NAME == "indextts-2.5":
    missing_media_tools = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing_media_tools:
        raise RuntimeError(f"缺少媒体处理工具：{', '.join(missing_media_tools)}。请先执行 !apt-get -qq update && apt-get -qq install -y ffmpeg，再运行第 4 步。")

def resolve_app_api_key():
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
        "已勾选 REQUIRE_API_KEY，但未找到 APP_API_KEY。请在 Colab 左侧 🔑 Secrets 中配置 APP_API_KEY。"
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
    "COLAB_API_KEY": app_api_key,
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
    "auth_sha256": hashlib.sha256(app_api_key.encode("utf-8")).hexdigest(),
    "env": {key: value for key, value in env_overrides.items() if key != "COLAB_API_KEY"},
}, sort_keys=True)
running = ready() or (process_running(PROCESS_PATTERN) and ready(timeout=15))
if running and read_text(LAUNCH_CONFIG) != launch_fingerprint:
    print("服务配置已变更，正在重启应用服务...")
    stop_processes(PROCESS_PATTERN, 30)
    running = False

if running:
    print("[OK] Web 与 API 服务已经在运行。")
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
    print("正在启动 FastAPI 服务与静态前端工作台...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if process.poll() is not None:
            print(tail(LOG))
            raise RuntimeError(f"应用服务启动失败（退出码 {process.returncode}），详见上方日志。")
        if ready():
            print("[OK] Web 与 API 服务启动成功。")
            break
        time.sleep(1.5)
    else:
        print(tail(LOG))
        raise TimeoutError("应用服务 2 分钟内未就绪，请查看上方日志。")

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
    {"text": "你好，欢迎调用 IndexTTS 2.5 API 服务！", "speaker_audio": "preset:ref_audio", "language": "zh"},
    ensure_ascii=False,
)
auth_note = ' -H "Authorization: Bearer $APP_API_KEY"' if app_api_key else ""
tunnel_tip = (
    "⚠️ 提示：当前使用 Cloudflare Quick Tunnel 临时公网域名，实例关闭或重连隧道后地址即失效；如需固定域名请在上方选择「自有 Tunnel」。"
    if tunnel_mode_key == "quick"
    else "✅ 当前使用自有 Cloudflare Tunnel 固定域名。"
)
print(f"""
=== 访问入口 ===
🌐 现代 Web 操作台 : {host_url}
📖 在线 API 文档   : {host_url}/docs
🩺 系统与显存状态  : {host_url}/api/v1/system
{tunnel_tip}

=== 快速 API 调用示例 ===
curl -X POST "{host_url}/api/v1/generate" \\
  -H "Content-Type: application/json"{auth_note} \\
  -d '{sample_body}'
""")
