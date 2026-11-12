# AI translator (Gemini / Groq): casual Hindi, speaker ke gender ke hisaab se.
# Har page = 1 request. Limit khatam ho to agla provider, sab fail to NLLB.
import base64
import io
import json
import os
import re
import threading
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
MEMORY_PATH = os.path.join(HERE, "memory.json")

DEFAULT_CONFIG = {
    "providers": ["gemini", "groq", "nllb"],
    "gemini": {"api_key": "", "model": ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]},
    "groq": {"api_key": "", "model": "openai/gpt-oss-120b", "vision": False},
    "image_max_side": 1024,
}

LANG_NAMES = {"ja": "Japanese", "ko": "Korean", "zh_hans": "Chinese",
              "zh_hant": "Chinese", "en": "English"}


class RateLimited(RuntimeError):
    pass


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    cfg["gemini"]["api_key"] = cfg["gemini"]["api_key"] or os.environ.get("GEMINI_API_KEY", "")
    cfg["groq"]["api_key"] = cfg["groq"]["api_key"] or os.environ.get("GROQ_API_KEY", "")
    return cfg


# ---------- series memory: characters ka gender + pichli lines ----------
_mem_lock = threading.Lock()
try:
    with open(MEMORY_PATH, encoding="utf-8") as f:
        _memory = json.load(f)
except Exception:
    _memory = {}


def series_key(page_url):
    # site + pehle 2 path parts (aam taur par series ka naam), chapter number hatao
    m = re.match(r"https?://([^/]+)(/[^?#]*)?", page_url or "")
    if not m:
        return "unknown"
    parts = [p for p in (m.group(2) or "").split("/") if p and not re.search(r"\d", p)]
    return m.group(1) + "/" + "/".join(parts[:2])


def get_memory(key):
    with _mem_lock:
        return json.loads(json.dumps(_memory.get(key, {"characters": {}, "recent": []})))


