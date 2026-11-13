# manga-ocr (Japanese manga OCR, Apache-2.0) ka ONNX version: l0wgear/manga-ocr-2025-onnx.
# Torch / transformers ke bina, seedha onnxruntime. Khada (vertical) text, furigana, stylish font sab padhta hai.
import os
import re
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "models", "manga-ocr")
START, EOS, MAX_LEN = 2, 3, 120

_enc = _dec = _vocab = None
_lock = threading.Lock()


def available():
    return all(os.path.exists(os.path.join(DIR, f)) for f in ("encoder_model.onnx", "decoder_model.onnx", "vocab.txt"))


_cpu_only = False


def _load():
    global _enc, _dec, _vocab
    if _enc is None:
        import onnxruntime as ort
        wanted = ("CPUExecutionProvider",) if _cpu_only else ("DmlExecutionProvider", "CPUExecutionProvider")
        prov = [p for p in wanted if p in ort.get_available_providers()]
        try:
            _enc = ort.InferenceSession(os.path.join(DIR, "encoder_model.onnx"), providers=prov)
            _dec = ort.InferenceSession(os.path.join(DIR, "decoder_model.onnx"), providers=prov)
        except Exception:
            _enc = ort.InferenceSession(os.path.join(DIR, "encoder_model.onnx"), providers=["CPUExecutionProvider"])
            _dec = ort.InferenceSession(os.path.join(DIR, "decoder_model.onnx"), providers=["CPUExecutionProvider"])
        with open(os.path.join(DIR, "vocab.txt"), encoding="utf-8") as f:
            _vocab = [l.rstrip("\n") for l in f]
        print("[manga-ocr] loaded on", _enc.get_providers()[0])


def _prep(img):
    # manga-ocr: grayscale -> RGB, 224x224, (x/255 - 0.5) / 0.5
    from PIL import Image
    im = img.convert("L").convert("RGB").resize((224, 224), Image.BILINEAR)
    x = np.asarray(im, dtype=np.float32) / 255.0
    return ((x - 0.5) / 0.5).transpose(2, 0, 1)


def _clean(text):
    text = "".join(text.split())
    text = re.sub(r"[・.]{2,}|…+", "…", text)
    # aadhi-chaudi ASCII ko poori chaudai mein (manga-ocr jaisa)
    return text.translate({i: i + 0xFEE0 for i in range(0x21, 0x7F) if chr(i) not in ".!?"})


def read(crops, batch=8):
    """crops: list of PIL images (ek bubble ka text har ek). Return list of str.
    GPU sleep / driver update se toot jaye to CPU par (detector jaisa)."""
    global _enc, _dec, _cpu_only
    try:
        return _read(crops, batch)
    except Exception as e:
        if _cpu_only:
            raise
        print(f"[manga-ocr] GPU fail ({str(e)[:80]}), ab CPU par")
        _enc = _dec = None
        _cpu_only = True
        return _read(crops, batch)


def _read(crops, batch):
    if not crops:
        return []
    with _lock:
        _load()
        out = []
        for i in range(0, len(crops), batch):
            part = crops[i:i + batch]
            hs = _enc.run(None, {"pixel_values": np.stack([_prep(c) for c in part])})[0]
            ids = np.full((len(part), 1), START, dtype=np.int64)
            done = np.zeros(len(part), bool)
            for _ in range(MAX_LEN):
                logits = _dec.run(None, {"input_ids": ids, "encoder_hidden_states": hs})[0]
                nxt = logits[:, -1].argmax(-1)
                nxt[done] = 0
                ids = np.concatenate([ids, nxt[:, None]], axis=1)
                done |= nxt == EOS
                if done.all():
                    break
            for row in ids[:, 1:]:
                toks = []
                for t in row:
                    if t == EOS:
                        break
                    if t > 4:
                        toks.append(_vocab[t])
                out.append(_clean("".join(toks)))
        return out
