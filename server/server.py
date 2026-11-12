# FastAPI server: POST /translate  {image: base64, lang: "Auto"}
import dllfix  # noqa: F401  (PIL se pehle)
import asyncio
import base64
import traceback

import requests
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import llm
import nllb
import translator


@asynccontextmanager
async def lifespan(app):
    # NLLB sirf backup hai: startup par load nahi, zaroorat padne par hoga
    # detector + LaMa pehle se load: pehla page intezaar na kare
    def warm():
        import detector, inpaint
        try:
            if detector.available():
                detector._session()
            if inpaint.available():
                inpaint._session()
        except Exception as e:
            print("[server] warm-up fail:", e)
    await asyncio.to_thread(warm)
    print("[server] ready on http://127.0.0.1:7860")
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TranslateRequest(BaseModel):
    image: str = ""
    src: str = ""        # image URL: server khud download karega (hotlink protection ke liye page ka Referer)
    lang: str = "Auto"
    page_url: str = ""


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
    return {"ok": True, "device": nllb.DEVICE, "providers": llm.provider_status()}


@app.post("/translate")
async def translate(req: TranslateRequest):
    try:
        if req.image:
            raw = base64.b64decode(req.image.split(",", 1)[-1])
        elif req.src.startswith(("http://", "https://")):
            raw = await asyncio.to_thread(download_image, req.src, req.page_url)
        else:
            return {"error": "image ya src nahi mila"}
        return await translator.translate_page(raw, req.lang, req.page_url)
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}
