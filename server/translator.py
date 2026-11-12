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
import llm
from nllb import translate_texts
from ocr_windows import CJK_LANGS, OcrLanguageMissing, recognize_lines
from render import assign_to_bubbles, attach_bubbles, render_ml, render_translations

KANA = re.compile(r"[\u3040-\u30ff]")
LATIN = re.compile(r"[A-Za-z]")
HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
HAN = re.compile(r"[\u4e00-\u9fff]")
VALID_LANGS = {"ja", "ko", "zh_hans", "zh_hant", "en"}

_cache = OrderedDict()
_ocr_lock = asyncio.Lock()   # OCR/render ek time par ek; AI calls ek saath chal sakti hain
_nllb_lock = asyncio.Lock()  # GPU
MAX_CACHE = 60


def _count(pattern, lines):
    return sum(len(pattern.findall(l["text"])) for l in lines)


async def _ocr(img, lang):
    try:
        return await recognize_lines(img, lang)
    except OcrLanguageMissing as e:
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
        if _count(HANGUL, ko) >= 3:
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


def _near(a, b):
    ta, tb = _thick(a["box"]), _thick(b["box"])
    if ta <= 0 or tb <= 0 or max(ta, tb) / min(ta, tb) > 2.2:
        return False  # size bahut alag (jaise SFX vs dialogue)
    pad = 0.8 * min(ta, tb)
    A, B = a["box"], b["box"]
    return not (A[2] + pad < B[0] or B[2] + pad < A[0] or A[3] + pad < B[1] or B[3] + pad < A[1])


def _fix_english(text):
    text = re.sub(r"-\s+(?=[a-zA-Z])", "", text)
    if sum(c.isupper() for c in text) > sum(c.islower() for c in text):
        # ALL CAPS manga text -> normal case (NLLB isse better samajhta hai)
        text = text.lower()
        text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
        text = re.sub(r"\bi\b", "I", text)
    return text


