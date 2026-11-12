# LaMa inpainting (Carve/LaMa-ONNX, Apache-2.0): art ke upar likhe text ko mita kar background wapas banata hai.
# DirectML par ye model nahi chalta, isliye CPU (~2s per 512px crop).
import os
import threading

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "LaMa-ONNX", "lama_fp32.onnx")
SIZE = 512

_sess = None
_lock = threading.Lock()


def available():
    return os.path.exists(MODEL_PATH)


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        _sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
        print("[inpaint] LaMa loaded (CPU)")
    return _sess


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
    x = np.asarray(Image.fromarray(crop).resize((SIZE, SIZE), Image.BICUBIC), dtype=np.float32) / 255.0
    mm = (cv2.resize(m, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
    with _lock:
        out = _session().run(None, {"image": x.transpose(2, 0, 1)[None], "mask": mm[None, None]})[0][0]
    out = np.clip(out.transpose(1, 2, 0), 0, 255).astype(np.uint8)
    out = np.asarray(Image.fromarray(out).resize((w, h), Image.BICUBIC))
    sel = m.astype(bool)
    crop[sel] = out[sel]


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
