# Purana text hatana + Hindi text box mein fit karke likhna
import dllfix  # noqa: F401  (PIL se pehle)
import os

import cv2
import numpy as np
from PIL import ImageDraw, ImageFont, features

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_CANDIDATES = [
    os.path.join(HERE, "fonts", "Baloo2.ttf"),  # comic jaisa, OFL license
    os.path.join(HERE, "fonts", "NotoSansDevanagari-Regular.ttf"),
    r"C:\Windows\Fonts\Nirmala.ttc",
    r"C:\Windows\Fonts\Nirmala.ttf",
]
FONT_PATH = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
HAS_RAQM = features.check("raqm")
_fonts = {}


def get_font(size):
    if FONT_PATH is None:
        raise RuntimeError("Devanagari font nahi mila. server/fonts mein NotoSansDevanagari-Regular.ttf rakho.")
    font = _fonts.get(size)
    if font is None:
        layout = ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC
        font = ImageFont.truetype(FONT_PATH, size, layout_engine=layout)
        try:
            if b"SemiBold" in font.get_variation_names():
                font.set_variation_by_name("SemiBold")
        except Exception:
            pass  # variable font nahi
        _fonts[size] = font
    return font


def bg_color(arr, box, pad=4):
    # Box ke border ke pixels ka median = bubble ka background color
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = box
    region = arr[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)]
    if region.size == 0:
        return (255, 255, 255)
    border = np.concatenate([region[0], region[-1], region[:, 0], region[:, -1]])
    return tuple(int(v) for v in np.median(border, axis=0))


