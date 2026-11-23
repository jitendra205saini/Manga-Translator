"""Backup translator (IndicTrans2 web API): sirf English -> Hindi, text hi bhejta hai (image nahi).
Popup ka switch on ho aur saari AI limit khatam ho tabhi use hota hai. Formal Hindi, gender ka dhyan nahi."""
from concurrent.futures import ThreadPoolExecutor

import requests

DEFAULT_URL = "https://translate-api.abym.us/translate"
LANGS = {"en"}


import re

# OCR ki aam galtiyan (stylized font): AI image dekh ke sudhaar leta, backup nahi
_FIX = [(r"\bRt(?='s\b)", "It"), (r"\bPon't\b", "Don't"), (r"\bWaa t\b", "Wait"),
        (r"\btais\b", "this"), (r"\bI'rn\b", "I'm"), (r"\brn\b", "m")]


def clean(text):
    """Backup ko bhejne se pehle OCR text saaf karo. "" = kachra (bina matlab ke akshar), mat bhejo."""
    t = " ".join(text.split())
    t = re.sub(r"\.{2,}|…", "... ", t)  # "But...the" -> "But... the" (warna jud ke "But.the" aata)
    for a, b in _FIX:
        t = re.sub(a, b, t)
    t = re.sub(r"[^\w\s.,!?'\"()\-:;~]", "", t).strip()
    words = re.findall(r"[A-Za-z']+", t)
    real = [w for w in words if len(w.strip("'")) >= 2 and re.search(r"[aeiouyAEIOUY]", w)]
    letters = sum(len(w) for w in real)
    if letters < 3 or len(real) < 0.6 * max(1, len(words)):
        return ""
    # shuru mein akela atka akshar ("W what") hata do
    t = re.sub(r"^([A-Za-z])\s+(?=\1)", "", t, flags=re.I)
    return t


def _one(text, key, url):
    text = clean(text)
    if not text.strip():
        return ""
    r = requests.post(url, json={"text": text, "source_lang": "en", "target_lang": ["hi"]},
                      headers={"X-API-Key": key}, timeout=60)
    r.raise_for_status()
    return r.json()["results"][0]["translation"]


def translate(texts, cfg):
    """texts: har bubble ka text. Ek request mein ek hi bubble (kai lines jod deta hai), isliye saath-saath."""
    key = cfg.get("api_key", "")
    url = cfg.get("url") or DEFAULT_URL
    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(lambda t: _one(t, key, url), texts))
