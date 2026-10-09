import re

DEFAULT = "it"

LANGS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "it": ("italiano", "italiano", ("italiano", "italian", "italien", "italienisch", "italiano")),
    "en": ("inglese", "English", ("inglese", "english", "anglais", "englisch", "inglés", "ingles", "inglês")),
    "es": ("spagnolo", "español", ("spagnolo", "spanish", "español", "espanol", "espagnol", "spanisch", "castigliano")),
    "fr": ("francese", "français", ("francese", "french", "français", "francais", "französisch", "francés")),
    "de": ("tedesco", "Deutsch", ("tedesco", "german", "deutsch", "allemand", "alemán", "aleman")),
    "pt": ("portoghese", "português", ("portoghese", "portuguese", "português", "portugues", "brasiliano")),
    "nl": ("olandese", "Nederlands", ("olandese", "dutch", "nederlands", "fiammingo")),
    "ru": ("russo", "русский", ("russo", "russian", "русский")),
    "uk": ("ucraino", "українська", ("ucraino", "ukrainian")),
    "pl": ("polacco", "polski", ("polacco", "polish", "polski")),
    "cs": ("ceco", "čeština", ("ceco", "czech")),
    "sk": ("slovacco", "slovenčina", ("slovacco", "slovak")),
    "sl": ("sloveno", "slovenščina", ("sloveno", "slovenian")),
    "hr": ("croato", "hrvatski", ("croato", "croatian")),
    "sr": ("serbo", "српски", ("serbo", "serbian")),
    "bg": ("bulgaro", "български", ("bulgaro", "bulgarian")),
    "ro": ("rumeno", "română", ("rumeno", "romeno", "romanian")),
    "hu": ("ungherese", "magyar", ("ungherese", "hungarian")),
    "el": ("greco", "ελληνικά", ("greco", "greek")),
    "tr": ("turco", "Türkçe", ("turco", "turkish")),
    "ar": ("arabo", "العربية", ("arabo", "arabic")),
    "he": ("ebraico", "עברית", ("ebraico", "hebrew")),
    "fa": ("persiano", "فارسی", ("persiano", "farsi", "persian")),
    "hi": ("hindi", "हिन्दी", ("hindi",)),
    "ur": ("urdu", "اردو", ("urdu",)),
    "bn": ("bengalese", "বাংলা", ("bengalese", "bengali")),
    "ta": ("tamil", "தமிழ்", ("tamil",)),
    "te": ("telugu", "తెలుగు", ("telugu",)),
    "ml": ("malayalam", "മലയാളം", ("malayalam",)),
    "mr": ("marathi", "मराठी", ("marathi",)),
    "ne": ("nepalese", "नेपाली", ("nepalese", "nepali")),
    "zh": ("cinese", "中文", ("cinese", "mandarino", "chinese", "mandarin")),
    "ja": ("giapponese", "日本語", ("giapponese", "japanese")),
    "ko": ("coreano", "한국어", ("coreano", "korean")),
    "vi": ("vietnamita", "Tiếng Việt", ("vietnamita", "vietnamese")),
    "th": ("thailandese", "ไทย", ("thailandese", "thai")),
    "id": ("indonesiano", "Bahasa Indonesia", ("indonesiano", "indonesian")),
    "ms": ("malese", "Bahasa Melayu", ("malese", "malay")),
    "sw": ("swahili", "Kiswahili", ("swahili",)),
    "sv": ("svedese", "svenska", ("svedese", "swedish")),
    "no": ("norvegese", "norsk", ("norvegese", "norwegian")),
    "da": ("danese", "dansk", ("danese", "danish")),
    "fi": ("finlandese", "suomi", ("finlandese", "finnish")),
    "is": ("islandese", "íslenska", ("islandese", "icelandic")),
    "et": ("estone", "eesti", ("estone", "estonian")),
    "lv": ("lettone", "latviešu", ("lettone", "latvian")),
    "lt": ("lituano", "lietuvių", ("lituano", "lithuanian")),
    "ca": ("catalano", "català", ("catalano", "catalan")),
    "eu": ("basco", "euskara", ("basco", "basque")),
    "gl": ("galiziano", "galego", ("galiziano", "galician")),
    "cy": ("gallese", "Cymraeg", ("gallese", "welsh")),
    "ga": ("irlandese", "Gaeilge", ("irlandese", "irish")),
    "sq": ("albanese", "shqip", ("albanese", "albanian")),
    "mk": ("macedone", "македонски", ("macedone", "macedonian")),
    "ka": ("georgiano", "ქართული", ("georgiano", "georgian")),
    "hy": ("armeno", "հայերեն", ("armeno", "armenian")),
    "kk": ("kazako", "қазақ", ("kazako", "kazakh")),
    "lb": ("lussemburghese", "Lëtzebuergesch", ("lussemburghese", "luxembourgish")),
    "mt": ("maltese", "Malti", ("maltese",)),
    "af": ("afrikaans", "Afrikaans", ("afrikaans",)),
    "fil": ("filippino", "Filipino", ("filippino", "tagalog", "filipino")),
    "la": ("latino", "Latina", ("latino", "latin")),
}


