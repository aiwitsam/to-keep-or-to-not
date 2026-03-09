"""Tests for tokeep.manifest module."""


from tokeep.manifest import (
    _structural_checksum, create_manifest, save_manifest,
    load_manifest, content_checksum,
)


class TestStructuralChecksum:
    def test_deterministic(self):
        entries = [("a.py", 100, 1234.0), ("b.py", 200, 5678.0)]
        h1 = _structural_checksum(entries)
        h2 = _structural_checksum(entries)
        assert h1 == h2

    def test_order_independent(self):
        """Checksum sorts internally, so order shouldn't matter."""
        entries_a = [("b.py", 200, 5678.0), ("a.py", 100, 1234.0)]
        entries_b = [("a.py", 100, 1234.0), ("b.py", 200, 5678.0)]
        assert _structural_checksum(entries_a) == _structural_checksum(entries_b)

    def test_different_content_different_hash(self):
        h1 = _structural_checksum([("a.py", 100, 1234.0)])
        h2 = _structural_checksum([("a.py", 200, 1234.0)])
        assert h1 != h2

    def test_empty_entries(self):
        h = _structural_checksum([])
        assert isinstance(h, str)
        assert len(h) == 64  # SHA256 hex


class TestCreateManifest:
    def test_creates_manifest(self, tmp_path):
        # Create a fake project
        project = tmp_path / "my-project"
        project.mkdir()
        (project / "main.py").write_text("print('hello')")
        (project / "readme.md").write_text("# My Project")

        manifest = create_manifest(str(tmp_path), ["my-project"])
        assert manifest.total_files == 2
        assert len(manifest.projects) == 1
        assert manifest.projects[0].name == "my-project"
        assert manifest.projects[0].file_count == 2
        assert manifest.projects[0].structural_checksum

    def test_skips_missing_project(self, tmp_path):
        manifest = create_manifest(str(tmp_path), ["nonexistent"])
        assert len(manifest.projects) == 0

    def test_multiple_projects(self, tmp_path):
        for name in ("proj-a", "proj-b"):
            p = tmp_path / name
            p.mkdir()
            (p / "file.txt").write_text(f"content of {name}")

        manifest = create_manifest(str(tmp_path), ["proj-a", "proj-b"])
        assert len(manifest.projects) == 2
        assert manifest.total_files == 2


class TestSaveAndLoadManifest:
    def test_roundtrip(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "file.txt").write_text("hello")

        manifest = create_manifest(str(tmp_path), ["proj"])
        save_manifest(manifest, str(tmp_path))

        loaded = load_manifest(str(tmp_path))
        assert loaded is not None
        assert loaded.total_files == manifest.total_files
        assert len(loaded.projects) == 1
        assert loaded.projects[0].structural_checksum == manifest.projects[0].structural_checksum

    def test_load_missing_returns_none(self, tmp_path):
        assert load_manifest(str(tmp_path)) is None

    def test_load_corrupt_returns_none(self, tmp_path):
        (tmp_path / "_manifest.json").write_text("not json")
        assert load_manifest(str(tmp_path)) is None


class TestContentChecksum:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = content_checksum(str(f))
        h2 = content_checksum(str(f))
        assert h1 == h2

    def test_different_content(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")
        assert content_checksum(str(f1)) != content_checksum(str(f2))

    def test_missing_file(self):
        assert content_checksum("/nonexistent/file.txt") == ""
