"""Tests for tokeep.drives module."""


from tokeep.drives import _human_size, check_space, validate_drive


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(500) == "500.0 B"

    def test_kilobytes(self):
        assert _human_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert _human_size(10 * 1024 * 1024) == "10.0 MB"

    def test_gigabytes(self):
        assert _human_size(2.5 * 1024**3) == "2.5 GB"

    def test_zero(self):
        assert _human_size(0) == "0.0 B"


class TestCheckSpace:
    def test_has_space(self, tmp_path):
        result = check_space(str(tmp_path), 1024)
        assert result.has_space is True
        assert result.needed_bytes == 1024

    def test_needs_too_much(self, tmp_path):
        result = check_space(str(tmp_path), 10**18)  # 1 exabyte
        assert result.has_space is False

    def test_nonexistent_path(self):
        result = check_space("/nonexistent/path", 1024)
        assert result.free_bytes == 0
        assert result.has_space is False


class TestValidateDrive:
    def test_valid_directory(self, tmp_path):
        drive = validate_drive(str(tmp_path))
        assert drive is not None
        assert drive.mount_point == str(tmp_path)

    def test_nonexistent(self):
        assert validate_drive("/nonexistent/path") is None

    def test_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("test")
        assert validate_drive(str(f)) is None
