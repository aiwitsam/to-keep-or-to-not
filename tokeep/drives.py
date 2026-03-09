"""External drive detection, mount validation, and space checks."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

# System mounts to skip in WSL2
SYSTEM_MOUNTS = {"c", "wsl", "wslg"}


@dataclass
class DriveInfo:
    """Information about a detected drive."""
    mount_point: str
    label: str
    filesystem: str
    total_bytes: int
    free_bytes: int
    free_human: str


@dataclass
class SpaceCheck:
    """Result of a space availability check."""
    drive_path: str
    needed_bytes: int
    free_bytes: int
    has_space: bool
    needed_human: str
    free_human: str


def _human_size(nbytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024.0:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} PB"


def _get_filesystem(mount_point: str) -> str:
    """Try to detect filesystem type for a mount point."""
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == mount_point:
                    return parts[2]
    except OSError:
        pass
    return "unknown"


def find_external_drives() -> list[DriveInfo]:
    """Scan /mnt/ for non-system mounted drives."""
    drives = []
    mnt = Path("/mnt")

    if not mnt.exists():
        return drives

    for entry in sorted(mnt.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.lower() in SYSTEM_MOUNTS:
            continue

        drive = validate_drive(str(entry), require_external=True)
        if drive:
            drives.append(drive)

    return drives


def validate_drive(path: str, require_external: bool = False) -> DriveInfo | None:
    """Validate a path as a writable directory. Returns DriveInfo or None.

    Args:
        path: Directory path to validate
        require_external: If True, reject paths on the root filesystem
                          (used for auto-detection in /mnt/)
    """
    p = Path(path)

    if not p.exists() or not p.is_dir():
        return None

    try:
        # Check if writable
        if not os.access(str(p), os.W_OK):
            return None

        usage = shutil.disk_usage(str(p))

        # For auto-detection, skip root filesystem mounts
        if require_external:
            root_usage = shutil.disk_usage("/")
            if usage.total == root_usage.total:
                try:
                    has_content = any(p.iterdir())
                except PermissionError:
                    return None
                if not has_content:
                    return None

    except (OSError, PermissionError):
        return None

    fs_type = _get_filesystem(str(p))
    label = p.name

    return DriveInfo(
        mount_point=str(p),
        label=label,
        filesystem=fs_type,
        total_bytes=usage.total,
        free_bytes=usage.free,
        free_human=_human_size(usage.free),
    )


def check_space(drive_path: str, needed_bytes: int) -> SpaceCheck:
    """Check if a drive has enough free space."""
    try:
        usage = shutil.disk_usage(drive_path)
        free = usage.free
    except OSError:
        free = 0

    return SpaceCheck(
        drive_path=drive_path,
        needed_bytes=needed_bytes,
        free_bytes=free,
        has_space=free >= needed_bytes,
        needed_human=_human_size(needed_bytes),
        free_human=_human_size(free),
    )
