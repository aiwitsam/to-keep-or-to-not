"""Snapshot pruning and retention management."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SnapshotInfo:
    """Information about a single snapshot."""
    name: str
    path: str
    date_human: str
    project_count: int
    size_human: str
    size_bytes: int
    is_latest: bool


def _dir_size(path: Path) -> tuple[str, int]:
    """Get human-readable and byte size of a directory."""
    try:
        result = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            size_bytes = int(result.stdout.split()[0])
            # Human-readable
            nbytes = size_bytes
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if abs(nbytes) < 1024.0:
                    return f"{nbytes:.1f} {unit}", size_bytes
                nbytes /= 1024.0
            return f"{nbytes:.1f} PB", size_bytes
    except (subprocess.TimeoutExpired, OSError, IndexError, ValueError):
        pass
    return "?", 0


def _count_projects(snapshot_path: Path) -> int:
    """Count project directories in a snapshot (exclude _manifest.json)."""
    try:
        return sum(
            1 for d in snapshot_path.iterdir()
            if d.is_dir() and not d.name.startswith("_")
        )
    except OSError:
        return 0


def _parse_snapshot_date(name: str) -> str:
    """Parse snapshot name like 2026-03-08T14-30-00 to readable date."""
    try:
        # Replace T separator and dashes in time portion
        parts = name.split("T")
        if len(parts) == 2:
            date_part = parts[0]
            time_part = parts[1].replace("-", ":")
            return f"{date_part} {time_part}"
    except (IndexError, ValueError):
        pass
    return name


def list_snapshots(vault_path: str) -> list[SnapshotInfo]:
    """List all snapshots in a vault directory, sorted oldest first."""
    vault = Path(vault_path)
    if not vault.exists():
        return []

    # Find latest symlink target
    latest_target = None
    latest_link = vault / "latest"
    if latest_link.is_symlink():
        try:
            latest_target = latest_link.resolve().name
        except OSError:
            pass

    snapshots = []
    try:
        for entry in sorted(vault.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in ("latest",) or entry.is_symlink():
                continue
            # Skip non-snapshot dirs (no timestamp pattern)
            if len(entry.name) < 10 or "T" not in entry.name:
                continue

            size_human, size_bytes = _dir_size(entry)
            snapshots.append(SnapshotInfo(
                name=entry.name,
                path=str(entry),
                date_human=_parse_snapshot_date(entry.name),
                project_count=_count_projects(entry),
                size_human=size_human,
                size_bytes=size_bytes,
                is_latest=(entry.name == latest_target),
            ))
    except OSError:
        pass

    return snapshots


def plan_retention(snapshots: list[SnapshotInfo], keep: int) -> tuple[list[SnapshotInfo], list[SnapshotInfo]]:
    """Determine which snapshots to delete and which to keep.

    Args:
        snapshots: List of snapshots, sorted oldest first
        keep: Number of most recent snapshots to retain

    Returns:
        (to_delete, to_keep) tuple
    """
    if len(snapshots) <= keep:
        return [], snapshots

    to_keep = snapshots[-keep:]
    to_delete = snapshots[:-keep]

    return to_delete, to_keep


def prune_snapshots(to_delete: list[SnapshotInfo], dry_run: bool = False) -> int:
    """Remove snapshot directories.

    Args:
        to_delete: Snapshots to remove
        dry_run: If True, don't actually delete

    Returns:
        Number of snapshots removed
    """
    removed = 0
    for snap in to_delete:
        if dry_run:
            removed += 1
            continue
        try:
            shutil.rmtree(snap.path)
            removed += 1
        except OSError:
            pass
    return removed
