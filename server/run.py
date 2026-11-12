# Bina console window ke server chalao (pythonw). Output server\server.log mein jaata hai.
# Port pehle se busy ho (server already chal raha) to chupchap band ho jaata hai.
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

s = socket.socket()
try:
    s.bind(("127.0.0.1", 7860))
except OSError:
    sys.exit(0)
finally:
    s.close()

log = open(os.path.join(HERE, "server.log"), "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log

import uvicorn  # noqa: E402

uvicorn.run("server:app", host="127.0.0.1", port=7860, log_config=None)