def update_memory(key, characters, recent_pairs):
    with _mem_lock:
        m = _memory.setdefault(key, {"characters": {}, "recent": []})
        for name, g in (characters or {}).items():
            if g in ("m", "f") and name:
                m["characters"][name] = g
        m["characters"] = dict(list(m["characters"].items())[-40:])
        m["recent"] = (m["recent"] + recent_pairs)[-8:]
        try:
            with open(MEMORY_PATH, "w", encoding="utf-8") as f:
                json.dump(_memory, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[memory] save fail:", e)


# ---------- prompt ----------
def build_prompt(groups, lang, img_size, memory, with_image):
    W, H = img_size
    bubbles = []
    for i, g in enumerate(groups, 1):
        x0, y0, x1, y1 = g["box"]
        box = [round(x0 * 1000 / W), round(y0 * 1000 / H), round(x1 * 1000 / W), round(y1 * 1000 / H)]
        bubbles.append({"id": i, "box": box, "text": g["text"] or "(OCR could not read this bubble: read it from the image)"})

    chars = ", ".join(f"{n} ({'female' if g == 'f' else 'male'})"
                      for n, g in memory["characters"].items()) or "none yet"
    recent = "\n".join(f"- {s} => {h}" for s, h in memory["recent"]) or "none"

    look = ("The manga page image is attached. Each bubble is marked with a RED BOX and a RED NUMBER = its id. "
            "OCR is often incomplete or garbled (missing lines, wrong letters): for each id, READ THE REAL FULL TEXT "
            "inside that red box in the image and translate that, not the OCR. If a red box has no text, return \"\" for it. "
            "Also look at who is speaking each bubble (bubble tail, character face, clothes) to decide the speaker's gender."
            if with_image else
            "No image is given; infer the speaker's gender from speech style "
            "(e.g. Japanese あたし/わ/のよ/かしら = female, 俺/僕/ぜ/だぞ = male), names and context.")

    with_extra = False
    extra_rule = ("- OCR misses some bubbles. Look at the image: for every speech bubble / narration box / important text that is NOT "
                  "covered by the boxes above, add it to \"extra\" with box_2d = [ymin, xmin, ymax, xmax] normalized 0-1000 covering the whole text. "
                  "Ignore watermarks, site names and page numbers. Use [] if nothing is missing."
                  if with_extra else "- Set \"extra\" to [].")
    return f"""You translate {LANG_NAMES.get(lang, lang)} manga/manhwa/comic dialogue into natural, casual spoken Hindi.

Text bubbles on this page (OCR output, may contain small OCR mistakes; box = [x0,y0,x1,y1] on a 0-1000 scale):
{json.dumps(bubbles, ensure_ascii=False)}

{look}

Known characters in this series: {chars}
Previous lines (for context):
{recent}

Rules:
- Write Hindi in Devanagari, the way young people actually talk in everyday life / Hindi anime dubs. NOT shuddh/bookish Hindi.
  Use common words people really say, including common English-origin words (जैसे: टाइम, प्लान, सॉरी, ओके, फ्रेंड, स्कूल) where natural.
  Bad: "मैं इस कार्य को संपन्न करने की इच्छा रखता हूँ"  Good: "मैं ये काम करना चाहता हूँ"
- Verb and adjective gender MUST match the speaker: female speaker -> "मैं जा रही हूँ", "मैं थक गई"; male -> "मैं जा रहा हूँ", "मैं थक गया".
  Also match the gender of the person being addressed when Hindi needs it ("तू आ गई?" to a girl).
- Choose तू / तुम / आप by relationship (friends/rivals: तू or तुम, elders/strangers/boss: आप).
- Keep names as they are, written in Devanagari. Keep honorifics like -san/-kun/-chan only if natural, otherwise drop them.
- Write numbers with normal digits 0-9 (not १२३).
- Each id is a separate bubble: translate exactly that bubble's text. Never move words or half-sentences between bubbles.
- Keep it short so it fits in the bubble. Keep the emotion, jokes and tone (angry, shy, sarcastic).
- Never use English/Latin letters in "hi" (write English words in Devanagari: "ओके", "थैंक्स").
- Website names, watermarks, scan-group credits, page numbers: return "" for them.
- Fix obvious OCR mistakes using context. If a bubble/box has no real text (just art, noise, watermark), return "" for it.
- Sound effects (SFX): give a short Hindi equivalent (e.g. "धड़ाम!", "हम्म...") or "" if meaningless.

{extra_rule}
Return ONLY JSON:
{{"lines": [{{"id": 1, "gender": "m|f|u", "speaker": "name or empty", "hi": "Hindi text"}}],
  "extra": [{{"box_2d": [ymin, xmin, ymax, xmax], "text": "original", "hi": "Hindi"}}],
  "characters": {{"Name": "m|f"}}}}
Include every id exactly once."""


def mark_bubbles(img, groups):
    """AI ke liye har bubble par laal box + id number (kaunsa text kis bubble ka, ye pakka ho)."""
    from PIL import ImageDraw, ImageFont
    im = img.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    size = max(18, img.size[0] // 30)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fontsrialbd.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    for i, g in enumerate(groups, 1):
        x0, y0, x1, y1 = g["bubble"][3] if "bubble" in g else g["box"]
        d.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=max(2, size // 8))
        tx, ty = x0 + 2, max(0, y0 - size // 3)
        d.rectangle([tx, ty, tx + size * (0.7 * len(str(i)) + 0.3), ty + size * 1.1], fill=(255, 0, 0))
        d.text((tx + size * 0.15, ty), str(i), font=font, fill=(255, 255, 255))
    return im


def clean_hi(text):
    # Hindi font mein English akshar nahi (dabbe bante hain): website/watermark jaise Latin hatao
    text = str(text or "")
    text = re.sub(r"\S*\.(com|net|org|io|co)\S*", "", text, flags=re.I)
    text = re.sub(r"[A-Za-z]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if re.search(r"[ऀ-ॿ]", text) else ""


def _jpeg_b64(img, max_side):
    im = img.copy()
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


# ---------- providers ----------
def _check(r, name):
    if r.status_code == 429:
        raise RateLimited(f"{name}: limit khatam (429)")
    if r.status_code >= 400:
        raise RuntimeError(f"{name}: HTTP {r.status_code} {r.text[:300]}")


def call_gemini(cfg, prompt, img_b64):
    c = cfg["gemini"]
    parts = [{"text": prompt}]
    if img_b64:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": img_b64}})
    models = c["model"] if isinstance(c["model"], list) else [c["model"]]
    last = None
    for model in models:
        for attempt in range(2):
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": c["api_key"], "Content-Type": "application/json"},
                json={"contents": [{"role": "user", "parts": parts}],
                      "generationConfig": {"temperature": 0.5, "responseMimeType": "application/json"}},
                timeout=90,
            )
            if r.status_code in (500, 503):  # bheed: thoda ruko, phir agla model
                last = f"{model}: HTTP {r.status_code}"
                time.sleep(2)
                continue
            break
        else:
            continue
        if r.status_code == 404:
            last = f"{model}: model nahi mila"
            continue
        if r.status_code == 429:
            last = f"{model}: limit"
            continue  # har model ki limit alag hoti hai
        _check(r, "gemini " + model)
        data = r.json()
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            last = f"{model}: khaali jawab {str(data)[:200]}"
    if last and last.endswith("limit"):
        raise RateLimited("gemini: sab models ki limit khatam")
    raise RuntimeError(f"gemini: {last}")


def call_groq(cfg, prompt, img_b64):
    c = cfg["groq"]
    if img_b64:
        content = [{"type": "text", "text": prompt},
                   {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64}}]
    else:
        content = prompt
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": "Bearer " + c["api_key"]},
        json={"model": c["model"], "temperature": 0.5,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "user", "content": content}]},
        timeout=90,
    )
    _check(r, "groq")
    return r.json()["choices"][0]["message"]["content"]


