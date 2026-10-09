use whatlang::{Detector, Lang};

const CODES: &[(&str, Lang)] = &[
    ("it", Lang::Ita),
    ("en", Lang::Eng),
    ("es", Lang::Spa),
    ("fr", Lang::Fra),
    ("de", Lang::Deu),
    ("pt", Lang::Por),
    ("nl", Lang::Nld),
    ("ru", Lang::Rus),
    ("uk", Lang::Ukr),
    ("pl", Lang::Pol),
    ("cs", Lang::Ces),
    ("sk", Lang::Slk),
    ("sl", Lang::Slv),
    ("hr", Lang::Hrv),
    ("sr", Lang::Srp),
    ("bg", Lang::Bul),
    ("ro", Lang::Ron),
    ("hu", Lang::Hun),
    ("el", Lang::Ell),
    ("tr", Lang::Tur),
    ("ar", Lang::Ara),
    ("he", Lang::Heb),
    ("fa", Lang::Pes),
    ("hi", Lang::Hin),
    ("ur", Lang::Urd),
    ("bn", Lang::Ben),
    ("ta", Lang::Tam),
    ("te", Lang::Tel),
    ("ml", Lang::Mal),
    ("mr", Lang::Mar),
    ("ne", Lang::Nep),
    ("zh", Lang::Cmn),
    ("ja", Lang::Jpn),
    ("ko", Lang::Kor),
    ("vi", Lang::Vie),
    ("th", Lang::Tha),
    ("id", Lang::Ind),
    ("sv", Lang::Swe),
    ("no", Lang::Nob),
    ("da", Lang::Dan),
    ("fi", Lang::Fin),
    ("et", Lang::Est),
    ("lv", Lang::Lav),
    ("lt", Lang::Lit),
    ("ca", Lang::Cat),
    ("mk", Lang::Mkd),
    ("ka", Lang::Kat),
    ("hy", Lang::Hye),
    ("af", Lang::Afr),
    ("fil", Lang::Tgl),
    ("la", Lang::Lat),
];

#[derive(Debug, Clone, PartialEq)]
pub struct Guess {
    pub code: &'static str,
    pub confidence: f64,
    pub reliable: bool,
}

#[must_use]
pub fn code_of(lang: Lang) -> Option<&'static str> {
    CODES.iter().find(|(_, l)| *l == lang).map(|(c, _)| *c)
}

#[must_use]
pub fn lang_of(code: &str) -> Option<Lang> {
    CODES.iter().find(|(c, _)| *c == code).map(|(_, l)| *l)
}

#[must_use]
pub fn supported() -> Vec<&'static str> {
    CODES.iter().map(|(c, _)| *c).collect()
}

#[must_use]
pub fn detect(text: &str, allowed: &[&str]) -> Option<Guess> {
    let mut wanted: Vec<Lang> = allowed.iter().filter_map(|c| lang_of(c)).collect();
    if wanted.is_empty() {
        wanted = CODES.iter().map(|(_, l)| *l).collect();
    }
    let detector = Detector::with_allowlist(wanted);
    let info = detector.detect(text)?;
    Some(Guess {
        code: code_of(info.lang())?,
        confidence: info.confidence(),
        reliable: info.is_reliable(),
    })
}

#[cfg(test)]
mod tests {
    use super::{detect, lang_of, supported};

    #[test]
    fn recognises_common_sentences() {
        let cases = [
            (
                "Ho acceso la luce dello studio e spento quella della cucina.",
                "it",
            ),
            (
                "I turned on the light in the study and switched off the kitchen one.",
                "en",
            ),
            (
                "J'ai allumé la lumière du bureau et éteint celle de la cuisine.",
                "fr",
            ),
            ("Ich habe das Licht im Arbeitszimmer eingeschaltet.", "de"),
            (
                "He encendido la luz del estudio y apagado la de la cocina.",
                "es",
            ),
            ("Я включил свет в кабинете.", "ru"),
            ("書斎の電気をつけました。", "ja"),
        ];
        for (text, code) in cases {
            assert_eq!(detect(text, &[]).map(|g| g.code), Some(code), "{text}");
        }
    }

    #[test]
    fn allowlist_restricts_the_answer() {
        let guess = detect("Ho acceso la luce dello studio.", &["en", "fr"]);
        assert!(guess.is_none_or(|g| g.code == "en" || g.code == "fr"));
    }

    #[test]
    fn every_code_round_trips() {
        for code in supported() {
            assert!(lang_of(code).is_some(), "{code}");
        }
        assert!(detect("", &[]).is_none());
    }
}
