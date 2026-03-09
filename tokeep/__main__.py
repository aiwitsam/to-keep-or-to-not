"""CLI entry point for To Keep or to Not."""

import argparse
import sys

from tokeep import __version__
from tokeep.config import (
    load_config, save_config, load_backup_history, save_backup_record,
    BackupRecord, load_togit_decisions, CONFIG_FILE,
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
    show_schedule_confirmation, show_restore_result,
    show_encrypt_result, show_init_complete, show_farewell,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tokeep",
        description="To Keep or to Not — Shakespeare-themed external drive backup",
    )
    parser.add_argument("--version", action="version", version=f"tokeep {__version__}")

    sub = parser.add_subparsers(dest="command")

    # run — non-interactive backup with saved config
    run_parser = sub.add_parser("run", help="Run backup (non-interactive with flags)")
    run_parser.add_argument("--drive", metavar="PATH", help="Target drive(s), comma-separated for multi-drive")
    run_parser.add_argument("--all", action="store_true", help="Back up all non-denied projects")
    run_parser.add_argument("--include", metavar="NAMES", help="Only these projects (comma-separated)")
    run_parser.add_argument("--exclude", metavar="NAMES", help="Skip these projects (comma-separated)")
    run_parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    run_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    run_parser.add_argument("--quiet", action="store_true", help="Minimal output (for cron)")
    run_parser.add_argument("--bwlimit", metavar="RATE", help="Bandwidth limit for rsync (e.g. 10m, 1000k)")
    run_parser.add_argument("--encrypt", action="store_true", help="Encrypt snapshot with GPG after backup")

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

    # restore — restore from backup
    restore_parser = sub.add_parser("restore", help="Restore a project from backup")
    restore_parser.add_argument("--drive", metavar="PATH", required=True, help="Source drive")
    restore_parser.add_argument("--project", metavar="NAME", required=True, help="Project name to restore")
    restore_parser.add_argument("--to", metavar="PATH", required=True, help="Destination path")
    restore_parser.add_argument("--snapshot", metavar="NAME", help="Specific snapshot (default: latest)")
    restore_parser.add_argument("--dry-run", action="store_true", help="Show what would be restored")

    # init — config wizard
    init_parser = sub.add_parser("init", help="Initialize configuration interactively")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing config")

    return parser


def cmd_drives(args):
    """List detected external drives."""
    show_header()
    drives = find_external_drives()
    show_drive_list(drives)
    show_farewell()


def _run_single_drive(args, config, drive_path, projects, quiet):
    """Execute backup for a single drive. Returns BackupResult."""
    drive = validate_drive(drive_path)
    if not drive:
        console.print(f"[red]Error: '{drive_path}' is not a valid writable drive/directory.[/]")
        return None

    include = [n.strip() for n in args.include.split(",")] if args.include else None
    exclude = [n.strip() for n in args.exclude.split(",")] if args.exclude else None
    bwlimit = getattr(args, "bwlimit", None) or config.get("backup", {}).get("bwlimit")

    plan = build_plan(config, drive_path, projects, include=include, exclude=exclude, all_projects=args.all)

    if not plan.projects:
        console.print(f"[yellow]No projects selected for backup to {drive_path}.[/]")
        return None

    if not quiet:
        show_backup_plan(plan, dry_run=args.dry_run)

    if plan.space_check and not plan.space_check.has_space:
        console.print(f"[red]Insufficient space on {drive_path}.[/]")
        console.print(f"[red]Need: {plan.space_check.needed_human}, Free: {plan.space_check.free_human}[/]")
        return None

    if not args.dry_run and not args.yes and not quiet:
        if not confirm_backup():
            console.print("[dim]Backup cancelled.[/]")
            return None

    if not quiet:
        progress = create_backup_progress()
        tasks = {}

        def progress_callback(name, pct):
            if name in tasks:
                progress.update(tasks[name], completed=pct)

        with progress:
            for project in plan.projects:
                tasks[project.name] = progress.add_task(project.name, total=100)
            result = run_backup(plan, progress_callback=progress_callback, dry_run=args.dry_run, bwlimit=bwlimit)
    else:
        result = run_backup(plan, dry_run=args.dry_run, bwlimit=bwlimit)

    # Create manifest
    if not args.dry_run and result.projects_synced > 0:
        from pathlib import Path
        snapshot_path = str(Path(plan.vault_path) / plan.snapshot_name)
        synced_names = [name for name, ok in result.project_results.items() if ok]
        manifest = create_manifest(snapshot_path, synced_names)
        save_manifest(manifest, snapshot_path)

        # Optional encryption
        if getattr(args, "encrypt", False):
            gpg_key = config.get("backup", {}).get("gpg_key_id")
            if gpg_key:
                from tokeep.encryption import encrypt_snapshot
                enc_result = encrypt_snapshot(snapshot_path, gpg_key)
                if not quiet:
                    show_encrypt_result(enc_result)
            elif not quiet:
                console.print("[yellow]--encrypt specified but no gpg_key_id in config. Skipping.[/]")

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

    # Notifications
    from tokeep.notify import send_backup_notification
    send_backup_notification(config, result)

    return result


