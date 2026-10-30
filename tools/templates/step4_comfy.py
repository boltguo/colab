# @title 4. 启动并打开 ComfyUI {display-mode: "form"}
import json, os, re, socket, subprocess, sys, time, urllib.request
from pathlib import Path

COMFY_DIR = Path("/content/ComfyUI")
PORT = 8188
BASE = f"http://127.0.0.1:{PORT}"
LOG = Path("/content/comfyui.log")
LAUNCHER = Path("/content/comfy_userdata_compat.py")
LAUNCH_CONFIG = Path("/content/comfyui.launch.json")
PROCESS_PATTERN = r"comfy_userdata_compat\.py|ComfyUI/main\.py"
LAUNCH_ARGS = [
    "--output-directory", str(COMFY_DIR / "output"),
    "--enable-cors-header",
    "--enable-compress-response-body",
    "--disable-all-custom-nodes",
{{LAUNCH_ARGS}}    "--disable-partner-nodes",
]
REQUIRED_NODES = {{REQUIRED_NODES}}

{{HELPERS}}
if not (COMFY_DIR / "main.py").is_file():
    raise RuntimeError("未找到 ComfyUI，请先运行第 2 步。")

LAUNCHER_SOURCE = r'''{{LAUNCHER_SOURCE}}'''

def get_json(route, timeout=5):
    with urllib.request.urlopen(BASE + route, timeout=timeout) as response:
        return json.load(response)

def ready(timeout=5):
    try:
        get_json("/system_stats", timeout)
        return True
    except Exception:
        return False

def get_listen_addrs():
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.bind(("::1", 0))
        return "127.0.0.1,::1"
    except OSError:
        return "127.0.0.1"

launch_config = json.dumps({"launcher": LAUNCHER_SOURCE, "args": LAUNCH_ARGS})
running = ready() or (process_running(PROCESS_PATTERN) and ready(timeout=30))
if running and read_text(LAUNCH_CONFIG) != launch_config:
    try:
        queue = get_json("/queue", timeout=10)
        busy = bool(queue["queue_running"] or queue["queue_pending"])
    except Exception:
        busy = True
    if busy:
        print("[WARN] 启动配置已更新，但 ComfyUI 正在执行任务；任务完成后重新运行本步骤即可应用。")
    else:
        print("启动配置已更新，正在重启 ComfyUI...")
        stop_processes(PROCESS_PATTERN, 60)
        running = False

if running:
    print("[OK] ComfyUI 已经在运行。")
else:
    stop_processes(PROCESS_PATTERN, 60)
    LAUNCHER.write_text(LAUNCHER_SOURCE)
    rotate_log(LOG)
    with LOG.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, str(LAUNCHER), "--listen", get_listen_addrs(), "--port", str(PORT), *LAUNCH_ARGS],
            cwd=COMFY_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    LAUNCH_CONFIG.write_text(launch_config)
    print("正在启动 ComfyUI...")
    deadline = time.time() + 600
    while time.time() < deadline:
        if process.poll() is not None:
            print(tail(LOG))
            raise RuntimeError(f"ComfyUI 启动失败（退出码 {process.returncode}），请查看上方日志。")
        if ready():
            print("[OK] ComfyUI 启动成功。")
            break
        time.sleep(2)
    else:
        print(tail(LOG))
        raise TimeoutError("ComfyUI 10 分钟内未就绪，请查看上方日志。")

missing = sorted(REQUIRED_NODES - set(get_json("/object_info", timeout=60)))
if missing:
    print(tail(LOG))
    raise RuntimeError(f"缺少节点：{', '.join(missing)}。请重新运行第 2 步安装指定版本后，再运行本步骤。日志：{LOG}")

host_url = start_cf_tunnel(cf_token)
check_public_url(host_url, "/system_stats")
