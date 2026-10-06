export class I18nError extends Error {
    constructor(message) {
        super(message);
        this.name = this.constructor.name;
    }
}

export class LanguageLoadError extends I18nError {
    constructor(feature, lang, details) {
        super(`Failed to load language '${lang}' for feature '${feature}': ${details}`);
        this.feature = feature;
        this.lang = lang;
    }
}

export class TranslationNotFoundError extends I18nError {
    constructor(feature, key) {
        super(`Translation key '${key}' not found in feature '${feature}'`);
        this.feature = feature;
        this.key = key;
    }
}

export class SecurityViolationError extends I18nError {
    constructor(message) {
        super(`Security Violation: ${message}`);
    }
}
