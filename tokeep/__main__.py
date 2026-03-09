"""CLI entry point for To Keep or to Not."""

import argparse
import sys

from tokeep import __version__
from tokeep.config import (
    load_config, load_backup_history, save_backup_record, BackupRecord,
    load_togit_decisions,
)
from tokeep.drives import find_external_drives, validate_drive
from tokeep.planner import scan_projects, build_plan
from tokeep.syncer import run_backup
from tokeep.manifest import create_manifest, save_manifest, load_manifest
from tokeep.presenter import (
    console, show_header, show_drive_list, prompt_drive_selection,
    show_project_selection, prompt_project_selection,
    show_backup_plan, confirm_backup, create_backup_progress,
    show_backup_result, show_verify_result, show_snapshot_list,
    show_prune_plan, confirm_prune, show_history,
    show_schedule_confirmation, show_farewell,
)
from tokeep.shakespeare import get_farewell


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tokeep",
        description="To Keep or to Not — Shakespeare-themed external drive backup",
    )
    parser.add_argument("--version", action="version", version=f"tokeep {__version__}")

    sub = parser.add_subparsers(dest="command")

    # run — non-interactive backup with saved config
    run_parser = sub.add_parser("run", help="Run backup (non-interactive with flags)")
    run_parser.add_argument("--drive", metavar="PATH", help="Target drive or directory")
    run_parser.add_argument("--all", action="store_true", help="Back up all non-denied projects")
    run_parser.add_argument("--include", metavar="NAMES", help="Only these projects (comma-separated)")
    run_parser.add_argument("--exclude", metavar="NAMES", help="Skip these projects (comma-separated)")
    run_parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    run_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    run_parser.add_argument("--quiet", action="store_true", help="Minimal output (for cron)")

    # drives — list detected drives
    sub.add_parser("drives", help="List detected external drives")

    # status — show what's on a drive
    status_parser = sub.add_parser("status", help="Show snapshots on a drive")
    status_parser.add_argument("--drive", metavar="PATH", help="Target drive or directory")

    # verify — check backup integrity
    verify_parser = sub.add_parser("verify", help="Verify backup integrity")
    verify_parser.add_argument("--drive", metavar="PATH", required=True, help="Target drive")
    verify_parser.add_argument("--snapshot", metavar="NAME", help="Specific snapshot (default: latest)")
    verify_parser.add_argument("--deep", action="store_true", help="Full content hash (slow)")

    # prune — remove old snapshots
    prune_parser = sub.add_parser("prune", help="Remove old snapshots")
    prune_parser.add_argument("--drive", metavar="PATH", required=True, help="Target drive")
    prune_parser.add_argument("--keep", type=int, metavar="N", help="Override retention count")
    prune_parser.add_argument("--yes", action="store_true", help="Skip confirmation")

    # schedule — set up cron
    schedule_parser = sub.add_parser("schedule", help="Set up cron backup schedule")
    schedule_parser.add_argument("--daily", action="store_true", help="Daily at 2am")
    schedule_parser.add_argument("--weekly", action="store_true", help="Weekly Sunday at 2am")
    schedule_parser.add_argument("--drive", metavar="PATH", help="Target drive (required)")
    schedule_parser.add_argument("--remove", action="store_true", help="Remove existing schedule")

    # history — show backup log
    sub.add_parser("history", help="Show backup history")

    return parser


def cmd_drives(args):
    """List detected external drives."""
    show_header()
    drives = find_external_drives()
    show_drive_list(drives)
    show_farewell()


