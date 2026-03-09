"""Project selection, exclude logic, and backup plan generation."""

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from tokeep.config import load_config, is_denied, load_togit_decisions
from tokeep.drives import check_space, SpaceCheck

# Try to import togit scanner, fall back to embedded scanner
try:
    from togit.scanner import scan_all as togit_scan_all
    from togit.models import ProjectInfo
    TOGIT_AVAILABLE = True
except ImportError:
    TOGIT_AVAILABLE = False

# Project markers for fallback scanner
PROJECT_MARKERS = [
    ".git", "package.json", "requirements.txt", "pyproject.toml",
    "setup.py", "Makefile", "Dockerfile", "Cargo.toml", "go.mod",
]
ROOT_FILE_EXTENSIONS = [".py", ".js", ".sh", ".html"]


@dataclass
class BackupPlan:
    """A complete backup plan ready for execution."""
    projects: list = field(default_factory=list)
    drive_path: str = ""
    vault_path: str = ""
    snapshot_name: str = ""
    exclude_patterns: list[str] = field(default_factory=list)
    estimated_size: int = 0
    space_check: Optional[SpaceCheck] = None


if not TOGIT_AVAILABLE:
    @dataclass
    class ProjectInfo:
        """Minimal project info (fallback when togit not available)."""
        name: str = ""
        path: Path = field(default_factory=Path)
        project_type: str = "Unknown"
        has_git: bool = False
        has_remote: bool = False
        remote_url: str = ""
        has_github: bool = False
        is_dirty: bool = False
        file_count: int = 0
        last_modified: float = 0.0
        size_human: str = ""
        has_gitignore: bool = False
        has_sensitive_markers: bool = False
        deny_list_matches: list[str] = field(default_factory=list)


def _detect_project_type(path: Path) -> str:
    """Detect project type from marker files."""
    if (path / "package.json").exists():
        return "Node"
    if any((path / m).exists() for m in ("setup.py", "pyproject.toml", "requirements.txt")):
        return "Python"
    if (path / "Cargo.toml").exists():
        return "Rust"
    if (path / "go.mod").exists():
        return "Go"
    try:
        if list(path.glob("*.sh")):
            return "Bash"
    except OSError:
        pass
    if (path / "index.html").exists():
        return "Static"
    return "Unknown"


def _is_project(path: Path) -> bool:
    """Check if a directory looks like a project."""
    for marker in PROJECT_MARKERS:
        if (path / marker).exists():
            return True
    try:
        for ext in ROOT_FILE_EXTENSIONS:
            if list(path.glob(f"*{ext}"))[:1]:
                return True
    except OSError:
        pass
    return False


def _dir_size(path: Path) -> str:
    """Get human-readable directory size via du."""
    try:
        result = subprocess.run(
            ["du", "-sh", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.split()[0]
    except (subprocess.TimeoutExpired, OSError, IndexError):
        pass
    return "?"


def _dir_size_bytes(path: Path) -> int:
    """Get directory size in bytes via du."""
    try:
        result = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.split()[0])
    except (subprocess.TimeoutExpired, OSError, IndexError, ValueError):
        pass
    return 0


def _scan_project(path: Path, config: dict) -> ProjectInfo:
    """Build a ProjectInfo for a single directory (fallback scanner)."""
    path = path.resolve()
    project_type = _detect_project_type(path)
    deny_matches = is_denied(str(path), config)

    has_git = (path / ".git").exists()
    sensitive_files = [".env", "credentials.json", "token.json", "settings.local.json"]
    has_sensitive = any((path / f).exists() for f in sensitive_files)

    return ProjectInfo(
        name=path.name,
        path=path,
        project_type=project_type,
        has_git=has_git,
        file_count=sum(1 for f in path.iterdir() if f.is_file()) if path.exists() else 0,
        last_modified=os.path.getmtime(str(path)) if path.exists() else 0.0,
        size_human=_dir_size(path),
        has_gitignore=(path / ".gitignore").exists(),
        has_sensitive_markers=has_sensitive,
        deny_list_matches=deny_matches,
    )


def scan_projects(config: dict = None) -> list:
    """Discover all projects. Uses togit scanner if available, otherwise fallback."""
    if config is None:
        config = load_config()

    if TOGIT_AVAILABLE:
        return togit_scan_all(config)

    # Fallback scanner — same logic as togit
    scan_path = Path(config.get("scan_path", str(Path.home()))).expanduser().resolve()
    exclude_dirs = set(config.get("exclude_dirs", []))

    projects = []
    try:
        for child in sorted(scan_path.iterdir()):
            if not child.is_dir() or child.name.startswith(".") or child.name in exclude_dirs or child.is_symlink():
                continue
            if _is_project(child):
                projects.append(_scan_project(child, config))
    except (OSError, PermissionError):
        pass

    projects.sort(key=lambda p: p.name.lower())
    return projects


def filter_projects(
    projects: list,
    togit_decisions: dict | None,
    config: dict,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    all_projects: bool = False,
) -> list:
    """Filter projects based on togit decisions, include/exclude lists, and deny list."""
    filtered = []

    for project in projects:
        # Always exclude denied projects
        if is_denied(str(project.path), config):
            continue

        name = project.name

        # Explicit include list
        if include:
            if name in include:
                filtered.append(project)
            continue

        # Explicit exclude list
        if exclude and name in exclude:
            continue

        # All flag includes everything non-denied
        if all_projects:
            filtered.append(project)
            continue

        # togit decision-based filtering
        if togit_decisions:
            decision = togit_decisions.get(str(project.path))
            if decision:
                action = decision.get("action", "")
                if action == "deny":
                    continue
                elif action in ("git", "github"):
                    filtered.append(project)
                    continue
                # skip / no decision = not auto-included

        # No togit or no decision — include by default for interactive
        if not togit_decisions:
            filtered.append(project)

    return filtered


def build_plan(
    config: dict,
    drive_path: str,
    projects: list,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    all_projects: bool = False,
) -> BackupPlan:
    """Build a complete backup plan."""
    togit_decisions = load_togit_decisions()

    # Filter projects
    selected = filter_projects(projects, togit_decisions, config, include, exclude, all_projects)

    # Build exclude patterns from config
    backup_config = config.get("backup", {})
    exclude_patterns = list(backup_config.get("global_excludes", []))
    exclude_patterns.extend(backup_config.get("sensitive_excludes", []))

    # Vault and snapshot paths
    vault_name = backup_config.get("vault_name", "tokeep-vault")
    vault_path = str(Path(drive_path) / vault_name)
    snapshot_name = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    # Estimate size
    estimated_size = sum(_dir_size_bytes(p.path) for p in selected)

    # Check space
    space = check_space(drive_path, estimated_size)

    return BackupPlan(
        projects=selected,
        drive_path=drive_path,
        vault_path=vault_path,
        snapshot_name=snapshot_name,
        exclude_patterns=exclude_patterns,
        estimated_size=estimated_size,
        space_check=space,
    )
