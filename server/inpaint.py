# LaMa inpainting: art ke upar likhe text ko mita kar background wapas banata hai.
# Pehli pasand: ogkalu/lama-manga-onnx-dynamic (manga / anime par fine-tune, kisi bhi size par, Apache-2.0).
# Purane install: Carve/LaMa-ONNX (512x512 fixed). DirectML par nahi chalta, isliye CPU.
import os
import threading

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MANGA_PATH = os.path.join(HERE, "models", "lama-manga", "lama-manga-dynamic.onnx")
OLD_PATH = os.path.join(HERE, "models", "LaMa-ONNX", "lama_fp32.onnx")
MODEL_PATH = MANGA_PATH if os.path.exists(MANGA_PATH) else OLD_PATH
MANGA = MODEL_PATH == MANGA_PATH
SIZE = 512       # purana model: hamesha 512x512
MAX_SIDE = 768   # manga model: isse bada crop chhota karke (speed)

_sess = None
from gpu_lock import LOCK as _lock  # sab GPU models ka ek hi lock


def available():
    return os.path.exists(MODEL_PATH)


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        import detector
        # GPU par ~5 guna tez (768 crop: ~0.3 s vs 1.5 s); GPU toota ho to CPU
        prov = ["CPUExecutionProvider"] if (_on_cpu or detector._cpu_only) else ["DmlExecutionProvider", "CPUExecutionProvider"]
        prov = [p for p in prov if p in ort.get_available_providers()]
        try:
            _sess = ort.InferenceSession(MODEL_PATH, providers=prov)
        except Exception as e:
            print("[inpaint] GPU load fail, CPU:", e)
            _sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
        print(f"[inpaint] LaMa loaded ({_sess.get_providers()[0]}, {'manga' if MANGA else 'generic'})")
    return _sess


_on_cpu = False


def _run(feed):
    """GPU par chalao; GPU error aaye to ek baar CPU session bana ke dobara."""
    global _sess, _on_cpu
    with _lock:
        try:
            return _session().run(None, feed)
        except Exception as e:
            if _on_cpu:
                raise
            print("[inpaint] GPU run fail, ab CPU:", e)
            _on_cpu, _sess = True, None
            return _session().run(None, feed)


def inpaint_region(arr, mask, box):
    """arr: HxWx3 uint8 (in-place badla jaata hai), mask: HxW uint8 (1 = mitana), box: jis text ke liye."""
    H, W = mask.shape
    x0, y0, x1, y1 = box
    side = int(max(x1 - x0, y1 - y0) * 1.6) + 32
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    cx0, cy0 = max(0, cx - side // 2), max(0, cy - side // 2)
    cx1, cy1 = min(W, cx0 + side), min(H, cy0 + side)
    crop = arr[cy0:cy1, cx0:cx1]
    m = mask[cy0:cy1, cx0:cx1]
    if crop.size == 0 or m.sum() == 0:
        return
    if not available():
        arr[cy0:cy1, cx0:cx1] = cv2.inpaint(crop, m * 255, 3, cv2.INPAINT_NS)
        return
    h, w = m.shape
    if MANGA:
        out = _run_manga(crop, m)
    else:
        x = np.asarray(Image.fromarray(crop).resize((SIZE, SIZE), Image.BICUBIC), dtype=np.float32) / 255.0
        mm = (cv2.resize(m, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
        out = _run({"image": x.transpose(2, 0, 1)[None], "mask": mm[None, None]})[0][0]
        out = np.clip(out.transpose(1, 2, 0), 0, 255).astype(np.uint8)
        out = np.asarray(Image.fromarray(out).resize((w, h), Image.BICUBIC))
    sel = m.astype(bool)
    crop[sel] = out[sel]


def _run_manga(crop, m):
    """Manga LaMa: asli size par (bada ho to MAX_SIDE tak chhota), 8 ke multiple tak pad. Output 0..1."""
    h, w = m.shape
    s = min(1.0, MAX_SIDE / max(h, w))
    if s < 1:
        sw, sh = max(8, round(w * s)), max(8, round(h * s))
        img = cv2.resize(crop, (sw, sh), interpolation=cv2.INTER_AREA)
        mk = cv2.resize(m, (sw, sh), interpolation=cv2.INTER_NEAREST)
    else:
        img, mk = crop, m
    ih, iw = mk.shape
    ph, pw = (8 - ih % 8) % 8, (8 - iw % 8) % 8
    x = np.pad(img, ((0, ph), (0, pw), (0, 0)), mode="reflect").astype(np.float32) / 255.0
    mm = (np.pad(mk, ((0, ph), (0, pw)), mode="reflect") > 0).astype(np.float32)
    out = _run({"image": x.transpose(2, 0, 1)[None], "mask": mm[None, None]})[0][0]
    out = np.clip(out.transpose(1, 2, 0) * 255, 0, 255).astype(np.uint8)[:ih, :iw]
    if s < 1:
        out = cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC)
    return out


def _components(binary, margin=1, min_area=10):
    """Crop ke kinare ko na chhoone wale tukde (letters); kinare tak jaati lambi art lines nahi."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return np.zeros_like(binary)
    h, w = binary.shape
    x, y, cw, ch, a = st[1:, 0], st[1:, 1], st[1:, 2], st[1:, 3], st[1:, 4]
    keep = ((a > min_area) | ((a >= 4) & (cw <= 6) & (ch <= 6))) & (x >= margin) & (y >= margin)         & (x + cw <= w - margin) & (y + ch <= h - margin)
    if h * w > 150:
        keep &= a < 0.5 * h * w  # rangeen narration box ka background nahi
    return np.isin(lab, np.flatnonzero(keep) + 1).astype(np.uint8)


def content_mask(arr, box, grow=2):
    """Art par text (comic-translate ka tarika, Apache-2.0): Otsu se kaale aur safed dono letters,
    sirf box ke andar band tukde. Box thoda bada hona chahiye taaki letters kinare na chhooen."""
    x0, y0, x1, y1 = box
    region = arr[y0:y1, x0:x1]
    if region.size == 0 or min(region.shape[:2]) < 6:
        return None
    g = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    t, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = _components((g < t).astype(np.uint8)) | _components((g > t).astype(np.uint8))
    if not m.any():
        return None
    return cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=grow)


def text_mask(arr, box, grow=4):
    """Box ke andar asli text pixels (background se alag rang) + thoda phailao."""
    x0, y0, x1, y1 = box
    region = arr[y0:y1, x0:x1]
    if region.size == 0:
        return None
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    border = np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])
    bgv = np.median(border)
    diff = np.abs(gray.astype(np.int16) - int(bgv))
    m = (diff > 60).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=grow)
    return m


def letter_mask(arr, box, grow=3):
    """Art ke upar bade stylish letters: sirf letter jaise (chhote, alag) kaale/safed tukde, lambi art lines nahi."""
    x0, y0, x1, y1 = box
    region = arr[y0:y1, x0:x1]
    if region.size == 0:
        return None
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    out = np.zeros_like(gray, dtype=np.uint8)
    for m in ((gray < 90).astype(np.uint8), (gray > 200).astype(np.uint8)):
        n, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for i in range(1, n):
            cx, cy, cw, ch, area = stats[i]
            short = min(w, h)
            if ch < 0.45 * h and cw < 0.45 * w and max(cw, ch) < 0.6 * short + 40 and area > 15                     and area > 0.2 * cw * ch:
                out[labels == i] = 1
    out = cv2.dilate(out, np.ones((3, 3), np.uint8), iterations=grow)
    return out
