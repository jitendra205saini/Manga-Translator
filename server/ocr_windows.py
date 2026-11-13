# Windows 11 built-in OCR helpers (sirf winsdk, EasyOCR nahi)
import io
import math
import re

from PIL import Image
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import (
    BitmapAlphaMode,
    BitmapDecoder,
    BitmapPixelFormat,
)
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

LANG_TAGS = {
    "ja": "ja",
    "ko": "ko",
    "zh_hans": "zh-Hans-CN",
    "zh_hant": "zh-Hant-TW",
    "en": "en-US",
}
CJK_LANGS = {"ja", "zh_hans", "zh_hant"}

_engine_cache = {}


class OcrLanguageMissing(RuntimeError):
    pass


def installed_ocr_languages():
    return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]


def get_engine(lang):
    if lang in _engine_cache:
        return _engine_cache[lang]
    tag = LANG_TAGS[lang]
    engine = OcrEngine.try_create_from_language(Language(tag))
    if engine is None:
        raise OcrLanguageMissing(
            f"OCR language pack '{tag}' install nahi hai. INSTALL_OCR_LANGUAGES.bat chalao. "
            f"Abhi installed: {installed_ocr_languages()}"
        )
    _engine_cache[lang] = engine
    return engine


def _max_dim():
    try:
        return int(OcrEngine.max_image_dimension)
    except Exception:
        return 4000


async def pil_to_software_bitmap(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(buf.getvalue())
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()  # warna writer ke saath stream bhi band ho jata hai
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    # OCR ke liye BGRA8 zaroori (decode ke time hi convert)
    return await decoder.get_software_bitmap_converted_async(
        BitmapPixelFormat.BGRA8, BitmapAlphaMode.PREMULTIPLIED)


def _prepare_image(img):
    # Badi image ko OCR limit tak chhota, chhoti ko 2x bada (chhote text ke liye better)
    max_dim = _max_dim()
    w, h = img.size
    scale = 1.0
    if max(w, h) < 1200 and max(w, h) * 2 <= max_dim:
        scale = 2.0
    if max(w, h) * scale > max_dim:
        scale = max_dim / max(w, h)
    if scale != 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img, scale


def _clean_text(text, lang):
    if lang in CJK_LANGS:
        return re.sub(r"\s+", "", text)  # CJK characters ke beech ke spaces hatao
    return text.strip()


async def recognize_lines(img, lang):
    # Return: [{"text": str, "box": (x0, y0, x1, y1)}]  original image coords mein
    engine = get_engine(lang)
    ocr_img, scale = _prepare_image(img)
    bmp = await pil_to_software_bitmap(ocr_img)
    result = await engine.recognize_async(bmp)

    # Windows OCR page ko tircha (text_angle) samjhe to boxes ghoomi hui image ke hote hain: wapas ghumao
    try:
        ang = math.radians(float(result.text_angle or 0))
    except Exception:
        ang = 0.0
    cx, cy = ocr_img.size[0] / 2, ocr_img.size[1] / 2
    ca, sa = math.cos(ang), math.sin(ang)

    def unrotate(x, y):
        dx, dy = x - cx, y - cy
        return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca

    lines = []
    for line in result.lines:
        rects = [word.bounding_rect for word in line.words]
        if not rects:
            continue
        pts = [unrotate(px, py) for r in rects
               for px, py in ((r.x, r.y), (r.x + r.width, r.y), (r.x, r.y + r.height), (r.x + r.width, r.y + r.height))]
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        x1 = max(p[0] for p in pts)
        y1 = max(p[1] for p in pts)
        text = _clean_text(line.text, lang)
        if text:
            lines.append({
                "text": text,
                "box": tuple(max(0, int(round(v / scale))) for v in (x0, y0, x1, y1)),
            })
    return lines


if __name__ == "__main__":
    # Test: python ocr_windows.py page.png ja
    import asyncio
    import sys
    image = Image.open(sys.argv[1])
    for lg in sys.argv[2:] or list(LANG_TAGS):
        print(f"===== {lg} =====")
        try:
            for item in asyncio.run(recognize_lines(image, lg)):
                print(item["box"], item["text"])
        except OcrLanguageMissing as e:
            print("ERROR:", e)
