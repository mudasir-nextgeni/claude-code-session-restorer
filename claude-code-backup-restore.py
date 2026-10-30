#!/usr/bin/env python3
"""
  claude-code-backup-restore.py
  --------------------------------------------------------------------------
  macOS / Linux port of claude-code-backup-restore.ps1.

  Full local BACKUP & RESTORE for Claude Code. Protects/moves the data that
  actually matters:
    - ~/.claude/projects            all session transcripts (.jsonl)
    - <app dir>/claude-code-sessions the Code-tab card index
        Linux : ~/.config/Claude/claude-code-sessions
        macOS : ~/Library/Application Support/Claude/claude-code-sessions
    - ~/.claude/settings.json       your settings

  Use it for disaster recovery, moving to a new machine, before reinstalling,
  or to guard against the 30-day transcript auto-cleanup. Transcripts are
  account-independent, so a backup restores cleanly under ANY account.

  BACK UP (default)  -- writes claude-code-backup_<timestamp>/ under --path
    python3 claude-code-backup-restore.py
    python3 claude-code-backup-restore.py --path ~/Backups

  RESTORE
    python3 claude-code-backup-restore.py --restore --path "<backup-folder>"

  SAFETY
    - Restore MERGES: it never deletes, and by default never overwrites a NEWER
      local file (pass --force to overwrite everything from the backup).
    - Quit Claude Desktop before restoring the Code-tab index (it rewrites that
      folder on exit). The script skips the index if Claude is running.
    - After restoring transcripts under a different account, run
      restore-code-tab-sessions.py so they appear in the Code tab.

  Options: --transcripts-only (skip the Code-tab index), --force, --ignore-running.
  Python 3.8+ (standard library only). MIT. Unofficial; use at your own risk.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HOME = os.path.expanduser('~')


def app_dir():
    if sys.platform == 'darwin':
        return os.path.join(HOME, 'Library', 'Application Support', 'Claude')
    xdg = os.environ.get('XDG_CONFIG_HOME') or os.path.join(HOME, '.config')
    return os.path.join(xdg, 'Claude')


PROJ_DIR = os.path.join(HOME, '.claude', 'projects')
IDX_DIR = os.path.join(app_dir(), 'claude-code-sessions')
SET_FILE = os.path.join(HOME, '.claude', 'settings.json')
# Exact process name of the desktop app (NOT the `claude` CLI / VS Code binary)
APP_PROCESS = 'Claude' if sys.platform == 'darwin' else 'claude-desktop'

COLORS = {'White': '1;37', 'Cyan': '36', 'Green': '32', 'Yellow': '33', 'Gray': '90'}


def say(m, c='Gray'):
    if sys.stdout.isatty():
        print('\033[{}m{}\033[0m'.format(COLORS[c], m))
    else:
        print(m)


def claude_running():
    try:
        return subprocess.run(['pgrep', '-x', APP_PROCESS], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


def merge_copy(src, dst, skip_older):
    """Recursive copy that never deletes; with skip_older, never overwrites a newer destination file."""
    if not os.path.isdir(src):
        return 'skipped (source not present)'
    errors = 0
    for d, _, files in os.walk(src):
        out = os.path.join(dst, os.path.relpath(d, src))
        os.makedirs(out, exist_ok=True)
        for n in files:
            s, t = os.path.join(d, n), os.path.join(out, n)
            try:
                if os.path.exists(t):
                    ss, ts = os.stat(s), os.stat(t)
                    if skip_older and ss.st_mtime <= ts.st_mtime:
                        continue
                shutil.copy2(s, t)
            except OSError as e:
                errors += 1
                say('  ! {}: {}'.format(s, e), 'Yellow')
    return 'ok' if not errors else 'ERROR ({} file(s) failed)'.format(errors)


def main():
    ap = argparse.ArgumentParser(description='Back up / restore Claude Code transcripts, Code-tab index and settings.')
    ap.add_argument('--restore', action='store_true', help='restore from the backup folder given by --path')
    ap.add_argument('--path', help='backup parent folder (backup) or backup folder (restore)')
    ap.add_argument('--transcripts-only', action='store_true', help='skip the Code-tab index')
    ap.add_argument('--force', action='store_true', help='on restore, overwrite newer local files too')
    ap.add_argument('--ignore-running', action='store_true', help="restore the index even if Claude is running")
    a = ap.parse_args()
    path = os.path.expanduser(a.path) if a.path else None

    if a.restore:
        say('== Claude Code RESTORE ==', 'White')
        if not path or not os.path.isdir(os.path.join(path, 'projects')):
            say("Pass --path to an existing backup folder (the one that contains a 'projects' subfolder).", 'Yellow')
            return 1
        skip_older = not a.force
        say('transcripts -> {} : {}'.format(PROJ_DIR, merge_copy(os.path.join(path, 'projects'), PROJ_DIR, skip_older)), 'Green')
        if not a.transcripts_only:
            if claude_running() and not a.ignore_running:
                say('Skipping Code-tab index: Claude Desktop is running. Quit it and re-run (or pass --ignore-running) to restore the index.', 'Yellow')
            else:
                res = merge_copy(os.path.join(path, 'claude-code-sessions'), IDX_DIR, skip_older)
                say('code-tab index -> {} : {}'.format(IDX_DIR, res), 'Green')
        bset = os.path.join(path, 'settings.json')
        if os.path.isfile(bset) and not os.path.exists(SET_FILE):
            os.makedirs(os.path.dirname(SET_FILE), exist_ok=True)
            shutil.copy2(bset, SET_FILE)
            say('settings.json restored (was missing locally).', 'Green')
        say("Restore complete. If sessions don't appear in the Code tab, run restore-code-tab-sessions.py.", 'Cyan')
        return 0

    # ---- BACKUP ----
    say('== Claude Code BACKUP ==', 'White')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    root = path or HOME
    dest = os.path.join(root, 'claude-code-backup_' + stamp)
    os.makedirs(dest, exist_ok=True)

    say('transcripts    : {}'.format(merge_copy(PROJ_DIR, os.path.join(dest, 'projects'), False)), 'Green')
    if not a.transcripts_only:
        say('code-tab index : {}'.format(merge_copy(IDX_DIR, os.path.join(dest, 'claude-code-sessions'), False)), 'Green')
    if os.path.isfile(SET_FILE):
        shutil.copy2(SET_FILE, os.path.join(dest, 'settings.json'))
        say('settings.json  : ok', 'Green')

    count = size = 0
    for d, _, files in os.walk(os.path.join(dest, 'projects')):
        for n in files:
            if n.endswith('.jsonl'):
                count += 1
                size += os.path.getsize(os.path.join(d, n))
    mb = round(size / 1048576, 1)
    restore_cmd = 'python3 claude-code-backup-restore.py --restore --path "{}"'.format(dest)
    with open(os.path.join(dest, 'MANIFEST.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join([
            'Claude Code backup',
            'created     : {}'.format(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')),
            'transcripts : {} sessions, {} MB'.format(count, mb),
            '',
            'Restore with:',
            '  ' + restore_cmd,
        ]) + '\n')
    say('\nBacked up {} transcript(s), {} MB -> {}'.format(count, mb, dest), 'White')
    say('Restore later:  ' + restore_cmd, 'Cyan')
    return 0


if __name__ == '__main__':
    sys.exit(main())
