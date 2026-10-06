class I18nError(Exception):
    pass

class InvalidLanguageCodeError(I18nError):
    pass

class TranslationNotFoundError(I18nError):
    pass

class SecurityViolationError(I18nError):
    pass

class TranslationFileLoadError(I18nError):
    pass
