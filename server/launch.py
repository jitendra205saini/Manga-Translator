# "Manga Translator" shortcut: server background mein chalao, ready hone ka intezaar,
# key na ho to /setup page kholo. Koi console window nahi (pythonw).
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "http://127.0.0.1:7860"


def health():
    try:
        with urllib.request.urlopen(URL + "/health", timeout=2) as r:
            return json.load(r)
    except Exception:
        return None


def box(text, icon=0x40):
    ctypes.windll.user32.MessageBoxW(None, text, "Manga Translator", icon)


h = health()
if not h:
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([exe, os.path.join(HERE, "run.py")], cwd=HERE,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    for _ in range(120):
        time.sleep(1)
        h = health()
        if h:
            break
if not h:
    box("Server start nahi hua.\n\nLog: " + os.path.join(HERE, "server.log"), 0x10)
    sys.exit(1)

p = h.get("providers", {})
if not any(v == "ready" or str(v).startswith("limit") for k, v in p.items() if k in ("gemini", "groq")):
    webbrowser.open(URL + "/setup")
elif "--quiet" not in sys.argv:
    box("Manga Translator chal raha hai.\n\nManga page kholo aur extension ON karo (Alt+T).")
