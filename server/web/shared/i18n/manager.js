import { LanguageLoadError, TranslationNotFoundError, SecurityViolationError } from './errors.js';

export class I18nManager {
    #cache = new Map();
    #currentLang;
    #defaultLang;
    #supportedLangs;

    constructor(defaultLang = 'en', supportedLangs = ['en', 'it']) {
        this.#defaultLang = defaultLang;
        this.#currentLang = defaultLang;
        this.#supportedLangs = new Set(supportedLangs);
    }

    #validateInputs(feature, lang) {
        const strictPattern = /^[a-zA-Z0-9_-]+$/;

        if (!strictPattern.test(feature)) {
            throw new SecurityViolationError('Invalid feature identifier');
        }

        if (!strictPattern.test(lang)) {
            throw new SecurityViolationError('Invalid language identifier');
        }

        if (!this.#supportedLangs.has(lang)) {
            throw new SecurityViolationError('Unsupported language code');
        }
    }

    async loadFeature(feature) {
        this.#validateInputs(feature, this.#currentLang);
        const cacheKey = `${feature}:${this.#currentLang}`;

        if (this.#cache.has(cacheKey)) {
            return;
        }

        try {
            const basePath = window.I18N_BASE_PATH || '/features';
            const response = await fetch(`${basePath}/${feature}/language/${this.#currentLang}.json`);

            if (!response.ok) {
                throw new LanguageLoadError(feature, this.#currentLang, `HTTP ${response.status}`);
            }

            const data = await response.json();
            this.#cache.set(cacheKey, data);
        } catch (error) {
            if (error instanceof LanguageLoadError) {
                throw error;
            }
            throw new LanguageLoadError(feature, this.#currentLang, error.message);
        }
    }

    translate(feature, key) {
        const cacheKey = `${feature}:${this.#currentLang}`;
        const translations = this.#cache.get(cacheKey);

        if (!translations) {
            throw new TranslationNotFoundError(feature, key);
        }

        const parts = key.split('.');
        let current = translations;

        for (const part of parts) {
            if (current[part] === undefined) {
                throw new TranslationNotFoundError(feature, key);
            }
            current = current[part];
        }

        return current;
    }

    async setLanguage(lang, activeFeatures = []) {
        if (!this.#supportedLangs.has(lang)) {
            throw new SecurityViolationError('Unsupported language code');
        }

        this.#currentLang = lang;
        const promises = activeFeatures.map(feature => this.loadFeature(feature));
        await Promise.all(promises);
        this.updateDOM();
    }

    updateDOM(rootElement = document) {
        const elements = rootElement.querySelectorAll('[data-i18n]');

        elements.forEach(el => {
            const mapping = el.getAttribute('data-i18n');
            const [feature, key] = mapping.split(':');

            if (!feature || !key) {
                return;
            }

            try {
                if (el.tagName === 'INPUT' && el.type === 'button') {
                    el.value = this.translate(feature, key);
                } else {
                    // Prendi i tag HTML interni (es <span>)
                    const existingHTML = el.innerHTML;
                    if (existingHTML.includes('<span') || existingHTML.includes('<b')) {
                        // Limitazione temporanea: per non rompere l'HTML interno (es logo)
                        // mappiamo solo il testo dove non è strettamente HTML strutturato.
                    }
                    el.textContent = this.translate(feature, key);
                }
            } catch (error) {
                if (error instanceof TranslationNotFoundError) {
                    el.textContent = `[${key}]`;
                } else {
                    throw error;
                }
            }
        });

        const placeholders = rootElement.querySelectorAll('[data-i18n-placeholder]');
        placeholders.forEach(el => {
            const mapping = el.getAttribute('data-i18n-placeholder');
            const [feature, key] = mapping.split(':');
            if (feature && key) {
                try {
                    el.placeholder = this.translate(feature, key);
                } catch (error) {
                    // Ignore missing
                }
            }
        });
    }

    getCurrentLanguage() {
        return this.#currentLang;
    }
}