def label(code: str) -> str:
    base = (code or "").split("-")[0].split("_")[0].lower()
    return LANGS[base][0].capitalize() if base in LANGS else (code or "?")


def base(code: str) -> str:
    return (code or "").replace("_", "-").split("-")[0].lower()


_WORDS = {
    "it": "il lo la gli le di che è e un una per non sono mi ti ci si con come cosa questo questa della del nel "
          "anche ma più perché ho hai ha abbiamo sei siamo dove quando quale grazie ciao buongiorno vorrei puoi "
          "fammi dimmi sai oggi domani io tu lui lei noi voi loro mio tuo bene molto",
    "en": "the a an is are was were be been to of and in on for with you your i my me we our it this that "
          "what how why when where who which can could would should will do does did have has not please "
          "thanks hello hi yes no today tomorrow tell about from there here",
    "es": "el la los las de que y en un una es por con para no sí como qué cuál más pero muy yo tú usted "
          "nosotros estoy está están hola gracias buenos días dónde cuándo quiero puedes hoy mañana también",
    "fr": "le la les de des du que et en un une est pour avec pas je tu il elle nous vous ils ce cette qui "
          "quoi comment pourquoi où bonjour merci oui non suis es sont très mais aussi aujourd'hui demain",
    "de": "der die das und ist nicht ich du er sie wir ihr ein eine zu mit von für auf den dem des was wie "
          "warum wo wer bitte danke hallo ja nein heute morgen auch aber sehr bin bist sind habe hast kann",
    "pt": "o a os as de que e em um uma é para com não sim como mais mas muito eu você nós está estão olá "
          "obrigado obrigada bom dia onde quando quero pode hoje amanhã também isso",
    "nl": "de het een en is van in op dat die niet ik je jij we wij zijn met voor wat hoe waarom waar wie "
          "dank hallo ja nee vandaag morgen ook maar heel",
}
_VOCAB = {lang: set(words.split()) for lang, words in _WORDS.items()}
_SCRIPTS = [
    (re.compile(r"[぀-ヿ]"), "ja"), (re.compile(r"[가-힯]"), "ko"),
    (re.compile(r"[一-鿿]"), "zh"), (re.compile(r"[֐-׿]"), "he"),
    (re.compile(r"[؀-ۿ]"), "ar"), (re.compile(r"[ऀ-ॿ]"), "hi"),
    (re.compile(r"[฀-๿]"), "th"), (re.compile(r"[Ͱ-Ͽ]"), "el"),
    (re.compile(r"[Ⴀ-ჿ]"), "ka"), (re.compile(r"[԰-֏]"), "hy"),
    (re.compile(r"[іїєґ]", re.I), "uk"), (re.compile(r"[Ѐ-ӿ]"), "ru"),
]
_TOKEN = re.compile(r"[a-zà-ÿ']+", re.I)


def _native():
    import os
    if os.environ.get("ATENA_NATIVE", "auto").strip() == "0":
        return None
    try:
        import atena_native
    except ImportError:
        return None
    return atena_native if hasattr(atena_native, "detect_language") else None


NATIVE = _native()
NATIVE_MIN_CHARS = 12


def detect_native(text: str, allowed: str = "") -> str | None:
    if NATIVE is None or len(text.strip()) < NATIVE_MIN_CHARS:
        return None
    guess = NATIVE.detect_language(text, allowed)
    if guess and (guess[2] or guess[1] >= 0.5) and guess[0] in LANGS:
        return guess[0]
    return None


def detect(text: str, default: str = DEFAULT) -> str:
    text = text or ""
    for pattern, lang in _SCRIPTS:
        if len(pattern.findall(text)) >= 2:
            return lang
    native = detect_native(text)
    if native:
        return native
    tokens = [t.lower().strip("'") for t in _TOKEN.findall(text)]
    if not tokens:
        return default
    scores = {lang: sum(t in vocab for t in tokens) for lang, vocab in _VOCAB.items()}
    best = max(scores, key=scores.get)
    top = scores[best]
    if top < 2 or (best != default and scores.get(default, 0) * 1.5 + 1 > top):
        return default
    return best


