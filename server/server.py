# FastAPI server: POST /translate  {image: base64 | src: url, lang, page_url, fast}
import dllfix  # noqa: F401  (PIL se pehle)
import asyncio
import base64
import json
import os
import re
import traceback
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import detector
import llm
import mangaocr
import translator


@asynccontextmanager
async def lifespan(app):
    # NLLB sirf backup hai: startup par load nahi, zaroorat padne par hoga
    # detector + LaMa pehle se load: pehla page intezaar na kare
    def warm():
        import inpaint
        try:
            # sirf load nahi, ek dummy run bhi: GPU/CPU ka pehla run dheema hota hai (~15s), page ka nahi
            import numpy as np
            from PIL import Image
            if detector.available():
                detector.detect(Image.new("RGB", (800, 1100), "white"))
            if mangaocr.available():
                mangaocr.read([Image.new("RGB", (60, 200), "white")])
            if inpaint.available():
                arr = np.full((200, 200, 3), 255, np.uint8)
                m = np.zeros((200, 200), np.uint8)
                m[80:120, 80:120] = 1
                inpaint.inpaint_region(arr, m, (80, 80, 120, 120))
        except Exception as e:
            print("[server] warm-up fail:", e)
    await asyncio.to_thread(warm)
    print("[server] ready on http://127.0.0.1:47391")
    yield


app = FastAPI(lifespan=lifespan)
# sirf apna browser extension aur apna /setup page: koi website tumhara AI quota use na kar sake
ALLOWED_ORIGIN = r"^(moz-extension|chrome-extension)://[^/]+$|^http://(127\.0\.0\.1|localhost):47391$"
app.add_middleware(CORSMiddleware, allow_origin_regex=ALLOWED_ORIGIN, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def block_websites(request, call_next):
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and not re.match(ALLOWED_ORIGIN, origin):
        return JSONResponse({"error": "only the Manga Translator extension can use this server"}, status_code=403)
    return await call_next(request)


class TranslateRequest(BaseModel):
    image: str = ""
    src: str = ""        # image URL: server khud download karega (hotlink protection ke liye page ka Referer)
    lang: str = "Auto"
    page_url: str = ""
    fast: bool = False   # Fast mode: Groq pehle
    url: str = ""        # page ki asli image URL: agla chapter pehle se translate ho to seedha cache se
    fresh: bool = False  # "dobara translate karo": cache mat dekho
    prev_images: list[str] = []  # upar wale tukde, paas wala pehle (webtoon ke kate bubble poore dikhane ke liye)
    next_images: list[str] = []  # neeche wale tukde


def download_image(url, referer):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
        raise RuntimeError(f"image download fail: HTTP {r.status_code} {url}")
    return r.content


@app.get("/health")
async def health():
    gpu_lost = detector._cpu_only or mangaocr._cpu_only  # GPU toota, CPU par chal raha: tray restart karega
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.txt"), encoding="utf-8") as f:
            ver = f.read().strip()
    except Exception:
        ver = ""
    return {"ok": True, "version": ver, "gpu_lost": gpu_lost, "providers": llm.provider_status(), "usage": llm.usage_today()}


HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ORIGINS = {"http://127.0.0.1:47391", "http://localhost:47391"}


def _mask(k):
    keys = [x for x in k.replace(",", " ").split() if x]
    if not keys:
        return ""
    m = keys[0][:4] + "..." + keys[0][-4:]
    return m + (f" (+{len(keys) - 1} more)" if len(keys) > 1 else "")


@app.get("/setup")
async def setup_page():
    return FileResponse(os.path.join(HERE, "setup.html"))


@app.get("/icon.png")
async def icon():
    return FileResponse(os.path.join(HERE, "..", "extension", "icons", "icon128.png"))


@app.get("/config")
async def get_config():
    cfg = llm.load_config()
    return {p: _mask(cfg.get(p, {}).get("api_key", "")) for p in ("gemini", "groq")}


@app.post("/config")
async def set_config(request: Request):
    # sirf apne /setup page se: koi aur website keys na badal sake
    if request.headers.get("origin") not in SETUP_ORIGINS:
        raise HTTPException(403, "keys can only be changed from http://127.0.0.1:47391/setup")
    body = await request.json()
    path = llm.CONFIG_PATH
    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    for p in ("gemini", "groq"):
        key = str(body.get(p) or "").strip()
        if key:
            cfg.setdefault(p, {})["api_key"] = key
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    full = llm.load_config()
    return {"ready": bool(full["gemini"]["api_key"] or full["groq"]["api_key"])}


@app.post("/translate")
async def translate(req: TranslateRequest):
    try:
        if req.url and not req.fresh:
            hit = translator.url_cached(req.url, req.lang)
            if hit:
                return hit
        if req.image:
            raw = base64.b64decode(req.image.split(",", 1)[-1])
        elif req.src.startswith(("http://", "https://")):
            raw = await asyncio.to_thread(download_image, req.src, req.page_url)
        else:
            return {"error": "image ya src nahi mila"}
        nb = lambda xs: [base64.b64decode(x.split(",", 1)[-1]) for x in xs] or None
        return await translator.translate_page(raw, req.lang, req.page_url, req.fast, req.url, req.fresh,
                                               nb(req.prev_images), nb(req.next_images))
    except Exception as e:
        traceback.print_exc()
        wait = llm.limit_wait()
        if wait:
            return {"error": "AI ki free limit khatam", "retry_after": wait}
        return {"error": str(e)}
