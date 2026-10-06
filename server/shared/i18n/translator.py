from typing import Dict, Any, Optional

from .config import I18nConfig
from .loader import I18nLoader
from .errors import TranslationNotFoundError
from .context import current_language

class Translator:
    def __init__(self, loader: I18nLoader, config: I18nConfig, root_path: str):
        self._loader = loader
        self._config = config
        self._root_path = root_path
        self._cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _get_module_translations(self, module_path: str, lang: str) -> Dict[str, Any]:
        if module_path not in self._cache:
            self._cache[module_path] = {}
            
        if lang not in self._cache[module_path]:
            self._cache[module_path][lang] = self._loader.load_translations(self._root_path, module_path, lang)
            
        return self._cache[module_path][lang]

    def translate(self, module_path: str, key: str, lang: Optional[str] = None, fallback: bool = True, **kwargs) -> str:
        target_lang = lang or current_language.get()
        translations = self._get_module_translations(module_path, target_lang)

        parts = key.split('.')
        current = translations
        
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                if fallback and target_lang != self._config.default_language:
                    return self.translate(module_path, key, self._config.default_language, fallback=False, **kwargs)
                raise TranslationNotFoundError(f"Key '{key}' not found in module '{module_path}' for lang '{target_lang}'")
            current = current[part]
            
        text = str(current)
        if kwargs:
            text = text.format(**kwargs)
        return text
