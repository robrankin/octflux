"""Load and validate config from a YAML file, expanding ``${ENV_VAR}`` refs.

Keeping secrets as ``${ENV}`` references means the YAML can be committed/mounted
while the API key and DSNs come from the environment (or a .env-style export).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .schema import Config

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-(.*?))?\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        def sub(match: re.Match) -> str:
            name, default = match.group(1), match.group(2)
            return os.environ.get(name, default if default is not None else "")
        return _ENV_RE.sub(sub, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return Config.model_validate(_expand(raw))
