import re

from config import env_get

from features.chat import context as request_context
from features.people import identity

SELF_VOCATIVE = re.compile(r"([,!]\s*|^)(?:A\.\s?T\.\s?E\.\s?N\.\s?A\.?|Atena)(?=\s*[!?.,;:]|\s*$)", re.I)


def name() -> str:
    profile = identity.current(request_context.voice.get())
    if profile:
        return identity.first_name(profile)
    return env_get("ATENA_USER_NAME", "").strip().split(" ")[0]


def instruction() -> str:
    who = name()
    base = ("Tu sei Atena (A.T.E.N.A.), l'assistente. La persona che ti parla NON si chiama Atena: "
            "non chiamarla mai «Atena» o «A.T.E.N.A.».")
    if who:
        return f"{base} Stai parlando con {who}: chiamalo {who} oppure «signore»."
    return f"{base} Non conosci ancora il suo nome: chiamalo «signore»."


def fix_address(reply: str) -> str:
    if not reply:
        return reply
    who = name()

    def swap(m: re.Match) -> str:
        lead = m.group(1)
        if who:
            return f"{lead}{who}"
        return "" if lead.strip() in (",", "") else lead.strip()

    return SELF_VOCATIVE.sub(swap, reply)
