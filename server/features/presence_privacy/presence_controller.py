from typing import List
from fastapi import APIRouter
from server.features.presence_privacy.models import (
    PresenceStatus,
    VerificationPayload,
    SystemTelemetryData,
    WidgetPrivacyPolicy,
)
from server.features.presence_privacy.presence_service import presence_service
from server.features.presence_privacy.system_metrics import system_metrics_collector

presence_router = APIRouter(prefix="/presence", tags=["presence"])
system_router = APIRouter(prefix="/system", tags=["system"])
privacy_router = APIRouter(prefix="/privacy", tags=["privacy"])

@presence_router.get("/status", response_model=PresenceStatus)
async def get_presence_status() -> PresenceStatus:
    return presence_service.get_status()

@presence_router.post("/verify", response_model=PresenceStatus)
async def record_presence_verification(payload: VerificationPayload) -> PresenceStatus:
    return presence_service.record_verification(payload)

@presence_router.post("/toggle-mock", response_model=PresenceStatus)
async def toggle_mock_presence(approaching: bool = True, verified: bool = True) -> PresenceStatus:
    return presence_service.set_presence(approaching=approaching, verified=verified, user="owner")

@system_router.get("/metrics", response_model=SystemTelemetryData)
async def get_system_metrics() -> SystemTelemetryData:
    return system_metrics_collector.collect()

@privacy_router.get("/policies", response_model=List[WidgetPrivacyPolicy])
async def get_privacy_policies() -> List[WidgetPrivacyPolicy]:
    return presence_service.get_policies()
