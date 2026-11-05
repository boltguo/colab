CF_BIN = Path("/usr/local/bin/cloudflared")
CF_LOG = Path("/content/cloudflared.log")

def read_text(path):
    return path.read_text(errors="replace") if path.exists() else ""

def tail(path, size=8000):
    return read_text(path)[-size:]

def rotate_log(path):
    if path.is_file() and path.stat().st_size:
        path.replace(path.with_name(path.name + ".1"))

def process_running(pattern):
    return subprocess.run(["pgrep", "-f", pattern], stdout=subprocess.DEVNULL).returncode == 0

def stop_processes(pattern, timeout):
    subprocess.run(["pkill", "-f", pattern], check=False)
    deadline = time.time() + timeout
    while process_running(pattern) and time.time() < deadline:
        time.sleep(2)
    if process_running(pattern):
        subprocess.run(["pkill", "-9", "-f", pattern], check=False)
        time.sleep(2)

def resolve_cf_token():
    t = ""
    try:
        from google.colab import userdata
        t = (userdata.get("CF_TUNNEL_TOKEN") or "").strip()
    except Exception:
        t = ""
    if not t:
        t = os.environ.get("CF_TUNNEL_TOKEN", "").strip()
    return t.split()[-1] if t else ""

def start_cf_tunnel(token=""):
    if not CF_BIN.exists():
        raise RuntimeError("未找到 cloudflared，请先运行第 2 步。")
    stop_processes("cloudflared tunnel", 10)
    rotate_log(CF_LOG)
    cmd = [
        str(CF_BIN),
        "tunnel",
        "--no-autoupdate",
        "--protocol", "http2",
        "--edge-ip-version", "4",
    ]
    if token:
        cmd.extend(["run", "--url", BASE, "--token", token])
    else:
        cmd.extend(["--url", BASE])
    with CF_LOG.open("w") as cf_log:
        cf_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=cf_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.time() + (30 if token else 60)
    while time.time() < deadline:
        if cf_proc.poll() is not None:
            print(tail(CF_LOG, 4000))
            if token:
                raise RuntimeError("Cloudflare Tunnel 启动失败，请检查 CF_TUNNEL_TOKEN 是否正确。")
            raise RuntimeError("Cloudflare 临时隧道启动失败，请查看上方日志。")
        log_text = read_text(CF_LOG)
        if not token:
            match = re.search(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com", log_text)
            if match and "Registered tunnel connection" in log_text:
                url = match.group(0)
                print(f"[OK] Cloudflare 临时隧道已连接 (HTTP/2): {url} -> {BASE}")
                return url
        elif "Registered tunnel connection" in log_text:
            if "Updated to new configuration" not in log_text:
                time.sleep(1)
                log_text = read_text(CF_LOG)
            configs = [line for line in log_text.splitlines() if "Updated to new configuration" in line]
            config = configs[-1].replace('\\"', '"') if configs else ""
            routes = re.findall(r'"hostname"\s*:\s*"([^"]+)"(?:(?!"hostname").)*?"service"\s*:\s*"([^"]+)"', config)
            for host, service in routes:
                print(f"[OK] Cloudflare Tunnel 已连接 (HTTP/2): https://{host} -> {service}")
            hosts = [host for host, service in routes if f":{PORT}" in service]
            if not routes:
                print("[OK] Cloudflare Tunnel 已连接 (HTTP/2)，请通过你在 Cloudflare 绑定的域名访问。")
            elif not hosts:
                print(f"[WARN] 没有域名转发到本服务的 {PORT} 端口！")
                print(f"       请前往 Cloudflare Zero Trust -> Networks -> Tunnels -> Public Hostname，将 Service URL 改为 {BASE}")
            return f"https://{hosts[0]}" if hosts else "https://<你的CF域名>"
        time.sleep(1)
    if not token:
        match = re.search(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com", read_text(CF_LOG))
        if match:
            url = match.group(0)
            print(f"[OK] Cloudflare 临时隧道已创建: {url} -> {BASE}")
            return url
        print(tail(CF_LOG, 4000))
        raise RuntimeError(f"Cloudflare 临时隧道 60 秒内未返回地址，详见 {CF_LOG}。")
    print(f"[WARN] Cloudflare Tunnel 30 秒内未确认连接，仍在后台运行，详见 {CF_LOG}。")
    return "https://<你的CF域名>"

def check_public_url(url, route):
    if "<" in url:
        return
    error = None
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            request = urllib.request.Request(url + route, headers={"User-Agent": "colab-tunnel-check"})
            with urllib.request.urlopen(request, timeout=10):
                print(f"[OK] 公网访问正常：{url}")
                return
        except Exception as e:
            error = e
        time.sleep(3)
    print(f"[WARN] 公网地址 60 秒内无法访问：{url}{route}（{error}）")

cf_token = resolve_cf_token() if USE_CF_TUNNEL_TOKEN else ""
if USE_CF_TUNNEL_TOKEN and not cf_token:
    raise RuntimeError("已勾选 USE_CF_TUNNEL_TOKEN，但未检测到 CF_TUNNEL_TOKEN；请在 Colab 左侧 🔑 Secrets 中添加 CF_TUNNEL_TOKEN 并开启访问权限，或取消勾选改用临时隧道。")
