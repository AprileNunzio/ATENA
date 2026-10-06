import socket
import json
import threading
import logging
import uuid
import time

log = logging.getLogger("atena.mesh")

class AtenaMeshCoordinator:
    """
    Gestisce la rete P2P decentralizzata di nodi Atena.
    Permette il Tensor Sharding (distribuzione dell'inferenza pesante su altri nodi della rete locale).
    """
    def __init__(self, port=9999):
        self.node_id = str(uuid.uuid4())
        self.port = port
        self.peers = {} # node_id -> {ip, capabilities, load}
        self.running = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start_discovery(self):
        self.sock.bind(("", self.port))
        self.running = True
        threading.Thread(target=self._listen_for_peers, daemon=True).start()
        threading.Thread(target=self._broadcast_presence, daemon=True).start()
        log.info(f"Atena Mesh attivato. Node ID: {self.node_id}. In attesa di peer...")

    def _listen_for_peers(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                if msg["node_id"] != self.node_id and msg["action"] == "HELLO":
                    self.peers[msg["node_id"]] = {
                        "ip": addr[0],
                        "gpus": msg["capabilities"].get("gpus", 0),
                        "load": msg["load"],
                        "last_seen": time.time()
                    }
            except Exception:
                pass

    def _broadcast_presence(self):
        while self.running:
            msg = json.dumps({
                "node_id": self.node_id,
                "action": "HELLO",
                "capabilities": {"gpus": 1, "cpu_cores": 8},
                "load": 0.2
            }).encode('utf-8')
            # Invia broadcast sulla porta della mesh
            self.sock.sendto(msg, ("<broadcast>", self.port))
            time.sleep(5)

    async def offload_tensor_inference(self, model_name: str, tensor_data: bytes):
        """
        Sharda la matrice e la invia al nodo con il minor carico computazionale.
        """
        if not self.peers:
            log.warning("Nessun peer disponibile. Esecuzione inferenza in locale (fallback).")
            return None # Torna a fallback locale
            
        best_peer = min(self.peers.values(), key=lambda p: p["load"])
        log.info(f"Offloading inferenza {model_name} sul peer {best_peer['ip']} via gRPC...")
        
        # TODO: Chiamata gRPC reale per trasferire i tensori binari
        time.sleep(0.01) # Simulazione latenza LAN
        return {"offloaded": True, "peer_ip": best_peer["ip"], "result": "mock_tensor_out"}

    def commit_state_event(self, event_data: dict):
        log.info(f"Committing state event to mesh: {event_data}")

    def register_peer(self, peer):
        log.info(f"Registering peer: {peer}")

    def get_sync_payload(self):
        class MockSync:
            def model_dump(self):
                return {}
        return MockSync()

p2p_mesh = AtenaMeshCoordinator()
