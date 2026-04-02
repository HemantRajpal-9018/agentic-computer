"""Configuration management for agentic-computer.

Loads settings from environment variables with sensible defaults.
All secrets come from env vars — never hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: Literal["openai", "anthropic", "ollama"] = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4096
    api_key: str = ""
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Create LLMConfig from environment variables."""
        provider = os.getenv("LLM_PROVIDER", "openai")
        key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "ollama": "",
        }
        return cls(
            provider=provider,  # type: ignore[arg-type]
            model=os.getenv("LLM_MODEL", "gpt-4o"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            api_key=os.getenv(key_map.get(provider, ""), ""),
            base_url=os.getenv("OLLAMA_BASE_URL") if provider == "ollama" else None,
        )


@dataclass
class BrowserConfig:
    """Browser automation configuration."""

    headless: bool = True
    timeout: int = 30000

    @classmethod
    def from_env(cls) -> BrowserConfig:
        return cls(
            headless=os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
            timeout=int(os.getenv("BROWSER_TIMEOUT", "30000")),
        )


@dataclass
class MemoryConfig:
    """Memory / storage configuration."""

    sqlite_path: Path = field(default_factory=lambda: Path("./data/agentic.db"))
    chroma_dir: Path = field(default_factory=lambda: Path("./data/chroma"))
    max_entries: int = 10000

    @classmethod
    def from_env(cls) -> MemoryConfig:
        return cls(
            sqlite_path=Path(os.getenv("SQLITE_DB_PATH", "./data/agentic.db")),
            chroma_dir=Path(os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")),
            max_entries=int(os.getenv("MEMORY_MAX_ENTRIES", "10000")),
        )


@dataclass
class SearchConfig:
    """Web search configuration."""

    provider: Literal["serper", "tavily"] = "serper"
    api_key: str = ""

    @classmethod
    def from_env(cls) -> SearchConfig:
        provider = os.getenv("SEARCH_PROVIDER", "serper")
        key_map = {"serper": "SERPER_API_KEY", "tavily": "TAVILY_API_KEY"}
        return cls(
            provider=provider,  # type: ignore[arg-type]
            api_key=os.getenv(key_map.get(provider, ""), ""),
        )


@dataclass
class SandboxConfig:
    """Code execution sandbox configuration."""

    enabled: bool = True
    timeout: int = 30
    max_memory_mb: int = 512

    @classmethod
    def from_env(cls) -> SandboxConfig:
        return cls(
            enabled=os.getenv("SANDBOX_ENABLED", "true").lower() == "true",
            timeout=int(os.getenv("SANDBOX_TIMEOUT", "30")),
            max_memory_mb=int(os.getenv("SANDBOX_MAX_MEMORY_MB", "512")),
        )


@dataclass
class ServerConfig:
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])

    @classmethod
    def from_env(cls) -> ServerConfig:
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
        return cls(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8000")),
            reload=os.getenv("SERVER_RELOAD", "true").lower() == "true",
            cors_origins=[o.strip() for o in origins.split(",")],
        )


@dataclass
class Settings:
    """Root settings container — aggregates all sub-configs."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "text"

    @classmethod
    def from_env(cls) -> Settings:
        """Load all settings from environment variables."""
        return cls(
            llm=LLMConfig.from_env(),
            browser=BrowserConfig.from_env(),
            memory=MemoryConfig.from_env(),
            search=SearchConfig.from_env(),
            sandbox=SandboxConfig.from_env(),
            server=ServerConfig.from_env(),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_format=os.getenv("LOG_FORMAT", "text"),  # type: ignore[arg-type]
        )


def get_settings() -> Settings:
    """Return application settings loaded from environment."""
    return Settings.from_env()
