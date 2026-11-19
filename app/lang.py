"""Language helpers: read numbers and claims written in words, in English,
Hinglish (Hindi in Roman script) and Hindi (Devanagari).

Examples it understands:
  "₹7,000", "Rs 7k", "seven thousand rupees", "saat hazaar rupaye", "सात हज़ार रुपये", "₹७,०००"
  "50% off", "fifty percent off", "pachas pratishat chhoot", "५०% छूट", "half price", "aadhe daam"
  "5-year warranty", "do saal ki warranty", "दो साल की वारंटी"
Every match keeps its exact position in the original text, so findings can be highlighted
and fixed in place.
"""
from __future__ import annotations

import re

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
L = r"(?<![\w\u0900-\u0963\u0966-\u097F])"   # left word boundary that also works for Devanagari
R = r"(?![\w\u0900-\u0963\u0966-\u097F])"    # right word boundary

WORDS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
    # Hinglish (Roman Hindi). "saath" (60) is left out on purpose: it also means "with".
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6, "saat": 7, "aath": 8,
    "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20, "pachees": 25, "pachchees": 25, "tees": 30,
    "chalis": 40, "chaalis": 40, "paintalis": 45, "pachas": 50, "pachaas": 50, "pachpan": 55, "sattar": 70, "assi": 80,
    "nabbe": 90, "dedh": 1.5, "dhai": 2.5, "dhaai": 2.5,
    # Hindi (Devanagari)
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पैंतालीस": 45, "पचास": 50, "साठ": 60, "सत्तर": 70,
    "अस्सी": 80, "नब्बे": 90, "डेढ़": 1.5, "ढाई": 2.5,
}
MULT = {
    "hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000, "crore": 10000000,
    "sau": 100, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "hajaar": 1000,
    "सौ": 100, "हज़ार": 1000, "हजार": 1000, "लाख": 100000, "करोड़": 10000000, "k": 1000,
}

_ALL = sorted(list(WORDS) + list(MULT), key=len, reverse=True)
_WORD_ALT = "|".join(re.escape(w) for w in _ALL if w != "k")
NUMTOK = r"(?:[\d०-९]+(?:[.,][\d०-९]+)*k?|(?:" + _WORD_ALT + r"))"
PHRASE = L + NUMTOK + r"(?:(?:\s+|-)(?:and\s+)?" + NUMTOK + r")*" + R
PHRASE_RE = re.compile(PHRASE, re.I)


def parse_number(phrase: str) -> float | None:
    """'seven thousand' -> 7000, 'saat hazaar' -> 7000, '१०,०००' -> 10000, '7k' -> 7000, 'dedh lakh' -> 150000."""
    s = phrase.translate(DEV_DIGITS).lower().replace("-", " ")
    toks = [t for t in re.split(r"\s+", s) if t and t != "and"]
    total, current, seen = 0.0, 0.0, False
    for t in toks:
        k = False
        if re.fullmatch(r"\d+(?:[.,]\d+)*k?", t):
            k = t.endswith("k")
            t = t.rstrip("k")
            # "10,000" -> 10000 ; "1.5" -> 1.5 ; "10.000" (rare) -> 10000
            if "," in t:
                n = float(t.replace(",", ""))
            else:
                n = float(t)
            current += n
            seen = True
            if k:
                total += current * 1000
                current = 0
            continue
        if t in WORDS:
            current += WORDS[t]
            seen = True
        elif t in MULT:
            m = MULT[t]
            if m == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * m
                current = 0
            seen = True
        else:
            return None
    return total + current if seen else None


def is_words(phrase: str) -> bool:
    return bool(re.search(r"[A-Za-zऀ-ॿ]{2,}", phrase.replace("k", "")))


CUR_BEFORE = r"(?:₹|\brs\.?|\binr\b|\brupees?\b|रु\.?)"
CUR_AFTER = r"(?:rupees?|rupaye|rupaiye|rupay|rupaya|rs\.?|/-|रुपये|रुपए|रुपया|रु\.?)"
_PRICE_1 = re.compile(r"(" + CUR_BEFORE + r")\s?(" + NUMTOK + r"(?:(?:\s+|-)(?:and\s+)?" + NUMTOK + r")*)" + R + r"(?:\s*/-)?", re.I)
_PRICE_2 = re.compile(PHRASE + r"\s*" + CUR_AFTER + R, re.I)


