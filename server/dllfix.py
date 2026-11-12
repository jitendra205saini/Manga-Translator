# server/bin ki DLLs (fribidi) ko PATH par daalo, taaki Pillow Hindi sahi shape kare (raqm).
# Ye module PIL se PEHLE import hona chahiye.
import os

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
if os.path.isdir(BIN):
    os.environ["PATH"] = BIN + os.pathsep + os.environ.get("PATH", "")
    try:
        os.add_dll_directory(BIN)
    except (AttributeError, OSError):
        pass
