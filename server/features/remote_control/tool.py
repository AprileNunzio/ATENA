import json
from typing import Dict, Any
from server.features.remote_control.manager import RemoteComputerManager

# Questa è l'annotazione fittizia/ipotetica che il tuo sistema Agent potrebbe usare
# Sostituisci o adatta l'implementazione in base al sistema di plugin/tool di ATENA
class RemoteControlTool:
    """
    Tool Agentico per l'amministrazione dei PC di rete.
    Permette all'LLM di interagire con le macchine censite in network_map.json
    """
    
    def __init__(self):
        self.manager = RemoteComputerManager()
        
    @property
    def name(self) -> str:
        return "remote_computer_control"
        
    @property
    def description(self) -> str:
        return (
            "Permette di gestire i PC remoti della rete censiti nella network map. "
            "Comandi supportati: 'status' (stato di sistema), 'updates' (aggiornamenti), "
            "'disk' (spazio libero), 'restart_service' (riavvia servizio), 'reboot' (riavvia o spegne), "
            "'cpu' (carico cpu), 'network' (info rete), 'users' (utenti attivi)."
        )

    async def execute(self, pc_name: str, command: str, **kwargs) -> str:
        """
        Esegue il comando richiesto tramite il manager centralizzato in modo sicuro.
        
        :param pc_name: Il nome del PC (es. PC10)
        :param command: Il comando da eseguire (status, updates, disk, restart_service, reboot, cpu, network, users)
        :param kwargs: Argomenti extra (es. service_name="Nginx" se command="restart_service")
        """
        result = await self.manager.dispatch_command(pc_name, command, **kwargs)
        
        if result["status"] == "error":
            return f"Errore durante l'esecuzione su {pc_name}: {result['message']}"
            
        return f"Comando {command} completato su {pc_name}. Risultato:\n{json.dumps(result.get('data', result), indent=2)}"
