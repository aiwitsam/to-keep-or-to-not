"""Tests for tokeep.verify module."""


from tokeep.manifest import create_manifest
from tokeep.verify import verify_backup


class TestVerifyBackup:
    def _setup_snapshot(self, tmp_path):
        """Create a snapshot with a project and its manifest."""
        project = tmp_path / "my-project"
        project.mkdir()
        (project / "main.py").write_text("print('hello')")
        (project / "data.txt").write_text("some data here")

        manifest = create_manifest(str(tmp_path), ["my-project"])
        return manifest

    def test_passes_valid_snapshot(self, tmp_path):
        manifest = self._setup_snapshot(tmp_path)
        result = verify_backup(str(tmp_path), manifest)
        assert result.passed is True
        assert result.projects_checked == 1
        assert result.projects_passed == 1
        assert result.missing == []
        assert result.corrupted == []

    def test_detects_missing_file(self, tmp_path):
        manifest = self._setup_snapshot(tmp_path)
        # Remove a file
        (tmp_path / "my-project" / "main.py").unlink()

        result = verify_backup(str(tmp_path), manifest)
        assert result.passed is False
        assert len(result.missing) == 1
        assert "main.py" in result.missing[0]

    def test_detects_missing_project(self, tmp_path):
        manifest = self._setup_snapshot(tmp_path)
        # Remove entire project directory
        import shutil
        shutil.rmtree(tmp_path / "my-project")

        result = verify_backup(str(tmp_path), manifest)
        assert result.passed is False
        assert len(result.missing) == 1
        assert "entire project" in result.missing[0]

    def test_detects_size_change(self, tmp_path):
        manifest = self._setup_snapshot(tmp_path)
        # Modify a file's content (changes size)
        (tmp_path / "my-project" / "main.py").write_text("print('this is much longer content now')")

        result = verify_backup(str(tmp_path), manifest)
        assert result.passed is False
        assert len(result.corrupted) >= 1

    def test_detects_extra_files(self, tmp_path):
        manifest = self._setup_snapshot(tmp_path)
        # Add an extra file
        (tmp_path / "my-project" / "extra.txt").write_text("I shouldn't be here")

        result = verify_backup(str(tmp_path), manifest)
        assert result.passed is True  # Extra files don't cause failure
        assert len(result.extra) == 1

    def test_deep_mode(self, tmp_path):
        manifest = self._setup_snapshot(tmp_path)
        result = verify_backup(str(tmp_path), manifest, deep=True)
        assert result.passed is True
        assert result.projects_passed == 1

    def test_empty_manifest(self, tmp_path):
        from tokeep.manifest import Manifest
        manifest = Manifest()
        result = verify_backup(str(tmp_path), manifest)
        assert result.passed is True
        assert result.projects_checked == 0
