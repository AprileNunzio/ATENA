from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class BiometricType(str, Enum):
    FACE = "face"
    VOICE = "voice"
    FUSION = "fusion"
    MANUAL = "manual"

class PresenceStatus(BaseModel):
    is_owner_approaching: bool
    is_biometrically_verified: bool
    detected_user: Optional[str] = None
    verification_method: Optional[BiometricType] = None
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    distance_meters: float = Field(0.0, ge=0.0)
    last_detected_timestamp: float

class VerificationPayload(BaseModel):
    user_id: str
    modality: BiometricType
    confidence: float = Field(..., ge=0.0, le=1.0)
    distance_meters: float = Field(1.0, ge=0.0)

class SystemTelemetryData(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    local_ip: str
    active_connections: int
    estimated_power_watts: float
    energy_mode: str
    uptime_seconds: float
    active_agents: List[str]

class WidgetPrivacyPolicy(BaseModel):
    widget_id: str
    is_sensitive: bool
    max_exposure_seconds: int
    allowed_users: List[str] = Field(default_factory=list)
