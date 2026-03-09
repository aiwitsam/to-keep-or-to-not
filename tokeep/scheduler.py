"""Cron entry generation, installation, and removal."""

import subprocess
import sys
from pathlib import Path

CRON_MARKER = "# tokeep backup"

# Presets
SCHEDULES = {
    "daily": "0 2 * * *",
    "weekly": "0 2 * * 0",
}


def _find_python() -> str:
    """Find the Python executable path (prefer venv)."""
    # Check if we're in a venv
    venv_python = Path(sys.prefix) / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _find_tokeep() -> str:
    """Find the tokeep script path."""
    # Check common locations
    venv_bin = Path(sys.prefix) / "bin" / "tokeep"
    if venv_bin.exists():
        return str(venv_bin)

    # Fall back to python -m tokeep
    return f"{_find_python()} -m tokeep"


def generate_cron_entry(schedule: str, drive_path: str) -> str:
    """Generate a full cron entry string.

    Args:
        schedule: 'daily' or 'weekly'
        drive_path: Target drive path

    Returns:
        Complete cron line with marker comment
    """
    cron_time = SCHEDULES.get(schedule, SCHEDULES["daily"])
    tokeep_cmd = _find_tokeep()
    log_path = Path.home() / ".tokeep" / "cron.log"

    # The command checks if drive is mounted before running
    cmd = (
        f'{cron_time} '
        f'test -d "{drive_path}" && '
        f'{tokeep_cmd} run --drive "{drive_path}" --all --yes --quiet '
        f'>> "{log_path}" 2>&1 '
        f'{CRON_MARKER}'
    )
    return cmd


def _get_current_crontab() -> str:
    """Read current crontab contents."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _write_crontab(content: str) -> bool:
    """Write new crontab contents."""
    try:
        process = subprocess.run(
            ["crontab", "-"],
            input=content, text=True,
            capture_output=True, timeout=10,
        )
        return process.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def install_cron(entry: str) -> bool:
    """Install a cron entry, replacing any existing tokeep entry.

    Args:
        entry: The cron line to install

    Returns:
        True if successful
    """
    current = _get_current_crontab()

    # Remove existing tokeep entries
    lines = [line for line in current.splitlines() if CRON_MARKER not in line]

    # Add new entry
    lines.append(entry)

    # Ensure trailing newline
    new_content = "\n".join(lines) + "\n"
    return _write_crontab(new_content)


def remove_cron() -> bool:
    """Remove all tokeep cron entries.

    Returns:
        True if an entry was found and removed
    """
    current = _get_current_crontab()
    if CRON_MARKER not in current:
        return False

    lines = [line for line in current.splitlines() if CRON_MARKER not in line]
    new_content = "\n".join(lines) + "\n" if lines else ""
    _write_crontab(new_content)
    return True
