import json
import re
from pathlib import Path
from typing import Dict, Any

from .config import I18nConfig
from .errors import SecurityViolationError, TranslationFileLoadError

class I18nLoader:
    def __init__(self, config: I18nConfig):
        self._config = config
        self._lang_pattern = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")

    def _validate_inputs(self, module_path: str, lang: str) -> None:
        if not self._lang_pattern.match(lang):
            raise SecurityViolationError(f"Invalid language code format: {lang}")
        if ".." in module_path or "\0" in module_path:
            raise SecurityViolationError("Path traversal or null byte injection attempt detected")
        if lang not in self._config.supported_languages:
            raise SecurityViolationError(f"Language not in supported languages whitelist: {lang}")

    def load_translations(self, root_path: str, module_path: str, lang: str) -> Dict[str, Any]:
        self._validate_inputs(module_path, lang)
        
        try:
            base_path = Path(root_path)
            target_path = base_path / module_path / "language" / f"{lang}.json"
            resolved_path = target_path.resolve()
            
            if not str(resolved_path).startswith(str(base_path.resolve())):
                raise SecurityViolationError("Resolved path is outside the allowed root directory")
            
            if not resolved_path.is_file():
                return {}
                
            with open(resolved_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except SecurityViolationError:
            raise
        except Exception as e:
            raise TranslationFileLoadError(f"Failed to load translation file: {str(e)}") from e