PROVIDERS = {"gemini": call_gemini, "groq": call_groq}
_cooldown = {}   # provider -> time.time() tak band
_strikes = {}    # lagatar 429 ki ginti


def _overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
    return ix * iy / small


def provider_status():
    cfg = load_config()
    out = {}
    for p in cfg["providers"]:
        if p == "nllb":
            out[p] = "ready"
        elif not cfg.get(p, {}).get("api_key"):
            out[p] = "no key"
        elif _cooldown.get(p, 0) > time.time():
            out[p] = f"limit, {int(_cooldown[p] - time.time())}s baad"
        else:
            out[p] = "ready"
    return out


def translate_with_llm(img, groups, lang, page_url=""):
    """Return (hindi_list, provider_name) ya None agar koi AI provider kaam na kare."""
    cfg = load_config()
    key = series_key(page_url)
    memory = get_memory(key)

    for name in cfg["providers"]:
        if name not in PROVIDERS:
            continue
        pc = cfg.get(name, {})
        if not pc.get("api_key") or _cooldown.get(name, 0) > time.time():
            continue
        with_image = name == "gemini" or pc.get("vision", False)
        prompt = build_prompt(groups, lang, img.size, memory, with_image)
        img_b64 = _jpeg_b64(mark_bubbles(img, groups), cfg["image_max_side"]) if with_image else None
        try:
            t = time.time()
            raw = PROVIDERS[name](cfg, prompt, img_b64)
            data = _parse_json(raw)
            by_id = {int(l["id"]): l for l in data.get("lines", []) if "id" in l}
            hindi = [clean_hi(by_id.get(i, {}).get("hi", "")) for i in range(1, len(groups) + 1)]
            if not any(hindi):
                raise RuntimeError("koi translation nahi aayi")
            _strikes[name] = 0
            pairs = [[g["text"], h] for g, h in zip(groups, hindi) if h][-8:]
            update_memory(key, data.get("characters"), pairs)
            genders = "".join(str(by_id.get(i, {}).get("gender", "u"))[:1] for i in range(1, len(groups) + 1))
            print(f"[{name}] {len(groups)} bubbles, gender={genders}, {time.time() - t:.1f}s")
            extras = []  # ab bubbles hum khud dhoondhte hain; AI ke andaaze wale box galat jagah aate the
            # jo extra OCR boxes ke upar hi hai, wo duplicate: hatao
            extras = [e for e in extras if not any(_overlap(e["box"], g["box"]) > 0.4 for g in groups)]
            if extras:
                print(f"[{name}] +{len(extras)} bubbles jo OCR se chhoot gaye the")
            return hindi, name, extras
        except RateLimited as e:
            _strikes[name] = _strikes.get(name, 0) + 1
            wait = 60 if _strikes[name] < 3 else 3600  # baar baar 429 = roz ki limit khatam
            _cooldown[name] = time.time() + wait
            print(f"[{name}] {e}, {wait}s ke liye skip")
        except Exception as e:
            print(f"[{name}] fail: {e}")
    return None


