"""
Configuration for Configuration Service (SVC-004).

Uses pydantic-settings for environment-based configuration.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    Loaded from environment variables with CONFIG_ prefix.

    Profile Collection Integration:
        The service loads device registries from beamline profile collections:
        1. startup_scripts: Execute startup scripts and introspect device namespace
        2. happi: Parse happi_db.json
        3. bits: Parse devices.yml + iconfig.yml
        4. mock: Use mock data for testing without profile collection

    Set CONFIG_PROFILE_PATH environment variable to point to
    the profile collection directory (e.g., /opt/bluesky/profile_collection).
    """

    # Service identification
    service_name: str = "configuration_service"
    service_id: str = "SVC-004"

    # Profile collection configuration
    # Can be set via CONFIG_PROFILE_PATH
    profile_path: Optional[Path] = None

    # Path to startup directory (auto-derived from profile_path if not set)
    startup_dir: Optional[Path] = None

    # Loading strategy: "auto", "startup_scripts", "happi", "bits", or "mock"
    # auto: Auto-detect based on files present in profile_path (default)
    # startup_scripts: Execute startup scripts and introspect device namespace
    # happi: Parse happi_db.json (LCLS/SLAC format)
    # bits: Parse devices.yml + iconfig.yml (BCDA-APS format)
    # mock: Use mock data for testing
    load_strategy: str = "auto"

    # If True, use mock data instead of loading from profile (legacy, use load_strategy instead)
    use_mock_data: bool = False

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8004

    # Logging
    log_level: str = "INFO"

    # CORS (if needed for web UI)
    cors_origins: list[str] = ["*"]

    # Metrics
    metrics_enabled: bool = True
    metrics_port: int = 9004

    # SQLite database for persistent stores (device change history, standalone PVs)
    db_path: Path = Path("/var/lib/bluesky/config_service.db")

    # Enable runtime device change history (CRUD endpoints)
    device_change_history_enabled: bool = True

    model_config = SettingsConfigDict(
        env_prefix="CONFIG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    def get_startup_dir(self) -> Optional[Path]:
        """Get path to startup directory."""
        if self.startup_dir:
            return self.startup_dir
        if self.profile_path:
            return self.profile_path / "startup"
        return None

    def get_effective_load_strategy(self) -> str:
        """Get effective load strategy, considering legacy use_mock_data flag."""
        if self.use_mock_data:
            return "mock"
        return self.load_strategy

