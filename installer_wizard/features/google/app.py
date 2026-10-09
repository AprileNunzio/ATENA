import base64
import hashlib
import secrets
import urllib.parse

import httpx
from config import env_get

from features.google.constants import REDIRECT_URI, SERVICES
from features.google.flows import LinkError, flows, parse

_HINTS = {
    "invalid_grant": "il codice è già stato usato o è scaduto (vale pochi minuti): premi di nuovo «Collega»",
    "redirect_uri_mismatch": "l'ID client non è di tipo «App desktop»: ricrealo come App desktop",
    "invalid_client": "Client ID o Client Secret errati: ricontrollali nella sezione App Google",
    "unauthorized_client": "l'app Google non è autorizzata a questo flusso: usa un ID client «App desktop»",
}


class OAuthApp:
    @staticmethod
    def credentials() -> tuple[str, str]:
        return env_get("ATENA_GOOGLE_CLIENT_ID", "").strip(), env_get("ATENA_GOOGLE_CLIENT_SECRET", "").strip()

    def ready(self) -> bool:
        return all(self.credentials())

    def auth_url(self, slug: str, services: list[str]) -> str:
        cid, secret = self.credentials()
        if not (cid and secret):
            raise ValueError("Inserisci prima Client ID e Client Secret dell'app Google")
        services = [s for s in services if s in SERVICES]
        if not services:
            raise ValueError("Scegli almeno un servizio")
        scopes = ["openid", "email", "profile"] + [x for s in services for x in SERVICES[s]["scopes"]]
        state, verifier = secrets.token_urlsafe(16), secrets.token_urlsafe(48)
        flows.create(state, slug, verifier)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": cid, "response_type": "code", "redirect_uri": REDIRECT_URI, "scope": " ".join(scopes),
            "state": state, "access_type": "offline", "prompt": "consent select_account",
            "include_granted_scopes": "true", "code_challenge": challenge, "code_challenge_method": "S256"})

    async def token(self, data: dict) -> dict:
        cid, secret = self.credentials()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post("https://oauth2.googleapis.com/token",
                                  data={**data, "client_id": cid, "client_secret": secret})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200:
            code = str(body.get("error") or "")
            if code == "invalid_grant" and data.get("grant_type") == "refresh_token":
                raise ValueError("Google: autorizzazione scaduta o revocata: ricollega l'account")
            err = _HINTS.get(code) or body.get("error_description") or code or f"errore {r.status_code}"
            raise LinkError(f"Google: {err}") if code in _HINTS else ValueError(f"Google: {err}")
        return body

    async def exchange(self, pasted: str, slug_hint: str = "") -> tuple[str, dict]:
        found = parse(pasted)
        if found.error:
            raise LinkError("Autorizzazione negata su Google" if found.error == "access_denied"
                            else f"Google ha risposto con un errore: {found.error}")
        if not found.code:
            raise LinkError("Nell'indirizzo incollato non trovo il codice: copia tutta la barra degli indirizzi "
                            "della pagina che non si apre (contiene «code=»)")
        state, flow = flows.resolve(found, slug_hint)
        body = await self.token({"grant_type": "authorization_code", "code": found.code,
                                 "redirect_uri": REDIRECT_URI, "code_verifier": flow["verifier"]})
        flows.consume(state)
        if not body.get("refresh_token"):
            raise LinkError("Google non ha rilasciato il token di rinnovo: rimuovi l'accesso di Atena da "
                            "myaccount.google.com/permissions e ricollega")
        return flow["slug"], body

    @staticmethod
    async def revoke(token: str) -> None:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post("https://oauth2.googleapis.com/revoke", data={"token": token})


oauth = OAuthApp()
