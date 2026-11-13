# ML text/bubble detector: ogkalu/comic-text-and-bubble-detector (RT-DETR-v2, Apache-2.0, ONNX)
# Classes: 0 = bubble, 1 = text_bubble (text inside a bubble), 2 = text_free (text on artwork / SFX)
import os
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "comic-text-and-bubble-detector", "detector.onnx")
LABELS = {0: "bubble", 1: "text_bubble", 2: "text_free"}
SIZE = 640

_sess = None
_lock = threading.Lock()


def available():
    return os.path.exists(MODEL_PATH)


_cpu_only = False


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        wanted = ("CPUExecutionProvider",) if _cpu_only else ("DmlExecutionProvider", "CPUExecutionProvider")
        providers = [p for p in wanted if p in ort.get_available_providers()]
        try:
            _sess = ort.InferenceSession(MODEL_PATH, providers=providers)
        except Exception:
            _sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
        print("[detector] loaded on", _sess.get_providers()[0])
    return _sess


def _run(feed):
    """GPU (DirectML) sleep / driver update ke baad toot jaata hai ("GPU device instance has been suspended").
    Usi process mein GPU session dobara banana atak jaata hai, isliye seedha CPU. (Tray server restart kare to GPU wapas.)"""
    global _sess, _cpu_only
    try:
        return _session().run(None, feed)
    except Exception as e:
        if _cpu_only:
            raise
        print(f"[detector] GPU fail ({str(e)[:80]}), ab CPU par")
        _sess, _cpu_only = None, True
        return _session().run(None, feed)


def detect(img, threshold=0.3):
    """Return list of {"label", "box": (x0,y0,x1,y1), "score"} in original image pixels."""
    W, H = img.size
    x = np.asarray(img.convert("RGB").resize((SIZE, SIZE)), dtype=np.float32) / 255.0
    x = x.transpose(2, 0, 1)[None]
    feed = {"images": x, "orig_target_sizes": np.array([[W, H]], dtype=np.int64)}
    with _lock:
        labels, boxes, scores = _run(feed)
    out = []
    for lab, box, sc in zip(labels[0], boxes[0], scores[0]):
        if sc < threshold or int(lab) not in LABELS:
            continue
        x0, y0, x1, y1 = (float(v) for v in box)
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(W, int(x1)), min(H, int(y1))
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        out.append({"label": LABELS[int(lab)], "box": (x0, y0, x1, y1), "score": float(sc)})
    return out
