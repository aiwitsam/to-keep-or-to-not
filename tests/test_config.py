"""Tests for tokeep.config module."""

import pytest

from tokeep.config import (
    load_config, save_config, _deep_copy_config, DEFAULT_CONFIG,
    load_backup_history, save_backup_record, BackupRecord,
    is_denied,
)


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Redirect config dir to temp path."""
    import tokeep.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg, "HISTORY_FILE", tmp_path / "history.json")
    return tmp_path


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, config_dir):
        config = load_config()
        assert config["backup"]["vault_name"] == "tokeep-vault"
        assert config["backup"]["retention_count"] == 5

    def test_merges_with_defaults(self, config_dir):
        import yaml
        custom = {"backup": {"retention_count": 10}}
        with open(config_dir / "config.yaml", "w") as f:
            yaml.dump(custom, f)

        config = load_config()
        assert config["backup"]["retention_count"] == 10
        assert config["backup"]["vault_name"] == "tokeep-vault"  # default preserved

    def test_handles_corrupt_yaml(self, config_dir):
        (config_dir / "config.yaml").write_text("{{invalid yaml: [")
        config = load_config()
        assert config["backup"]["vault_name"] == "tokeep-vault"


class TestSaveConfig:
    def test_creates_file(self, config_dir):
        save_config({"test": "value"})
        assert (config_dir / "config.yaml").exists()

    def test_roundtrip(self, config_dir):
        original = {"backup": {"vault_name": "my-vault", "retention_count": 3}}
        save_config(original)
        loaded = load_config()
        assert loaded["backup"]["vault_name"] == "my-vault"
        assert loaded["backup"]["retention_count"] == 3


class TestDeepCopy:
    def test_nested_dict_independence(self):
        copy = _deep_copy_config(DEFAULT_CONFIG)
        copy["backup"]["retention_count"] = 999
        assert DEFAULT_CONFIG["backup"]["retention_count"] == 5

    def test_list_independence(self):
        copy = _deep_copy_config(DEFAULT_CONFIG)
        copy["exclude_dirs"].append("new_dir")
        assert "new_dir" not in DEFAULT_CONFIG["exclude_dirs"]


class TestBackupHistory:
    def test_empty_when_no_file(self, config_dir):
        records = load_backup_history()
        assert records == []

    def test_save_and_load(self, config_dir):
        record = BackupRecord(
            drive_path="/mnt/d",
            snapshot_name="2026-03-08T14-30-00",
            projects_synced=5,
            projects_failed=0,
            bytes_transferred=1024,
            duration_seconds=12.5,
        )
        save_backup_record(record)
        loaded = load_backup_history()
        assert len(loaded) == 1
        assert loaded[0].drive_path == "/mnt/d"
        assert loaded[0].projects_synced == 5

    def test_appends_records(self, config_dir):
        save_backup_record(BackupRecord(drive_path="/mnt/d", projects_synced=1))
        save_backup_record(BackupRecord(drive_path="/mnt/e", projects_synced=2))
        loaded = load_backup_history()
        assert len(loaded) == 2

    def test_handles_corrupt_json(self, config_dir):
        (config_dir / "history.json").write_text("not json")
        records = load_backup_history()
        assert records == []


class TestIsDenied:
    def test_pattern_match(self):
        config = {"deny_list": {"patterns": ["secret"], "paths": []}}
        matches = is_denied("/home/user/my-secret-project", config)
        assert any("secret" in m for m in matches)

    def test_pattern_case_insensitive(self):
        config = {"deny_list": {"patterns": ["SECRET"], "paths": []}}
        matches = is_denied("/home/user/my-secret-project", config)
        assert len(matches) == 1

    def test_explicit_path_match(self, tmp_path):
        target = tmp_path / "sensitive"
        target.mkdir()
        config = {"deny_list": {"patterns": [], "paths": [str(target)]}}
        matches = is_denied(str(target), config)
        assert len(matches) == 1

    def test_no_match(self):
        config = {"deny_list": {"patterns": ["secret"], "paths": []}}
        matches = is_denied("/home/user/my-project", config)
        assert matches == []

    def test_empty_deny_list(self):
        config = {"deny_list": {"patterns": [], "paths": []}}
        matches = is_denied("/anything", config)
        assert matches == []