def find_prices(text: str) -> list[dict]:
    out = []
    for m in _PRICE_1.finditer(text):
        v = parse_number(m.group(2))
        if v is not None:
            out.append({"start": m.start(), "end": m.end(), "value": v, "text": m.group(0), "words": is_words(m.group(2))})
    for m in _PRICE_2.finditer(text):
        if any(m.start() < o["end"] and o["start"] < m.end() for o in out):
            continue
        num = PHRASE_RE.match(text, m.start())
        v = parse_number(num.group(0)) if num else None
        if v is not None:
            out.append({"start": m.start(), "end": m.end(), "value": v, "text": m.group(0), "words": is_words(num.group(0))})
    return sorted(out, key=lambda o: o["start"])


PCT = r"(?:%|\s?percent\b|\s?per\s?cent\b|\s?pratishat\b|\s?prateeshat\b|\s?fisadi\b|\s?feesadi\b|\s?प्रतिशत|\s?फीसदी|\s?फ़ीसदी)"
OFF = r"(?:\s*(?:off|discount|flat|cashback|chhoot|chhut|chut|ki\s+chhoot|की\s+छूट|छूट|डिस्काउंट|ऑफ))"
_DISC_1 = re.compile(r"(?P<num>" + PHRASE + r")" + PCT + OFF, re.I)
_DISC_2 = re.compile(r"(?:flat|up\s?to|upto|save|tak|तक)\s?(?P<num>" + PHRASE + r")" + PCT, re.I)
_DISC_3 = re.compile(r"(?P<num>" + PHRASE + r")" + PCT + r"\s*(?:tak\s+)?(?:ki\s+)?(?:chhoot|chhut|छूट|discount|off)", re.I)
HALF = re.compile(L + r"(?:half[\s-]price|half\s+off|aadhe\s+daam|aadhe\s+dam|adhe\s+daam|आधे\s+दाम|आधी\s+कीमत)" + R, re.I)


def find_discounts(text: str) -> list[dict]:
    out = []
    for rx in (_DISC_1, _DISC_2, _DISC_3):
        for m in rx.finditer(text):
            ns, ne = m.span("num")
            if any(ns < o["num_end"] and o["num_start"] < ne for o in out):
                continue
            v = parse_number(m.group("num"))
            if v is None:
                continue
            out.append({"start": m.start(), "end": m.end(), "num_start": ns, "num_end": ne, "value": v, "text": m.group(0),
                        "words": is_words(m.group("num"))})
    for m in HALF.finditer(text):
        out.append({"start": m.start(), "end": m.end(), "num_start": m.start(), "num_end": m.end(), "value": 50.0,
                    "text": m.group(0), "words": True, "phrase": True})
    return sorted(out, key=lambda o: o["start"])


YEARS = r"\s*-?\s*(?:years?|yrs?|saal|sal|varsh|साल|वर्ष)"
WARRANTY = r"(?:warranty|warrantee|guarantee|वारंटी|गारंटी)"
_WAR_1 = re.compile(r"(?P<num>" + PHRASE + r")" + YEARS + r"(?:\s+(?:of|ki|की|का))?\s+" + WARRANTY, re.I)
_WAR_2 = re.compile(WARRANTY + r"\s+(?:of|for)\s+(?P<num>" + PHRASE + r")" + YEARS, re.I)
LIFETIME = re.compile(
    L + r"(?:(?:lifetime|life-long|lifelong|aajeevan|aajivan|आजीवन|zindagi\s+bhar\s+(?:ki|ka)|umr\s+bhar\s+(?:ki|ka)|"
    r"jeevan\s+bhar\s+(?:ki|ka)|जीवन\s+भर\s+(?:की|का)|ज़िंदगी\s+भर\s+(?:की|का)|जिंदगी\s+भर\s+(?:की|का))\s+" + WARRANTY + r"|"
    + WARRANTY + r"\s+(?:for\s+life|for\s+a\s+lifetime|that\s+never\s+(?:ends|expires)|forever|kabhi\s+khatam\s+nahi(?:\s+hogi)?))" + R, re.I)


def find_warranty_years(text: str) -> list[dict]:
    out = []
    for rx in (_WAR_1, _WAR_2):
        for m in rx.finditer(text):
            if any(m.start() < o["end"] and o["start"] < m.end() for o in out):
                continue
            v = parse_number(m.group("num"))
            if v is not None:
                out.append({"start": m.start(), "end": m.end(), "value": v, "text": m.group(0)})
    return out


