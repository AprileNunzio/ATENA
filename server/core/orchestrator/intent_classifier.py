import json
import logging
from typing import Tuple, Dict
from server.features.llm_gateway.gateway import llm_gateway
from server.features.llm_gateway.contracts import LLMRequest, LLMMessage

logger = logging.getLogger("atena.intent_classifier")

INTENT_CATALOG: Dict[str, str] = {
    "HOME_AUTOMATION": "Controllo luci, termostati, serrature, porte, prese smart, scene domotiche, climatizzazione",
    "VISION_SURVEILLANCE": "Telecamere, rilevamento intrusi, cancelli, garage, sorveglianza, persone, veicoli",
    "AUTONOMOUS_PROGRAMMING": "Scrivere codice, creare script, correggere bug, refactoring, generare funzioni",
    "SYSOPS_AUTOMATION": "Gestione server, SSH, servizi systemd, backup, database, rete, DNS, firewall, Docker",
    "3D_GENERATION": "Creare modelli 3D, disegnare case in 3D, generare asset tridimensionali, architettura 3D",
    "WEB_RESEARCH_CATALOGS": "Scaricare cataloghi, cercare informazioni di prodotti, estrarre dati da siti web, scraping",
    "PEOPLE_MANAGEMENT": "Gestione persone, identità, anagrafica e memoria personale: scoprire o ricordare quanti anni ha una persona, compleanni, relazioni, lavoro, preferenze, oppure appuntare, aggiornare e memorizzare automaticamente dettagli, note e fatti su chi parla o su altre persone in qualunque lingua",
    "GENERAL_INTELLIGENCE": "Domande di conoscenza generale, conversazione aperta, ragionamento logico",
}

_SYSTEM_PROMPT_TEMPLATE: str = (
    "Sei il classificatore cognitivo degli intenti di Atena, un orchestratore autonomo e multilingue.\n"
    "Il tuo compito è comprendere l'intenzione semantica profonda dell'utente, formulata in qualsiasi lingua o stile.\n\n"
    "Principio di ragionamento autonomo:\n"
    "- Se l'utente chiede informazioni su di sé o su altre persone (ad es. quanti anni ha, quando è nato, chi è, che lavoro fa, cosa gli piace), "
    "oppure desidera che Atena impari, appunti, ricordi o aggiorni dettagli, fatti o preferenze personali, "
    "l'intento logico corretto è interagire con la funzionalità Persone e anagrafe: PEOPLE_MANAGEMENT.\n\n"
    "Schema obbligatorio:\n"
    '  {{"intent": "<INTENT_NAME>", "confidence": <float 0.0-1.0>, "reasoning": "<ragionamento cognitivo>"}}\n\n'
    "Funzionalità disponibili:\n{catalog}\n\n"
    "Regole:\n"
    "- Scegli l'intent che meglio realizza lo scopo dell'utente attraverso le funzionalità del sistema.\n"
    "- Rispondi ESCLUSIVAMENTE con il JSON, nessun altro testo."
)


class LLMIntentClassifier:

    def __init__(self, model_name: str = "qwen2.5:7b") -> None:
        self._model = model_name
        self._system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            catalog="\n".join(f"- {k}: {v}" for k, v in INTENT_CATALOG.items())
        )

    async def classify(self, user_query: str) -> Tuple[str, float]:
        try:
            response = await llm_gateway.generate_completion(
                LLMRequest(
                    model_name=self._model,
                    messages=[LLMMessage(role="user", content=user_query)],
                    system_prompt=self._system_prompt,
                    temperature=0.05,
                    max_tokens=200,
                    component="intent_classifier",
                )
            )
            result = json.loads(self._extract_json(response.content))
            intent = result.get("intent", "GENERAL_INTELLIGENCE")
            confidence = float(result.get("confidence", 0.5))
            if intent not in INTENT_CATALOG:
                logger.warning("LLM returned unknown intent '%s', falling back", intent)
                return self._fallback_routing(user_query), 0.4
            logger.info("Intent classified: %s (%.2f) — %s", intent, confidence, result.get("reasoning", ""))
            return intent, confidence
        except Exception as exc:
            logger.warning("LLM intent classification failed (%s), using fallback routing", exc)
            return self._fallback_routing(user_query), 0.5

    @staticmethod
    def _extract_json(raw: str) -> str:
        raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return raw[start : end + 1]
        return raw

    @staticmethod
    def _fallback_routing(text: str) -> str:
        # Minimal emergency fallback when LLM gateway is completely unreachable
        lowered = text.lower()
        if any(w in lowered for w in ["luce", "light", "spegni", "switch", "termostato", "thermostat"]):
            return "HOME_AUTOMATION"
        if any(w in lowered for w in ["telecamera", "camera", "webcam", "intruso", "intruder"]):
            return "VISION_SURVEILLANCE"
        if any(w in lowered for w in ["anni", "age", "compleanno", "birthday", "chi sono", "who am i", "appunta", "remember"]):
            return "PEOPLE_MANAGEMENT"
        return "GENERAL_INTELLIGENCE"


intent_classifier = LLMIntentClassifier()