_NAMES = {alias: code for code, (_, _, aliases) in LANGS.items() for alias in aliases}
_NAME_RE = "|".join(sorted((re.escape(a) for a in _NAMES), key=len, reverse=True))
_VERB = (r"(?:parla(?:mi|re|ndo)?|parliamo|rispondi(?:mi)?|rispondere|continua(?:mo)?|conversiamo|"
         r"passa(?:re|iamo)?|torna(?:re|iamo)?(?:\s+a\s+parlare)?|d'ora in poi|da ora in poi|"
         r"speak|talk|answer|reply|respond|switch|let'?s\s+(?:speak|talk))")
_SWITCH_RE = re.compile(
    r"\b" + _VERB + r"\b(?:\s+|[^.?!]{0,30}?\b(?:in|all'|al|a|to|en|auf|em)\s*)(?:lingua\s+)?(" + _NAME_RE + r")\b", re.I)
_TEACH_RE = re.compile(
    r"\b(?:insegna(?:mi|re|rmi)|imparare|impariamo|studiare|studiamo|esercita(?:rmi|rci|iamoci|mi)|"
    r"facciamo\s+pratica|lezion[ei]|ripassare|migliorare|teach\s+me|learn|practi[cs]e)\b"
    r"[^.?!]{0,40}?\b(?:(?:l'|il|lo|la|di|in|del|dello|della)\s*)?(" + _NAME_RE + r")\b", re.I)
_BACK_RE = re.compile(r"\b(?:basta|smettila|smetti|stop|enough)\s+(?:di\s+|with\s+)?(?:parlare\s+|speaking\s+)?"
                      r"(?:in\s+)?(" + _NAME_RE + r")\b", re.I)


def requested(text: str) -> tuple[str, bool] | None:
    if _BACK_RE.search(text or ""):
        return "", False
    if m := _TEACH_RE.search(text or ""):
        code = _NAMES[m.group(1).lower()]
        return code, code != DEFAULT
    if m := _SWITCH_RE.search(text or ""):
        return _NAMES[m.group(1).lower()], False
    return None


def _resync() -> None:
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    from features.locale import household
    from tasks import background
    background(household.sync())


def resolve(text: str, device: str, heard: str | None = None, person: str = "") -> dict:
    from features.locale import service
    req = requested(text)
    if req:
        lang, teach = req
        if lang:
            choice = service.choose(lang, teach, person=person, device=device)
            _resync()
            return {"lang": choice.lang, "teach": choice.teach, "sticky": True, "switched": True}
        return {"lang": service.forget_choice(person=person, device=device), "teach": False, "sticky": False,
                "switched": True}
    choice = service.chosen(person, device)
    if choice:
        return {"lang": choice.lang, "teach": choice.teach, "sticky": True, "switched": False}
    heard = base(heard or "")
    spoken = heard if heard in LANGS else detect(text, service.preferred(person))
    return {"lang": spoken, "teach": False, "sticky": False, "switched": False}


ADDRESS = {
    "en": "rivolgiti all'utente con «sir» o per nome, con il tono di un maggiordomo britannico",
    "fr": "dai del vous e chiama l'utente «monsieur» o per nome",
    "de": "dai del Sie e chiama l'utente «mein Herr» o per nome",
    "es": "dai del usted e chiama l'utente «señor» o per nome",
    "pt": "usa o senhor e chiama l'utente «senhor» o per nome",
    "nl": "dai del u e chiama l'utente «meneer» o per nome",
    "ja": "usa il keigo (forma cortese) e il suffisso -sama con il nome",
}


def instruction(lang: str, teach: bool) -> str:
    if lang == DEFAULT and not teach:
        return ""
    name, native, _ = LANGS.get(lang, (lang, lang, ()))
    rule = (f"LINGUA: rispondi esclusivamente in {name} ({native}), con frasi naturali adatte a essere lette "
            f"ad alta voce, anche se il resto di queste istruzioni è in italiano. Le formule di cortesia italiane "
            f"(Lei, «signore») vanno rese in modo naturale in quella lingua")
    rule += f": {ADDRESS[lang]}." if lang in ADDRESS else "."
    if teach:
        rule += (f" Stai facendo da insegnante di {name} a un italiano: usa frasi semplici, correggi con gentilezza "
                 f"i suoi errori riscrivendo la frase giusta, proponi ogni tanto una breve domanda o un esercizio "
                 f"e, solo se lui non capisce o lo chiede, spiega in italiano.")
    return rule