def cmd_run(args):
    """Non-interactive backup with flags."""
    config = load_config()
    quiet = getattr(args, "quiet", False)

    if not quiet:
        show_header()

    # Resolve drive
    drive_path = args.drive
    if not drive_path:
        console.print("[red]Error: --drive PATH is required for 'run' command.[/]")
        console.print("[dim]Use 'tokeep drives' to see available drives.[/]")
        sys.exit(1)

    drive = validate_drive(drive_path)
    if not drive:
        console.print(f"[red]Error: '{drive_path}' is not a valid writable drive/directory.[/]")
        sys.exit(1)

    # Scan projects
    if not quiet:
        console.print("[dim]Scanning the realm for projects...[/]")
    projects = scan_projects(config)

    if not projects:
        console.print("[yellow]No projects found.[/]")
        sys.exit(0)

    # Parse include/exclude
    include = [n.strip() for n in args.include.split(",")] if args.include else None
    exclude = [n.strip() for n in args.exclude.split(",")] if args.exclude else None

    # Build plan
    plan = build_plan(config, drive_path, projects, include=include, exclude=exclude, all_projects=args.all)

    if not plan.projects:
        console.print("[yellow]No projects selected for backup.[/]")
        sys.exit(0)

    if not quiet:
        show_backup_plan(plan, dry_run=args.dry_run)

    # Space check
    if plan.space_check and not plan.space_check.has_space:
        console.print(f"[red]Insufficient space on {drive_path}.[/]")
        console.print(f"[red]Need: {plan.space_check.needed_human}, Free: {plan.space_check.free_human}[/]")
        sys.exit(1)

    # Confirm
    if not args.dry_run and not args.yes and not quiet:
        if not confirm_backup():
            console.print("[dim]Backup cancelled.[/]")
            return

    # Execute backup
    if not quiet:
        progress = create_backup_progress()
        tasks = {}

        def progress_callback(name, pct):
            if name in tasks:
                progress.update(tasks[name], completed=pct)

        with progress:
            for project in plan.projects:
                tasks[project.name] = progress.add_task(project.name, total=100)

            result = run_backup(plan, progress_callback=progress_callback, dry_run=args.dry_run)
    else:
        result = run_backup(plan, dry_run=args.dry_run)

    # Create manifest
    if not args.dry_run and result.projects_synced > 0:
        from pathlib import Path as P
        snapshot_path = str(P(plan.vault_path) / plan.snapshot_name)
        synced_names = [name for name, ok in result.project_results.items() if ok]
        manifest = create_manifest(snapshot_path, synced_names)
        save_manifest(manifest, snapshot_path)

    # Show result
    if not quiet:
        show_backup_result(result)

    # Save history
    if not args.dry_run:
        record = BackupRecord(
            drive_path=drive_path,
            snapshot_name=plan.snapshot_name,
            projects_synced=result.projects_synced,
            projects_failed=result.projects_failed,
            bytes_transferred=result.bytes_transferred,
            duration_seconds=result.duration_seconds,
            errors=result.errors,
        )
        save_backup_record(record)

    if not quiet:
        show_farewell()

    if result.projects_failed > 0:
        sys.exit(1)


def cmd_interactive(args):
    """Interactive mode: detect drives, select projects, back up."""
    config = load_config()
    show_header()

    # Detect drives
    drives = find_external_drives()
    show_drive_list(drives)

    # Also allow manual path entry
    drive = None
    if drives:
        drive = prompt_drive_selection(drives)

    if not drive:
        console.print("[dim]Enter a target path manually:[/]")
        from rich.prompt import Prompt
        path = Prompt.ask("Drive/directory path")
        drive = validate_drive(path)
        if not drive:
            console.print(f"[red]'{path}' is not a valid writable directory.[/]")
            return

    # Scan projects
    console.print("[dim]Scanning the realm for projects...[/]")
    projects = scan_projects(config)
    togit_decisions = load_togit_decisions()

    if not projects:
        console.print("[yellow]No projects found. The stage is empty.[/]")
        return

    console.print(f"[dim]Found {len(projects)} projects.[/]\n")

    # Show project selection
    show_project_selection(projects, togit_decisions)
    selected = prompt_project_selection(projects, togit_decisions)

    if not selected:
        console.print("[dim]No projects selected. The curtain falls.[/]")
        show_farewell()
        return

    # Build plan
    plan = build_plan(config, drive.mount_point, projects)
    plan.projects = selected  # Override with interactive selection

    show_backup_plan(plan)

    if not confirm_backup():
        console.print("[dim]Backup cancelled.[/]")
        return

    # Execute
    progress = create_backup_progress()
    tasks = {}

    def progress_callback(name, pct):
        if name in tasks:
            progress.update(tasks[name], completed=pct)

    with progress:
        for project in plan.projects:
            tasks[project.name] = progress.add_task(project.name, total=100)

        result = run_backup(plan, progress_callback=progress_callback)

    # Create manifest
    if result.projects_synced > 0:
        from pathlib import Path as P
        snapshot_path = str(P(plan.vault_path) / plan.snapshot_name)
        synced_names = [name for name, ok in result.project_results.items() if ok]
        manifest = create_manifest(snapshot_path, synced_names)
        save_manifest(manifest, snapshot_path)

    show_backup_result(result)

    # Save history
    record = BackupRecord(
        drive_path=drive.mount_point,
        snapshot_name=plan.snapshot_name,
        projects_synced=result.projects_synced,
        projects_failed=result.projects_failed,
        bytes_transferred=result.bytes_transferred,
        duration_seconds=result.duration_seconds,
        errors=result.errors,
    )
    save_backup_record(record)

    show_farewell()


