"""Text extraction for PDF / DOCX / TXT and measured visual checks for images."""
from __future__ import annotations

import io
import math
import re

from PIL import Image


def extract_text(filename: str, data: bytes) -> dict:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        parts, pages, pos = [], [], 0
        for p in reader.pages:
            t = (p.extract_text() or "").strip()
            t = re.sub(r"[ \t]+\n", "\n", t)
            pages.append(pos)
            parts.append(t)
            pos += len(t) + 2
        return {"text": "\n\n".join(parts), "pages": pages, "kind": "pdf", "page_count": len(pages)}
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
        return {"text": "\n\n".join(paras), "pages": None, "kind": "docx", "page_count": None}
    if name.endswith((".txt", ".md")):
        return {"text": data.decode("utf-8", errors="ignore"), "pages": None, "kind": "txt", "page_count": None}
    raise ValueError("Unsupported file type. Use PDF, DOCX, TXT, PNG or JPG.")


# ---------------------------------------------------------------- colour science

def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(int(c) for c in rgb)


def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb):
    r, g, b = (_lin(c) for c in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(c1, c2) -> float:
    """CIE76 colour difference. ~2 is barely visible, >10 is clearly a different colour."""
    a, b = rgb_to_lab(c1), rgb_to_lab(c2)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def luminance(rgb):
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1, c2) -> float:
    l1, l2 = sorted([luminance(c1), luminance(c2)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def analyse_image(data: bytes, palette: list[dict], de_limit: float = 20.0) -> dict:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    small = img.copy()
    small.thumbnail((200, 200))
    q = small.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    brand = [(p["name"], hex_to_rgb(p["hex"]), p["hex"]) for p in palette]
    colours = []
    for cnt, idx in counts:
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        share = cnt / total
        best = min(brand, key=lambda b: delta_e(rgb, b[1])) if brand else None
        de = delta_e(rgb, best[1]) if best else 0
        colours.append({"hex": rgb_to_hex(rgb), "share": round(share * 100, 1), "nearest": best[0] if best else None,
                        "nearest_hex": best[2] if best else None, "delta_e": round(de, 1),
                        "on_palette": de <= de_limit})
    main = [c for c in colours if c["share"] >= 8]
    off = [c for c in main if not c["on_palette"]]
    est_contrast = None
    if len(colours) >= 2:
        est_contrast = round(contrast(hex_to_rgb(colours[0]["hex"]), hex_to_rgb(colours[1]["hex"])), 2)
    palette_match = round(sum(c["share"] for c in colours if c["on_palette"]), 1)
    return {"width": w, "height": h, "colours": colours, "off_palette": off, "palette_match": palette_match,
            "contrast_estimate": est_contrast, "de_limit": de_limit}
