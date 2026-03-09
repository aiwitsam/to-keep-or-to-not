"""Rsync wrapper with progress parsing for backup operations."""

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class BackupResult:
    """Result of a complete backup run."""
    success: bool = True
    projects_synced: int = 0
    projects_failed: int = 0
    bytes_transferred: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    project_results: dict[str, bool] = field(default_factory=dict)


@dataclass
class ProjectSyncResult:
    """Result of syncing a single project."""
    name: str
    success: bool
    bytes_transferred: int = 0
    files_transferred: int = 0
    error: str = ""


# Regex to parse rsync --info=progress2 output
# Example: "  1,234,567  45%   12.34MB/s    0:01:23"
PROGRESS_RE = re.compile(r"(\d+(?:,\d+)*)\s+(\d+)%\s+(\S+)\s+(\S+)")

# Regex to parse total bytes from rsync stats
BYTES_SENT_RE = re.compile(r"Total transferred file size:\s+([\d,]+)")
FILES_TRANSFERRED_RE = re.compile(r"Number of regular files transferred:\s+([\d,]+)")


def _build_rsync_cmd(
    source: str,
    dest: str,
    exclude_patterns: list[str],
    link_dest: Optional[str] = None,
    dry_run: bool = False,
    bwlimit: Optional[str] = None,
) -> list[str]:
    """Build the rsync command with all flags."""
    cmd = [
        "rsync",
        "-a",
        "--delete",
        "--info=progress2",
        "--human-readable",
        "--stats",
        "--filter=:- .gitignore",
    ]

    for pattern in exclude_patterns:
        cmd.append(f"--exclude={pattern}")

    if link_dest:
        cmd.append(f"--link-dest={link_dest}")

    if dry_run:
        cmd.append("--dry-run")

    if bwlimit:
        cmd.append(f"--bwlimit={bwlimit}")

    # Trailing slash on source means "contents of", not the dir itself
    if not source.endswith("/"):
        source += "/"

    cmd.extend([source, dest])
    return cmd


def _parse_progress(line: str) -> Optional[int]:
    """Extract percentage from rsync progress2 output."""
    match = PROGRESS_RE.search(line)
    if match:
        return int(match.group(2))
    return None


def _parse_stats(output: str) -> tuple[int, int]:
    """Parse bytes and files transferred from rsync stats output."""
    bytes_transferred = 0
    files_transferred = 0

    match = BYTES_SENT_RE.search(output)
    if match:
        bytes_transferred = int(match.group(1).replace(",", ""))

    match = FILES_TRANSFERRED_RE.search(output)
    if match:
        files_transferred = int(match.group(1).replace(",", ""))

    return bytes_transferred, files_transferred


def sync_project(
    name: str,
    source_path: str,
    dest_path: str,
    exclude_patterns: list[str],
    link_dest: Optional[str] = None,
    dry_run: bool = False,
    bwlimit: Optional[str] = None,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> ProjectSyncResult:
    """Sync a single project via rsync.

    Args:
        name: Project name for display
        source_path: Source directory path
        dest_path: Destination directory path
        exclude_patterns: List of rsync exclude patterns
        link_dest: Previous snapshot path for hardlink dedup
        dry_run: If True, show what would happen without executing
        progress_callback: Called with (project_name, percentage)

    Returns:
        ProjectSyncResult with sync details
    """
    # Ensure destination exists
    Path(dest_path).mkdir(parents=True, exist_ok=True)

    cmd = _build_rsync_cmd(source_path, dest_path, exclude_patterns, link_dest, dry_run, bwlimit)

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        full_output = []
        for line in iter(process.stdout.readline, ""):
            full_output.append(line)
            pct = _parse_progress(line)
            if pct is not None and progress_callback:
                progress_callback(name, pct)

        process.wait(timeout=600)  # 10 minute timeout per project
        stderr = process.stderr.read()

        if process.returncode not in (0, 24):
            # returncode 24 = "vanished source files" — acceptable for active projects
            error = stderr.strip() or f"rsync exited with code {process.returncode}"
            return ProjectSyncResult(name=name, success=False, error=error)

        output = "".join(full_output)
        bytes_transferred, files_transferred = _parse_stats(output)

        return ProjectSyncResult(
            name=name,
            success=True,
            bytes_transferred=bytes_transferred,
            files_transferred=files_transferred,
        )

    except subprocess.TimeoutExpired:
        process.kill()
        return ProjectSyncResult(name=name, success=False, error="rsync timed out (10 min)")
    except FileNotFoundError:
        return ProjectSyncResult(name=name, success=False, error="rsync not found — install with: sudo apt install rsync")
    except OSError as e:
        return ProjectSyncResult(name=name, success=False, error=str(e))


def run_backup(
    plan,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    dry_run: bool = False,
    bwlimit: Optional[str] = None,
) -> BackupResult:
    """Execute a full backup plan, syncing all projects sequentially.

    Args:
        plan: BackupPlan object with projects, paths, and settings
        progress_callback: Called with (project_name, percentage)
        dry_run: If True, simulate without writing

    Returns:
        BackupResult with aggregate stats
    """
    start = time.time()
    result = BackupResult()

    snapshot_path = Path(plan.vault_path) / plan.snapshot_name
    snapshot_path.mkdir(parents=True, exist_ok=True)

    # Find previous snapshot for hardlink dedup
    link_dest = _find_previous_snapshot(plan.vault_path, plan.snapshot_name)

    for project in plan.projects:
        dest = str(snapshot_path / project.name)
        prev_dest = str(Path(link_dest) / project.name) if link_dest else None

        sync_result = sync_project(
            name=project.name,
            source_path=str(project.path),
            dest_path=dest,
            exclude_patterns=plan.exclude_patterns,
            link_dest=prev_dest,
            dry_run=dry_run,
            bwlimit=bwlimit,
            progress_callback=progress_callback,
        )

        result.project_results[project.name] = sync_result.success

        if sync_result.success:
            result.projects_synced += 1
            result.bytes_transferred += sync_result.bytes_transferred
        else:
            result.projects_failed += 1
            result.errors.append(f"{project.name}: {sync_result.error}")
            result.success = False

    # Update latest symlink
    if not dry_run and result.projects_synced > 0:
        _update_latest_symlink(plan.vault_path, plan.snapshot_name)

    result.duration_seconds = time.time() - start
    if result.projects_failed == 0:
        result.success = True

    return result


def _find_previous_snapshot(vault_path: str, current_snapshot: str) -> Optional[str]:
    """Find the most recent previous snapshot for hardlink dedup."""
    vault = Path(vault_path)
    latest_link = vault / "latest"

    if latest_link.is_symlink():
        target = latest_link.resolve()
        if target.exists() and target.name != current_snapshot:
            return str(target)

    return None


def _update_latest_symlink(vault_path: str, snapshot_name: str):
    """Update the 'latest' symlink to point to the newest snapshot."""
    vault = Path(vault_path)
    latest_link = vault / "latest"

    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()

    latest_link.symlink_to(snapshot_name)
