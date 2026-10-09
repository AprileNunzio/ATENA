PHRASES = {
    "it": {
        "openers": ("Eccomi, {who}.", "Al suo servizio, {who}.", "Agli ordini, {who}.", "Sono qui, {who}.", "Presente, {who}.",
                    "Dica pure, {who}.", "A sua disposizione, {who}."),
        "all_ok": ("Tutti i sistemi sono operativi.", "Sistemi nominali, nessuna anomalia.", "Tutto in ordine qui dentro.",
                   "Reattore stabile e sistemi al cento per cento.", "Nessun allarme: possiamo procedere."),
        "late": ("Ore piccole anche stanotte, vedo.", "Il resto della casa dorme: parliamo sottovoce."),
        "watch": "Quasi tutto operativo: tengo d'occhio {names}.",
        "event": "Alle {time} ha {title}.",
        "who": "signore", "systems": "sistemi", "check": "da controllare", "help": "Come posso aiutarla?",
    },
    "en": {
        "openers": ("Here I am, {who}.", "At your service, {who}.", "Ready when you are, {who}.", "I'm here, {who}.",
                    "Go ahead, {who}.", "At your disposal, {who}."),
        "all_ok": ("All systems are operational.", "Systems nominal, no anomalies.", "Everything is in order in here.",
                   "Reactor stable and systems at one hundred percent.", "No alarms: we can proceed."),
        "late": ("Another late night, I see.", "The rest of the house is asleep: let's keep our voices down."),
        "watch": "Almost everything is running: I'm keeping an eye on {names}.",
        "event": "At {time} you have {title}.",
        "who": "sir", "systems": "systems", "check": "to check", "help": "How can I help you?",
    },
    "fr": {
        "openers": ("Me voici, {who}.", "À votre service, {who}.", "À vos ordres, {who}.", "Je suis là, {who}.",
                    "Je vous écoute, {who}.", "À votre disposition, {who}."),
        "all_ok": ("Tous les systèmes sont opérationnels.", "Systèmes nominaux, aucune anomalie.", "Tout est en ordre ici.",
                   "Réacteur stable et systèmes à cent pour cent.", "Aucune alarme : nous pouvons continuer."),
        "late": ("Encore une nuit tardive, à ce que je vois.", "Le reste de la maison dort : parlons doucement."),
        "watch": "Presque tout fonctionne : je surveille {names}.",
        "event": "À {time}, vous avez {title}.",
        "who": "monsieur", "systems": "systèmes", "check": "à vérifier", "help": "Comment puis-je vous aider ?",
    },
}


def phrases(lang: str) -> dict:
    return PHRASES.get(lang, PHRASES["it"])


def native(lang: str) -> bool:
    return lang in PHRASES
