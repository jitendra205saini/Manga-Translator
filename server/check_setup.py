# Setup ka status check karta hai
import dllfix  # noqa: F401  (PIL se pehle)
import torch
from PIL import features

import render
from ocr_windows import LANG_TAGS, OcrLanguageMissing, get_engine, installed_ocr_languages

print("CUDA available :", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU            :", torch.cuda.get_device_name(0))
else:
    print("  -> GPU nahi mila, translation CPU par chalega (slow). NVIDIA driver update karke dekho.")

print("Font           :", render.FONT_PATH)
print("Hindi shaping  :", "OK (raqm)" if features.check("raqm") else "raqm nahi mila - matras galat jagah dikh sakti hain")

print("OCR installed  :", installed_ocr_languages())
for lang, tag in LANG_TAGS.items():
    try:
        get_engine(lang)
        print(f"  {tag:12s} OK")
    except OcrLanguageMissing:
        print(f"  {tag:12s} MISSING  -> INSTALL_OCR_LANGUAGES.bat chalao")

import llm
print("AI providers   :", llm.provider_status())

import detector, inpaint
print("ML detector    :", "OK" if detector.available() else "nahi mila (SETUP.bat chalao) - OpenCV tarika chalega")
print("LaMa inpaint   :", "OK" if inpaint.available() else "nahi mila - OpenCV inpaint chalega")
