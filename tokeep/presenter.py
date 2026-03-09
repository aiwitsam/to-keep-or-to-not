"""Rich TUI: panels, prompts, progress, tables."""

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from rich import box

from tokeep.shakespeare import (
    get_banner, get_confirmation, get_farewell,
    get_drive_message, get_progress_message,
)

console = Console()

VAULT_ART = r"""
      _____
     /     \
    |  |||  |
    |  |||  |
    |  |||  |
    |_______|
    |=======|
    |  T K  |
    |_______|
"""

TYPE_BADGES = {
    "Python": "[bold yellow]Python[/]",
    "Node": "[bold green]Node.js[/]",
    "Bash": "[bold cyan]Bash[/]",
    "Rust": "[bold red]Rust[/]",
    "Go": "[bold blue]Go[/]",
    "Static": "[bold magenta]Static[/]",
    "Unknown": "[dim]Unknown[/]",
}

STATUS_BADGES = {
    "synced": "[bold green]synced[/]",
    "failed": "[bold red]failed[/]",
    "skipped": "[dim]skipped[/]",
    "pending": "[yellow]pending[/]",
}


def _human_size(nbytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024.0:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} PB"


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


def show_header():
    """Display the title banner."""
    banner_quote = get_banner()
    header_text = Text()
    header_text.append(VAULT_ART, style="dim cyan")
    header_text.append("\n  To Keep or to Not\n", style="bold bright_white")
    header_text.append(f"\n  \"{banner_quote}\"\n", style="italic dim")

    console.print(Panel(
        header_text,
        border_style="bright_cyan",
        box=box.DOUBLE,
        padding=(0, 2),
    ))
    console.print()


def show_drive_list(drives: list):
    """Display detected external drives."""
    drive_msg = get_drive_message()
    console.print(f"\n[italic dim]{drive_msg}[/]\n")

    if not drives:
        console.print("[yellow]No external drives detected at /mnt/.[/]")
        console.print("[dim]Tip: Mount a drive or use --drive PATH to specify a target.[/]\n")
        return

    table = Table(
        title="[bold]Detected Drives[/]",
        box=box.ROUNDED,
        show_header=True,
    )
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Mount Point", style="bright_white", min_width=20)
    table.add_column("Label", style="dim")
    table.add_column("Filesystem", style="dim")
    table.add_column("Total", style="dim", justify="right")
    table.add_column("Free", style="green", justify="right")

    for i, drive in enumerate(drives, 1):
        table.add_row(
            str(i),
            drive.mount_point,
            drive.label,
            drive.filesystem,
            _human_size(drive.total_bytes),
            drive.free_human,
        )

    console.print(table)
    console.print()


def prompt_drive_selection(drives: list):
    """Prompt user to select a drive. Returns selected DriveInfo or None."""
    if not drives:
        return None

    if len(drives) == 1:
        drive = drives[0]
        if Confirm.ask(f"Use [bold]{drive.mount_point}[/] ({drive.free_human} free)?", default=True):
            return drive
        return None

    choices = [str(i) for i in range(1, len(drives) + 1)]
    choice = Prompt.ask("Select a drive", choices=choices)
    return drives[int(choice) - 1]


def show_project_selection(projects: list, togit_decisions: dict | None = None):
    """Display projects for selection with togit decision hints."""
    table = Table(
        title="[bold]Projects Available for Backup[/]",
        box=box.ROUNDED,
        show_header=True,
    )
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Project", style="bright_white", min_width=20)
    table.add_column("Type", style="dim")
    table.add_column("Size", style="dim", justify="right")
    table.add_column("Git", style="dim")
    table.add_column("togit", style="dim")

    for i, project in enumerate(projects, 1):
        type_badge = TYPE_BADGES.get(project.project_type, TYPE_BADGES["Unknown"])

        togit_status = "[dim]--[/]"
        if togit_decisions:
            decision = togit_decisions.get(str(project.path))
            if decision:
                action = decision.get("action", "")
                togit_status = {
                    "git": "[yellow]git[/]",
                    "github": "[green]github[/]",
                    "skip": "[dim]skip[/]",
                    "deny": "[red]deny[/]",
                }.get(action, "[dim]--[/]")

        git_status = "[green]yes[/]" if project.has_git else "[red]no[/]"

        table.add_row(
            str(i),
            project.name,
            type_badge,
            project.size_human,
            git_status,
            togit_status,
        )

    console.print(table)
    console.print()


