import inspect

from features.chat.skills.camera import camera_skill
from features.chat.skills.music import music_skill
from features.chat.skills.network import network_skill
from features.chat.skills.people import introduce_skill, person_info_skill, vision_skill
from features.chat.skills.place import place_skill
from features.chat.skills.system import system_skill, time_skill
from features.chat.skills.voices import voices_skill
from features.chat.skills.weather import weather_skill

BRAIN_REPLY = ("Ecco la mia mente. Ogni punto luminoso è un ricordo reale: "
               "tocca un neurone per esplorarlo.", {"mode": "brain"})


def _study():
    from features.study.study import speech_summary
    return speech_summary()


SKILLS = {
    "weather": lambda text: weather_skill(text),
    "camera": lambda text: camera_skill(text),
    "system": lambda text: system_skill(),
    "vision": lambda text: vision_skill(),
    "network": lambda text: network_skill(),
    "introduce": lambda text: introduce_skill(text),
    "person_info": lambda text: person_info_skill(text),
    "time": lambda text: time_skill(),
    "voices": lambda text: voices_skill(text),
    "place": lambda text: place_skill(text),
    "music": lambda text: music_skill(),
    "study": lambda text: _study(),
    "brain": lambda text: BRAIN_REPLY,
}


async def run_skill(intent: str, text: str) -> tuple[str, dict]:
    handler = SKILLS.get(intent)
    if handler is None:
        raise LookupError(intent)
    outcome = handler(text)
    speech, ui = await outcome if inspect.isawaitable(outcome) else outcome
    ui = dict(ui)
    if intent == "vision":
        ui["personal"] = ui.get("mode") == "focus"
    elif intent == "person_info":
        ui["personal"] = True
    return speech, ui
