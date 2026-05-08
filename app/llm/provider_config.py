import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ProviderConfig:
    api_key: str
    base_url: str
    model: str


def _load_config() -> dict:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _provider_presets() -> dict:
    return _load_config().get("providers", {}) or {}


def default_provider() -> str:
    return (
        os.getenv("LLM_PROVIDER")
        or _load_config().get("default", {}).get("provider")
        or "deepseek"
    ).lower()


def provider_options() -> list:
    providers = _provider_presets()
    return [
        {
            "name": name,
            "label": preset.get("label") or name,
            "default_model": preset.get("default_model") or "",
        }
        for name, preset in providers.items()
        if name != "custom"
    ]


def _preset_for(provider: str) -> dict:
    presets = _provider_presets()
    return presets.get(provider) or presets.get("custom", {})


def resolve(
    purpose: str = "chat",
    override: Optional[dict] = None,
) -> ProviderConfig:
    """
    purpose="chat":
      1. provider 来自 override["provider"] 或 LLM_PROVIDER env，fallback config.default.provider
      2. api_key  = config providers.<provider>.api_key_env，fallback LLM_API_KEY，fallback "local"
      3. base_url = LLM_BASE_URL env，fallback config providers.<provider>.base_url
      4. model    = override["model_id"]（非空）> LLM_MODEL_ID env > config providers.<provider>.default_model

    purpose="summary":
      1. 若 SUMMARY_LLM_PROVIDER / SUMMARY_LLM_API_KEY / SUMMARY_LLM_BASE_URL /
         SUMMARY_LLM_MODEL_ID 任一存在，则使用 SUMMARY_LLM_* 分支，不受 override 影响
      2. 否则 fallback 到 chat 分支（复用主模型）
    """
    if purpose == "summary":
        has_summary_cfg = any(
            os.getenv(k)
            for k in [
                "SUMMARY_LLM_PROVIDER",
                "SUMMARY_LLM_API_KEY",
                "SUMMARY_LLM_BASE_URL",
                "SUMMARY_LLM_MODEL_ID",
            ]
        )
        if has_summary_cfg:
            provider = os.getenv("SUMMARY_LLM_PROVIDER", "deepseek").lower()
            preset = _preset_for(provider)
            api_key_env = preset.get("api_key_env")
            api_key = (
                os.getenv("SUMMARY_LLM_API_KEY")
                or (os.getenv(api_key_env) if api_key_env else None)
                or "local"
            )
            base_url = os.getenv("SUMMARY_LLM_BASE_URL") or preset.get("base_url") or ""
            model = os.getenv("SUMMARY_LLM_MODEL_ID") or preset.get("default_model") or ""
            if not base_url or not model:
                raise ValueError(f"Provider '{provider}' 配置不完整，请检查 config.yaml 或环境变量")
            return ProviderConfig(api_key=api_key, base_url=base_url, model=model)
        override = None

    provider = (
        (override.get("provider") if override else None)
        or default_provider()
    ).lower()
    preset = _preset_for(provider)
    api_key_env = preset.get("api_key_env")
    api_key = (
        (os.getenv(api_key_env) if api_key_env else None)
        or os.getenv("LLM_API_KEY")
        or "local"
    )
    base_url = os.getenv("LLM_BASE_URL") or preset.get("base_url") or ""
    model = (
        (override.get("model_id") if override and override.get("model_id") else None)
        or os.getenv("LLM_MODEL_ID")
        or preset.get("default_model")
        or ""
    )
    if not base_url or not model:
        raise ValueError(f"Provider '{provider}' 配置不完整，请检查 config.yaml 或环境变量")
    return ProviderConfig(api_key=api_key, base_url=base_url, model=model)