HOURS = r"\s*\+?\s*(?:hours?|hrs?|h|ghante|ghanta|घंटे|घंटा)" + R
BATTERY = r"(?:battery|batteri|playback|play\s?time|music|बैटरी|प्लेबैक)"
_BAT_1 = re.compile(r"(?P<num>" + PHRASE + r")" + HOURS + r"(?:\s+(?:of|ki|की|का))?\s+" + BATTERY, re.I)
_BAT_2 = re.compile(BATTERY + r"(?:\s+life)?\D{0,25}?(?P<num>" + PHRASE + r")" + HOURS, re.I)
ENDLESS_BATTERY = re.compile(
    r"(?:battery|बैटरी)[^.!?\n]{0,30}?(?:never\s+(?:runs?\s+out|dies|ends)|lasts\s+forever|kabhi\s+khatam\s+nahi|kabhi\s+khatm\s+nahi|"
    r"कभी\s+खत्म\s+नहीं|कभी\s+ख़त्म\s+नहीं)|"
    r"(?:never|no\s+need\s+to)\s+(?:needs?\s+)?charg(?:e|ing)|kabhi\s+charge\s+(?:karne\s+ki\s+zaroorat\s+)?nahi|unlimited\s+battery", re.I)


def find_battery_hours(text: str) -> list[dict]:
    out = []
    for rx in (_BAT_1, _BAT_2):
        for m in rx.finditer(text):
            ns, ne = m.span("num")
            if any(ns < o["num_end"] and o["num_start"] < ne for o in out):
                continue
            v = parse_number(m.group("num"))
            if v is not None:
                out.append({"num_start": ns, "num_end": ne, "value": v, "text": m.group(0)})
    return out


OFFER_WORDS = re.compile(r"\b(?:off|discount|sale|offer|deal|cashback|chhoot|chhut)\b|छूट|ऑफर|सेल|डिस्काउंट", re.I)
DISCLAIMER = re.compile(r"t\s?&\s?c|terms\s+(?:and|&)\s+conditions|conditions\s+apply|sharte[nm]?\s+lagu|शर्तें\s+लागू|नियम\s+व\s+शर्तें", re.I)

SUPERLATIVES_HI = [
    r"(?:india|bharat|desh|hindustan)\s+(?:ka|ki|ke)\s+(?:no\.?\s?1|number\s+(?:one|1|ek)|sabse\s+(?:best|accha|achha|badhiya|behtareen))",
    r"(?:भारत|देश|हिंदुस्तान)\s+(?:का|की|के)\s+(?:नंबर\s?(?:1|१|वन)|सबसे\s+(?:अच्छा|बेहतरीन|बढ़िया))",
    r"sabse\s+(?:best|accha|achha|acha|badhiya|behtareen|top)",
    r"सबसे\s+(?:अच्छा|अच्छी|बेहतरीन|बढ़िया|बेस्ट)",
    r"नंबर\s?(?:1|१|वन)",
    r"(?:top[- ]rated|most\s+loved|most\s+popular|world[- ]famous)",
]
GUARANTEES_HI = [
    (r"pakk[ai]\s+(?:guarantee|result|results)", "reliable results"),
    (r"100\s?%\s+guarantee(?:d)?\s+(?:result|results|performance)", "reliable performance"),
    (r"पक्की\s+गारंटी", "भरोसेमंद"),
    (r"100\s?%\s+गारंटी", "भरोसेमंद"),
]
URGENCY_HI = r"(?:jaldi\s+(?:karo|kijiye|kare|karein)|aakhri\s+mauka|akhri\s+mauka|aakhiri\s+mauka|sirf\s+aaj|bas\s+aaj|आखिरी\s+मौका|आख़िरी\s+मौका|जल्दी\s+करें|जल्दी\s+करो|सिर्फ\s+आज|stock\s+khatam\s+hone\s+se\s+pehle)"
HYPE_HI = [(r"dhamakedar|dhamaakedar|धमाकेदार", "great"), (r"bawaal|bawal|बवाल", "great"), (r"jhakaas|jhakas|झकास", "great"),
           (r"mind[- ]?blowing", "impressive")]
