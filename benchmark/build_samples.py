"""Builds benchmark/samples.json — the labelled accuracy set for BrandProof AI.

Each sample: text, expected rule IDs, language (en / hinglish / hi), form (digits / words /
paraphrase / clean), and `ai_only` when we know the rule engine cannot catch it (meaning-based).
Templates are written by the team; prefixes create realistic variants. All brand data is the
fictional ABC Electronics demo brand (price ₹10,000, max discount 20%, warranty 2 years,
battery 30 h, IPX4).

Run:  python -m benchmark.build_samples
"""
import json
import os

PREFIX = {"en": ["", "This Diwali, ", "Weekend special: "],
          "hinglish": ["", "Is Diwali, ", "Naye saal par: "],
          "hi": ["", "इस दिवाली, ", "नए साल पर: "]}

# (text, expected, lang, form, ai_only)
BASE = [
    # ---------------- clean (no issues expected)
    ("SoundPods Pro – Smart Technology for Everyday Life. Now ₹10,000 with a 2-year warranty.", [], "en", "clean", False),
    ("Enjoy clear calls and a comfortable fit with SoundPods Pro, backed by a 2-year warranty.", [], "en", "clean", False),
    ("SoundPods Pro gives you up to 30 hours of battery with the charging case.", [], "en", "clean", False),
    ("Get SoundPods Pro for ₹8,500 with up to 15% off. T&C apply.", [], "en", "clean", False),
    ("Festive offer: up to 20% off on SoundPods Pro. T&C apply.", [], "en", "clean", False),
    ("Visit your nearest ABC store to try SoundPods Pro today.", [], "en", "clean", False),
    ("SoundPods Pro is splash-resistant (IPX4), so a little rain is no problem.", [], "en", "clean", False),
    ("SoundPods Pro: ten thousand rupees, two-year warranty, made for everyday listening.", [], "en", "clean", False),
    ("SoundPods Pro sirf ₹10,000 mein, do saal ki warranty ke saath.", [], "hinglish", "clean", False),
    ("SoundPods Pro par 20 pratishat tak ki chhoot. T&C apply.", [], "hinglish", "clean", False),
    ("Roz ke liye bani SoundPods Pro – 30 ghante ki battery ke saath.", [], "hinglish", "clean", False),
    ("Apne nazdeeki ABC store par SoundPods Pro try kijiye.", [], "hinglish", "clean", False),
    ("SoundPods Pro अब ₹10,000 में, दो साल की वारंटी के साथ।", [], "hi", "clean", False),
    ("SoundPods Pro पर 20 प्रतिशत तक की छूट। शर्तें लागू।", [], "hi", "clean", False),
    ("रोज़ाना इस्तेमाल के लिए SoundPods Pro – 30 घंटे का प्लेबैक।", [], "hi", "clean", False),
    ("Our best-selling colour is back: SoundPods Pro in navy.", [], "en", "clean", False),
    # ---------------- R-PRC-01 price
    ("Buy SoundPods Pro for just ₹7,000 today.", ["R-PRC-01"], "en", "digits", False),
    ("SoundPods Pro now ₹12,000 only.", ["R-PRC-01"], "en", "digits", False),
    ("SoundPods Pro at Rs 7k – grab yours.", ["R-PRC-01"], "en", "digits", False),
    ("Buy SoundPods Pro for seven thousand rupees.", ["R-PRC-01"], "en", "words", False),
    ("SoundPods Pro for Rs. 7 thousand only.", ["R-PRC-01"], "en", "words", False),
    ("SoundPods Pro sirf saat hazaar rupaye mein.", ["R-PRC-01"], "hinglish", "words", False),
    ("SoundPods Pro ab barah hazaar rupaye mein.", ["R-PRC-01"], "hinglish", "words", False),
    ("SoundPods Pro सिर्फ सात हज़ार रुपये में।", ["R-PRC-01"], "hi", "words", False),
    ("SoundPods Pro अब ₹७,००० में।", ["R-PRC-01"], "hi", "digits", False),
    ("SoundPods Pro costs less than a weekend pizza party.", ["R-PRC-01"], "en", "paraphrase", True),
    # ---------------- R-PRC-02 discount (with disclaimer, so only the discount is wrong)
    ("Get 50% OFF on SoundPods Pro. T&C apply.", ["R-PRC-02"], "en", "digits", False),
    ("Flat 35% discount on SoundPods Pro. T&C apply.", ["R-PRC-02"], "en", "digits", False),
    ("Get fifty percent off SoundPods Pro. T&C apply.", ["R-PRC-02"], "en", "words", False),
    ("SoundPods Pro at half price this week. T&C apply.", ["R-PRC-02"], "en", "paraphrase", False),
    ("SoundPods Pro par pachas pratishat chhoot. T&C apply.", ["R-PRC-02"], "hinglish", "words", False),
    ("SoundPods Pro aadhe daam par! T&C apply.", ["R-PRC-02"], "hinglish", "paraphrase", False),
    ("SoundPods Pro पर पचास प्रतिशत की छूट। शर्तें लागू।", ["R-PRC-02"], "hi", "words", False),
    ("SoundPods Pro पर ५०% छूट। शर्तें लागू।", ["R-PRC-02"], "hi", "digits", False),
    ("Pay for one, take two SoundPods Pro home. T&C apply.", ["R-PRC-02"], "en", "paraphrase", True),
    # ---------------- R-PRC-03 missing disclaimer
    ("SoundPods Pro: up to 20% off this festive season.", ["R-PRC-03"], "en", "digits", False),
    ("Festive sale on SoundPods Pro starts today.", ["R-PRC-03"], "en", "words", False),
    ("SoundPods Pro par 20 pratishat tak ki chhoot.", ["R-PRC-03"], "hinglish", "words", False),
    ("SoundPods Pro पर 20 प्रतिशत की छूट।", ["R-PRC-03"], "hi", "words", False),
    # ---------------- R-WAR-01 warranty
    ("SoundPods Pro comes with a lifetime warranty.", ["R-WAR-01"], "en", "digits", False),
    ("Relax with a 5-year warranty on SoundPods Pro.", ["R-WAR-01"], "en", "digits", False),
    ("SoundPods Pro – covered by warranty for life.", ["R-WAR-01"], "en", "paraphrase", False),
    ("SoundPods Pro par paanch saal ki warranty.", ["R-WAR-01"], "hinglish", "words", False),
    ("SoundPods Pro ke saath aajeevan warranty.", ["R-WAR-01"], "hinglish", "paraphrase", False),
    ("SoundPods Pro par zindagi bhar ki warranty.", ["R-WAR-01"], "hinglish", "paraphrase", False),
    ("SoundPods Pro के साथ आजीवन वारंटी।", ["R-WAR-01"], "hi", "paraphrase", False),
    ("SoundPods Pro पर पांच साल की वारंटी।", ["R-WAR-01"], "hi", "words", False),
    ("A warranty that outlives your phone – only on SoundPods Pro.", ["R-WAR-01"], "en", "paraphrase", True),
    # ---------------- R-SPEC-01 specs
    ("SoundPods Pro offers 40 hours of battery life.", ["R-SPEC-01"], "en", "digits", False),
    ("Swim with SoundPods Pro – fully waterproof.", ["R-SPEC-01"], "en", "digits", False),
    ("SoundPods Pro is rated IP68 for total protection.", ["R-SPEC-01"], "en", "digits", False),
    ("With SoundPods Pro, your battery never runs out.", ["R-SPEC-01"], "en", "paraphrase", False),
    ("SoundPods Pro never needs charging on a normal day.", ["R-SPEC-01"], "en", "paraphrase", False),
    ("SoundPods Pro mein chalis ghante ki battery.", ["R-SPEC-01"], "hinglish", "words", False),
    ("SoundPods Pro ki battery kabhi khatam nahi hoti.", ["R-SPEC-01"], "hinglish", "paraphrase", False),
    ("SoundPods Pro: बैटरी 40 घंटे।", ["R-SPEC-01"], "hi", "digits", False),
    ("One charge of SoundPods Pro lasts the whole week.", ["R-SPEC-01"], "en", "paraphrase", True),
    ("Take SoundPods Pro scuba diving this summer.", ["R-SPEC-01"], "en", "paraphrase", True),
    # ---------------- R-CLM-01 superlatives
    ("ABC Electronics – India's No. 1 Brand for audio.", ["R-CLM-01"], "en", "digits", False),
    ("SoundPods Pro: the best earbuds you can buy.", ["R-CLM-01"], "en", "words", False),
    ("Unbeatable sound from SoundPods Pro.", ["R-CLM-01"], "en", "words", False),
    ("SoundPods Pro: the top-rated earbuds of 2026.", ["R-CLM-01"], "en", "paraphrase", False),
    ("SoundPods Pro – sabse best earbuds.", ["R-CLM-01"], "hinglish", "words", False),
    ("ABC – India ka number one audio brand.", ["R-CLM-01"], "hinglish", "words", False),
    ("ABC – भारत का नंबर 1 ऑडियो ब्रांड।", ["R-CLM-01"], "hi", "digits", False),
    ("SoundPods Pro – सबसे बेहतरीन ईयरबड्स।", ["R-CLM-01"], "hi", "words", False),
    ("Nine out of ten music teachers prefer SoundPods Pro.", ["R-CLM-01"], "en", "paraphrase", True),
    ("No other earbuds come close to SoundPods Pro.", ["R-CLM-01"], "en", "paraphrase", True),
    # ---------------- R-CLM-02 guarantees
    ("100% guaranteed performance from SoundPods Pro.", ["R-CLM-02"], "en", "digits", False),
    ("SoundPods Pro never fails, whatever you do.", ["R-CLM-02"], "en", "words", False),
    ("SoundPods Pro – pakka result guarantee.", ["R-CLM-02"], "hinglish", "words", False),
    ("SoundPods Pro – पक्की गारंटी।", ["R-CLM-02"], "hi", "words", False),
    ("SoundPods Pro will make you sleep better, guaranteed or nothing.", ["R-CLM-02"], "en", "paraphrase", True),
    # ---------------- R-TERM-01 / R-TERM-02
    ("Looking for cheap earbuds? Try SoundPods Pro.", ["R-TERM-01"], "en", "words", False),
    ("ABC Earbuds are back in stock.", ["R-TERM-01"], "en", "words", False),
    ("SoundPods Pro is risk-free to try.", ["R-TERM-01"], "en", "words", False),
    ("Cheap mein accha – SoundPods Pro.", ["R-TERM-01"], "hinglish", "words", False),
    ("Grab Sound Pods Pro at your nearest store.", ["R-TERM-02"], "en", "words", False),
    ("Soundpods ab har ABC store par.", ["R-TERM-02"], "hinglish", "words", False),
    # ---------------- R-VOICE-01 / R-VOICE-02
    ("OMG, SoundPods Pro sounds amazing.", ["R-VOICE-01"], "en", "words", False),
    ("SoundPods Pro is INSANE value!!", ["R-VOICE-01"], "en", "words", False),
    ("SoundPods Pro – ekdum dhamakedar sound.", ["R-VOICE-01"], "hinglish", "words", False),
    ("Hurry, SoundPods Pro is selling fast.", ["R-VOICE-02"], "en", "words", False),
    ("Last chance to try SoundPods Pro in store.", ["R-VOICE-02"], "en", "words", False),
    ("Jaldi karo, SoundPods Pro stock mein kam hai.", ["R-VOICE-02"], "hinglish", "words", False),
    ("SoundPods Pro – aakhri mauka store par try karne ka.", ["R-VOICE-02"], "hinglish", "words", False),
    ("सिर्फ आज: SoundPods Pro स्टोर पर देखें।", ["R-VOICE-02"], "hi", "words", False),
    ("If you wait, you will regret it forever – get SoundPods Pro.", ["R-VOICE-02"], "en", "paraphrase", True),
    # ---------------- R-CONF-01
    ("Something exciting is coming: Project Falcon.", ["R-CONF-01"], "en", "words", False),
    ("The new SoundPods Max will launch soon.", ["R-CONF-01"], "en", "words", False),
    ("Naya SoundPods Max jaldi aa raha hai.", ["R-CONF-01"], "hinglish", "words", False),
    # ---------------- R-A11Y-01
    ("SoundPods Pro is designed with care for people who listen to music on long journeys, during busy work days, at the gym and late at night when everyone else in the house is asleep and quiet.",
     ["R-A11Y-01"], "en", "words", False),
    # ---------------- R-MSG-01 (meaning-based, AI only)
    ("Better than Brand X earbuds, which break in a month.", ["R-MSG-01"], "en", "paraphrase", True),
    ("Other earbuds will ruin your hearing – choose SoundPods Pro.", ["R-MSG-01"], "en", "paraphrase", True),
    ("Brand X waale earbuds ek mahine mein toot jaate hain, SoundPods Pro lijiye.", ["R-MSG-01"], "hinglish", "paraphrase", True),
    ("दूसरे ब्रांड के ईयरबड्स आपके कान खराब कर देंगे।", ["R-MSG-01"], "hi", "paraphrase", True),
    # ---------------- mixed real-world ads
    ("ABC Electronics – India's No. 1 Brand! Buy SoundPods Pro for just ₹7,000. Get 50% OFF. 100% guaranteed performance with lifetime warranty!!",
     ["R-CLM-01", "R-PRC-01", "R-PRC-02", "R-CLM-02", "R-WAR-01", "R-VOICE-01", "R-PRC-03"], "en", "digits", False),
    ("OMG this weekend is INSANE! SoundPods Pro at ₹12,000 with a killer deal. Don't miss out!!",
     ["R-VOICE-01", "R-PRC-01", "R-TERM-01", "R-VOICE-02", "R-PRC-03"], "en", "digits", False),
    ("SoundPods Pro sirf saat hazaar rupaye mein! Aadhe daam par, aajeevan warranty ke saath. Jaldi karo!",
     ["R-PRC-01", "R-PRC-02", "R-WAR-01", "R-VOICE-02", "R-PRC-03"], "hinglish", "words", False),
    ("सिर्फ सात हज़ार रुपये में SoundPods Pro! पचास प्रतिशत की छूट और आजीवन वारंटी। भारत का नंबर 1 ब्रांड।",
     ["R-PRC-01", "R-PRC-02", "R-WAR-01", "R-CLM-01", "R-PRC-03"], "hi", "words", False),
]


def build():
    out = []
    for text, exp, lang, form, ai_only in BASE:
        prefixes = PREFIX[lang] if not ai_only and len(exp) <= 1 else [""]
        for p in prefixes:
            t = p + (text[0].lower() + text[1:] if p and text[:1].isupper() and not text.startswith(("ABC", "SoundPods", "Sound", "OMG", "INSANE")) else text)
            out.append({"text": t, "expect": exp, "lang": lang, "form": form, "ai_only": ai_only})
    return out


if __name__ == "__main__":
    s = build()
    path = os.path.join(os.path.dirname(__file__), "samples.json")
    json.dump(s, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(s), "samples written to", path)
