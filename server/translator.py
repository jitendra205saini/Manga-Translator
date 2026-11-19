# Pipeline: detect -> OCR -> group -> translate -> render
import asyncio
import base64
import hashlib
import os
import io
import json
import re
import statistics
import time
from collections import OrderedDict

from PIL import Image

import detector
import mangaocr
import paddle_ocr
import llm
from nllb import translate_texts
import backup_api
from ocr_windows import CJK_LANGS, OcrLanguageMissing, recognize_lines
from render import erase_ml, render_ml

KANA = re.compile(r"[\u3040-\u30ff]")
LATIN = re.compile(r"[A-Za-z]")
HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
HAN = re.compile(r"[\u4e00-\u9fff]")
VALID_LANGS = {"ja", "ko", "zh_hans", "zh_hant", "en"}

_cache = OrderedDict()
_series_lang = {}  # series -> pehchani hui language (Auto mode tez)
_series_vote = {}  # series -> [pichhle pages ki language]: 2 page ek jaise hon tab hi yaad rakho
_ocr_lock = asyncio.Lock()   # OCR/render ek time par ek; AI calls ek saath chal sakti hain
_nllb_lock = asyncio.Lock()  # GPU
MAX_CACHE = 20  # RAM mein (har page ~2-5 MB); baaki disk cache se


def _count(pattern, lines):
    return sum(len(pattern.findall(l["text"])) for l in lines)


async def _ocr(img, lang):
    try:
        return await recognize_lines(img, lang)
    except OcrLanguageMissing as e:
        # Windows mein Korean/Chinese pack nahi: PaddleOCR se pehchano
        if paddle_ocr.available(lang):
            return await asyncio.to_thread(paddle_ocr.recognize, img, lang)
        print("[warn]", e)
        return None


async def detect_and_ocr(img):
    # Quick check: pehle Japanese, phir Korean. Mil gaya to turant return.
    ja = await _ocr(img, "ja") or []
    kana, han, latin = _count(KANA, ja), _count(HAN, ja), _count(LATIN, ja)
    # English page par Japanese OCR bhi kuch kana bana deta hai: Latin zyada ho to Japanese nahi
    if kana >= 5 and kana >= 0.15 * (kana + han) and kana + han > latin:
        return "ja", ja

    if latin < 20:  # bahut saara Latin = English, Korean OCR ki zaroorat nahi
        ko = await _ocr(img, "ko") or []
        # credits / website header par Korean OCR 2-4 jhoothe akshar bana deta hai: pakka saboot chahiye
        if _count(HANGUL, ko) >= 8 and _count(HANGUL, ko) > _count(LATIN, ko):
            return "ko", ko

    if han >= 3 and han > latin:
        zh = await _ocr(img, "zh_hans")
        if zh:
            return "zh_hans", zh

    en = await _ocr(img, "en")
    if en is None:
        raise RuntimeError("Koi OCR language pack nahi mila. INSTALL_OCR_LANGUAGES.bat chalao.")
    return "en", en


def _thick(box):
    return min(box[2] - box[0], box[3] - box[1])


def _fix_english(text):
    text = re.sub(r"-\s+(?=[a-zA-Z])", "", text)
    if sum(c.isupper() for c in text) > sum(c.islower() for c in text):
        # ALL CAPS manga text -> normal case (NLLB isse better samajhta hai)
        text = text.lower()
        text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
        text = re.sub(r"\bi\b", "I", text)
    return text


def _center_in(box, outer, pad=6):
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return outer[0] - pad <= cx <= outer[2] + pad and outer[1] - pad <= cy <= outer[3] + pad


