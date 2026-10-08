(() => {
  const D = window.AtenaDisplay;
  const RETURN_AFTER = 60000;
  let following = "", lastSeen = 0;

  function systemLanguage(i18n) {
    const wanted = (window.ATENA_UI_LANG || navigator.language || "it").slice(0, 2).toLowerCase();
    return i18n.languages.includes(wanted) ? wanted : "it";
  }

  D.followLanguage = (presence) => {
    const i18n = window.AtenaI18n;
    if (!i18n) return;
    const people = (presence && presence.people) || [];
    const langs = [...new Set(people.filter((p) => p.known && p.ui_lang).map((p) => p.ui_lang))];
    const now = Date.now();
    if (langs.length === 1 && i18n.languages.includes(langs[0])) {
      lastSeen = now;
      following = langs[0];
      if (i18n.language() !== following) i18n.switchTo(following, false);
      return;
    }
    if (following && now - lastSeen > RETURN_AFTER) {
      following = "";
      const base = systemLanguage(i18n);
      if (i18n.language() !== base) i18n.switchTo(base, false);
    }
  };
})();