def cmd_run(args):
    """Non-interactive backup with flags, supports multi-drive."""
    config = load_config()
    quiet = getattr(args, "quiet", False)

    if not quiet:
        show_header()

    drive_arg = args.drive
    if not drive_arg:
        console.print("[red]Error: --drive PATH is required for 'run' command.[/]")
        console.print("[dim]Use 'tokeep drives' to see available drives.[/]")
        sys.exit(1)

    # Scan projects once
    if not quiet:
        console.print("[dim]Scanning the realm for projects...[/]")
    projects = scan_projects(config)

    if not projects:
        console.print("[yellow]No projects found.[/]")
        sys.exit(0)

    # Multi-drive support: split on commas
    drive_paths = [d.strip() for d in drive_arg.split(",")]
    any_failed = False

    for i, drive_path in enumerate(drive_paths):
        if len(drive_paths) > 1 and not quiet:
            console.print(f"\n[bold cyan]--- Drive {i + 1}/{len(drive_paths)}: {drive_path} ---[/]\n")

        result = _run_single_drive(args, config, drive_path, projects, quiet)
        if result is None or (result and result.projects_failed > 0):
            any_failed = True

    if not quiet:
        show_farewell()

    if any_failed:
        sys.exit(1)


def cmd_interactive(args):
    """Interactive mode: detect drives, select projects, back up."""
    config = load_config()
    show_header()

    drives = find_external_drives()
    show_drive_list(drives)

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

    console.print("[dim]Scanning the realm for projects...[/]")
    projects = scan_projects(config)
    togit_decisions = load_togit_decisions()

    if not projects:
        console.print("[yellow]No projects found. The stage is empty.[/]")
        return

    console.print(f"[dim]Found {len(projects)} projects.[/]\n")

    show_project_selection(projects, togit_decisions)
    selected = prompt_project_selection(projects, togit_decisions)

    if not selected:
        console.print("[dim]No projects selected. The curtain falls.[/]")
        show_farewell()
        return

    plan = build_plan(config, drive.mount_point, projects)
    plan.projects = selected

    show_backup_plan(plan)

    if not confirm_backup():
        console.print("[dim]Backup cancelled.[/]")
        return

    bwlimit = config.get("backup", {}).get("bwlimit")
    progress = create_backup_progress()
    tasks = {}

    def progress_callback(name, pct):
        if name in tasks:
            progress.update(tasks[name], completed=pct)

    with progress:
        for project in plan.projects:
            tasks[project.name] = progress.add_task(project.name, total=100)
        result = run_backup(plan, progress_callback=progress_callback, bwlimit=bwlimit)

    if result.projects_synced > 0:
        from pathlib import Path
        snapshot_path = str(Path(plan.vault_path) / plan.snapshot_name)
        synced_names = [name for name, ok in result.project_results.items() if ok]
        manifest = create_manifest(snapshot_path, synced_names)
        save_manifest(manifest, snapshot_path)

    show_backup_result(result)

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

    from tokeep.notify import send_backup_notification
    send_backup_notification(config, result)

    show_farewell()