def prompt_project_selection(projects: list, togit_decisions: dict | None = None) -> list:
    """Interactive project selection. Returns list of selected projects.

    Projects with togit git/github decisions are pre-selected.
    Projects with togit deny decisions are excluded.
    """
    auto_included = []
    available = []

    for project in projects:
        if togit_decisions:
            decision = togit_decisions.get(str(project.path))
            if decision:
                action = decision.get("action", "")
                if action in ("git", "github"):
                    auto_included.append(project)
                    continue
                elif action == "deny":
                    continue  # excluded entirely

        available.append(project)

    if auto_included:
        names = ", ".join(p.name for p in auto_included)
        console.print(f"[green]Auto-included (togit git/github):[/] {names}")

    if not available:
        return auto_included

    console.print(f"\n[bold]Select additional projects to back up:[/]")
    console.print("[dim]Enter numbers separated by commas, 'all' for all, or 'none' to skip.[/]\n")

    for i, project in enumerate(available, 1):
        type_badge = TYPE_BADGES.get(project.project_type, TYPE_BADGES["Unknown"])
        console.print(f"  [bold cyan]{i}[/] {project.name} ({type_badge}, {project.size_human})")

    console.print()
    answer = Prompt.ask("Thy selections", default="none")

    selected = list(auto_included)

    if answer.lower() == "all":
        selected.extend(available)
    elif answer.lower() != "none":
        try:
            indices = [int(x.strip()) for x in answer.split(",")]
            for idx in indices:
                if 1 <= idx <= len(available):
                    selected.append(available[idx - 1])
        except ValueError:
            console.print("[red]Invalid selection. Proceeding with auto-included only.[/]")

    return selected


def show_backup_plan(plan, dry_run: bool = False):
    """Display the backup plan before execution."""
    mode = "[yellow]DRY RUN[/] — " if dry_run else ""
    console.print(Panel(
        f"{mode}[bold]The Backup Plan — A Most Noble Endeavor[/]",
        border_style="bright_cyan",
        box=box.DOUBLE,
    ))

    table = Table(box=box.SIMPLE_HEAVY, show_header=True)
    table.add_column("Project", style="bright_white", min_width=20)
    table.add_column("Path", style="dim")
    table.add_column("Size", style="dim", justify="right")

    for project in plan.projects:
        table.add_row(project.name, str(project.path), project.size_human)

    console.print(table)

    console.print(f"\n  Drive:      [bold]{plan.drive_path}[/]")
    console.print(f"  Vault:      [dim]{plan.vault_path}[/]")
    console.print(f"  Snapshot:   [bold cyan]{plan.snapshot_name}[/]")
    console.print(f"  Projects:   {len(plan.projects)}")
    if plan.estimated_size:
        console.print(f"  Est. size:  {_human_size(plan.estimated_size)}")
    if plan.space_check:
        status = "[green]OK[/]" if plan.space_check.has_space else "[red]INSUFFICIENT[/]"
        console.print(f"  Free space: {plan.space_check.free_human} ({status})")
    console.print()


def confirm_backup() -> bool:
    """Ask for backup confirmation."""
    return Confirm.ask("Shall we proceed with the backup?", default=True)