def cmd_status(args):
    """Show snapshots on a drive."""
    from tokeep.retention import list_snapshots

    config = load_config()
    show_header()

    drive_path = args.drive
    if not drive_path:
        drives = find_external_drives()
        show_drive_list(drives)
        if drives:
            drive = prompt_drive_selection(drives)
            if drive:
                drive_path = drive.mount_point
        if not drive_path:
            console.print("[yellow]No drive specified. Use --drive PATH.[/]")
            return

    vault_name = config.get("backup", {}).get("vault_name", "tokeep-vault")
    from pathlib import Path
    vault_path = str(Path(drive_path) / vault_name)

    snapshots = list_snapshots(vault_path)
    show_snapshot_list(snapshots, drive_path)
    show_farewell()


def cmd_verify(args):
    """Verify backup integrity."""
    from tokeep.verify import verify_backup
    from pathlib import Path

    config = load_config()
    show_header()

    vault_name = config.get("backup", {}).get("vault_name", "tokeep-vault")
    vault_path = Path(args.drive) / vault_name

    # Find snapshot
    if args.snapshot:
        snapshot_path = vault_path / args.snapshot
    else:
        latest = vault_path / "latest"
        if latest.is_symlink():
            snapshot_path = latest.resolve()
        else:
            console.print("[red]No 'latest' symlink found. Use --snapshot NAME.[/]")
            return

    if not snapshot_path.exists():
        console.print(f"[red]Snapshot not found: {snapshot_path}[/]")
        return

    manifest = load_manifest(str(snapshot_path))
    if not manifest:
        console.print(f"[red]No manifest found in {snapshot_path}.[/]")
        return

    console.print(f"[dim]Verifying snapshot: {snapshot_path.name}...[/]")
    result = verify_backup(str(snapshot_path), manifest, deep=args.deep)
    show_verify_result(result)
    show_farewell()


def cmd_prune(args):
    """Remove old snapshots."""
    from tokeep.retention import list_snapshots, plan_retention, prune_snapshots
    from pathlib import Path

    config = load_config()
    show_header()

    vault_name = config.get("backup", {}).get("vault_name", "tokeep-vault")
    vault_path = str(Path(args.drive) / vault_name)

    snapshots = list_snapshots(vault_path)
    if not snapshots:
        console.print("[yellow]No snapshots found to prune.[/]")
        return

    keep = args.keep or config.get("backup", {}).get("retention_count", 5)
    to_delete, to_keep = plan_retention(snapshots, keep)

    if not to_delete:
        console.print(f"[green]Nothing to prune. Only {len(snapshots)} snapshot(s), keeping {keep}.[/]")
        return

    show_prune_plan(to_delete, to_keep)

    if not args.yes:
        if not confirm_prune():
            console.print("[dim]Pruning cancelled.[/]")
            return

    removed = prune_snapshots(to_delete)
    console.print(f"[green]Pruned {removed} snapshot(s).[/]")
    show_farewell()


def cmd_schedule(args):
    """Set up or remove cron schedule."""
    from tokeep.scheduler import generate_cron_entry, install_cron, remove_cron

    show_header()

    if args.remove:
        removed = remove_cron()
        if removed:
            console.print("[green]Cron schedule removed.[/]")
        else:
            console.print("[yellow]No existing tokeep schedule found.[/]")
        return

    if not args.drive:
        console.print("[red]--drive PATH is required for scheduling.[/]")
        return

    if not args.daily and not args.weekly:
        console.print("[red]Specify --daily or --weekly.[/]")
        return

    schedule = "daily" if args.daily else "weekly"
    cron_entry = generate_cron_entry(schedule, args.drive)
    install_cron(cron_entry)
    show_schedule_confirmation(schedule, args.drive, cron_entry)
    show_farewell()


def cmd_history(args):
    """Show backup history."""
    show_header()
    records = load_backup_history()
    show_history(records)
    show_farewell()


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "run":
            cmd_run(args)
        elif args.command == "drives":
            cmd_drives(args)
        elif args.command == "status":
            cmd_status(args)
        elif args.command == "verify":
            cmd_verify(args)
        elif args.command == "prune":
            cmd_prune(args)
        elif args.command == "schedule":
            cmd_schedule(args)
        elif args.command == "history":
            cmd_history(args)
        else:
            # Default: interactive mode
            cmd_interactive(args)
    except KeyboardInterrupt:
        console.print("\n[dim]Exit, pursued by a bear.[/]\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
