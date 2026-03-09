"""Restore files from backup snapshots."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RestoreResult:
    """Result of a restore operation."""
    success: bool = True
    project_name: str = ""
    snapshot_name: str = ""
    dest_path: str = ""
    files_restored: int = 0
    bytes_restored: int = 0
    duration_seconds: float = 0.0
    error: str = ""


def list_projects_in_snapshot(snapshot_path: str) -> list[str]:
    """List project directories available in a snapshot."""
    snap = Path(snapshot_path)
    if not snap.exists():
        return []

    projects = []
    for entry in sorted(snap.iterdir()):
        if entry.is_dir() and not entry.name.startswith("_"):
            projects.append(entry.name)
    return projects


def restore_project(
    snapshot_path: str,
    project_name: str,
    dest_path: str,
    dry_run: bool = False,
) -> RestoreResult:
    """Restore a project from a backup snapshot.

    Args:
        snapshot_path: Path to the snapshot directory
        project_name: Name of the project directory within the snapshot
        dest_path: Where to restore to
        dry_run: If True, show what would happen without writing

    Returns:
        RestoreResult with details
    """
    start = time.time()
    source = Path(snapshot_path) / project_name

    if not source.exists():
        return RestoreResult(
            success=False,
            project_name=project_name,
            error=f"Project '{project_name}' not found in snapshot",
        )

    dest = Path(dest_path)
    dest.mkdir(parents=True, exist_ok=True)

    cmd = [
        "rsync",
        "-a",
        "--info=progress2",
        "--human-readable",
        "--stats",
    ]

    if dry_run:
        cmd.append("--dry-run")

    source_str = str(source)
    if not source_str.endswith("/"):
        source_str += "/"

    cmd.extend([source_str, str(dest)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or f"rsync exited with code {result.returncode}"
            return RestoreResult(
                success=False,
                project_name=project_name,
                snapshot_name=Path(snapshot_path).name,
                dest_path=str(dest),
                error=error,
                duration_seconds=time.time() - start,
            )

        # Parse stats
        files_restored = 0
        bytes_restored = 0
        import re
        files_match = re.search(r"Number of regular files transferred:\s+([\d,]+)", result.stdout)
        bytes_match = re.search(r"Total transferred file size:\s+([\d,]+)", result.stdout)
        if files_match:
            files_restored = int(files_match.group(1).replace(",", ""))
        if bytes_match:
            bytes_restored = int(bytes_match.group(1).replace(",", ""))

        return RestoreResult(
            success=True,
            project_name=project_name,
            snapshot_name=Path(snapshot_path).name,
            dest_path=str(dest),
            files_restored=files_restored,
            bytes_restored=bytes_restored,
            duration_seconds=time.time() - start,
        )

    except subprocess.TimeoutExpired:
        return RestoreResult(
            success=False,
            project_name=project_name,
            error="rsync timed out (10 min)",
            duration_seconds=time.time() - start,
        )
    except FileNotFoundError:
        return RestoreResult(
            success=False,
            project_name=project_name,
            error="rsync not found — install with: sudo apt install rsync",
        )
    except OSError as e:
        return RestoreResult(
            success=False,
            project_name=project_name,
            error=str(e),
        )
