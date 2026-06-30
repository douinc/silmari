# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuration via environment (prefix ``SILMARI_``) / ``.env``."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SILMARI_", env_file=".env", extra="ignore")

    # LLM (via a LiteLLM-compatible proxy)
    llm_enabled: bool = False
    litellm_base_url: str = "http://localhost:4000"
    litellm_api_key: str = ""
    llm_default_model: str = "local/default"
    llm_summary_model: str = "local/default"

    # Sensitive-data filter (redaction for any non-local model call)
    sensitive_filter_enabled: bool = True
    sensitive_filter_url: str = ""
    sensitive_filter_mode: str = "local"  # local | hybrid | remote

    # Audit store
    audit_store_url: str = "sqlite://"


@lru_cache
def get_settings() -> Settings:
    return Settings()
