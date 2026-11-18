"""Backup translator (IndicTrans2 web API): sirf English -> Hindi, text hi bhejta hai (image nahi).
Popup ka switch on ho aur saari AI limit khatam ho tabhi use hota hai. Formal Hindi, gender ka dhyan nahi."""
from concurrent.futures import ThreadPoolExecutor

import requests

DEFAULT_URL = "https://translate-api.abym.us/translate"
LANGS = {"en"}


def _one(text, key, url):
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
