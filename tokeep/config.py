"""Configuration and backup history for tokeep."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR = Path.home() / ".tokeep"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
HISTORY_FILE = CONFIG_DIR / "history.json"
CRON_LOG = CONFIG_DIR / "cron.log"

DEFAULT_CONFIG = {
    "scan_path": str(Path.home()),
    "exclude_dirs": [
        "node_modules",
        "snap",
        ".cache",
        ".local",
        ".vscode-server",
        ".npm",
        ".nvm",
        ".cargo",
        ".rustup",
        ".ollama",
        ".config",
        ".ssh",
        ".gnupg",
        ".git",
        ".togit",
        ".tokeep",
        "__pycache__",
    ],
    "deny_list": {
        "patterns": [],
        "paths": [],
    },
    "backup": {
        "vault_name": "tokeep-vault",
        "retention_count": 5,
        "global_excludes": [
            "node_modules",
            ".venv",
            "venv",
            "__pycache__",
            ".git",
            ".cache",
            "dist",
            "build",
            "*.pyc",
            "*.pyo",
            ".eggs",
        ],
        "sensitive_excludes": [
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "credentials.json",
            "token.json",
            "settings.local.json",
            "*.p12",
            "*.pfx",
        ],
    },
}


@dataclass
class BackupRecord:
    """A single backup run record."""
    timestamp: str = ""
    drive_path: str = ""
    snapshot_name: str = ""
    projects_synced: int = 0
    projects_failed: int = 0
    bytes_transferred: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load config from ~/.tokeep/config.yaml, merged with defaults."""
    if not CONFIG_FILE.exists():
        return _deep_copy_config(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r") as f:
            loaded = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return _deep_copy_config(DEFAULT_CONFIG)

    merged = _deep_copy_config(DEFAULT_CONFIG)
    for key, value in loaded.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _deep_copy_config(config: dict) -> dict:
    """Deep copy config dict to avoid mutation of defaults."""
    result = {}
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = _deep_copy_config(value)
        elif isinstance(value, list):
            result[key] = value.copy()
        else:
            result[key] = value
    return result


def save_config(config: dict):
    """Write config to disk."""
    _ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def load_backup_history() -> list[BackupRecord]:
    """Load backup history from disk."""
    if not HISTORY_FILE.exists():
        return []

    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    records = []
    for entry in data:
        records.append(BackupRecord(
            timestamp=entry.get("timestamp", ""),
            drive_path=entry.get("drive_path", ""),
            snapshot_name=entry.get("snapshot_name", ""),
            projects_synced=entry.get("projects_synced", 0),
            projects_failed=entry.get("projects_failed", 0),
            bytes_transferred=entry.get("bytes_transferred", 0),
            duration_seconds=entry.get("duration_seconds", 0.0),
            errors=entry.get("errors", []),
        ))
    return records


def save_backup_record(record: BackupRecord):
    """Append a backup record to history."""
    _ensure_config_dir()
    history = load_backup_history()
    history.append(record)

    with open(HISTORY_FILE, "w") as f:
        json.dump([asdict(r) for r in history], f, indent=2)


def load_togit_decisions() -> Optional[dict]:
    """Load togit decisions if togit is installed. Returns dict or None."""
    decisions_file = Path.home() / ".togit" / "decisions.json"
    if not decisions_file.exists():
        return None

    try:
        with open(decisions_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def is_denied(path: str, config: Optional[dict] = None) -> list[str]:
    """Check if a path matches deny-list patterns. Returns matching patterns."""
    if config is None:
        config = load_config()

    deny = config.get("deny_list", {})
    patterns = deny.get("patterns", [])
    explicit_paths = deny.get("paths", [])

    matches = []
    name = Path(path).name.lower()
    resolved = str(Path(path).resolve())

    for pattern in patterns:
        if pattern.lower() in name:
            matches.append(f"pattern:{pattern}")

    for p in explicit_paths:
        if str(Path(p).resolve()) == resolved:
            matches.append(f"path:{p}")

    return matches
