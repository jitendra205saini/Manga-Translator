# PaddleOCR (PP-OCRv3 detection + PP-OCRv5 recognition), ONNX: monkt/paddleocr-onnx (Apache-2.0).
# Korean / Chinese / English ke liye Windows OCR se behtar. Torch / paddle ke bina, seedha onnxruntime.
# Return format Windows OCR jaisa: [{"text": str, "box": (x0, y0, x1, y1)}]
import math
import os
import threading

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "models", "paddleocr")
LANG_DIR = {"ko": "korean", "zh_hans": "chinese", "zh_hant": "chinese"}  # English: Windows OCR behtar nikla
DET_LIMIT = 1280          # lambi side isse badi ho to chhota karke dhundho
REC_H = 48

_det = None
_rec = {}
_dicts = {}
from gpu_lock import LOCK as _lock  # sab GPU models ka ek hi lock
_cpu_only = False


def _path(*p):
    return os.path.join(DIR, *p)


def available(lang):
    d = LANG_DIR.get(lang)
    return bool(d) and all(os.path.exists(p) for p in
                           (_path("detection", "v3", "det.onnx"), _path("languages", d, "rec.onnx"), _path("languages", d, "dict.txt")))


def _session(path):
    import onnxruntime as ort
    wanted = ("CPUExecutionProvider",) if _cpu_only else ("DmlExecutionProvider", "CPUExecutionProvider")
    prov = [p for p in wanted if p in ort.get_available_providers()]
    try:
        return ort.InferenceSession(path, providers=prov)
    except Exception:
        return ort.InferenceSession(path, providers=["CPUExecutionProvider"])


def _load(lang):
    global _det
    if _det is None:
        _det = _session(_path("detection", "v3", "det.onnx"))
        print("[paddle] det loaded on", _det.get_providers()[0])
    d = LANG_DIR[lang]
    if d not in _rec:
        # rec ki input width har line alag hai: DirectML har naye shape par dheema, isliye CPU (chhota model, tez)
        import onnxruntime as ort
        _rec[d] = ort.InferenceSession(_path("languages", d, "rec.onnx"), providers=["CPUExecutionProvider"])
        with open(_path("languages", d, "dict.txt"), encoding="utf-8") as f:
            _dicts[d] = ["<blank>"] + [l.rstrip("\r\n") for l in f] + [" "]
        print(f"[paddle] {d} rec loaded")
    return _rec[d], _dicts[d]


# ---------- detection (DBNet) ----------
def _detect(arr):
    h, w = arr.shape[:2]
    s = min(1.0, DET_LIMIT / max(h, w))
    nh, nw = max(32, int(round(h * s / 32)) * 32), max(32, int(round(w * s / 32)) * 32)
    x = cv2.resize(arr, (nw, nh)).astype(np.float32) / 255.0
    x = (x - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    prob = _det.run(None, {"x": x})[0][0, 0]
    mask = (prob > 0.3).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    sx, sy = w / nw, h / nh
    boxes = []
    for c in contours:
        if cv2.contourArea(c) < 12:
            continue
        x0, y0, bw, bh = cv2.boundingRect(c)
        if float(prob[y0:y0 + bh, x0:x0 + bw][mask[y0:y0 + bh, x0:x0 + bw] > 0].mean()) < 0.55:
            continue
        # DB ka "unclip" (ratio 1.6): sikuda hua area failao, warna akshar ke upar-neeche ke stroke kat jaate (찮 -> 잖)
        pad = cv2.contourArea(c) * 1.6 / max(1.0, cv2.arcLength(c, True))
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x0 + bw + pad, y0 + bh + pad
        boxes.append((max(0, int(x0 * sx)), max(0, int(y0 * sy)), min(w, int(math.ceil(x1 * sx))), min(h, int(math.ceil(y1 * sy)))))
    return boxes


# ---------- recognition (CTC) ----------
def _rec_batch(sess, chars, crops):
    out = []
    for i in range(0, len(crops), 16):
        part = crops[i:i + 16]
        ws = [max(16, int(math.ceil(REC_H * c.shape[1] / max(1, c.shape[0])))) for c in part]
        W = min(max(ws), 2400)
        x = np.zeros((len(part), 3, REC_H, W), np.float32)
        for k, (c, cw) in enumerate(zip(part, ws)):
            r = cv2.resize(c, (min(cw, W), REC_H)).astype(np.float32) / 255.0
            x[k, :, :, :r.shape[1]] = ((r - 0.5) / 0.5).transpose(2, 0, 1)
        pred = sess.run(None, {"x": x})[0]
        idx, conf = pred.argmax(2), pred.max(2)
        for row, cf in zip(idx, conf):
            txt, sc, prev = [], [], 0
            for j, (t, p) in enumerate(zip(row, cf)):
                if t != 0 and t != prev and t < len(chars):
                    txt.append(chars[t])
                    sc.append(p)
                prev = t
            out.append(("".join(txt).strip(), float(np.mean(sc)) if sc else 0.0))
    return out


def recognize(img, lang):
    """img: PIL RGB. Lines upar se neeche."""
    global _det, _cpu_only
    arr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)  # Paddle BGR par train hua
    with _lock:
        try:
            sess, chars = _load(lang)
            boxes = _detect(arr)
        except Exception as e:
            if _cpu_only:
                raise
            print("[paddle] GPU fail, CPU par:", e)
            _cpu_only, _det = True, None
            sess, chars = _load(lang)
            boxes = _detect(arr)
        # line ke charon taraf thodi jagah: tight crop mein Korean ke stroke kat jaate (무 -> 부, 줄 -> 출)
        H, W = arr.shape[:2]
        crops = []
        for x0, y0, x1, y1 in boxes:
            m = max(3, int(0.15 * (y1 - y0)))
            crops.append(arr[max(0, y0 - m):min(H, y1 + m), max(0, x0 - m):min(W, x1 + m)])
        res = _rec_batch(sess, chars, crops) if crops else []
    lines = [{"text": t, "box": b} for b, (t, sc) in zip(boxes, res) if t and sc >= 0.5]
    lines.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return lines