def group_lines(lines, lang):
    n = len(lines)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _near(lines[i], lines[j]):
                parent[find(i)] = find(j)

    buckets = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(lines[i])

    groups = []
    for members in buckets.values():
        ratios = [(l["box"][3] - l["box"][1]) / max(1, l["box"][2] - l["box"][0]) for l in members]
        vertical = lang in CJK_LANGS and statistics.median(ratios) > 1.5
        if vertical:
            members.sort(key=lambda l: (-l["box"][2], l["box"][1]))  # right to left
        else:
            members.sort(key=lambda l: (l["box"][1], l["box"][0]))

        sep = "" if lang in CJK_LANGS else " "
        text = sep.join(l["text"] for l in members)
        if lang == "en":
            text = _fix_english(text)

        letters = re.findall(r"[^\W\d_]", text)
        if len(letters) < (2 if lang == "en" else 1):
            continue

        groups.append({
            "lines": members,
            "text": text,
            "vertical": vertical,
            "thickness": statistics.median(_thick(l["box"]) for l in members),
            "box": (min(l["box"][0] for l in members), min(l["box"][1] for l in members),
                    max(l["box"][2] for l in members), max(l["box"][3] for l in members)),
        })
    # padhne ka order: Japanese right->left, baaki left->right (AI ko context sahi mile)
    H = max((g["box"][3] for g in groups), default=1)
    band = max(1, H // 6)
    rtl = lang == "ja"
    groups.sort(key=lambda g: (g["box"][1] // band, -g["box"][2] if rtl else g["box"][0]))
    return groups


def _center_in(box, outer, pad=6):
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return outer[0] - pad <= cx <= outer[2] + pad and outer[1] - pad <= cy <= outer[3] + pad


def _area(b):
    return max(1, (b[2] - b[0]) * (b[3] - b[1]))


def ml_groups(img, lines, lang):
    """ML detector se text regions; OCR lines unme baanto. Region ka OCR na mile to AI image se padhega."""
    dets = detector.detect(img)
    bubbles = [d["box"] for d in dets if d["label"] == "bubble"]
    groups = []
    for d in dets:
        if d["label"] == "bubble":
            continue
        box = d["box"]
        mine = [l for l in lines if _center_in(l["box"], box)]
        sep = "" if lang in CJK_LANGS else " "
        if lang in CJK_LANGS and (box[3] - box[1]) > 1.3 * (box[2] - box[0]):
            mine.sort(key=lambda l: (-l["box"][2], l["box"][1]))
        else:
            mine.sort(key=lambda l: (l["box"][1], l["box"][0]))
        text = sep.join(l["text"] for l in mine)
        if lang == "en" and text:
            text = _fix_english(text)
        # text ka bubble: jo bubble is text ke center ko sabse chhota gherta hai
        bbox = None
        if d["label"] == "text_bubble":
            cands = [b for b in bubbles if _center_in(box, b, pad=0)]
            if cands:
                bbox = min(cands, key=_area)
        th = statistics.median([_thick(l["box"]) for l in mine]) if mine else             max(16, min(40, min(box[2] - box[0], box[3] - box[1]) / 3))
        groups.append({"lines": mine, "text": text, "box": box, "bbox": bbox,
                       "kind": "bubble" if bbox else "free", "vertical": False, "thickness": th})
    # padhne ka order
    Hh = max((g["box"][3] for g in groups), default=1)
    band = max(1, Hh // 6)
    groups.sort(key=lambda g: (g["box"][1] // band, -g["box"][2] if lang == "ja" else g["box"][0]))
    return groups


# ---------- disk cache (server band hone par bhi yaad) ----------
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_VERSION = "v2"


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
        files = sorted((os.path.join(CACHE_DIR, n) for n in os.listdir(CACHE_DIR)), key=os.path.getmtime)
        for old in files[:-400]:  # sirf aakhri 400 pages
            os.remove(old)
    except Exception as e:
        print("[cache] save fail:", e)


def groups_from_found(found):
    out = []
    for f in found:
        x0, y0, x1, y1 = f["box"]
        out.append({"lines": [{"box": f["box"], "text": f["text"]}], "text": f["text"],
                    "vertical": (y1 - y0) > 1.5 * (x1 - x0),
                    "thickness": min(60, max(16, min(x1 - x0, y1 - y0) // 2)), "box": f["box"]})
    return out


def hindi_for(groups, found):
    # attach_bubbles groups jod sakta hai: har group ki saari lines ka Hindi jodo
    return [" ".join(f["hi"] for f in found if any(l["box"] == f["box"] for l in g["lines"])) for g in groups]


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


async def translate_page(raw, lang_choice="Auto", page_url=""):
    key = hashlib.md5(raw).hexdigest() + "_" + lang_choice + "_" + CACHE_VERSION
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    disk = _disk_get(key)
    if disk:
        print(f"[cache] disk se mila ({disk.get('bubbles')} bubbles)")
        _cache[key] = disk
        return disk

    t0 = time.time()
    img = Image.open(io.BytesIO(raw)).convert("RGB")

    async with _ocr_lock:
        if lang_choice in VALID_LANGS:
            lang, lines = lang_choice, await recognize_lines(img, lang_choice)
        else:
            lang, lines = await detect_and_ocr(img)
        use_ml = detector.available()
        if use_ml:
            groups = await asyncio.to_thread(ml_groups, img, lines, lang)
        else:
            groups = group_lines(lines, lang)
            groups = await asyncio.to_thread(assign_to_bubbles, img, groups)
            # padhne ka order dobara (khaali bubbles bhi jude hain)
            Hh = max((g["box"][3] for g in groups), default=1)
            band = max(1, Hh // 6)
            groups.sort(key=lambda g: (g["box"][1] // band, -g["box"][2] if lang == "ja" else g["box"][0]))
    if use_ml and not groups:
        result = {"image": None, "lang": lang, "bubbles": 0}
    elif not use_ml and not any(g["text"] for g in groups):  # OCR ko kuch nahi mila (italic/stylized): Gemini khud dhoondhe
        found = await asyncio.to_thread(llm.detect_with_llm, img, page_url)
        if found:
            async with _ocr_lock:
                # Gemini ke box ko page ke asli bubbles mein fit karo (box thoda galat ho to bhi sahi bubble)
                dgroups = await asyncio.to_thread(assign_to_bubbles, img, groups_from_found(found))
                hindi = hindi_for(dgroups, found)
                out = await asyncio.to_thread(render_translations, img, dgroups, hindi)
            save_debug(img, out)
            buf = io.BytesIO()
            out.save(buf, format="PNG", compress_level=1)
            result = {"image": base64.b64encode(buf.getvalue()).decode(), "lang": lang,
                      "bubbles": len(dgroups), "provider": "gemini-detect"}
            for f in found:
                print(f"    [detect] {f['text']}  ->  {f['hi']}")
        else:
            result = {"image": None, "lang": lang, "bubbles": 0}
    else:
        ai = await asyncio.to_thread(llm.translate_with_llm, img, groups, lang, page_url)
        extras = []
        if ai:
            hindi, provider, extras = ai
        else:
            provider = "nllb"
            try:
                async with _nllb_lock:
                    hindi = await asyncio.to_thread(translate_texts, [g["text"] for g in groups], lang)
                hindi = [h if g["text"] else "" for g, h in zip(groups, hindi)]
            except Exception as e:
                raise RuntimeError(f"AI translation fail aur NLLB bhi nahi chala ({e}). Server log dekho.")
        if extras:
            async with _ocr_lock:
                egroups = await asyncio.to_thread(attach_bubbles, img, groups_from_found(extras))
            groups, hindi = groups + egroups, list(hindi) + hindi_for(egroups, extras)
            for e in extras:
                print(f"    [extra] {e['text']}  ->  {e['hi']}")
        renderer = render_ml if use_ml else render_translations
        out = await asyncio.to_thread(renderer, img, groups, hindi)
        save_debug(img, out)
        buf = io.BytesIO()
        out.save(buf, format="PNG", compress_level=1)
        result = {"image": base64.b64encode(buf.getvalue()).decode(), "lang": lang, "bubbles": len(groups), "provider": provider}
        for g, h in zip(groups, hindi):
            print(f"    {g['text']}  ->  {h}")

    print(f"[translate] {img.size} lang={lang} via={result.get('provider', '-')} bubbles={result['bubbles']} {time.time() - t0:.1f}s")
    if result.get("provider") != "nllb":  # NLLB backup wala result cache nahi, taaki baad mein AI se dobara ho
        _cache[key] = result
        if result.get("image"):
            await asyncio.to_thread(_disk_put, key, result)
    if len(_cache) > MAX_CACHE:
        _cache.popitem(last=False)
    return result
