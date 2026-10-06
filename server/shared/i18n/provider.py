from pathlib import Path
from .config import I18nConfig
from .loader import I18nLoader
from .translator import Translator

def _init_translator() -> Translator:
    base_dir = str(Path(__file__).resolve().parent.parent.parent)
    config = I18nConfig(base_dir=base_dir)
    loader = I18nLoader(config)
    return Translator(loader, config, base_dir)

global_translator = _init_translator()
