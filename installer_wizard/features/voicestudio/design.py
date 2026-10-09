import re
from pathlib import Path

LANGS = ("it", "en", "fr", "es", "de", "pt")

CHOICES = {
    "gender": [{"value": "female", "icon": "👩", "title": "Donna"}, {"value": "male", "icon": "👨", "title": "Uomo"}],
    "age": [{"value": "child", "icon": "🧒", "title": "Bambino"}, {"value": "teenager", "icon": "🧑", "title": "Ragazzo"},
            {"value": "young adult", "icon": "🙂", "title": "Giovane"}, {"value": "middle-aged", "icon": "🧔", "title": "Adulto"},
            {"value": "elderly", "icon": "👴", "title": "Anziano"}],
    "pitch": [{"value": "very low pitch", "icon": "🐻", "title": "Molto grave"}, {"value": "low pitch", "icon": "🐢", "title": "Grave"},
              {"value": "moderate pitch", "icon": "🙂", "title": "Normale"}, {"value": "high pitch", "icon": "🐦", "title": "Acuta"},
              {"value": "very high pitch", "icon": "🐭", "title": "Molto acuta"}],
    "style": [{"value": "", "icon": "🗣", "title": "Normale"}, {"value": "whisper", "icon": "🤫", "title": "Sussurrata"}],
}

SENTENCES = {
    "it": "Mi chiamo {name}. Do il mio consenso perché Atena usi la mia voce in questa casa. Oggi è una bella giornata e leggo con calma.",
    "en": "My name is {name}. I give my consent for Atena to use my voice in this home. Today is a nice day and I read calmly.",
    "fr": "Je m'appelle {name}. Je donne mon accord pour qu'Atena utilise ma voix dans cette maison. Aujourd'hui il fait beau et je lis calmement.",
    "es": "Me llamo {name}. Doy mi consentimiento para que Atena use mi voz en esta casa. Hoy es un buen día y leo con calma.",
    "de": "Ich heiße {name}. Ich erlaube Atena, meine Stimme in diesem Zuhause zu verwenden. Heute ist ein schöner Tag und ich lese ruhig.",
    "pt": "Meu nome é {name}. Dou o meu consentimento para que a Atena use a minha voz nesta casa. Hoje é um belo dia e leio com calma.",
}

PREVIEW = {
    "it": "Ciao! Questa è la mia nuova voce. Ti piace?",
    "en": "Hello! This is my new voice. Do you like it?",
    "fr": "Bonjour ! Voici ma nouvelle voix. Elle te plaît ?",
    "es": "¡Hola! Esta es mi nueva voz. ¿Te gusta?",
    "de": "Hallo! Das ist meine neue Stimme. Gefällt sie dir?",
    "pt": "Olá! Esta é a minha nova voz. Gostas?",
}


def language(raw) -> str:
    lang = str(raw or "it").lower()[:2]
    return lang if lang in LANGS else "it"


def sentence(lang: str, name: str) -> str:
    return SENTENCES[language(lang)].format(name=name)


def filename(raw: str | None) -> str:
    suffix = Path(str(raw or "")).suffix.lower()
    return "registrazione" + (suffix if re.fullmatch(r"\.(webm|ogg|wav|mp3|m4a)", suffix) else ".webm")


def describe(body: dict) -> str:
    picked = []
    for key, options in CHOICES.items():
        value = str(body.get(key) or "")
        if value and value not in {o["value"] for o in options}:
            raise ValueError("scelta non valida")
        if value:
            picked.append(value)
    if not any(p for p in picked):
        raise ValueError("scegli almeno una caratteristica della voce")
    return ", ".join(picked)
