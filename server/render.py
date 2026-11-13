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


def get_font(size, weight=b"SemiBold"):
    if FONT_PATH is None:
        raise RuntimeError("Devanagari font nahi mila. server/fonts mein NotoSansDevanagari-Regular.ttf rakho.")
    font = _fonts.get((size, weight))
    if font is None:
        layout = ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC
        font = ImageFont.truetype(FONT_PATH, size, layout_engine=layout)
        try:
            if weight in font.get_variation_names():
                font.set_variation_by_name(weight)
        except Exception:
            pass  # variable font nahi
        _fonts[(size, weight)] = font
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


def is_sfx(text):
    """AI ne SFX bataya (\x01 nishaan) aur chhota hai: bubble ke bahar ho to bada comic style."""
    t = text.lstrip("\x01").strip()
    return text.startswith("\x01") and 0 < len(t) <= 16


def draw_sfx(draw, text, box):
    """SFX: box jitna bada, mota (ExtraBold), kaala text + moti safed outline, jaise comic SFX."""
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    # khada (vertical) SFX box: Hindi seedhi likhte hain, isliye box ki chaudai se thoda bahar ja sakte hain
    # SFX art ke upar hota hai: box se thoda (30%) bahar jaana theek, chhota padhne layak na rahe wo bura
    bw_eff = max(int(bw * 1.3), int(bh * 0.9)) if bh > 1.6 * bw else int(bw * 1.3)
    size = int(min(bh * 0.85, 110))
    while size > 14:
        font = get_font(size, b"ExtraBold")
        if draw.textlength(text, font=font) <= bw_eff * 0.95:
            break
        size -= 2
    font = get_font(size, b"ExtraBold")
    stroke = max(2, size // 7)
    # page ke kinare se bahar na jaye
    W, H = draw.im.size
    half = draw.textlength(text, font=font) / 2 + stroke + 2
    cx = min(max((x0 + x1) / 2, half), W - half)
    cy = min(max((y0 + y1) / 2, size * 0.6), H - size * 0.6)
    draw.text((cx, cy), text, font=font, fill=(0, 0, 0), anchor="mm",
              stroke_width=stroke, stroke_fill=(255, 255, 255))


def line_mask(arr, box):
    """Box ke andar lambi seedhi lines (panel border, frame): inhe mitana nahi hai."""
    x0, y0, x1, y1 = box
    region = arr[y0:y1, x0:x1]
    if region.size == 0:
        return None
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    dark = (gray < 110).astype(np.uint8)
    h, w = dark.shape
    hor = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((1, max(15, int(w * 0.6))), np.uint8))
    ver = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((max(15, int(h * 0.6)), 1), np.uint8))
    return cv2.dilate(hor | ver, np.ones((3, 3), np.uint8), iterations=1)


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


def _interior(arr, ebox, around=None):
    """Text ke chaaron taraf ka band safed (ya bubble rang) hissa: mitana isi ke andar.
    Return ebox jitna mask, ya None agar safed area na mile."""
    H, W = arr.shape[:2]
    x0, y0, x1, y1 = around or ebox
    pad = 12
    X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    gray = cv2.cvtColor(arr[Y0:Y1, X0:X1], cv2.COLOR_RGB2GRAY)
    bright = (gray > 170).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bright, connectivity=4)
    ex0, ey0, ex1, ey1 = ebox
    inner = labels[ey0 - Y0:ey1 - Y0, ex0 - X0:ex1 - X0]
    if inner.size == 0 or n < 2:
        return None
    counts = np.bincount(inner.ravel(), minlength=n)
    counts[0] = 0
    k = int(counts.argmax())
    if counts[k] < 0.25 * inner.size:
        return None
    comp = (labels == k).astype(np.uint8)
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(comp)
    cv2.drawContours(filled, [max(cs, key=cv2.contourArea)], -1, 1, -1)  # text ke chhed bhar do
    filled = cv2.erode(filled, np.ones((3, 3), np.uint8), iterations=2)   # outline se door
    return filled[ey0 - Y0:ey1 - Y0, ex0 - X0:ex1 - X0]


def _erase(arr, ebox, m, bg, around=None):
    """m (text mask) ko bubble ke andar tak seemit karke bg rang bharo."""
    inside = _interior(arr, ebox, around)
    if inside is not None:
        m = m & inside
    arr[ebox[1]:ebox[3], ebox[0]:ebox[2]][m.astype(bool)] = bg


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
                _erase(arr, ebox, m, bg, around=g["bbox"])
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
            if flat:
                m = inpaint.text_mask(arr, ebox, grow=4)
                lines = line_mask(arr, ebox)
                if m is not None and lines is not None:
                    m = m & (1 - lines)  # panel ki border mat mitao
            else:
                # art par: letters + unki safed outline, thoda zyada phailao taaki nishaan na bache
                lm = inpaint.letter_mask(arr, ebox, grow=5)
                tm = inpaint.text_mask(arr, ebox, grow=2)
                m = lm if tm is None else np.maximum(lm, tm & cv2.dilate(lm, np.ones((9, 9), np.uint8)))
            if m is not None:
                if flat:
                    _erase(arr, ebox, m, bg)
                else:
                    full = np.zeros((H, W), np.uint8)
                    full[ebox[1]:ebox[3], ebox[0]:ebox[2]] = m
                    inpaint.inpaint_region(arr, full, ebox)
                    # doosra pass: pehli baar ke baad bhi letter ke tukde bache hon to sirf wahi dobara
                    left = inpaint.letter_mask(arr, ebox, grow=3)
                    if left is not None and (left & m).sum() > 0.08 * max(1, m.sum()):
                        full[:] = 0
                        full[ebox[1]:ebox[3], ebox[0]:ebox[2]] = left & cv2.dilate(m, np.ones((5, 5), np.uint8))
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
        sfx = is_sfx(text or "")
        text = (text or "").replace("\x01", "").strip()
        if not text:
            continue
        fg = (0, 0, 0) if luminance(bg) > 128 else (255, 255, 255)
        if kind == "mask":
            draw_in_mask(draw, text, mask, ox, oy, fg, bg, thick)
        else:
            if sfx:
                draw_sfx(draw, text, ebox)
            else:
                sbg = (255, 255, 255) if fg == (0, 0, 0) else (0, 0, 0)
                draw_in_box(draw, text, ebox, fg, sbg, thick)
    return out
