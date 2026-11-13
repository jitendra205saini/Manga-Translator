# System tray app: server chalata hai, status dikhata hai, menu se keys / restart / log / update.
# Ek hi copy chalti hai; dobara kholne par sirf message aata hai.
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
URL = "http://127.0.0.1:7860"
REPO = "jitendra205saini/Manga-Translator"
VERSION = open(os.path.join(HERE, "version.txt"), encoding="utf-8").read().strip()
ICON = os.path.join(APP, "extension", "icons", "icon48.png")
LOG = os.path.join(HERE, "server.log")


def box(text, icon=0x40):
    ctypes.windll.user32.MessageBoxW(None, text, "Manga Translator", icon)


# ---- ek hi copy ----
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "MangaTranslatorTray")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    if "--quiet" not in sys.argv:
        box("Manga Translator is already running.\nLook for its icon near the clock (click ^ if hidden).")
    sys.exit(0)

import pystray  # noqa: E402
from PIL import Image  # noqa: E402

PYW = sys.executable.replace("python.exe", "pythonw.exe")
state = {"status": "Starting...", "update": None, "proc": None, "asked_key": False}


def health():
    try:
        with urllib.request.urlopen(URL + "/health", timeout=2) as r:
            return json.load(r)
    except Exception:
        return None


def start_server():
    if health():
        return
    state["proc"] = subprocess.Popen([PYW, os.path.join(HERE, "run.py")], cwd=HERE,
                                     creationflags=0x08000000)  # CREATE_NO_WINDOW


def stop_server():
    ps = ("Get-NetTCPConnection -LocalPort 7860 -State Listen -EA SilentlyContinue | "
          "% { Stop-Process -Id $_.OwningProcess -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)


def restart(icon=None, item=None):
    state["status"] = "Restarting..."
    stop_server()
    time.sleep(1)
    start_server()


def open_keys(icon=None, item=None):
    webbrowser.open(URL + "/setup")


def open_log(icon=None, item=None):
    os.startfile(LOG) if os.path.exists(LOG) else box("No log yet.")


def open_browser_help(icon=None, item=None):
    os.startfile(os.path.join(APP, "installer", "browser.html"))


def quit_app(icon, item):
    stop_server()
    icon.stop()


# ---- update ----
def _ver(v):
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def check_update(icon=None, item=None):
    manual = item is not None
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "manga-translator-updater"})
        with urllib.request.urlopen(req, timeout=10) as r:
            rel = json.load(r)
        tag = rel.get("tag_name", "")
        asset = next((a["browser_download_url"] for a in rel.get("assets", []) if a["name"].endswith(".exe")), None)
        if asset and _ver(tag) > _ver(VERSION):
            state["update"] = (tag, asset)
            if icon:
                icon.update_menu()
                icon.notify(f"Version {tag} is available. Right-click the icon and choose Update.", "Manga Translator")
        elif manual:
            box(f"You have the latest version ({VERSION}).")
    except Exception as e:
        if manual:
            box(f"Could not check for updates:\n{e}", 0x30)


def do_update(icon, item):
    tag, url = state["update"]
    try:
        icon.notify(f"Downloading {tag}...", "Manga Translator")
        path = os.path.join(tempfile.gettempdir(), "MangaTranslator-Setup.exe")
        urllib.request.urlretrieve(url, path)
    except Exception as e:
        box(f"Download failed:\n{e}", 0x10)
        return
    # installer purana server band karke naya version lagata hai aur tray dobara chalata hai
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
    quit_app(icon, item)


# ---- status loop ----
def watcher(icon):
    start_server()
    last_update_check = 0
    while True:
        h = health()
        if not h:
            st = "Starting..." if state["proc"] and state["proc"].poll() is None else "Server stopped"
        else:
            p = h.get("providers", {})
            ai = {k: v for k, v in p.items() if k in ("gemini", "groq")}
            if not any(v == "ready" or str(v).startswith("limit") for v in ai.values()):
                st = "API key needed"
                if not state["asked_key"]:
                    state["asked_key"] = True
                    open_keys()
            elif not any(v == "ready" for v in ai.values()):
                st = "Daily AI limit reached"
            else:
                st = "Ready"
        if st != state["status"]:
            state["status"] = st
            icon.title = f"Manga Translator {VERSION}: {st}"
            icon.update_menu()
        if time.time() - last_update_check > 24 * 3600:
            last_update_check = time.time()
            threading.Thread(target=check_update, args=(icon,), daemon=True).start()
        time.sleep(4)


menu = pystray.Menu(
    pystray.MenuItem(lambda i: f"Status: {state['status']}", None, enabled=False),
    pystray.MenuItem(lambda i: f"Update to {state['update'][0]}" if state["update"] else "Update",
                     do_update, visible=lambda i: bool(state["update"])),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("API keys", open_keys, default=True),
    pystray.MenuItem("Add extension to browser", open_browser_help),
    pystray.MenuItem("Restart server", restart),
    pystray.MenuItem("Open log", open_log),
    pystray.MenuItem("Check for updates", check_update),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("Quit", quit_app),
)

icon = pystray.Icon("MangaTranslator", Image.open(ICON), f"Manga Translator {VERSION}", menu)
icon.run(setup=lambda i: (setattr(i, "visible", True), threading.Thread(target=watcher, args=(i,), daemon=True).start()))
