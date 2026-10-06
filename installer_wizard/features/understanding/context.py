import re
import unicodedata
from dataclasses import dataclass, field

from features.chat.dialogue import dialogue
from features.desktop.desk import desk

RECENT = 300.0


def plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text).lower())
    return re.sub(r"\s+", " ", "".join(c for c in folded if not unicodedata.combining(c))).strip(" .?!,;:")


@dataclass
class Context:
    text: str
    plain: str
    device: str
    last_text: str = ""
    last_intent: str = ""
    last_age: float = 1e9
    widgets: set = field(default_factory=set)
    history: str = ""

    def follows(self, intent: str) -> bool:
        return self.last_intent == intent and self.last_age < RECENT


def build(text: str, device: str) -> Context:
    last = dialogue.last(device)
    return Context(text=text, plain=plain(text), device=device, last_text=last.text if last else "", last_intent=last.intent if last else "",
                   last_age=dialogue.since_reply(device), widgets={i["id"] for i in desk.active()}, history=dialogue.context(device))
