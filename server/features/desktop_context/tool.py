import aiohttp
from typing import Dict, Any

class ActiveContextTool:
    """
    Strumento che permette ad ATENA di "vedere" cosa sta facendo l'utente sul suo PC locale,
    interrogando il Satellite di Contesto (Context Bridge).
    """
    def __init__(self, satellite_url: str = "http://127.0.0.1:19999"):
        self.satellite_url = satellite_url.rstrip("/")
        
    @property
    def name(self) -> str:
        return "get_active_screen_context"
        
    @property
    def description(self) -> str:
        return (
            "Usa questo strumento per capire a cosa sta lavorando l'utente. "
            "Legge la finestra attiva in primo piano sul PC dell'utente estraendone il testo o scattando uno screenshot. "
            "Argomenti: 'mode' (valori: 'text' o 'vision')."
        )

    async def execute(self, mode: str = "text") -> Dict[str, Any]:
        endpoint = "/api/v1/context/text" if mode == "text" else "/api/v1/context/vision"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.satellite_url}{endpoint}", timeout=5) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except Exception as e:
            return {
                "status": "error", 
                "message": f"Impossibile comunicare col Context Satellite. Assicurati che sia in esecuzione sul PC dell'utente. Errore: {str(e)}"
            }
