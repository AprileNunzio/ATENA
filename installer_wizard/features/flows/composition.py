import auth
from config import ETC_DIR, STATE_DIR, read_env
from settings import apply_config

from features.flows.application.studio import Studio
from features.flows.infrastructure.env_settings import EnvSettings
from features.flows.infrastructure.password_verifier import PasswordVerifier
from features.flows.infrastructure.signed_store import SignedVersionStore

studio = Studio(
    settings=EnvSettings(read_env, apply_config),
    store=SignedVersionStore(STATE_DIR / "flows" / "main.json", ETC_DIR / "flows.key"),
    verifier=PasswordVerifier(auth.authenticate),
)
