"""Optional GPG encryption for backup snapshots."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EncryptResult:
    """Result of an encryption operation."""
    success: bool = True
    archive_path: str = ""
    original_size: int = 0
    encrypted_size: int = 0
    error: str = ""


def is_gpg_available() -> bool:
    """Check if gpg is installed and accessible."""
    try:
        result = subprocess.run(
            ["gpg", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def list_gpg_keys() -> list[str]:
    """List available GPG key IDs."""
    try:
        result = subprocess.run(
            ["gpg", "--list-keys", "--keyid-format", "long"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        keys = []
        for line in result.stdout.splitlines():
            # Lines like "pub   rsa4096/ABCDEF1234567890 2024-01-01 [SC]"
            if line.strip().startswith(("pub", "sub")):
                parts = line.split("/")
                if len(parts) >= 2:
                    key_id = parts[1].split()[0]
                    keys.append(key_id)
        return keys
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def encrypt_snapshot(snapshot_path: str, gpg_key_id: str) -> EncryptResult:
    """Encrypt a snapshot directory into a .tar.gpg archive.

    Creates: <snapshot_path>.tar.gpg
    The original snapshot directory is preserved (not deleted).

    Args:
        snapshot_path: Path to the snapshot directory
        gpg_key_id: GPG key ID to encrypt with

    Returns:
        EncryptResult with details
    """
    snap = Path(snapshot_path)
    if not snap.exists():
        return EncryptResult(success=False, error=f"Snapshot not found: {snapshot_path}")

    if not is_gpg_available():
        return EncryptResult(success=False, error="gpg not installed — install with: sudo apt install gnupg")

    archive_path = str(snap) + ".tar.gpg"

    try:
        # tar the directory and pipe to gpg
        # tar -cf - <dir> | gpg --encrypt --recipient <key> -o <output>
        tar_cmd = ["tar", "-cf", "-", "-C", str(snap.parent), snap.name]
        gpg_cmd = ["gpg", "--encrypt", "--recipient", gpg_key_id, "--output", archive_path, "--trust-model", "always"]

        tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        gpg_proc = subprocess.Popen(gpg_cmd, stdin=tar_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tar_proc.stdout.close()

        gpg_stdout, gpg_stderr = gpg_proc.communicate(timeout=1800)  # 30 min timeout
        tar_proc.wait(timeout=10)

        if gpg_proc.returncode != 0:
            error = gpg_stderr.decode().strip() if gpg_stderr else f"gpg exited with code {gpg_proc.returncode}"
            return EncryptResult(success=False, error=error)

        # Get sizes
        original_size = sum(f.stat().st_size for f in snap.rglob("*") if f.is_file())
        encrypted_size = Path(archive_path).stat().st_size

        return EncryptResult(
            success=True,
            archive_path=archive_path,
            original_size=original_size,
            encrypted_size=encrypted_size,
        )

    except subprocess.TimeoutExpired:
        for proc in (tar_proc, gpg_proc):
            try:
                proc.kill()
            except OSError:
                pass
        return EncryptResult(success=False, error="Encryption timed out (30 min)")
    except OSError as e:
        return EncryptResult(success=False, error=str(e))


def decrypt_snapshot(archive_path: str, dest_path: str) -> EncryptResult:
    """Decrypt a .tar.gpg archive back to a directory.

    Args:
        archive_path: Path to the .tar.gpg file
        dest_path: Directory to extract into

    Returns:
        EncryptResult with details
    """
    archive = Path(archive_path)
    if not archive.exists():
        return EncryptResult(success=False, error=f"Archive not found: {archive_path}")

    if not is_gpg_available():
        return EncryptResult(success=False, error="gpg not installed")

    dest = Path(dest_path)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        # gpg --decrypt <file> | tar -xf - -C <dest>
        gpg_cmd = ["gpg", "--decrypt", str(archive)]
        tar_cmd = ["tar", "-xf", "-", "-C", str(dest)]

        gpg_proc = subprocess.Popen(gpg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tar_proc = subprocess.Popen(tar_cmd, stdin=gpg_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        gpg_proc.stdout.close()

        tar_stdout, tar_stderr = tar_proc.communicate(timeout=1800)
        gpg_proc.wait(timeout=10)

        if tar_proc.returncode != 0:
            error = tar_stderr.decode().strip() if tar_stderr else f"tar exited with code {tar_proc.returncode}"
            return EncryptResult(success=False, error=error)

        return EncryptResult(
            success=True,
            archive_path=str(archive),
            encrypted_size=archive.stat().st_size,
        )

    except subprocess.TimeoutExpired:
        for proc in (gpg_proc, tar_proc):
            try:
                proc.kill()
            except OSError:
                pass
        return EncryptResult(success=False, error="Decryption timed out (30 min)")
    except OSError as e:
        return EncryptResult(success=False, error=str(e))
