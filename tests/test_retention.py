"""Tests for tokeep.retention module."""


from tokeep.retention import (
    SnapshotInfo, list_snapshots, plan_retention, prune_snapshots,
    _parse_snapshot_date,
)


def _make_snapshot(tmp_path, name, project_names=None):
    """Helper to create a fake snapshot directory."""
    snap = tmp_path / name
    snap.mkdir()
    for proj in (project_names or ["proj-a"]):
        p = snap / proj
        p.mkdir()
        (p / "file.txt").write_text("content")
    return snap


class TestListSnapshots:
    def test_empty_vault(self, tmp_path):
        assert list_snapshots(str(tmp_path)) == []

    def test_nonexistent_path(self):
        assert list_snapshots("/nonexistent/path") == []

    def test_finds_snapshots(self, tmp_path):
        _make_snapshot(tmp_path, "2026-03-01T10-00-00")
        _make_snapshot(tmp_path, "2026-03-02T10-00-00")
        snaps = list_snapshots(str(tmp_path))
        assert len(snaps) == 2
        assert snaps[0].name == "2026-03-01T10-00-00"
        assert snaps[1].name == "2026-03-02T10-00-00"

    def test_skips_non_snapshot_dirs(self, tmp_path):
        _make_snapshot(tmp_path, "2026-03-01T10-00-00")
        (tmp_path / "random-dir").mkdir()
        (tmp_path / "manifest.json").write_text("{}")
        snaps = list_snapshots(str(tmp_path))
        assert len(snaps) == 1

    def test_detects_latest(self, tmp_path):
        _make_snapshot(tmp_path, "2026-03-01T10-00-00")
        _make_snapshot(tmp_path, "2026-03-02T10-00-00")
        (tmp_path / "latest").symlink_to("2026-03-02T10-00-00")

        snaps = list_snapshots(str(tmp_path))
        assert snaps[1].is_latest is True
        assert snaps[0].is_latest is False

    def test_counts_projects(self, tmp_path):
        _make_snapshot(tmp_path, "2026-03-01T10-00-00", ["proj-a", "proj-b", "proj-c"])
        snaps = list_snapshots(str(tmp_path))
        assert snaps[0].project_count == 3


class TestPlanRetention:
    def _make_infos(self, names):
        return [SnapshotInfo(
            name=n, path=f"/fake/{n}", date_human=n,
            project_count=1, size_human="1 MB", size_bytes=1048576,
            is_latest=(i == len(names) - 1),
        ) for i, n in enumerate(names)]

    def test_keep_all_when_under_limit(self):
        snapshots = self._make_infos(["s1", "s2"])
        to_delete, to_keep = plan_retention(snapshots, keep=5)
        assert len(to_delete) == 0
        assert len(to_keep) == 2

    def test_prunes_oldest(self):
        snapshots = self._make_infos(["s1", "s2", "s3", "s4", "s5"])
        to_delete, to_keep = plan_retention(snapshots, keep=2)
        assert len(to_delete) == 3
        assert len(to_keep) == 2
        assert to_delete[0].name == "s1"
        assert to_keep[0].name == "s4"

    def test_keep_equals_count(self):
        snapshots = self._make_infos(["s1", "s2", "s3"])
        to_delete, to_keep = plan_retention(snapshots, keep=3)
        assert len(to_delete) == 0
        assert len(to_keep) == 3


class TestPruneSnapshots:
    def test_deletes_directories(self, tmp_path):
        snap = _make_snapshot(tmp_path, "2026-03-01T10-00-00")
        info = SnapshotInfo(
            name="2026-03-01T10-00-00", path=str(snap),
            date_human="", project_count=1, size_human="1 MB",
            size_bytes=1048576, is_latest=False,
        )
        removed = prune_snapshots([info])
        assert removed == 1
        assert not snap.exists()

    def test_dry_run_preserves(self, tmp_path):
        snap = _make_snapshot(tmp_path, "2026-03-01T10-00-00")
        info = SnapshotInfo(
            name="2026-03-01T10-00-00", path=str(snap),
            date_human="", project_count=1, size_human="1 MB",
            size_bytes=1048576, is_latest=False,
        )
        removed = prune_snapshots([info], dry_run=True)
        assert removed == 1
        assert snap.exists()  # Still there


class TestParseSnapshotDate:
    def test_valid_format(self):
        assert _parse_snapshot_date("2026-03-08T14-30-00") == "2026-03-08 14:30:00"

    def test_invalid_format(self):
        assert _parse_snapshot_date("not-a-date") == "not-a-date"