def cmd_status(args):
    """Show snapshots on a drive."""
    from tokeep.retention import list_snapshots
    from pathlib import Path

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


def cmd_restore(args):
    """Restore a project from backup."""
    from tokeep.restore import restore_project, list_projects_in_snapshot
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

    # Check project exists in snapshot
    available = list_projects_in_snapshot(str(snapshot_path))
    if args.project not in available:
        console.print(f"[red]Project '{args.project}' not found in snapshot.[/]")
        if available:
            console.print(f"[dim]Available: {', '.join(available)}[/]")
        return

    dest = args.to
    console.print(f"[dim]Restoring {args.project} from {snapshot_path.name} to {dest}...[/]")

    result = restore_project(
        snapshot_path=str(snapshot_path),
        project_name=args.project,
        dest_path=dest,
        dry_run=getattr(args, "dry_run", False),
    )

    show_restore_result(result)
    show_farewell()


def cmd_init(args):
    """Interactive configuration wizard."""
    from rich.prompt import Prompt

    show_header()

    if CONFIG_FILE.exists() and not args.force:
        console.print(f"[yellow]Config already exists at {CONFIG_FILE}[/]")
        console.print("[dim]Use --force to overwrite.[/]")
        return

    config = load_config()

    console.print("[bold]Let us prepare thy configuration![/]\n")

    # Scan path
    scan_path = Prompt.ask("Scan path (directory to discover projects)", default=config["scan_path"])
    config["scan_path"] = scan_path

    # Vault name
    vault_name = Prompt.ask("Vault name (directory on drive)", default=config["backup"]["vault_name"])
    config["backup"]["vault_name"] = vault_name

    # Retention count
    retention = Prompt.ask("Snapshots to keep", default=str(config["backup"]["retention_count"]))
    try:
        config["backup"]["retention_count"] = int(retention)
    except ValueError:
        console.print("[yellow]Invalid number, keeping default.[/]")

    # Deny list patterns
    console.print("\n[bold]Deny list patterns[/] (substring matches to always exclude)")
    console.print("[dim]Current: " + (", ".join(config["deny_list"]["patterns"]) or "none") + "[/]")
    patterns_input = Prompt.ask("Patterns (comma-separated, or 'none')", default="none")
    if patterns_input.lower() != "none":
        config["deny_list"]["patterns"] = [p.strip() for p in patterns_input.split(",") if p.strip()]

    # Deny list paths
    console.print("\n[bold]Deny list paths[/] (explicit directories to always exclude)")
    console.print("[dim]Current: " + (", ".join(config["deny_list"]["paths"]) or "none") + "[/]")
    paths_input = Prompt.ask("Paths (comma-separated, or 'none')", default="none")
    if paths_input.lower() != "none":
        config["deny_list"]["paths"] = [p.strip() for p in paths_input.split(",") if p.strip()]

    # Bandwidth limit
    console.print("\n[bold]Bandwidth limit[/] (for rsync, e.g. 10m, 5000k)")
    bwlimit = Prompt.ask("Bandwidth limit (or 'none')", default="none")
    if bwlimit.lower() != "none":
        config["backup"]["bwlimit"] = bwlimit

    # GPG key
    console.print("\n[bold]GPG encryption[/] (optional, for --encrypt flag)")
    gpg_key = Prompt.ask("GPG key ID (or 'none')", default="none")
    if gpg_key.lower() != "none":
        config["backup"]["gpg_key_id"] = gpg_key

    # Notifications
    console.print("\n[bold]Notifications[/]")
    from rich.prompt import Confirm
    notify = Confirm.ask("Enable desktop notifications after backup?", default=False)
    if notify:
        config["notifications"] = {"enabled": True, "desktop": True}

        email = Prompt.ask("Email for backup reports (or 'none')", default="none")
        if email.lower() != "none":
            config["notifications"]["email"] = email

    save_config(config)
    show_init_complete(str(CONFIG_FILE))
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
        elif args.command == "restore":
            cmd_restore(args)
        elif args.command == "init":
            cmd_init(args)
        else:
            cmd_interactive(args)
    except KeyboardInterrupt:
        console.print("\n[dim]Exit, pursued by a bear.[/]\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
