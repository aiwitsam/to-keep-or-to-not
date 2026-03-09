"""Per-snapshot manifest with structural checksums."""

import hashlib
import json
import socket
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ProjectManifest:
    """Manifest entry for a single backed-up project."""
    name: str
    file_count: int
    total_bytes: int
    structural_checksum: str
    files: list[dict] = field(default_factory=list)  # [{path, size, mtime}]


@dataclass
class Manifest:
    """Full snapshot manifest."""
    timestamp: str = ""
    hostname: str = ""
    snapshot_name: str = ""
    projects: list[ProjectManifest] = field(default_factory=list)
    total_files: int = 0
    total_bytes: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.hostname:
            self.hostname = socket.gethostname()


def _structural_checksum(file_entries: list[tuple[str, int, float]]) -> str:
    """Compute SHA256 of sorted (relative_path, size, mtime) tuples.

    This is fast — no file content is read, only metadata.
    """
    h = hashlib.sha256()
    for rel_path, size, mtime in sorted(file_entries):
        h.update(f"{rel_path}:{size}:{mtime:.6f}\n".encode())
    return h.hexdigest()


def _scan_project_files(project_path: Path) -> tuple[list[dict], list[tuple[str, int, float]]]:
    """Walk a backed-up project directory and collect file metadata.

    Returns:
        (file_entries_for_storage, tuples_for_checksum)
    """
    file_entries = []
    checksum_tuples = []

    try:
        for fpath in sorted(project_path.rglob("*")):
            if not fpath.is_file():
                continue
            try:
                stat = fpath.stat()
                rel = str(fpath.relative_to(project_path))
                size = stat.st_size
                mtime = stat.st_mtime

                file_entries.append({
                    "path": rel,
                    "size": size,
                    "mtime": mtime,
                })
                checksum_tuples.append((rel, size, mtime))
            except (OSError, ValueError):
                continue
    except OSError:
        pass

    return file_entries, checksum_tuples


def create_manifest(snapshot_path: str, project_names: list[str]) -> Manifest:
    """Create a manifest for a completed snapshot.

    Args:
        snapshot_path: Path to the snapshot directory
        project_names: List of project directory names within the snapshot

    Returns:
        Manifest object with structural checksums per project
    """
    snap = Path(snapshot_path)
    manifest = Manifest(snapshot_name=snap.name)

    total_files = 0
    total_bytes = 0

    for name in project_names:
        project_dir = snap / name
        if not project_dir.exists():
            continue

        file_entries, checksum_tuples = _scan_project_files(project_dir)
        checksum = _structural_checksum(checksum_tuples)

        proj_files = len(file_entries)
        proj_bytes = sum(e["size"] for e in file_entries)

        manifest.projects.append(ProjectManifest(
            name=name,
            file_count=proj_files,
            total_bytes=proj_bytes,
            structural_checksum=checksum,
            files=file_entries,
        ))

        total_files += proj_files
        total_bytes += proj_bytes

    manifest.total_files = total_files
    manifest.total_bytes = total_bytes

    return manifest


def save_manifest(manifest: Manifest, snapshot_path: str):
    """Save manifest as _manifest.json in the snapshot directory."""
    manifest_file = Path(snapshot_path) / "_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(asdict(manifest), f, indent=2)


def load_manifest(snapshot_path: str) -> Optional[Manifest]:
    """Load manifest from a snapshot directory."""
    manifest_file = Path(snapshot_path) / "_manifest.json"
    if not manifest_file.exists():
        return None

    try:
        with open(manifest_file, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    projects = []
    for p in data.get("projects", []):
        projects.append(ProjectManifest(
            name=p["name"],
            file_count=p["file_count"],
            total_bytes=p["total_bytes"],
            structural_checksum=p["structural_checksum"],
            files=p.get("files", []),
        ))

    return Manifest(
        timestamp=data.get("timestamp", ""),
        hostname=data.get("hostname", ""),
        snapshot_name=data.get("snapshot_name", ""),
        projects=projects,
        total_files=data.get("total_files", 0),
        total_bytes=data.get("total_bytes", 0),
    )


def content_checksum(file_path: str) -> str:
    """Compute SHA256 of actual file contents (for deep verify)."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()
