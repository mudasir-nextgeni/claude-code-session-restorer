# Contributing

Thanks for helping improve **Claude Code Session Restorer**! It's a small, focused, community
tool — contributions of every size are welcome, from typo fixes to a full macOS/Linux port.

> **Ground rule:** this project touches people's local Claude Code data. Every change must stay
> **safe by default** (back up first, never delete, never clobber newer data) and must **never**
> commit anyone's personal data.

## Good first contributions

- 🍎 **Verify on macOS** — the Python port picks `~/Library/Application Support/Claude` and the
  `Claude` process name, but hasn't been confirmed on a real Mac yet.
- 🐛 **App-version compatibility** — if a Claude Desktop update changes the card format or
  folder layout, a fix here helps everyone.
- 📝 **Docs** — clearer steps, troubleshooting, screenshots/GIFs.
- ✅ **Safer testing** — anything that makes it easier to verify before running against live data.

## Project layout

| File | What it is |
|------|------------|
| `restore-code-tab-sessions.ps1` | Rebuilds the per-account Code-tab session index (Windows). |
| `claude-code-backup-restore.ps1` | Full backup & restore of transcripts + index + settings (Windows). |
| `restore-code-tab-sessions.py` | macOS / Linux port of the restorer (Python 3.8+, stdlib only). |
| `claude-code-backup-restore.py` | macOS / Linux port of backup & restore. |
| `SKILL.md` | Claude skill wrapper. |
| `README.md` | User documentation. |

## How it works (reference for contributors)

Claude Code stores **transcripts** (the conversations) here, on every OS:

```
~/.claude/projects/<encoded-working-dir>/<sessionId>.jsonl
```

The Claude Desktop **Code tab** does not read those directly — it reads per-account "card"
files. On **Windows**:

```
%APPDATA%\Claude\claude-code-sessions\<accountId>\<organizationId>\local_<desktopId>.json
```

Each card links to a transcript through its `cliSessionId` field, and cards carry **no account
field** — they're scoped only by their folder. Notable fields:

| Field | Meaning |
|-------|---------|
| `sessionId` | Desktop card id (`local_<guid>`), also the filename. |
| `cliSessionId` | The transcript id — the `<sessionId>.jsonl` on disk. The link. |
| `cwd` / `originCwd` | Working directory. |
| `createdAt` / `lastActivityAt` / `lastFocusedAt` | Epoch milliseconds. |
| `title` / `titleSource` | Display title (we use the transcript's `aiTitle`). |
| `model`, `effort`, `permissionMode`, `isArchived` | Session settings. |
| `remoteMcpServersConfig` | Cached MCP config (cloned from an existing card). |

New cards must be written as **UTF-8 without a BOM**.

## Platform paths

The transcript path (`~/.claude/projects/`) is the same everywhere — only the Code-tab card
index location and the desktop app's process name differ:

| OS | Card-index base | Desktop process | Status |
|----|-----------------|-----------------|--------|
| Windows | `%APPDATA%\Claude\claude-code-sessions` | `Claude` | verified |
| macOS | `~/Library/Application Support/Claude/claude-code-sessions` | `Claude` | *unverified — please confirm* |
| Linux | `~/.config/Claude/claude-code-sessions` (`$XDG_CONFIG_HOME` respected) | `claude-desktop` | verified (Ubuntu) |

The "is Claude running" check must match the **desktop app only**, never the `claude` CLI /
VS Code binary — the Python scripts use an exact, case-sensitive `pgrep -x`.

The `.ps1` and `.py` scripts mirror each other step for step — when you change one, change
the other.

## Development & testing

**Never test against your only copy of your data.** Both scripts have safe dry-run paths:

```powershell
# Restorer: write cards to a throwaway folder instead of the live one
.\restore-code-tab-sessions.ps1 -DestRoot .\_dryrun -IgnoreRunning -NoBackup

# Backup/restore: back up to a temp folder (restore merges and won't clobber newer files)
.\claude-code-backup-restore.ps1 -Path .\_test
```

```bash
# Same for the Python port
python3 restore-code-tab-sessions.py --dest-root ./_dryrun --ignore-running --no-backup
python3 claude-code-backup-restore.py --path ./_test

# Fully isolated: point HOME at a fake home with synthetic transcripts/cards
HOME=/tmp/fakehome python3 restore-code-tab-sessions.py --ignore-running
```

Checklist before opening a PR:

- [ ] Backs up before writing; **never deletes**; doesn't overwrite newer data without `-Force`.
- [ ] **Idempotent** — safe to run twice (no duplicate cards).
- [ ] Writes JSON as UTF-8 **without a BOM**.
- [ ] Windows scripts stay **Windows PowerShell 5.1**–compatible (no PS7-only syntax).
- [ ] Python scripts stay **Python 3.8**–compatible and **standard library only**.
- [ ] `.ps1` and `.py` versions still behave the same.
- [ ] Tested against a dry-run/temp folder — say what you tested in the PR.

## Privacy rules (important)

This repo must contain **zero** personal data. Before you commit:

- Never commit transcripts (`*.jsonl`), backups (`*_backup_*`), `.claude/`, or `.claude.json`
  — `.gitignore` already blocks these; don't override it.
- Never hardcode user paths, account/organization IDs, emails, or machine names. Use
  `$env:USERPROFILE`, `$env:APPDATA`, `$HOME`, `os.path.expanduser('~')`, etc.
- When filing issues, **redact** your account/organization IDs and email.

## Submitting changes

1. Fork and branch: `git checkout -b fix/short-description`.
2. Make the change and test it via a dry-run/temp folder.
3. Commit with a clear message and open a PR describing **what changed** and **how you tested it**.
4. For app-format changes, note the **Claude Desktop version** you observed.

Be kind in issues and reviews — assume good intent.

## License

By contributing, you agree your contributions are licensed under the [MIT License](./LICENSE).