def create_backup_progress() -> Progress:
    """Create a Rich progress bar for backup operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}[/]"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )


def show_backup_result(result):
    """Display backup results."""
    if result.success:
        style = "green"
        title = "Backup Complete"
    else:
        style = "yellow"
        title = "Backup Complete (with errors)"

    lines = []
    lines.append(f"  Synced:     [green]{result.projects_synced}[/] projects")
    if result.projects_failed:
        lines.append(f"  Failed:     [red]{result.projects_failed}[/] projects")
    lines.append(f"  Transferred: {_human_size(result.bytes_transferred)}")
    lines.append(f"  Duration:   {_format_duration(result.duration_seconds)}")

    if result.errors:
        lines.append("")
        lines.append("  [bold red]Errors:[/]")
        for err in result.errors:
            lines.append(f"    [red]- {err}[/]")

    body = "\n".join(lines)

    console.print(Panel(
        body,
        title=f"[bold {style}]{title}[/]",
        border_style=style,
        box=box.ROUNDED,
        padding=(1, 2),
    ))

    confirmation = get_confirmation("backup")
    console.print(f"\n[italic dim]{confirmation}[/]\n")


def show_verify_result(result):
    """Display verification results."""
    if result.passed:
        style = "green"
        title = "Verification Passed"
    else:
        style = "red"
        title = "Verification Failed"

    lines = []
    lines.append(f"  Projects checked:  {result.projects_checked}")
    lines.append(f"  Projects passed:   [green]{result.projects_passed}[/]")
    if result.projects_failed:
        lines.append(f"  Projects failed:   [red]{result.projects_failed}[/]")

    if result.missing:
        lines.append("")
        lines.append("  [bold red]Missing files:[/]")
        for f in result.missing[:10]:
            lines.append(f"    [red]- {f}[/]")
        if len(result.missing) > 10:
            lines.append(f"    [dim]...and {len(result.missing) - 10} more[/]")

    if result.corrupted:
        lines.append("")
        lines.append("  [bold red]Corrupted files:[/]")
        for f in result.corrupted[:10]:
            lines.append(f"    [red]- {f}[/]")

    if result.extra:
        lines.append("")
        lines.append(f"  [yellow]Extra files (not in manifest): {len(result.extra)}[/]")

    body = "\n".join(lines)

    console.print(Panel(
        body,
        title=f"[bold {style}]{title}[/]",
        border_style=style,
        box=box.ROUNDED,
        padding=(1, 2),
    ))

    confirmation = get_confirmation("verify")
    console.print(f"\n[italic dim]{confirmation}[/]\n")


def show_snapshot_list(snapshots: list, drive_path: str):
    """Display snapshots on a drive."""
    if not snapshots:
        console.print(f"[yellow]No snapshots found on {drive_path}.[/]\n")
        return

    table = Table(
        title=f"[bold]Snapshots on {drive_path}[/]",
        box=box.ROUNDED,
        show_header=True,
    )
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Snapshot", style="bright_white", min_width=20)
    table.add_column("Date", style="dim")
    table.add_column("Projects", style="dim", justify="right")
    table.add_column("Size", style="dim", justify="right")
    table.add_column("Latest", style="dim")

    for i, snap in enumerate(snapshots, 1):
        latest = "[green]<--[/]" if snap.is_latest else ""
        table.add_row(
            str(i),
            snap.name,
            snap.date_human,
            str(snap.project_count),
            snap.size_human,
            latest,
        )

    console.print(table)
    console.print()


def show_prune_plan(to_delete: list, to_keep: list):
    """Display snapshots that will be pruned."""
    console.print(Panel(
        "[bold]Pruning Plan — Clearing the Old Growth[/]",
        border_style="yellow",
        box=box.DOUBLE,
    ))

    if to_delete:
        console.print("[bold red]To be removed:[/]")
        for snap in to_delete:
            console.print(f"  [red]- {snap.name}[/] ({snap.size_human})")

    if to_keep:
        console.print("[bold green]To be kept:[/]")
        for snap in to_keep:
            console.print(f"  [green]- {snap.name}[/] ({snap.size_human})")

    console.print()


def confirm_prune() -> bool:
    """Ask for prune confirmation."""
    return Confirm.ask("[yellow]Proceed with pruning?[/]", default=False)


def show_history(records: list):
    """Display backup history."""
    if not records:
        console.print("[dim]No backup history yet. Run tokeep to begin.[/]\n")
        return

    table = Table(
        title="[bold]Backup History — The Chronicles[/]",
        box=box.ROUNDED,
        show_header=True,
    )
    table.add_column("Date", style="dim", min_width=19)
    table.add_column("Drive", style="bright_white")
    table.add_column("Snapshot", style="dim")
    table.add_column("Synced", style="green", justify="right")
    table.add_column("Failed", style="red", justify="right")
    table.add_column("Duration", style="dim", justify="right")

    for r in reversed(records[-20:]):  # Show last 20, newest first
        date = r.timestamp[:19] if r.timestamp else "?"
        failed = str(r.projects_failed) if r.projects_failed else "[dim]0[/]"
        table.add_row(
            date,
            r.drive_path,
            r.snapshot_name,
            str(r.projects_synced),
            failed,
            _format_duration(r.duration_seconds),
        )

    console.print(table)
    console.print()


def show_schedule_confirmation(schedule: str, drive_path: str, cron_entry: str):
    """Show cron schedule confirmation."""
    console.print(Panel(
        f"  Schedule:   [bold]{schedule}[/]\n"
        f"  Drive:      [bold]{drive_path}[/]\n"
        f"  Cron entry: [dim]{cron_entry}[/]",
        title="[bold green]Schedule Installed[/]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2),
    ))

    confirmation = get_confirmation("schedule")
    console.print(f"\n[italic dim]{confirmation}[/]\n")


def show_farewell():
    """Display exit message."""
    farewell = get_farewell()
    console.print(f"[italic bright_cyan]{farewell}[/]\n")
