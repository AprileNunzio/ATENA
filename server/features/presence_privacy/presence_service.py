import time
from typing import Dict, List, Optional
from server.features.presence_privacy.models import (
    PresenceStatus,
    VerificationPayload,
    BiometricType,
    WidgetPrivacyPolicy,
)

class PresenceService:
    def __init__(self) -> None:
        self._is_approaching: bool = False
        self._is_verified: bool = False
        self._detected_user: Optional[str] = None
        self._modality: Optional[BiometricType] = None
        self._confidence: float = 0.0
        self._distance: float = 0.0
        self._last_timestamp: float = 0.0
        self._timeout_seconds: float = 20.0
        self._policies: Dict[str, WidgetPrivacyPolicy] = {
            "personal_profile": WidgetPrivacyPolicy(
                widget_id="personal_profile",
                is_sensitive=True,
                max_exposure_seconds=30,
                allowed_users=["owner", "admin", "nunzio"],
            ),
            "cognitive_flow": WidgetPrivacyPolicy(
                widget_id="cognitive_flow",
                is_sensitive=False,
                max_exposure_seconds=120,
            ),
            "system_health": WidgetPrivacyPolicy(
                widget_id="system_health",
                is_sensitive=False,
                max_exposure_seconds=60,
            ),
            "power_consumption": WidgetPrivacyPolicy(
                widget_id="power_consumption",
                is_sensitive=False,
                max_exposure_seconds=60,
            ),
            "network_ip": WidgetPrivacyPolicy(
                widget_id="network_ip",
                is_sensitive=True,
                max_exposure_seconds=45,
                allowed_users=["owner", "admin", "nunzio"],
            ),
        }

    def get_status(self) -> PresenceStatus:
        now = time.time()
        if self._last_timestamp > 0 and (now - self._last_timestamp > self._timeout_seconds):
            self._is_approaching = False
            self._is_verified = False
            self._detected_user = None

        return PresenceStatus(
            is_owner_approaching=self._is_approaching,
            is_biometrically_verified=self._is_verified,
            detected_user=self._detected_user,
            verification_method=self._modality,
            confidence_score=self._confidence,
            distance_meters=self._distance,
            last_detected_timestamp=self._last_timestamp,
        )

    def record_verification(self, payload: VerificationPayload) -> PresenceStatus:
        self._last_timestamp = time.time()
        self._detected_user = payload.user_id
        self._modality = payload.modality
        self._confidence = payload.confidence
        self._distance = payload.distance_meters
        self._is_approaching = payload.distance_meters <= 2.5
        self._is_verified = payload.confidence >= 0.75 and self._is_approaching
        return self.get_status()

    def set_presence(self, approaching: bool, verified: bool, user: Optional[str] = None) -> PresenceStatus:
        self._last_timestamp = time.time()
        self._is_approaching = approaching
        self._is_verified = verified
        self._detected_user = user
        self._confidence = 0.95 if verified else 0.0
        self._modality = BiometricType.MANUAL
        self._distance = 1.0 if approaching else 5.0
        return self.get_status()

    def get_policies(self) -> List[WidgetPrivacyPolicy]:
        return list(self._policies.values())

presence_service = PresenceService()
