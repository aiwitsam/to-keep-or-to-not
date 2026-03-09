# To Keep or to Not

> *"To keep, or not to keep -- that is the question."*

A Shakespeare-themed CLI tool for backing up project directories to external drives. Uses rsync for incremental snapshots with hardlink deduplication, so repeated backups of unchanged files cost zero extra space.

Built as a companion to [togit](https://github.com/aiwitsam/git-to-github-or-to-not) (optional -- works standalone too).

## Why

Git is not a backup. If your machine dies, local-only repos are gone. This tool provides physical redundancy by syncing projects to external hard drives with:

- **Incremental snapshots** -- timestamped directories, one per backup run
- **Hardlink dedup** -- unchanged files between snapshots share disk blocks (via rsync `--link-dest`)
- **Integrity verification** -- structural checksums per project, with optional deep content hashing
- **Retention pruning** -- automatically remove old snapshots beyond a configurable keep count
- **Restore** -- pull projects back from any snapshot
- **Multi-drive** -- back up to multiple drives in one command
- **Encryption** -- optional GPG encryption of snapshots
- **Bandwidth limiting** -- throttle rsync for slow drives
- **Notifications** -- desktop and email alerts after backups
- **Cron scheduling** -- set it and forget it
- **Config wizard** -- interactive setup via `tokeep init`
- **togit integration** -- if you use togit, backup decisions follow your git/github/skip/deny choices

## Install

```bash
pip install -e .
```

Or if you use togit's shared venv:

```bash
source ~/git-to-github-or-to-not/.venv/bin/activate
pip install -e ~/to-keep-or-to-not
```

**Requirements:** Python 3.10+, rsync, rich, pyyaml

## Usage

### First-Time Setup

```bash
tokeep init              # Interactive config wizard
```

### Interactive Mode

```bash
tokeep
```

Detects external drives, lets you pick projects, confirms, and backs up.

### Non-Interactive Backup

```bash
# Back up specific projects
tokeep run --drive /mnt/d --include myproject,another-project

# Back up everything
tokeep run --drive /mnt/d --all

# Preview without writing
tokeep run --drive /mnt/d --all --dry-run

# Skip confirmation (for scripts/cron)
tokeep run --drive /mnt/d --all --yes --quiet

# Multi-drive: back up to two drives at once
tokeep run --drive /mnt/d,/mnt/e --all --yes

# Limit bandwidth (useful for slow USB drives)
tokeep run --drive /mnt/d --all --bwlimit 10m

# Encrypt snapshot with GPG after backup
tokeep run --drive /mnt/d --all --encrypt
```

### Restore

```bash
# Restore a project from the latest snapshot
tokeep restore --drive /mnt/d --project myproject --to ~/restored/

# Restore from a specific snapshot
tokeep restore --drive /mnt/d --project myproject --to ~/restored/ --snapshot 2026-03-08T14-30-00

# Preview what would be restored
tokeep restore --drive /mnt/d --project myproject --to ~/restored/ --dry-run
```

### Other Commands

```bash
tokeep drives                            # List detected external drives
tokeep status --drive /mnt/d             # Show snapshots on a drive
tokeep verify --drive /mnt/d             # Verify latest backup integrity
tokeep verify --drive /mnt/d --deep      # Full content verification (slow)
tokeep prune --drive /mnt/d --keep 3     # Remove old snapshots, keep 3
tokeep schedule --daily --drive /mnt/d   # Install cron job (daily at 2am)
tokeep schedule --weekly --drive /mnt/d  # Weekly on Sunday at 2am
tokeep schedule --remove                 # Remove cron schedule
tokeep history                           # Show backup log
```

## How It Works

### Backup Structure

```
/mnt/your-drive/tokeep-vault/
    2026-03-08T14-30-00/         # Timestamped snapshot
        project-a/               # rsync'd project contents
        project-b/
        _manifest.json           # Structural checksums
    2026-03-09T14-30-00/         # Next snapshot (hardlinked unchanged files)
        project-a/
        project-b/
        _manifest.json
    latest -> 2026-03-09T14-30-00/  # Symlink to newest
```

### Hardlink Dedup

When rsync runs with `--link-dest` pointing to the previous snapshot, unchanged files are hardlinked instead of copied. This means:

- First backup: full copy (~200MB for a typical project)
- Second backup with no changes: ~0 bytes transferred
- Only modified files consume additional space

### togit Integration

If [togit](https://github.com/aiwitsam/git-to-github-or-to-not) is installed in the same venv, tokeep automatically:

- **Auto-includes** projects with `git` or `github` decisions
- **Excludes** projects with `deny` decisions
- **Shows but doesn't auto-select** projects with `skip` or no decision

Works fine without togit -- falls back to its own project scanner.

## Configuration

Run `tokeep init` for interactive setup, or edit `~/.tokeep/config.yaml` directly:

```yaml
scan_path: /home/you
exclude_dirs:
  - node_modules
  - .cache
  - .venv
  - __pycache__
deny_list:
  patterns: []     # Substring matches on directory names
  paths: []        # Explicit paths to always exclude
backup:
  vault_name: tokeep-vault
  retention_count: 5
  bwlimit: null    # e.g. "10m" to limit bandwidth
  gpg_key_id: null # GPG key for --encrypt
  global_excludes:
    - node_modules
    - .venv
    - __pycache__
    - .git
    - dist
    - build
  sensitive_excludes:
    - .env
    - "*.pem"
    - "*.key"
    - credentials.json
    - token.json
notifications:
  enabled: false
  desktop: true
  email: null      # e.g. "you@example.com"
```

### Deny List

Add patterns or paths to permanently exclude directories:

```yaml
deny_list:
  patterns:
    - secrets
    - confidential
  paths:
    - /home/you/sensitive-project
```

## Development

```bash
pip install -e .
pip install pytest ruff

# Run tests
pytest tests/ -v

# Lint
ruff check tokeep/ tests/
```

## State Files

```
~/.tokeep/
    config.yaml    # User preferences
    history.json   # Log of all backup runs
    cron.log       # Output from scheduled runs
```

## License

MIT
