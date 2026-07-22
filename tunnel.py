"""Run Codepet and a cloudflared quick tunnel, keeping both alive.

Starts the dashboard, opens a public tunnel to it, and publishes the resulting
URL to ~/.codepet-tunnel.json so the dashboard (and you) can find it — quick
tunnels get a new random hostname every start, so the URL has to be discovered
rather than remembered.

If either process dies it is restarted; a new tunnel URL is republished.

    python tunnel.py            # foreground, Ctrl+C to stop
    pythonw tunnel.py           # no console window (what autostart uses)
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE_DIR, "app.py")
URL_FILE = os.path.expanduser("~/.codepet-tunnel.json")
LOG_FILE = os.path.expanduser("~/.codepet-tunnel.log")
PORT = 8420
HEALTH_URL = f"http://127.0.0.1:{PORT}/"
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
CLOUDFLARED_CANDIDATES = [
    "cloudflared",
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
]
RESTART_BACKOFF_SECONDS = 5
WATCH_INTERVAL_SECONDS = 5


def log(message):
    line = f"{datetime.now().isoformat(timespec='seconds')}  {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def find_cloudflared():
    for candidate in CLOUDFLARED_CANDIDATES:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, timeout=15)
            return candidate
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return None


def publish(url):
    """Record the live tunnel URL where the dashboard and the user can read it."""
    payload = {"url": url, "updated": datetime.now().isoformat(timespec="seconds")}
    try:
        with open(URL_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError as error:
        log(f"no se pudo escribir {URL_FILE}: {error}")
    log(f"URL publica: {url or '(ninguna)'}")


def server_healthy(timeout=2):
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as response:
            return response.status < 400
    except (urllib.error.URLError, OSError):
        return False


def spawn(command):
    """Start a child process with its output piped, no console window."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=flags,
    )


def drain(process, label):
    """Consume a child's output so its pipe never fills up and blocks it."""
    for line in process.stdout:
        if any(word in line for word in ("Traceback", "Error", "CRITICAL")):
            log(f"{label}: {line.strip()[:160]}")


def start_server():
    log("iniciando servidor Codepet")
    process = spawn([sys.executable, APP, "--no-browser"])
    threading.Thread(target=drain, args=(process, "server"), daemon=True).start()
    for _ in range(60):
        if server_healthy():
            log(f"servidor listo en {HEALTH_URL}")
            return process
        if process.poll() is not None:
            log("el servidor murio durante el arranque")
            return process
        time.sleep(1)
    log("el servidor no respondio al health check")
    return process


def start_tunnel(cloudflared):
    """Launch the tunnel and publish the first URL it prints."""
    log("iniciando tunel cloudflared")
    process = spawn([cloudflared, "tunnel", "--url", f"http://localhost:{PORT}"])
    found = threading.Event()

    def reader():
        for line in process.stdout:
            match = URL_PATTERN.search(line)
            if match and not found.is_set():
                publish(match.group(0))
                found.set()
            if "ERR" in line and "DNS local resolver" not in line:
                log(f"cloudflared: {line.strip()[:160]}")

    threading.Thread(target=reader, daemon=True).start()
    if not found.wait(timeout=90):
        log("cloudflared no publico una URL en 90s")
    return process


def main():
    cloudflared = find_cloudflared()
    if not cloudflared:
        log("cloudflared no encontrado: instala con 'winget install --id Cloudflare.cloudflared'")
        return 1

    server = start_server()
    tunnel = start_tunnel(cloudflared)

    try:
        while True:
            time.sleep(WATCH_INTERVAL_SECONDS)
            if server.poll() is not None:
                log("el servidor se cayo, reiniciando")
                time.sleep(RESTART_BACKOFF_SECONDS)
                server = start_server()
            if tunnel.poll() is not None:
                log("el tunel se cayo, reiniciando (la URL cambiara)")
                time.sleep(RESTART_BACKOFF_SECONDS)
                tunnel = start_tunnel(cloudflared)
    except KeyboardInterrupt:
        log("deteniendo")
    finally:
        for process in (tunnel, server):
            if process and process.poll() is None:
                process.terminate()
        publish(None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
