# @title 4. 启动现代 Web 工作台与 API 服务 {display-mode: "form"}
TUNNEL_MODE = "Quick Tunnel (临时链接)"  # @param ["Quick Tunnel (临时链接)", "自有 Tunnel (读取 Secrets 中 CF_TUNNEL_TOKEN)"]
REQUIRE_API_KEY = False  # @param {type:"boolean"}
USE_CF_TUNNEL_TOKEN = TUNNEL_MODE.startswith("自有")
import json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

FEATURE_NAME = "{{FEATURE_NAME}}"
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
    raise RuntimeError("未找到内部推理引擎 /content/ComfyUI，请先运行第 2 步。")
if APP_DIR.is_symlink() or not (APP_DIR / "backend/run_server.py").is_file():
    raise RuntimeError("未找到应用服务目录 /content/app，请先运行第 2 步。")

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

# 1. 启动内部无头推理 Worker (127.0.0.1:8189，不对公网直接暴露)
comfy_cfg_str = json.dumps({"launcher": LAUNCHER_SOURCE, "args": COMFY_LAUNCH_ARGS, "port": COMFY_PORT})
comfy_running = comfy_ready() or (process_running(COMFY_PROCESS_PATTERN) and comfy_ready(timeout=30))
if comfy_running and read_text(COMFY_LAUNCH_CONFIG) != comfy_cfg_str:
    print("内部推理引擎参数已更新，正在重启...")
    stop_processes(COMFY_PROCESS_PATTERN, 60)
    comfy_running = False

if comfy_running:
    print("[OK] 内部推理引擎已在运行 (127.0.0.1:8189)。")
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
    print("正在启动内部 GPU 推理引擎...")
    deadline = time.time() + 600
    while time.time() < deadline:
        if comfy_proc.poll() is not None:
            print(tail(COMFY_LOG))
            raise RuntimeError(f"内部推理引擎启动失败（退出码 {comfy_proc.returncode}），详见上方日志。")
        if comfy_ready():
            print("[OK] 内部 GPU 推理引擎就绪 (127.0.0.1:8189)。")
            break
        time.sleep(2)
    else:
        print(tail(COMFY_LOG))
        raise TimeoutError("内部推理引擎 10 分钟内未就绪，请检查日志。")

missing = sorted(REQUIRED_NODES - set(comfy_get_json("/object_info", timeout=60)))
if missing:
    print(tail(COMFY_LOG))
    raise RuntimeError(f"推理引擎缺少必要算子节点：{', '.join(missing)}。请重新运行第 2 步。")

# 2. 启动对外 FastAPI + 现代静态前端工作台 (127.0.0.1:8188)
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

app_fingerprint = json.dumps({"cmd": app_cmd, "auth": bool(app_api_key)}, sort_keys=True)
app_is_up = app_ready() or (process_running(APP_PROCESS_PATTERN) and app_ready(timeout=15))
if app_is_up and read_text(APP_LAUNCH_CONFIG) != app_fingerprint:
    print("Web/API 服务配置变更，正在重启...")
    stop_processes(APP_PROCESS_PATTERN, 30)
    app_is_up = False

if app_is_up:
    print("[OK] 现代 Web 工作台与 API 服务已在运行 (127.0.0.1:8188)。")
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
    print("正在启动现代 Web 工作台与标准 API 网关...")
    deadline = time.time() + 120
    while time.time() < deadline:
        if app_proc.poll() is not None:
            print(tail(APP_LOG))
            raise RuntimeError(f"Web/API 服务启动失败（退出码 {app_proc.returncode}），详见上方日志。")
        if app_ready():
            print("[OK] 现代 Web 工作台与标准 API 服务启动成功。")
            break
        time.sleep(1.5)
    else:
        print(tail(APP_LOG))
        raise TimeoutError("Web/API 服务 2 分钟内未就绪，请检查日志。")

# 3. 挂载 Cloudflare Tunnel 并同步隧道地址供前端 API 调用示例自动读取
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
🩺 机器与显存状态  : {host_url}/api/v1/system
{tunnel_tip}

=== 快速 API 调用示例 ===
curl -X POST "{host_url}/api/v1/generate" \\
  -H "Content-Type: application/json"{auth_note} \\
  -d '{sample_body}'
""")