def boxes_from_llm(lines, W, H):
    out = []
    for l in lines or []:
        b, hi = l.get("box_2d"), str(l.get("hi") or "").strip()
        hi = re.sub(r"[A-Za-z]+", "", hi).strip()
        if not hi or not isinstance(b, list) or len(b) != 4:
            continue
        try:
            y0, x0, y1, x1 = (int(max(0, min(1000, float(v))) * s / 1000) for v, s in zip(b, (H, W, H, W)))
        except (TypeError, ValueError):
            continue
        if x1 - x0 < 5 or y1 - y0 < 5:
            continue
        # Gemini ke box aksar thode chhote: kinare tak mitane ke liye badhao
        px, py = int((x1 - x0) * 0.12) + 6, int((y1 - y0) * 0.06) + 6
        x0, y0, x1, y1 = max(0, x0 - px), max(0, y0 - py), min(W, x1 + px), min(H, y1 + py)
        out.append({"box": (x0, y0, x1, y1), "text": str(l.get("text", "")), "hi": hi})
    return out


# ---------- OCR ko kuch nahi mila: Gemini khud text dhoondhe (stylized / khada text, SFX) ----------
def detect_with_llm(img, page_url=""):
    """Return list of {"box": (x0,y0,x1,y1) pixels, "hi": str} ya None."""
    cfg = load_config()
    if not cfg["gemini"].get("api_key") or _cooldown.get("gemini", 0) > time.time():
        return None
    memory = get_memory(series_key(page_url))
    chars = ", ".join(f"{n} ({'female' if g == 'f' else 'male'})" for n, g in memory["characters"].items()) or "none yet"
    prompt = f"""This is a manga/comic page. Normal OCR found no text, but there may be stylized text
(big shouted lines, stacked vertical letters, narration, sound effects).
Find every piece of readable text (ignore watermarks / site names / page numbers) and translate it into
natural, casual spoken Hindi (Devanagari), like young people talk / Hindi anime dubs, not bookish Hindi.
Match the speaker's gender in verbs (female: "रही हूँ", male: "रहा हूँ"). Known characters: {chars}.
Keep names as they are in Devanagari, numbers as 0-9, keep it short and keep the emotion.
Use ONLY Devanagari letters in "hi" (no Latin letters); for shouting just use "!!!" (do not repeat matras).
For each text block give "box_2d": [ymin, xmin, ymax, xmax] normalized to 0-1000, covering the whole block.
Return ONLY JSON: {{"lines": [{{"box_2d": [ymin, xmin, ymax, xmax], "text": "original", "hi": "Hindi"}}]}}  (empty list if no text)."""
    data = None
    for attempt in range(2):  # JSON toota aaye to ek baar aur
        try:
            raw = call_gemini(cfg, prompt, _jpeg_b64(img, cfg["image_max_side"]))
            data = _parse_json(raw)
            break
        except Exception as e:
            print(f"[gemini detect] fail ({attempt + 1}):", e)
    if data is None:
        return None
    out = boxes_from_llm(data.get("lines", []), *img.size)
    print(f"[gemini detect] {len(out)} text blocks mile")
    return out
