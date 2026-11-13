# Setup ka status: GPU, font, OCR languages, models, AI keys
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # embeddable Python ke liye
import dllfix  # noqa: F401,E402  (PIL se pehle)
import onnxruntime as ort
from PIL import features

import detector
import inpaint
import llm
import mangaocr
import render
from ocr_windows import LANG_TAGS, OcrLanguageMissing, get_engine, installed_ocr_languages

gpu = "DmlExecutionProvider" in ort.get_available_providers()
print("GPU (DirectML) :", "OK" if gpu else "nahi mila - detector CPU par chalega (thoda slow)")
print("Font           :", render.FONT_PATH)
print("Hindi shaping  :", "OK (raqm)" if features.check("raqm") else "raqm nahi mila - matras galat jagah dikh sakti hain")

print("OCR installed  :", installed_ocr_languages())
for lang, tag in LANG_TAGS.items():
    try:
        get_engine(lang)
        print(f"  {tag:12s} OK")
    except OcrLanguageMissing:
        print(f"  {tag:12s} MISSING  -> INSTALL_OCR_LANGUAGES.bat chalao")

print("ML detector    :", "OK" if detector.available() else "MISSING - download_assets.py chalao")
print("LaMa inpaint   :", "OK" if inpaint.available() else "MISSING - download_assets.py chalao")
print("manga-ocr      :", "OK" if mangaocr.available() else "MISSING - Japanese ke liye Windows OCR chalega")
print("AI providers   :", llm.provider_status())
