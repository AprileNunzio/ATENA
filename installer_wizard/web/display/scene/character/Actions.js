(function (J) {
  "use strict";
  const C = (J.Char = J.Char || {});
  const gesture = (name, hold) => (a) => a.gestures.play(name, { hold });

  const ACTIONS = {
    saluto: (a) => { a.gestures.play("saluto"); a.animator.play("saluto"); },
    annuisce: (a) => a.motion.once("agree") || a.animator.play("annuisce"),
    disaccordo: (a) => { if (!a.motion.once("shake")) a.animator.play("disaccordo"); a.animator.express("disagree", 2); },
    inchino: (a) => { a.gestures.play("inchino"); a.animator.play("inchino"); },
    pensa: (a) => { a.gestures.play("pensa", { hold: 6 }); a.animator.express("think", 6); },
    ascolto: (a) => { a.gestures.play("ascolto", { hold: 6 }); a.animator.play("ascolto"); },
    balla: (a) => a.life.dance(true),
    canta: (a) => { a.gestures.play("canta"); a.animator.play("canta"); },
    cappello: (a) => { a.gestures.play("capelli"); a.animator.play("cappello"); },
    togli_cappello: (a) => { a.gestures.play("capelli"); a.animator.play("togli_cappello"); },
    cammina: (a) => a.life.fidget("stroll"),
    ombrello: (a) => a.life.umbrella(true),
    chiudi_ombrello: (a) => a.life.umbrella(false),
    applaude: gesture("applaude"), pollice_su: gesture("pollice_su"), indica: gesture("indica"),
    mani_fianchi: gesture("mani_fianchi", 6), braccia_conserte: gesture("braccia_conserte", 8),
    stiracchia: gesture("stiracchia"), capelli: gesture("capelli"), orologio: gesture("orologio"),
    spallucce: gesture("spallucce"), cuore: gesture("cuore"), bacio: gesture("bacio"),
    freddo: gesture("freddo"), sorpresa: gesture("sorpresa"),
    triste: (a) => a.life.setMood("sad", 6),
    furtivo: (a) => a.life.setMood("sneak", 6),
    corre: (a) => a.life.setMood("run", 4),
  };

  const STOPS = {
    balla: (a) => a.life.dance(false),
    ombrello: (a) => a.life.umbrella(false),
    canta: (a) => { a.gestures.stop("canta"); a.animator.stop("canta"); },
  };

  const ALIASES = {
    ciao: "saluto", saluta: "saluto", wave: "saluto", greet: "saluto",
    si: "annuisce", "sì": "annuisce", yes: "annuisce", nod: "annuisce", annuisci: "annuisce",
    no: "disaccordo", nega: "disaccordo", bow: "inchino", hat: "cappello", metti_cappello: "cappello", via_cappello: "togli_cappello",
    listen: "ascolto", ascolta: "ascolto", think: "pensa", dance: "balla", danza: "balla", sing: "canta",
    walk: "cammina", passeggia: "cammina", run: "corre", corri: "corre",
    umbrella: "ombrello", apri_ombrello: "ombrello", close_umbrella: "chiudi_ombrello",
    clap: "applaude", applausi: "applaude", applaudi: "applaude", thumbs_up: "pollice_su", ok: "pollice_su",
    point: "indica", punta: "indica", hips: "mani_fianchi", arms_crossed: "braccia_conserte",
    stretch: "stiracchia", hair: "capelli", watch: "orologio", shrug: "spallucce", heart: "cuore",
    kiss: "bacio", manda_un_bacio: "bacio", cold: "freddo", surprised: "sorpresa", sneak: "furtivo",
  };

  const EXPRESS = {
    sad: (a, s) => a.life.setMood("sad", s), cry: (a, s) => a.life.setMood("sad", s),
    surprise: (a) => a.gestures.play("sorpresa"), doubt: (a) => a.gestures.play("spallucce"),
    disagree: (a) => a.gestures.play("spallucce"), angry: (a, s) => a.gestures.play("mani_fianchi", { hold: s }),
    think: (a, s) => a.gestures.play("pensa", { hold: s }),
  };

  function key(name) {
    const k = String(name || "").trim().toLowerCase().replace(/\s+/g, "_");
    return ALIASES[k] || k;
  }

  C.Actions = { ACTIONS, STOPS, EXPRESS, key, names: () => Object.keys(ACTIONS) };
})(window.Atena3D);
