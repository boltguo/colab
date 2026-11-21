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

def resolve_colab_proxy_url(port):
    try:
        from google.colab import output
    except ImportError:
        return f"http://127.0.0.1:{int(port)}", "local"
    try:
        proxy_url = output.eval_js(f"google.colab.kernel.proxyPort({int(port)})")
    except Exception as exc:
        raise RuntimeError(
            "Failed to resolve Colab native proxy URL. Run Step 4 inside a browser Google Colab notebook session."
        ) from exc
    if not isinstance(proxy_url, str) or not proxy_url.strip().startswith("https://"):
        raise RuntimeError(
            f"Colab did not return a valid HTTPS proxy URL ({proxy_url!r}). Open the notebook in your browser and re-run Step 4."
        )
    return proxy_url.strip().rstrip("/"), "colab"

def open_colab_proxy(port, proxy_url, access_mode):
    if access_mode == "colab":
        from google.colab import output
        output.serve_kernel_port_as_window(int(port))
        print(f"[OK] Web Studio (Colab Native Proxy): {proxy_url}")
        print("Access is restricted to your signed-in Google account and expires when this runtime stops.")
    else:
        print(f"[OK] Web Studio (Local): {proxy_url}")
