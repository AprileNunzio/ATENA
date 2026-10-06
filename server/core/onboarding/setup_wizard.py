import os
from typing import Dict, Any, Optional
from pydantic import BaseModel
from server.core.onboarding.hardware_detector import hardware_detector, HardwareProfile
from server.core.onboarding.downloader import model_downloader
from server.shared.i18n.provider import global_translator

class OnboardingConfig(BaseModel):
    provider: str
    system1_model: str
    system2_model: str
    system2_quantization: str
    api_key: Optional[str] = None
    use_external_api: bool
    hardware: HardwareProfile
    lang: str = "en"

class OnboardingWizard:
    def __init__(self, env_path: str = ".env") -> None:
        self.env_path = env_path
        self._module_path = "core/onboarding"

    def analyze_system(self) -> HardwareProfile:
        return hardware_detector.detect()

    def build_recommendation(
        self,
        force_external_api: bool = False,
        api_provider: str = "gemini",
        api_key: Optional[str] = None,
        lang: str = "en",
    ) -> OnboardingConfig:
        profile = self.analyze_system()
        if force_external_api or not profile.supports_local:
            provider = api_provider
            use_ext = True
        else:
            provider = "ollama"
            use_ext = False

        return OnboardingConfig(
            provider=provider,
            system1_model=profile.recommended_system1,
            system2_model=profile.recommended_system2,
            system2_quantization=profile.system2_quantization,
            api_key=api_key,
            use_external_api=use_ext,
            hardware=profile,
            lang=lang,
        )

    def persist_config(self, config: OnboardingConfig) -> None:
        env_lines = []
        if os.path.exists(self.env_path):
            with open(self.env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        updates = {
            "LLM_PROVIDER": config.provider,
            "SYSTEM1_MODEL": config.system1_model,
            "SYSTEM2_MODEL": config.system2_model,
            "ATENA_LLM_MODEL": config.system2_model,
            "ATENA_LLM_FAST_MODEL": config.system1_model,
        }
        if config.api_key:
            if config.provider == "gemini":
                updates["GEMINI_API_KEY"] = config.api_key
            elif config.provider == "openai":
                updates["OPENAI_API_KEY"] = config.api_key
            elif config.provider == "claude" or config.provider == "anthropic":
                updates["ANTHROPIC_API_KEY"] = config.api_key

        existing_keys = set()
        new_lines = []
        for line in env_lines:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                existing_keys.add(key)
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}\n")
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        for k, v in updates.items():
            if k not in existing_keys:
                new_lines.append(f"{k}={v}\n")

        with open(self.env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    async def execute_setup(
        self,
        config: OnboardingConfig,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        self.persist_config(config)
        lang = config.lang
        
        status_completed = global_translator.translate(self._module_path, "status.completed", lang)
        
        results = {
            "status": status_completed,
            "provider": config.provider,
            "system1_model": config.system1_model,
            "system2_model": config.system2_model,
            "downloaded": [],
            "skipped": [],
            "errors": [],
        }

        if config.provider == "ollama" and not config.use_external_api:
            for model_name in [config.system1_model, config.system2_model]:
                already_present = await model_downloader.is_model_installed(model_name)
                if already_present:
                    skipped_msg = global_translator.translate(self._module_path, "status.skipped", lang)
                    results["skipped"].append({model_name: skipped_msg})
                    continue
                    
                success = await model_downloader.pull_model(model_name, progress_hook=progress_callback)
                if success:
                    results["downloaded"].append(model_name)
                else:
                    err_msg = global_translator.translate(self._module_path, "errors.pull_failed", lang, model=model_name)
                    results["errors"].append(err_msg)

        return results

onboarding_wizard = OnboardingWizard()
