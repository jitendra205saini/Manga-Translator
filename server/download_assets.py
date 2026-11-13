# Font aur NLLB model ek baar download karta hai
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
import sys  # noqa: E402
sys.path.insert(0, HERE)  # embeddable Python script ka folder khud nahi jodta
FONT_URL = ("https://github.com/notofonts/notofonts.github.io/raw/main/fonts/"
            "NotoSansDevanagari/hinted/ttf/NotoSansDevanagari-Regular.ttf")
MODEL_NAME = "facebook/nllb-200-distilled-600M"


def get_font():
    dst = os.path.join(HERE, "fonts", "NotoSansDevanagari-Regular.ttf")
    if os.path.exists(dst):
        print("[font] already hai")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        urllib.request.urlretrieve(FONT_URL, dst)
        with open(dst, "rb") as f:
            head = f.read(4)
        # check: asli TTF file hai, HTML error page nahi
        if os.path.getsize(dst) < 50_000 or head not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            raise ValueError("downloaded file font nahi lagti")
        print("[font] NotoSansDevanagari download ho gaya")
    except Exception as e:
        if os.path.exists(dst):
            os.remove(dst)
        print(f"[font] download fail ({e}). Windows ka Nirmala UI font use hoga, wo bhi Hindi support karta hai.")


def get_model():
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    print("[model] NLLB-200 600M download ho raha hai (~2.5 GB)...")
    AutoTokenizer.from_pretrained(MODEL_NAME)
    AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    print("[model] ready")


MSYS_REPO = "https://repo.msys2.org/mingw/ucrt64/"


def get_fribidi():
    # Pillow ke Windows build mein raqm hai, bas fribidi DLL chahiye (Hindi matras ke liye)
    bin_dir = os.path.join(HERE, "bin")
    dst = os.path.join(bin_dir, "fribidi-0.dll")
    if os.path.exists(dst):
        print("[fribidi] already hai")
        return
    try:
        index = urllib.request.urlopen(MSYS_REPO, timeout=30).read().decode()
        names = sorted(set(re.findall(r'mingw-w64-ucrt-x86_64-fribidi-[\w.+-]+?-any\.pkg\.tar\.zst(?=")', index)))
        if not names:
            raise RuntimeError("package list mein fribidi nahi mila")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = os.path.join(tmp, "fribidi.tar.zst")
            urllib.request.urlretrieve(MSYS_REPO + names[-1], pkg)
            subprocess.run(["tar", "-xf", pkg, "-C", tmp], check=True)
            os.makedirs(bin_dir, exist_ok=True)
            found = False
            for root, _, files in os.walk(tmp):
                for f in files:
                    if f.lower() == "libfribidi-0.dll":
                        shutil.copy(os.path.join(root, f), dst)
                        found = True
            if not found:
                raise RuntimeError("package mein libfribidi-0.dll nahi mili")
        print(f"[fribidi] {names[-1]} install ho gaya")
    except Exception as e:
        print(f"[fribidi] fail ({e}). Hindi matras galat dikh sakti hain.")


HF_FILES = [
    # (repo, file, local folder) - sab Apache-2.0
    ("ogkalu/comic-text-and-bubble-detector", "detector.onnx", "comic-text-and-bubble-detector"),
    ("Carve/LaMa-ONNX", "lama_fp32.onnx", "LaMa-ONNX"),
    ("l0wgear/manga-ocr-2025-onnx", "encoder_model.onnx", "manga-ocr"),
    ("l0wgear/manga-ocr-2025-onnx", "decoder_model.onnx", "manga-ocr"),
    ("l0wgear/manga-ocr-2025-onnx", "vocab.txt", "manga-ocr"),
]
BALOO_URL = "https://github.com/google/fonts/raw/main/ofl/baloo2/Baloo2%5Bwght%5D.ttf"


def get_models():
    # ML bubble/text detector (~170 MB) aur LaMa inpainting (~210 MB)
    from huggingface_hub import hf_hub_download
    for repo, name, folder in HF_FILES:
        dst = os.path.join(HERE, "models", folder, name)
        if os.path.exists(dst):
            print(f"[models] {name} already hai")
            continue
        try:
            print(f"[models] {repo}/{name} download ho raha hai...")
            hf_hub_download(repo, name, local_dir=os.path.join(HERE, "models", folder), token=False)
        except Exception as e:
            print(f"[models] {name} fail ({e}). Purana OpenCV tarika chalega.")


def get_comic_font():
    dst = os.path.join(HERE, "fonts", "Baloo2.ttf")
    if os.path.exists(dst):
        print("[font] Baloo 2 already hai")
        return
    try:
        urllib.request.urlretrieve(BALOO_URL, dst)
        print("[font] Baloo 2 (comic style Hindi) download ho gaya")
    except Exception as e:
        print(f"[font] Baloo 2 fail ({e}). Noto Sans Devanagari chalega.")


def make_config():
    dst = os.path.join(HERE, "config.json")
    if os.path.exists(dst):
        print("[config] config.json already hai")
        return
    import llm
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(llm.DEFAULT_CONFIG, f, indent=2)
    print("[config] config.json bana diya. Isme apni Gemini / Groq key daalo.")


if __name__ == "__main__":
    get_fribidi()
    make_config()
    get_font()
    get_comic_font()
    get_models()
    import sys
    if "--no-nllb" not in sys.argv:
        get_model()
