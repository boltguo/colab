cloudflared_bin = Path("/usr/local/bin/cloudflared")
try:
    installed = subprocess.run([str(cloudflared_bin), "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
except OSError:
    installed = ""
if CLOUDFLARED_VERSION not in installed.split():
    download = cloudflared_bin.with_name("cloudflared.download")
    urllib.request.urlretrieve(
        f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/cloudflared-linux-amd64",
        str(download),
    )
    download.chmod(0o755)
    download.replace(cloudflared_bin)
