from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class UniversalObservation(BaseModel):
    """
    Rappresenta un input sensoriale astratto.
    Può essere una frase testuale dell'utente, un frame visivo dalla webcam,
    un pacchetto di rete, o un interrupt USB.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    modality: str = Field(..., description="Es: 'text', 'vision', 'network_packet', 'usb_interrupt'")
    source_id: str = Field(..., description="ID del sensore o dell'utente (es: 'webcam_1', 'user_primary', 'eth0')")
    
    # Il payload raw embeddato nello spazio latente (se applicabile)
    raw_data: Any = Field(..., description="Il dato grezzo (es: base64 image, raw string, bytearray)")
    
    # Rappresentazione semantica estratta dal Sistema 2 (se disponibile)
    semantic_embedding: Optional[list[float]] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)

class UniversalAction(BaseModel):
    """
    Rappresenta un output motorio/attuativo astratto.
    Può essere una risposta testuale, un comando HTTP, un movimento XYZ per un braccio, ecc.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    target_modality: str = Field(..., description="Es: 'tts', 'servo_controller', 'http_client', 'ui_widget'")
    target_id: str = Field(..., description="ID dell'attuatore (es: 'speaker_1', 'arm_joint_3')")
    
    # Il vettore di controllo continuo
    control_vector: Any = Field(..., description="Può essere un array di float [x,y,z], una stringa, o un binario")
    
    # Aspettativa visiva/sensoriale (Il 'Grounding' per calcolare il Reward)
    expected_observation_state: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Cosa si aspetta di vedere Atena nel frame successivo dopo questa azione? Serve per l'Auto-Reward."
    )

class RewardSignal(BaseModel):
    """
    Segnale di rinforzo continuo calcolato correlando un UniversalAction con la UniversalObservation successiva.
    """
    action_id: str
    observation_id: str
    score: float = Field(..., ge=-1.0, le=1.0, description="-1.0 (Fallimento totale) a 1.0 (Successo perfetto)")
    reasoning: str = Field(default="Reward calcolato automaticamente per similarita' tra stato atteso e osservato.")
