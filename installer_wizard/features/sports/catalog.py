from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    code: str
    name: str
    flag: str
    cup: bool = False


LEAGUES: tuple[League, ...] = (
    League("ita.1", "Serie A", "🇮🇹"),
    League("ita.2", "Serie B", "🇮🇹"),
    League("ita.coppa_italia", "Coppa Italia", "🇮🇹", True),
    League("uefa.champions", "Champions League", "🇪🇺", True),
    League("uefa.europa", "Europa League", "🇪🇺", True),
    League("uefa.europa.conf", "Conference League", "🇪🇺", True),
    League("eng.1", "Premier League", "🏴"),
    League("esp.1", "LaLiga", "🇪🇸"),
    League("ger.1", "Bundesliga", "🇩🇪"),
    League("fra.1", "Ligue 1", "🇫🇷"),
    League("por.1", "Liga Portugal", "🇵🇹"),
    League("ned.1", "Eredivisie", "🇳🇱"),
    League("fifa.world", "Mondiali", "🌍", True),
    League("uefa.euro", "Europei", "🇪🇺", True),
    League("uefa.nations", "Nations League", "🇪🇺", True),
)
BY_CODE = {lg.code: lg for lg in LEAGUES}
TABLE_LEAGUES = tuple(lg.code for lg in LEAGUES if not lg.cup)
LIVE, PRE, POST = "in", "pre", "post"