def _overlap_frac(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy / max(1, min(_area(a), _area(b)))


def _area(b):
    return max(1, (b[2] - b[0]) * (b[3] - b[1]))


def ml_groups(img, lines, lang, dets=None):
    """ML detector se text regions; OCR lines unme baanto. Region ka OCR na mile to AI image se padhega."""
    dets = detector.detect(img) if dets is None else dets
    bubbles = [d["box"] for d in dets if d["label"] == "bubble"]
    # ek hi text ke kai (overlapping) boxes: sirf sabse pakka rakho
    keep = []
    for d in sorted((d for d in dets if d["label"] != "bubble"), key=lambda d: -d["score"]):
        b = d["box"]
        if any(_overlap_frac(b, k["box"]) > 0.6 for k in keep):
            continue
        keep.append(d)
    dets = keep
    lang = _manga_ocr(img, dets, lines, lang)
    groups = []
    for d in dets:
        box = d["box"]
        mine = [l for l in lines if _center_in(l["box"], box)]
        sep = "" if lang in CJK_LANGS else " "
        if lang in CJK_LANGS and (box[3] - box[1]) > 1.3 * (box[2] - box[0]):
            mine.sort(key=lambda l: (-l["box"][2], l["box"][1]))
        else:
            mine.sort(key=lambda l: (l["box"][1], l["box"][0]))
        text = sep.join(l["text"] for l in mine)
        if d.get("mocr"):  # Japanese: manga-ocr Windows OCR se kahin behtar (khada text, furigana)
            text = d["mocr"]
        if lang == "en" and text:
            text = _fix_english(text)
        # text ka bubble: jo bubble is text ke center ko sabse chhota gherta hai
        bbox = None
        if d["label"] == "text_bubble":
            cands = [b for b in bubbles if _center_in(box, b, pad=0)]
            if cands:
                # jude / chadhe hue bubbles: jisme text ka sabse bada hissa aata hai wahi (barabar ho to chhota)
                bbox = max(cands, key=lambda b: (round(_overlap_frac(box, b), 2), -_area(b)))
        th = statistics.median([_thick(l["box"]) for l in mine]) if mine else             max(16, min(40, min(box[2] - box[0], box[3] - box[1]) / 3))
        groups.append({"lines": mine, "text": text, "box": box, "bbox": bbox,
                       "kind": "bubble" if bbox else "free", "vertical": False, "thickness": th})
    # padhne ka order
    Hh = max((g["box"][3] for g in groups), default=1)
    band = max(1, Hh // 6)
    groups.sort(key=lambda g: (g["box"][1] // band, -g["box"][2] if lang == "ja" else g["box"][0]))
    return groups, lang


def _manga_ocr(img, dets, lines, lang):
    """Japanese page (ya aisa page jahan Windows OCR ko kuch khaas na mila): har text box manga-ocr se padho.
    d["mocr"] mein text rakhta hai. Return: language (manga-ocr ko kana mile to "ja")."""
    if not dets or not mangaocr.available():
        return lang
    latin = sum(len(LATIN.findall(l["text"])) for l in lines)
    if lang != "ja" and not (lang == "en" and latin < 15):
        return lang
    W, H = img.size
    crops = []
    for d in dets:
        x0, y0, x1, y1 = d["box"]
        crops.append(img.crop((max(0, x0 - 4), max(0, y0 - 4), min(W, x1 + 4), min(H, y1 + 4))))
    try:
        texts = mangaocr.read(crops)
    except Exception as e:
        print("[manga-ocr] fail:", e)
        return lang
    if lang != "ja" and sum(len(KANA.findall(t)) for t in texts) < 5:
        return lang  # Japanese nahi hai
    for d, t in zip(dets, texts):
        d["mocr"] = t if (KANA.search(t) or HAN.search(t)) else ""
    print(f"[manga-ocr] {len(texts)} box(es) padhe")
    return "ja"


# ---------- disk cache (server band hone par bhi yaad) ----------
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_VERSION = "v9"


def _disk_get(key):
    path = os.path.join(CACHE_DIR, key + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _disk_put(key, result):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(result, f)
        def mtime(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return 0
        files = sorted((os.path.join(CACHE_DIR, n) for n in os.listdir(CACHE_DIR)), key=mtime)
        for old in files[:-400]:  # sirf aakhri 400 pages
            try:
                os.remove(old)
            except OSError:
                pass  # doosre page ne saath mein hata diya
    except Exception as e:
        print("[cache] save fail:", e)


DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
_debug_n = [0]


def save_debug(img, out):
    # aakhri 40 pages ka original + translated (gadbad dekhne ke liye)
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        _debug_n[0] = (_debug_n[0] % 40) + 1
        n = _debug_n[0]
        img.save(os.path.join(DEBUG_DIR, f"{n:02d}_in.jpg"), quality=85)
        out.save(os.path.join(DEBUG_DIR, f"{n:02d}_out.jpg"), quality=85)
        print(f"    [debug] {n:02d}")
    except Exception as e:
        print("[debug] save fail:", e)


def _url_key(url, lang_choice):
    return "u" + hashlib.md5(url.encode("utf-8", "ignore")).hexdigest() + "_" + lang_choice + "_" + CACHE_VERSION


def _cached(key):
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    disk = _disk_get(key)
    if disk:
        _cache[key] = disk
        if len(_cache) > MAX_CACHE:
            _cache.popitem(last=False)
    return disk


def url_cached(url, lang_choice="Auto"):
    """Isi image URL ka translation pehle ho chuka (jaise agla chapter pehle se)? Download bhi nahi karna padta."""
    hit = _cached(_url_key(url, lang_choice)) if url else None
    if hit:
        print("[cache] URL se mila (pehle se translate)")
        llm.usage_bump("cached")
    return hit


_inflight = {}  # key -> Future: ek hi page do baar aaye (prefetch + asli) to ek hi baar translate


async def translate_page(raw, lang_choice="Auto", page_url="", fast=False, url="", fresh=False,
                         prev_raws=None, next_raws=None, backup=False):
    key = hashlib.md5(raw).hexdigest() + "_" + lang_choice + "_" + CACHE_VERSION
    if prev_raws or next_raws:  # padosi tukdon ke saath: kata bubble poora
        h = hashlib.md5()
        for r in (prev_raws or []) + [b"|"] + (next_raws or []):
            h.update(hashlib.md5(r).digest())
        key += "_n" + h.hexdigest()[:12]
    ukey = _url_key(url, lang_choice) if url else None
    if not fresh:
        hit = _cached(key)
        if hit:
            llm.usage_bump("cached")
            if ukey:
                _cache[ukey] = hit
            return hit
        if key in _inflight:
            return await asyncio.shield(_inflight[key])
    fut = asyncio.get_running_loop().create_future()
    _inflight[key] = fut
    try:
        result = await _translate_page(raw, key, lang_choice, page_url, fast, prev_raws, next_raws, backup)
        if not fut.done():
            fut.set_result(result)
    except BaseException as e:
        if not fut.done():
            fut.set_exception(e)
            fut.exception()  # "never retrieved" warning na aaye
        raise
    finally:
        _inflight.pop(key, None)
    if ukey and result.get("image"):
        _cache[ukey] = result
        _disk_put(ukey, result)
    return result


SEAM_CTX = 500  # padosi page ka kitna hissa saath jode (px, is page ki chaudai par)


def _b64png(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=1)
    return base64.b64encode(buf.getvalue()).decode()


def _stitch(img, prev_raws, next_raws):
    """Webtoon: site ne lambi image ko tukdon mein kaata, bubble do tukdon mein bat jaata hai.
    Upar wale tukdon ka neeche ka hissa + ye page + neeche walon ka upar ka hissa jodo.
    prev_raws / next_raws: paas wala pehle. Lautao (image, L, R, kitne upar wale, kitne neeche wale)."""
    W, h = img.size

    def chain(raws):
        out, tot = [], 0
        for raw in raws or []:
            try:
                n = Image.open(io.BytesIO(raw)).convert("RGB")
            except Exception:
                break
            if abs(n.width - W) > 0.15 * W:  # alag chaudai: ek hi patti ke tukde nahi
                break
            if n.width != W:
                n = n.resize((W, max(1, round(n.height * W / n.width))))
            out.append(n)
            tot += n.height
            if tot >= SEAM_CTX:
                break
        return out, tot

    prev, pt = chain(prev_raws)
    nxt, nt = chain(next_raws)
    L, R = min(SEAM_CTX, pt), min(SEAM_CTX, nt)
    if not L and not R:
        return img, 0, 0, 0, 0
    out = Image.new("RGB", (W, L + h + R))
    y = L - pt  # upar wale tukde: sirf aakhri L px dikhein
    for part in reversed(prev):
        out.paste(part, (0, y))
        y += part.height
    out.paste(img, (0, L))
    y = L + h
    for part in nxt:
        out.paste(part, (0, y))
        y += part.height
    return out, L, R, len(prev), len(nxt)


def _region(g):
    return g.get("bbox") or g["box"]


async def _translate_page(raw, key, lang_choice, page_url, fast, prev_raws=None, next_raws=None, backup=False):
    t0 = time.time()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    own_w, own_h = img.size
    img, L, R, n_prev, n_next = _stitch(img, prev_raws, next_raws)
    if own_h < 150 and not (L or R):
        # webtoon ki patli patti akeli aayi (padosi tukde nahi mile): isme poora bubble ho hi nahi sakta,
        # AI se anuvaad karwaya to galat Hindi patti par likh di jaati thi. Waisi hi chhod do.
        print(f"[translate] {img.size} patli patti, padosi nahi mile: chhodi")
        return {"image": None, "lang": "", "bubbles": 0}

    # pehle detector (GPU ~0.1 s): is page par koi text hi nahi to OCR / AI ka time mat lagao
    if not detector.available():
        raise RuntimeError("Bubble detector model nahi mila. Installer / SETUP.bat dobara chalao.")
    dets = await asyncio.to_thread(detector.detect, img)
    own_text = [d for d in dets if d["label"] != "bubble"
                and L <= (d["box"][1] + d["box"][3]) / 2 < L + own_h]
    if not own_text:
        print(f"[translate] {img.size} koi text nahi: chhoda ({time.time() - t0:.1f}s)")
        if L or R:  # padosi ka kata bubble is par chipkana pad sakta hai: asli image lautao
            return {"image": _b64png(img.crop((0, L, own_w, L + own_h))), "lang": "", "bubbles": 0, "provider": "none"}
        return {"image": None, "lang": "", "bubbles": 0}

    async with _ocr_lock:
        t_ocr = time.time()
        skey = llm.series_key(page_url)
        if lang_choice in VALID_LANGS:
            lang, lines = lang_choice, (await _ocr(img, lang_choice) or [])
        elif skey in _series_lang:
            # is series ki language pehle se pata: sirf ek OCR pass (pehle 4 tak hote the)
            lang = _series_lang[skey]
            lines = await _ocr(img, lang) or []
            # yaad ki hui language galat lag rahi (Korean OCR par bahut Latin / kuch nahi mila): dobara pehchano
            if sum(len(l["text"]) for l in lines) < 4 or (lang != "en" and _count(LATIN, lines) > 40):
                _series_lang.pop(skey, None)
                lang, lines = await detect_and_ocr(img)
        else:
            lang, lines = await detect_and_ocr(img)
        if lang_choice not in VALID_LANGS and skey not in _series_lang and sum(len(l["text"]) for l in lines) >= 20:
            votes = _series_vote.setdefault(skey, [])
            votes.append(lang)
            if len(votes) >= 2 and votes[-1] == votes[-2]:
                _series_lang[skey] = lang
        # Korean / Chinese: PaddleOCR v5 Windows OCR se kaafi sahi padhta hai (language pehchanne ke baad)
        if paddle_ocr.available(lang):
            try:
                lines = await asyncio.to_thread(paddle_ocr.recognize, img, lang) or lines
            except Exception as e:
                print("[paddle] fail, Windows OCR wala text:", e)
        t_ocr = time.time() - t_ocr
        if not detector.available():
            raise RuntimeError("Bubble detector model nahi mila. Installer / SETUP.bat dobara chalao.")
        groups, lang = await asyncio.to_thread(ml_groups, img, lines, lang, dets)
        if lang == "ja" and lang_choice not in VALID_LANGS:
            _series_lang[skey] = "ja"
    if L or R:
        # bubble usi page ka jiske andar uska beech hai; padosi wale padosi khud karega
        groups = [g for g in groups if L <= (_region(g)[1] + _region(g)[3]) / 2 < L + own_h]
    if not groups and (L or R):
        # apna koi bubble nahi, par padosi ka kata bubble is par chipkana pad sakta hai: asli image hi lauta do
        result = {"image": _b64png(img.crop((0, L, own_w, L + own_h))), "lang": lang, "bubbles": 0, "provider": "none"}
    elif not groups:
        result = {"image": None, "lang": lang, "bubbles": 0}
    else:
        # text mitana (LaMa) aur AI translation saath-saath
        erase_task = asyncio.create_task(asyncio.to_thread(erase_ml, img, groups))
        ai = await asyncio.to_thread(llm.translate_with_llm, img, groups, lang, page_url, fast)
        pre = await erase_task
        bcfg = llm.load_config().get("backup", {})
        if ai:
            hindi, provider = ai
        elif backup and lang in backup_api.LANGS and bcfg.get("api_key"):
            # saari AI limit khatam, popup ka backup switch on: English -> Hindi web API
            provider = "backup"
            try:
                hindi = await asyncio.to_thread(backup_api.translate, [g["text"] or "" for g in groups], bcfg)
            except Exception as e:
                raise RuntimeError(f"AI limit khatam aur backup translator bhi nahi chala ({e}).")
            llm.usage_bump("backup")
        else:
            provider = "nllb"
            try:
                async with _nllb_lock:
                    hindi = await asyncio.to_thread(translate_texts, [g["text"] for g in groups], lang)
                hindi = [h if g["text"] else "" for g, h in zip(groups, hindi)]
            except Exception as e:
                raise RuntimeError(f"AI translation fail aur NLLB bhi nahi chala ({e}). Server log dekho.")
        out = await asyncio.to_thread(render_ml, img, groups, hindi, pre)
        save_debug(img, out)
        spill = []
        if L or R:
            # jo bubble padosi page tak jaata hai: uska woh hissa padosi par chipkane ke liye
            P = 10
            up = [_region(g) for g in groups if _region(g)[1] < L]
            if up:
                spill.append({"dir": "prev", "patch": _b64png(out.crop((0, 0, own_w, L))),
                              "rects": [[max(0, b[0] - P), max(0, b[1] - P), min(own_w, b[2] + P), L] for b in up]})
            dn = [_region(g) for g in groups if _region(g)[3] > L + own_h]
            if dn:
                y0 = L + own_h
                spill.append({"dir": "next", "patch": _b64png(out.crop((0, y0, own_w, y0 + R))),
                              "rects": [[max(0, b[0] - P), 0, min(own_w, b[2] + P), min(R, b[3] - y0 + P)] for b in dn]})
            out = out.crop((0, L, own_w, L + own_h))
        result = {"image": _b64png(out), "lang": lang, "bubbles": len(groups), "provider": provider}
        if spill:
            result["spill"] = spill
            result["ctx"] = [n_prev, n_next]
        for g, h in zip(groups, hindi):
            print(f"    {g['text']}  ->  {h}")

    print(f"[translate] {img.size} lang={lang} via={result.get('provider', '-')} bubbles={result['bubbles']} "
          f"{time.time() - t0:.1f}s (ocr {t_ocr:.1f}s)")
    if result.get("provider") not in ("nllb", "none", "backup"):  # backup ka result cache nahi: limit khulne par AI se achha  # NLLB backup wala result cache nahi, taaki baad mein AI se dobara ho
        _cache[key] = result
        if result.get("image"):
            await asyncio.to_thread(_disk_put, key, result)
    if result.get("image") and result.get("bubbles"):
        llm.usage_bump("pages")
    if len(_cache) > MAX_CACHE:
        _cache.popitem(last=False)
    return result
