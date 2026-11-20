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
        raise RuntimeError("cloudflared not found; please run Step 2 first.")
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
                raise RuntimeError("Cloudflare Tunnel failed to start; check CF_TUNNEL_TOKEN.")
            raise RuntimeError("Cloudflare Quick Tunnel failed to start; check logs above.")
        log_text = read_text(CF_LOG)
        if not token:
            match = re.search(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com", log_text)
            if match and "Registered tunnel connection" in log_text:
                url = match.group(0)
                print(f"[OK] Cloudflare Quick Tunnel connected (HTTP/2): {url} -> {BASE}")
                return url
        elif "Registered tunnel connection" in log_text:
            if "Updated to new configuration" not in log_text:
                time.sleep(1)
                log_text = read_text(CF_LOG)
            configs = [line for line in log_text.splitlines() if "Updated to new configuration" in line]
            config = configs[-1].replace('\\"', '"') if configs else ""
            routes = re.findall(r'"hostname"\s*:\s*"([^"]+)"(?:(?!"hostname").)*?"service"\s*:\s*"([^"]+)"', config)
            for host, service in routes:
                print(f"[OK] Cloudflare Tunnel connected (HTTP/2): https://{host} -> {service}")
            hosts = [host for host, service in routes if f":{PORT}" in service]
            if not routes:
                print("[OK] Cloudflare Tunnel connected (HTTP/2); open via your configured Cloudflare hostname.")
            elif not hosts:
                print(f"[WARN] No public hostname forwards to port {PORT}!")
                print(f"       Set Service URL to {BASE} under Cloudflare Zero Trust -> Networks -> Tunnels -> Public Hostname")
            return f"https://{hosts[0]}" if hosts else "https://<your-cf-domain>"
        time.sleep(1)
    if not token:
        match = re.search(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com", read_text(CF_LOG))
        if match:
            url = match.group(0)
            print(f"[OK] Cloudflare Quick Tunnel ready: {url} -> {BASE}")
            return url
        print(tail(CF_LOG, 4000))
        raise RuntimeError(f"Cloudflare Quick Tunnel returned no URL within 60s; see {CF_LOG}.")
    print(f"[WARN] Cloudflare Tunnel connection not confirmed within 30s (still running); see {CF_LOG}.")
    return "https://<your-cf-domain>"

def verify_web_password(base_url, process_pattern):
    from urllib.error import HTTPError

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(base_url + "/", timeout=10):
            pass
    except HTTPError as error:
        if error.code == 303 and error.headers.get("Location") == "/auth/login":
            print("[OK] Web access password protection verified.")
            return
    except Exception:
        pass
    stop_processes(process_pattern, 30)
    raise RuntimeError("Web access password check failed; stopped web server. Update the notebook and rerun Steps 2 and 4.")

def check_public_url(url, route):
    if "<" in url:
        return
    error = None
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            request = urllib.request.Request(url + route, headers={"User-Agent": "colab-tunnel-check"})
            with urllib.request.urlopen(request, timeout=10):
                print(f"[OK] Public URL reachable: {url}")
                return
        except Exception as e:
            error = e
        time.sleep(3)
    print(f"[WARN] Public URL unreachable within 60s: {url}{route} ({error})")

cf_token = resolve_cf_token() if USE_CF_TUNNEL_TOKEN else ""
if USE_CF_TUNNEL_TOKEN and not cf_token:
    raise RuntimeError("Custom Tunnel is selected, but CF_TUNNEL_TOKEN was not found. Add CF_TUNNEL_TOKEN in Colab Secrets (or switch to Quick Tunnel).")