def luminance(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def wrap_text(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def expand_box(box, img_w, img_h, vertical):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if vertical:
        # Vertical Japanese ka box patla hota hai, Hindi horizontal likhni hai to chauda karo
        target_w = max(bw, bh * 0.7)
        mx = (target_w - bw) / 2 + bw * 0.1
        my = bh * 0.05
    else:
        mx, my = bw * 0.12, bh * 0.15
    return (max(0, int(x0 - mx)), max(0, int(y0 - my)),
            min(img_w, int(x1 + mx)), min(img_h, int(y1 + my)))


def draw_in_box(draw, text, box, fg, bg, thickness):
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    max_size = int(max(12, min(thickness * 1.1 if thickness else 40, bh * 0.6, 42)))
    min_size = 10

    chosen = None
    for size in range(max_size, min_size - 1, -1):
        font = get_font(size)
        lines = wrap_text(draw, text, font, bw)
        lh = int(size * 1.3)
        if len(lines) * lh <= bh and all(draw.textlength(l, font=font) <= bw for l in lines):
            chosen = (font, lines, lh, size)
            break
    if chosen is None:
        font = get_font(min_size)
        chosen = (font, wrap_text(draw, text, font, bw), int(min_size * 1.3), min_size)

    font, lines, lh, size = chosen
    cx = (x0 + x1) / 2
    y = (y0 + y1) / 2 - len(lines) * lh / 2
    stroke = max(1, size // 8)  # bg color ki outline: box se bahar jaye to bhi padhne mein aaye
    for line in lines:
        draw.text((cx, y + lh / 2), line, font=font, fill=fg, anchor="mm",
                  stroke_width=stroke, stroke_fill=bg)
        y += lh


def find_bubble(gray, box):
    # chhote window se shuru, bubble badi ho to window badhao
    for mult in (1.0, 2.0, 3.5, 6.0, 10.0):
        r = _find_bubble(gray, box, mult)
        if r != "grow":
            return r
    return None


def _find_bubble(gray, box, mult):
    """Text ke aas-paas ka band (closed) safed bubble dhoondo.
    Return (mask, (wx0, wy0)) window coords mein, ya None agar bubble nahi (text art par hai)."""
    H, W = gray.shape
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    pad = int(max(bw, bh) * mult) + 30
    wx0, wy0, wx1, wy1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    win = gray[wy0:wy1, wx0:wx1]
    bright = (win > 170).astype(np.uint8)
    n, labels = cv2.connectedComponents(bright, connectivity=4)
    if n < 2:
        return None
    inner = labels[y0 - wy0:y1 - wy0, x0 - wx0:x1 - wx0]
    counts = np.bincount(inner.ravel(), minlength=n)
    counts[0] = 0
    best = int(counts.argmax())
    if counts[best] < 0.2 * inner.size:
        return None
    region = (labels == best).astype(np.uint8)
    # window ke kinare tak pahunch gaya: ya bubble badi hai (window badhao) ya khula area hai
    edges = [(region[0].any(), wy0 > 0), (region[-1].any(), wy1 < H),
             (region[:, 0].any(), wx0 > 0), (region[:, -1].any(), wx1 < W)]
    if any(t and can_grow for t, can_grow in edges):
        return "grow"
    if sum(t for t, _ in edges) >= 2:  # image ke 2+ kinaron tak = background, bubble nahi
        return None
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(contours, key=cv2.contourArea)
    mask = np.zeros_like(region)
    cv2.drawContours(mask, [c], -1, 1, thickness=-1)  # text ke "chhed" bhi bhar jaate hain
    if mask.sum() > 0.2 * H * W or mask.sum() > 150 * bw * bh:  # bahut bada = shayad poora panel
        return None
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=2)  # outline bachao
    return mask, (wx0, wy0)


def attach_bubbles(img, groups):
    """Har group ka bubble dhoondo; ek hi bubble wale groups ko jod do (OCR ki tooti lines)."""
    gray = np.asarray(img.convert("L"))
    merged = []
    for g in groups:
        b = find_bubble(gray, g["box"])
        if b is not None:
            mask, (ox, oy) = b
            ys, xs = np.nonzero(mask)
            g["bubble"] = (mask, ox, oy, (ox + xs.min(), oy + ys.min(), ox + xs.max(), oy + ys.max()))
            for m in merged:
                if "bubble" in m and _iou(m["bubble"][3], g["bubble"][3]) > 0.5:
                    if _gap(m["box"], g["box"]) > 1.5 * max(m["thickness"], g["thickness"]):
                        # door ke texts ek hi "bubble" mein: wo asal mein judi hui alag bubbles hain
                        del m["bubble"], g["bubble"]
                        merged.append(g)
                        break
                    m["lines"] += g["lines"]
                    m["text"] = (m["text"] + " " + g["text"]).strip()
                    m["box"] = (min(m["box"][0], g["box"][0]), min(m["box"][1], g["box"][1]),
                                max(m["box"][2], g["box"][2]), max(m["box"][3], g["box"][3]))
                    break
            else:
                merged.append(g)
        else:
            merged.append(g)
    return merged


def _outline_mask(mask):
    # bubble ke kinare ki patti (outline yahan hai): ise nahi mitana
    return (cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=4) - cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)).clip(0, 1)


def _gap(a, b):
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return max(dx, dy)


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0


