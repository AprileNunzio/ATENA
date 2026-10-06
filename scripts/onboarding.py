import os
import sys
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server.core.onboarding.hardware_detector import hardware_detector
from server.core.onboarding.setup_wizard import onboarding_wizard

async def main() -> None:
    profile = hardware_detector.detect()
    print(f"RAM: {profile.ram_total_gb} GB (Available: {profile.ram_available_gb} GB)")
    print(f"CPU: {profile.cpu_cores} cores, Arch: {profile.cpu_arch}")
    print(f"CUDA: {profile.has_cuda}, Metal: {profile.has_metal}, Vulkan: {profile.has_vulkan}")
    if profile.gpu_name:
        print(f"GPU: {profile.gpu_name} (VRAM: {profile.vram_total_gb} GB)")
    print(f"Tier: {profile.tier}")
    print(f"Recommended System 1: {profile.recommended_system1}")
    print(f"Recommended System 2: {profile.recommended_system2} ({profile.system2_quantization})")
    print(f"Recommended Provider: {profile.recommended_provider}")

    auto = "--auto" in sys.argv
    use_api = "--api" in sys.argv
    provider = "gemini"
    for arg in sys.argv:
        if arg.startswith("--provider="):
            provider = arg.split("=")[1]

    cfg = onboarding_wizard.build_recommendation(
        force_external_api=use_api,
        api_provider=provider,
    )
    if auto or use_api:
        res = await onboarding_wizard.execute_setup(cfg)
        print(f"Setup completed: {res}")
    else:
        print("Run with --auto to trigger automated download, or --api --provider=gemini for cloud fallback.")

if __name__ == "__main__":
    asyncio.run(main())
