"""Runtime configuration. Everything policy-related is data, not prompt text."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SUPPORT_AI_", extra="ignore")

    # Storage
    db_url: str = f"sqlite:///{(ROOT / 'support.db').as_posix()}"

    # Model serving
    backend: str = Field(default="mock", description="mock | llamacpp")
    gguf_path: str = str(ROOT / "models" / "qwen2.5-3b-support-q4_k_m.gguf")
    n_ctx: int = 4096
    n_threads: int = 4
    temperature: float = 0.0
    max_tokens: int = 320

    # Policy constants (deterministic; versioned via POLICY_VERSION)
    policy_version: str = "2026.1"
    return_window_days: int = 30
    defective_return_window_days: int = 90
    refund_approval_threshold_cents: int = 15_000
    max_tool_calls: int = 6
    tool_timeout_s: float = 5.0

    # Safety
    allow_cross_account_lookup: bool = False  # must never be enabled in prod
    demo_mode: bool = True


settings = Settings()
