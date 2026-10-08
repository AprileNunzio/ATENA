import json
import aiohttp
from typing import Dict, Any

class ActiveContextTool:
    def __init__(self, satellite_url: str = "http://127.0.0.1:19999", psk: str = ""):
        self.satellite_url = satellite_url.rstrip("/")
        self.psk = psk
        self._cipher = None
        
        if self.psk:
            from cryptography.fernet import Fernet
            self._cipher = Fernet(self.psk.encode())
            
    def _encrypt(self, data: str) -> str:
        if not self._cipher: return data
        return self._cipher.encrypt(data.encode()).decode()

    def _decrypt(self, data: str) -> str:
        if not self._cipher: return data
        return self._cipher.decrypt(data.encode()).decode()
        
    @property
    def name(self) -> str:
        return "get_active_screen_context"
        
    @property
    def description(self) -> str:
        return (
            "Interroga il Satellite di Contesto tramite canale E2E crittografato AES. "
            "Argomenti supportati in 'mode': 'text', 'vision', oppure 'update' per aggiornare il satellite."
        )

    async def execute(self, mode: str = "text", download_url: str = "") -> Dict[str, Any]:
        if mode == "update":
            endpoint = "/api/v1/system/update"
            payload_str = json.dumps({"download_url": download_url})
        else:
            endpoint = "/api/v1/context/text" if mode == "text" else "/api/v1/context/vision"
            payload_str = "{}"
            
        enc_payload = self._encrypt(payload_str)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.satellite_url}{endpoint}", json={"payload": enc_payload}, timeout=10) as resp:
                    resp.raise_for_status()
                    resp_data = await resp.json()
                    decrypted_str = self._decrypt(resp_data["payload"])
                    return json.loads(decrypted_str)
        except Exception as e:
            return {
                "status": "error", 
                "message": f"Errore di comunicazione E2E col Context Satellite: {str(e)}"
            }