def _fits(inner, cx, cy, lines, widths, lh):
    """Har line ka rectangle bubble (inner mask) ke andar hai?"""
    H, W = inner.shape
    top = cy - len(lines) * lh / 2
    for i, w in enumerate(widths):
        y0, y1 = int(top + i * lh), int(top + (i + 1) * lh)
        x0, x1 = int(cx - w / 2), int(cx + w / 2)
        if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H:
            return False
        if not (inner[y0, x0] and inner[y0, x1] and inner[y1, x0] and inner[y1, x1]
                and inner[(y0 + y1) // 2, x0] and inner[(y0 + y1) // 2, x1]):
            return False
    return True


def draw_in_mask(draw, text, mask, ox, oy, fg, bg, thickness, tbox=None):
    """Bubble ki asli shape mein text fit karo (oval ho ya tircha)."""
    pad = 6
    # kinare par 0 ki patti: warna erode/distance transform mask ke kinare ko bubble ka andar samajhte hain
    P = pad + 2
    padded = np.pad(mask, P)
    inner = cv2.erode(padded, np.ones((3, 3), np.uint8), iterations=pad)[P:-P, P:-P]
    if tbox is not None and tbox[2] > tbox[0]:
        # bubble bahut bada (page ke safed hisse se juda): asli text ke aas-paas tak hi
        x0, y0, x1, y1 = tbox
        w, h = x1 - x0, y1 - y0
        if inner.sum() > 6 * max(1, w * h):
            lim = np.zeros_like(inner)
            ex, ey = int(w * 0.6) + 20, int(h * 0.4) + 20
            lim[max(0, y0 - oy - ey):max(0, y1 - oy + ey), max(0, x0 - ox - ex):max(0, x1 - ox + ex)] = 1
            inner = inner & lim
    if inner.sum() < 50:
        inner = mask
    dist = cv2.distanceTransform(np.pad(inner, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    ys, xs = np.nonzero(inner)
    # center: bubble ka "sabse andar" wala hissa, par bahut upar/neeche na jaye
    my, mx = np.unravel_index(dist.argmax(), dist.shape)
    cx = (mx + xs.mean()) / 2
    cy = (my + ys.mean()) / 2
    bw = xs.max() - xs.min()
    max_size = int(max(12, min(thickness * 1.1 if thickness else 40, 44)))

    def layout(size):
        font = get_font(size)
        lh = int(size * 1.45)
        # alag-alag chaudai try karo: patli bubble mein zyada lines
        for frac in (0.95, 0.8, 0.65, 0.5):
            lines = wrap_text(draw, text, font, bw * frac)
            widths = [draw.textlength(l, font=font) for l in lines]
            if _fits(inner, cx, cy, lines, widths, lh):
                return font, lines, lh
        return None

    # binary search: sabse bada size jo fit ho (pehle har size ek-ek karke try hota tha)
    lo, hi, best = 10, max_size, None
    while lo <= hi:
        mid = (lo + hi) // 2
        r = layout(mid)
        if r:
            best, lo = (mid, r), mid + 1
        else:
            hi = mid - 1
    if best:
        size, (font, lines, lh) = best
        _draw_lines(draw, lines, font, lh, ox + cx, oy + cy, fg, bg, size)
        return
    font = get_font(10)
    lines = wrap_text(draw, text, font, bw * 0.8)
    _draw_lines(draw, lines, font, 14, ox + cx, oy + cy, fg, bg, 10)


def _draw_lines(draw, lines, font, lh, cx, cy, fg, bg, size):
    y = cy - len(lines) * lh / 2
    stroke = max(1, size // 10)
    for line in lines:
        draw.text((cx, y + lh / 2), line, font=font, fill=fg, anchor="mm", stroke_width=stroke, stroke_fill=bg)
        y += lh


def render_translations(img, groups, texts):
    arr = np.array(img)
    W, H = img.size
    plans = []
    for group, text in zip(groups, texts):
        text = (text or "").strip()
        if not text:
            continue
        if "bubble" in group:
            mask, ox, oy, (bx0, by0, bx1, by1) = group["bubble"]
            mh, mw = mask.shape
            region = arr[oy:oy + mh, ox:ox + mw]
            bg = tuple(int(v) for v in np.median(region[mask.astype(bool)], axis=0))
            bg = (255, 255, 255) if luminance(bg) > 200 else bg
            # poora bubble saaf: convex hull se, taaki kinare ko chhoote akshar bhi mitein
            erase = mask.copy()
            cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cs:
                hull = np.zeros_like(mask)
                cv2.drawContours(hull, [cv2.convexHull(max(cs, key=cv2.contourArea))], -1, 1, -1)
                hull = cv2.erode(hull, np.ones((3, 3), np.uint8), iterations=3)  # outline bachao
                dark = (region.mean(axis=2) < 128).astype(np.uint8) if region.ndim == 3 else (region < 128).astype(np.uint8)
                # hull ke andar sirf wo kaale pixel jo bubble outline se jude nahi (akshar)
                erase = np.maximum(erase, hull & (1 - _outline_mask(mask)) & np.maximum(dark, mask))
            region[erase.astype(bool)] = bg
            # bubble (aksar oval) ke andar ka rectangle
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            hw, hh = (bx1 - bx0) * 0.34, (by1 - by0) * 0.38
            area = (int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh))
        else:
            # bubble nahi mila: lines ke beech ka gap bhi, poora group area ek saath mitao
            x0, y0, x1, y1 = group["box"]
            p = max(4, int(group["thickness"] * 0.25))
            bg = bg_color(arr, (x0 - p, y0 - p, x1 + p, y1 + p))
            if luminance(bg) > 110:  # screentone ka grey median: safed hi lagao
                bg = (255, 255, 255)
            arr[max(0, y0 - p):y1 + p, max(0, x0 - p):x1 + p] = bg
            area = expand_box(group["box"], W, H, group["vertical"])
        # bubble nahi: asli English jitna hi bada (bahar na phaile); bubble: thoda bada chalega
        if "bubble" in group:
            mask, ox, oy, _ = group["bubble"]
            tb = group["box"] if group.get("lines") else None
            plans.append((text, ("mask", mask, ox, oy, tb), bg, group["thickness"] * 1.4))
        else:
            plans.append((text, area, bg, group["thickness"] * 0.9))

    from PIL import Image
    out = Image.fromarray(arr)
    draw = ImageDraw.Draw(out)
    for text, area, bg, thick in plans:
        fg = (0, 0, 0) if luminance(bg) > 128 else (255, 255, 255)
        if area[0] == "mask":
            draw_in_mask(draw, text, area[1], area[2], area[3], fg, bg, thick, area[4])
        else:
            draw_in_box(draw, text, area, fg, bg, thick)
    return out


def _bubble_from_comp(comp, x, y, H, W):
    """comp = ek safed hissa (crop). Bubble jaisa ho to (mask, x, y, bbox), warna None."""
    h, w = comp.shape
    area = int(comp.sum())
    if area < 0.0015 * H * W or area > 0.2 * H * W or w < 25 or h < 25:
        return None
    if (x == 0) + (y == 0) + (x + w >= W) + (y + h >= H) >= 3:  # poora background (page kate bubble 2 kinare chhoo sakte hain)
        return None
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(contours, key=cv2.contourArea)
    filled = np.zeros_like(comp)
    cv2.drawContours(filled, [c], -1, 1, thickness=-1)
    fa = int(filled.sum())
    hull = cv2.contourArea(cv2.convexHull(c)) or 1
    if fa / hull < 0.85 or fa / (w * h) < 0.45:  # bubble lagbhag convex hote hain
        return "split"
    holes = fa - area  # andar ke kaale pixel = text
    if holes < 0.02 * fa or holes > 0.5 * fa:
        return None
    return (filled, int(x), int(y), (int(x), int(y), int(x + w), int(y + h)))


def _components(mask):
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        yield (labels[y:y + h, x:x + w] == i).astype(np.uint8), int(x), int(y)


def detect_bubbles(img):
    """Poore page ke band safed speech bubbles (jinke andar text jaisa kuch ho).
    Return list of (mask, ox, oy, (x0, y0, x1, y1))."""
    gray = np.asarray(img.convert("L"))
    H, W = gray.shape
    k3 = np.ones((3, 3), np.uint8)
    # 1px erode: bubble outline ke chhote gaps se bahar ke safed area se judna band
    bright = cv2.erode((gray > 190).astype(np.uint8), k3, iterations=1)
    out = []
    for comp, x, y in _components(bright):
        r = _bubble_from_comp(comp, x, y, H, W)
        if r == "split":
            # bubble ki poonch / patli line se kuch aur juda hai: aur erode karke todo
            for it in (2, 4):
                found = False
                for sub, sx, sy in _components(cv2.erode(comp, k3, iterations=it)):
                    sub = cv2.dilate(sub, k3, iterations=it)
                    sub &= comp[sy:sy + sub.shape[0], sx:sx + sub.shape[1]]
                    rs = _bubble_from_comp(sub, x + sx, y + sy, H, W)
                    if rs not in (None, "split"):
                        out.append(rs)
                        found = True
                if found:
                    break
        elif r is not None:
            out.append(r)
    return [b for b in out if _has_outline(gray, b)]


def _has_outline(gray, b):
    # asli speech bubble ke chaaron taraf kaali outline hoti hai (farsh/deewar ke safed hisse ki nahi)
    mask, ox, oy, _ = b
    H, W = gray.shape
    p = 4
    x0, y0 = max(0, ox - p), max(0, oy - p)
    x1, y1 = min(W, ox + mask.shape[1] + p), min(H, oy + mask.shape[0] + p)
    big = np.zeros((y1 - y0, x1 - x0), np.uint8)
    big[oy - y0:oy - y0 + mask.shape[0], ox - x0:ox - x0 + mask.shape[1]] = mask
    ring = cv2.dilate(big, np.ones((7, 7), np.uint8)) - big
    v = gray[y0:y1, x0:x1][ring.astype(bool)]
    return v.size > 0 and (v < 100).mean() >= 0.3


def bubble_index_at(bubbles, px, py):
    for k, (mask, ox, oy, (x0, y0, x1, y1)) in enumerate(bubbles):
        if x0 <= px < x1 and y0 <= py < y1 and mask[py - oy, px - ox]:
            return k
    return None


def assign_to_bubbles(img, groups):
    """OCR groups ko page ke bubbles se jodo. Jin bubbles mein OCR ko kuch nahi mila,
    unke liye khaali group (text="") banao taaki AI image se padh le."""
    bubbles = detect_bubbles(img)
    by_bubble, free = {}, []
    for g in groups:
        x0, y0, x1, y1 = g["box"]
        k = bubble_index_at(bubbles, (x0 + x1) // 2, (y0 + y1) // 2)
        if k is None:  # center bahar, par koi line bubble ke andar ho to bhi usi bubble ka
            for l in g["lines"]:
                lx0, ly0, lx1, ly1 = l["box"]
                k = bubble_index_at(bubbles, (lx0 + lx1) // 2, (ly0 + ly1) // 2)
                if k is not None:
                    break
        if k is None:  # box ka bada hissa kisi bubble ke box mein
            for kk, b in enumerate(bubbles):
                bx0, by0, bx1, by1 = b[3]
                ix = max(0, min(x1, bx1) - max(x0, bx0))
                iy = max(0, min(y1, by1) - max(y0, by0))
                if ix * iy > 0.5 * max(1, (x1 - x0) * (y1 - y0)):
                    k = kk
                    break
        if k is None:
            free.append(g)
        elif k in by_bubble:
            m = by_bubble[k]
            m["lines"] += g["lines"]
            m["text"] = (m["text"] + " " + g["text"]).strip()
            m["box"] = (min(m["box"][0], x0), min(m["box"][1], y0), max(m["box"][2], x1), max(m["box"][3], y1))
        else:
            g["bubble"] = bubbles[k]
            by_bubble[k] = g
    for k, b in enumerate(bubbles):
        if k not in by_bubble:
            bx0, by0, bx1, by1 = b[3]
            by_bubble[k] = {"lines": [], "text": "", "missing": True, "vertical": False,
                            "thickness": 30, "box": b[3], "bubble": b}
    # bubble ke bahar wale groups: purana tarika (aas-paas bubble dhoondo / rectangle)
    free = attach_bubbles(img, free)
    for g in free:
        # purane tarike ka bubble agar dusre (pakke) bubbles ke upar phaila hai to galat hai: chhote box mein hi likho
        if "bubble" in g:
            fb = g["bubble"][3]
            if any(_iou(fb, b[3]) > 0.05 or _contains(fb, b[3]) for b in bubbles):
                del g["bubble"]
    return list(by_bubble.values()) + free


def _contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


# ---------------- ML detector wale groups (kind = "bubble" / "free") ----------------
def _ellipse_mask(w, h, shrink=0.06):
    m = np.zeros((h, w), np.uint8)
    cv2.ellipse(m, (w // 2, h // 2), (max(1, int(w * (0.5 - shrink))), max(1, int(h * (0.5 - shrink)))),
                0, 0, 360, 1, -1)
    return m


def _is_flat(arr, box):
    x0, y0, x1, y1 = box
    region = arr[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6]
    if region.size == 0:
        return True
    g = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    border = np.concatenate([g[0], g[-1], g[:, 0], g[:, -1]])
    return border.std() < 18


def erase_ml(img, groups):
    """Translation se pehle hi saare text mitao (AI ke jawab ke intezaar ke saath-saath chalta hai).
    Return (orig_arr, erased_arr, plans) - plans[i] = group i ke likhne ki jagah."""
    import inpaint
    orig = np.array(img.convert("RGB"))
    arr = orig.copy()
    H, W = arr.shape[:2]
    plans = []
    for g in groups:
        x0, y0, x1, y1 = g["box"]
        p = 6
        ebox = (max(0, x0 - p), max(0, y0 - p), min(W, x1 + p), min(H, y1 + p))
        bg = bg_color(arr, ebox, pad=2)
        if g["kind"] == "bubble" and g.get("bbox"):
            bx0, by0, bx1, by1 = g["bbox"]
            bbg = bg_color(arr, (bx0 + (bx1 - bx0) // 4, by0 + (by1 - by0) // 4,
                                 bx1 - (bx1 - bx0) // 4, by1 - (by1 - by0) // 4), pad=0)
            bg = (255, 255, 255) if luminance(bbg) > 200 else bbg
            # text pixels mitao (bubble outline bachi rahe: sirf text box ke andar)
            m = inpaint.text_mask(arr, ebox, grow=3)
            if m is not None:
                arr[ebox[1]:ebox[3], ebox[0]:ebox[2]][m.astype(bool)] = bg
            # Hindi: bubble ke andar ka oval, jo bubble ke rang ka ho
            bub = arr[by0:by1, bx0:bx1]
            em = _ellipse_mask(bx1 - bx0, by1 - by0)
            gray = cv2.cvtColor(bub, cv2.COLOR_RGB2GRAY).astype(np.int16)
            same = (np.abs(gray - int(luminance(bg))) < 60).astype(np.uint8)
            same = cv2.morphologyEx(same, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            mask = em & same
            if mask.sum() < 0.3 * em.sum():
                mask = em
            plans.append(("mask", ebox, mask, bx0, by0, bg, g["thickness"] * 1.3))
        else:
            flat = _is_flat(arr, g["box"])
            m = inpaint.text_mask(arr, ebox, grow=4) if flat else inpaint.letter_mask(arr, ebox)
            if m is not None:
                if flat:
                    arr[ebox[1]:ebox[3], ebox[0]:ebox[2]][m.astype(bool)] = bg
                else:
                    full = np.zeros((H, W), np.uint8)
                    full[ebox[1]:ebox[3], ebox[0]:ebox[2]] = m
                    inpaint.inpaint_region(arr, full, ebox)
                    bg = bg_color(arr, ebox, pad=2)
            plans.append(("box", ebox, None, 0, 0, bg, g["thickness"]))
    return orig, arr, plans


def render_ml(img, groups, texts, pre=None):
    orig, arr, plans = pre if pre is not None else erase_ml(img, groups)
    arr = arr.copy()
    # jis text ka AI ne "" diya (watermark / noise), uska original wapas
    for (kind, ebox, *_), text in zip(plans, texts):
        if not (text or "").strip():
            x0, y0, x1, y1 = ebox
            arr[y0:y1, x0:x1] = orig[y0:y1, x0:x1]

    from PIL import Image
    out = Image.fromarray(arr)
    draw = ImageDraw.Draw(out)
    for (kind, ebox, mask, ox, oy, bg, thick), text in zip(plans, texts):
        text = (text or "").strip()
        if not text:
            continue
        fg = (0, 0, 0) if luminance(bg) > 128 else (255, 255, 255)
        if kind == "mask":
            draw_in_mask(draw, text, mask, ox, oy, fg, bg, thick)
        else:
            sbg = (255, 255, 255) if fg == (0, 0, 0) else (0, 0, 0)
            draw_in_box(draw, text, ebox, fg, sbg, thick)
    return out
