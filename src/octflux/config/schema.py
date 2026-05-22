"""Configuration model (Pydantic). Parsed from YAML; secrets via ${ENV} refs.

Each collector/sink entry follows the driver pattern: ``driver`` selects the
implementation from the registry, ``options`` are passed to its builder. The
entry's key is its instance name (so you can run the same driver twice, e.g. an
hourly and a weekly ``consumption``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OctopusSettings(BaseModel):
    api_key: str
    account_number: str
    postcode: str | None = None  # for carbon intensity; else derived from account
    rest_base_url: str = "https://api.octopus.energy/v1"
    graphql_url: str = "https://api.octopus.energy/v1/graphql/"


class CollectorConfig(BaseModel):
    driver: str | None = None  # defaults to the entry's key
    enabled: bool = True
    schedule: str = "0 * * * *"  # cron (5 fields) or "<int>s" interval
    options: dict = Field(default_factory=dict)


class SinkConfig(BaseModel):
    driver: str | None = None
    enabled: bool = True
    options: dict = Field(default_factory=dict)


class ApiConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8088


class McpConfig(BaseModel):
    enabled: bool = True
    mount_path: str = "/mcp"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "console"  # console | json


class MedallionConfig(BaseModel):
    enabled: bool = True
    schedule: str = "30 * * * *"  # silver fact_cost refresh cadence
    window_days: int = 7          # rolling window recomputed each refresh


class Config(BaseModel):
    octopus: OctopusSettings
    collectors: dict[str, CollectorConfig] = Field(default_factory=dict)
    sinks: dict[str, SinkConfig] = Field(default_factory=dict)
    medallion: MedallionConfig = Field(default_factory=MedallionConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def driver_of(self, name: str, cfg: CollectorConfig | SinkConfig) -> str:
        return cfg.driver or name
