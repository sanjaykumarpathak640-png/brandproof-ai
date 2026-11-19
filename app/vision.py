"""Creative (image) checks: read the text inside an image, measure each text block's
contrast, and check that the approved logo is present.

- Text reading uses the Gemini vision model (returns each line with a bounding box).
  Results are cached by image hash, so re-checking the same image is instant and free.
- Logo presence is checked twice: (1) pixel template matching with NumPy (works
  without AI), (2) the vision model, which also handles resized or recoloured logos.
- Per-text contrast is measured inside each text box (WCAG ratio), not guessed for
  the whole image.
"""
from __future__ import annotations

import base64
import hashlib
import io

import numpy as np
from PIL import Image

from . import ai
from .extract import contrast


def _img(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    head, b64 = data_url.split(",", 1)
    return base64.b64decode(b64), head[5:].split(";")[0]


# ---------------------------------------------------------------- per-box contrast

def box_contrast(img: Image.Image, box: list[float]) -> float | None:
    """box = [ymin, xmin, ymax, xmax] on a 0-1000 scale. Returns the WCAG contrast
    between the two dominant colours inside the box (text vs background)."""
    w, h = img.size
    y0, x0, y1, x1 = box
    l, t, r, b = int(x0 / 1000 * w), int(y0 / 1000 * h), int(x1 / 1000 * w), int(y1 / 1000 * h)
    if r - l < 4 or b - t < 4:
        return None
    crop = img.crop((max(0, l), max(0, t), min(w, r), min(h, b)))
    crop.thumbnail((240, 240))
    qz = crop.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = qz.getpalette()
    cols = sorted(qz.getcolors() or [], reverse=True)
    if len(cols) < 2:
        return None
    total = sum(n for n, _ in cols)
    bg = tuple(pal[cols[0][1] * 3: cols[0][1] * 3 + 3])  # most common colour = background
    # text colour = the cluster (at least 4% of the box) that stands out most from the background
    cands = [tuple(pal[i * 3: i * 3 + 3]) for n, i in cols[1:] if n / total >= 0.04]
    if not cands:
        return None
    fg = max(cands, key=lambda c: contrast(c, bg))
    return round(contrast(fg, bg), 2)


# ---------------------------------------------------------------- logo template matching (no AI)

def _gray(img: Image.Image, width: int) -> np.ndarray:
    im = img.copy()
    ratio = width / im.size[0]
    im = im.resize((width, max(8, int(im.size[1] * ratio))))
    return np.asarray(im.convert("L"), dtype=np.float64)


def _ncc_max(I: np.ndarray, T: np.ndarray) -> tuple[float, tuple[int, int]]:
    """Max normalised cross-correlation of template T over image I (FFT + integral images)."""
    th, tw = T.shape
    H, W = I.shape
    if th >= H or tw >= W or th < 6 or tw < 6:
        return 0.0, (0, 0)
    Tz = T - T.mean()
    tnorm = np.sqrt((Tz ** 2).sum())
    if tnorm < 1e-6:
        return 0.0, (0, 0)
    fh, fw = H + th, W + tw
    F = np.fft.rfft2(I, s=(fh, fw)) * np.conj(np.fft.rfft2(Tz, s=(fh, fw)))
    corr = np.fft.irfft2(F, s=(fh, fw))[: H - th + 1, : W - tw + 1]
    S = np.pad(I, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    S2 = np.pad(I ** 2, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def win(A):
        return A[th:, tw:] - A[:-th, tw:] - A[th:, :-tw] + A[:-th, :-tw]
    n = th * tw
    s1, s2 = win(S), win(S2)
    var = np.maximum(s2 - s1 ** 2 / n, 1e-6)
    ncc = corr / (np.sqrt(var) * tnorm)
    idx = np.unravel_index(np.argmax(ncc), ncc.shape)
    return float(ncc[idx]), (int(idx[0]), int(idx[1]))


def match_logo(creative: Image.Image, logo: Image.Image) -> dict:
    W = 320
    I = _gray(creative, W)
    best = {"score": 0.0, "box": None}
    for frac in np.linspace(0.06, 0.45, 14):
        tw = int(W * frac)
        T = _gray(logo, tw)
        sc, (y, x) = _ncc_max(I, T)
        if sc > best["score"]:
            H = I.shape[0]
            best = {"score": round(sc, 3), "box": [round(y / H * 1000), round(x / W * 1000),
                                                  round((y + T.shape[0]) / H * 1000), round((x + T.shape[1]) / W * 1000)]}
    best["present"] = best["score"] >= 0.82
    return best


# ---------------------------------------------------------------- main entry

def analyse_creative(image_bytes: bytes, mime: str, logo_data_url: str | None, *, use_ai: bool) -> dict:
    """Returns {'text': {...}, 'logo': {...}} — text lines with boxes and per-box contrast, and the logo result."""
    img = _img(image_bytes)
    out: dict = {"text": {"status": "skipped", "lines": [], "model": None, "reason": ""},
                 "logo": {"status": "skipped", "present": None, "method": None, "box": None, "score": None, "reason": ""}}

    logo_bytes = logo_mime = None
    if logo_data_url:
        logo_bytes, logo_mime = decode_data_url(logo_data_url)

    # 1) one AI call reads the text, drafts alt text and double-checks the logo
    res = None
    if not use_ai:
        out["text"]["reason"] = "Confidential mode: the image was not sent to any AI service, so text inside it was not read."
    elif not ai.available():
        out["text"]["reason"] = "No AI key configured, so text inside the image could not be read."
    else:
        res = ai.read_creative(image_bytes, mime, logo_bytes, logo_mime)
        if res.get("error"):
            out["text"].update(status="error", reason=res["error"])
            res = None
        else:
            lines = []
            for ln in res.get("lines", []):
                box = ln.get("box")
                lines.append({"text": ln["text"], "box": box, "contrast": box_contrast(img, box) if box else None})
            out["text"].update(status="ok", lines=lines, model=res.get("model"), cached=res.get("cached", False))
            out["alt"] = res.get("alt")

    # 2) logo: pixel template matching first (no AI); the vision model's answer is used when pixels don't match
    if logo_bytes:
        tm = match_logo(img, _img(logo_bytes))
        out["logo"].update(status="ok", present=tm["present"], method="pixel match", box=tm["box"] if tm["present"] else None, score=tm["score"])
        ai_logo = (res or {}).get("logo")
        if ai_logo:
            out["logo"]["ai"] = ai_logo
            if not tm["present"]:
                out["logo"]["method"] = "pixel match + vision model"
                out["logo"]["notes"] = ai_logo.get("notes", "")
                if ai_logo.get("present"):
                    out["logo"].update(present=True, method="vision model", box=ai_logo.get("box"), altered=ai_logo.get("altered"))
            elif ai_logo.get("altered"):
                out["logo"].update(altered=True, notes=ai_logo.get("notes", ""))
    else:
        out["logo"]["reason"] = "No approved logo in Brand Memory yet. The Brand Admin can upload one."
    return out


def image_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
