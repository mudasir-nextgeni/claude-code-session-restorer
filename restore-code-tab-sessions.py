#!/usr/bin/env python3
"""
  restore-code-tab-sessions.py
  --------------------------------------------------------------------------
  macOS / Linux port of restore-code-tab-sessions.ps1.

  Make your Claude Code transcripts show up again in the Claude Desktop
  "Code" tab -- including after you log in with a DIFFERENT Claude account,
  or for sessions you started from the CLI / VS Code that never appeared.

  WHY SESSIONS GO MISSING
    The Code tab does not list transcripts directly. It lists per-session
    "cards" stored per-account at:
      Linux : ~/.config/Claude/claude-code-sessions/<accountId>/<orgId>/local_*.json
      macOS : ~/Library/Application Support/Claude/claude-code-sessions/<accountId>/<orgId>/local_*.json
    Each card links to a real transcript through its "cliSessionId" field.
    Cards contain no account field -- only their FOLDER location scopes them.
    (Transcripts themselves live, untouched, in
    ~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl and are never
    account-bound.)

  WHAT THIS DOES (idempotent + reversible)
    1. Backs up the whole card index first.
    2. Copies cards that exist under OTHER account folders into yours.
    3. (default) Generates fresh cards for transcripts that have none anywhere
       -- pulling each session's real title from its transcript.

  USAGE
    Quit Claude Desktop completely, then:
      python3 restore-code-tab-sessions.py

  OPTIONS
    --existing-cards-only  Only migrate sessions ORIGINALLY created in the
                           desktop Code tab; skip CLI / VS Code sessions.
    --dest-root <path>     Write cards here instead of the live folder (testing).
    --ignore-running       Don't abort if Claude appears to be running.
    --no-backup            Skip the index backup (testing only).

  Python 3.8+ (standard library only). Unofficial tool that works with
  documented-by-observation app files; backs up before writing and is fully
  reversible. Use at your own risk. MIT licensed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone

HOME = os.path.expanduser('~')
PROJ_ROOT = os.path.join(HOME, '.claude', 'projects')


def app_dir():
    if sys.platform == 'darwin':
        return os.path.join(HOME, 'Library', 'Application Support', 'Claude')
    xdg = os.environ.get('XDG_CONFIG_HOME') or os.path.join(HOME, '.config')
    return os.path.join(xdg, 'Claude')


APP_BASE = os.path.join(app_dir(), 'claude-code-sessions')
# Exact process name of the desktop app (NOT the `claude` CLI / VS Code binary)
APP_PROCESS = 'Claude' if sys.platform == 'darwin' else 'claude-desktop'

COLORS = {'White': '1;37', 'Cyan': '36', 'Green': '32', 'Yellow': '33', 'Gray': '90'}


def say(m, c='Gray'):
    if sys.stdout.isatty():
        print('\033[{}m{}\033[0m'.format(COLORS[c], m))
    else:
        print(m)


def running_pids():
    try:
        out = subprocess.run(['pgrep', '-x', APP_PROCESS], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return []
    return out.split()


def load_json(path):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cards(folder, recursive):
    """Yield paths of local_*.json card files."""
    if not os.path.isdir(folder):
        return
    if recursive:
        for d, _, files in os.walk(folder):
            for n in files:
                if n.startswith('local_') and n.endswith('.json'):
                    yield os.path.join(d, n)
    else:
        for n in os.listdir(folder):
            p = os.path.join(folder, n)
            if n.startswith('local_') and n.endswith('.json') and os.path.isfile(p):
                yield p


def epoch_ms(iso, file_ts):
    if iso:
        try:
            s = iso.strip().replace('Z', '+00:00')
            # fromisoformat (< 3.11) wants 0, 3 or 6 fractional digits
            s = re.sub(r'\.(\d+)', lambda m: '.' + (m.group(1) + '000000')[:6], s, count=1)
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            pass
    return int(file_ts * 1000)


def get_meta(path):
    cwd = created = ai = summ = usr = None
    with open(path, encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f, 1):
            if i > 400:
                break
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if not isinstance(o, dict):
                continue
            if not created and o.get('timestamp'):
                created = o['timestamp']
            if not cwd and o.get('cwd'):
                cwd = o['cwd']
            if not ai and o.get('type') == 'ai-title' and o.get('aiTitle'):
                ai = o['aiTitle']
            if not summ and o.get('type') == 'summary' and o.get('summary'):
                summ = o['summary']
            if not usr and o.get('type') == 'user' and isinstance(o.get('message'), dict):
                c = o['message'].get('content')
                txt = None
                if isinstance(c, str):
                    txt = c
                elif isinstance(c, list):
                    txt = next((p.get('text') for p in c if isinstance(p, dict) and p.get('type') == 'text'), None)
                if (txt and not re.match(r'^\s*<', txt)
                        and not txt.startswith('This session is being continued')
                        and not re.match(r'^\s*Caveat:', txt)
                        and not txt.startswith('Base directory for this skill')):
                    usr = txt
            # stop early only once we have the ideal title (aiTitle); otherwise keep scanning for it
            if cwd and created and ai:
                break
    title = ai or summ or usr
    if title:
        title = re.sub(r'\s+', ' ', title)[:80]
    return cwd, created, title


def main():
    ap = argparse.ArgumentParser(description='Restore missing sessions in the Claude Desktop Code tab (macOS / Linux).')
    ap.add_argument('--existing-cards-only', action='store_true',
                    help='only copy existing cards from other accounts; skip CLI / VS Code sessions')
    ap.add_argument('--dest-root', help='write cards here instead of the live folder (testing)')
    ap.add_argument('--ignore-running', action='store_true', help="don't abort if Claude appears to be running")
    ap.add_argument('--no-backup', action='store_true', help='skip the index backup (testing only)')
    a = ap.parse_args()

    say('== Claude Code -> Code-tab session restorer ==', 'White')

    # 1) Claude must be closed (it rewrites this folder on exit)
    if not a.ignore_running:
        pids = running_pids()
        if pids:
            say('Claude Desktop is still running (PID {}). Quit it COMPLETELY, then re-run.'.format(', '.join(pids)), 'Yellow')
            return 1

    # 2) Resolve destination = <accountId>/<orgId> for the logged-in account
    if a.dest_root:
        dest = a.dest_root
    else:
        cj_path = os.path.join(HOME, '.claude.json')
        if not os.path.isfile(cj_path):
            say("Can't find {} -- is Claude Code installed for this user?".format(cj_path), 'Yellow')
            return 1
        acct_info = (load_json(cj_path) or {}).get('oauthAccount') or {}
        acct, org = acct_info.get('accountUuid'), acct_info.get('organizationUuid')
        if not acct or not org:
            say("Couldn't read the logged-in account from .claude.json (are you signed in?).", 'Yellow')
            return 1
        dest = os.path.join(APP_BASE, acct, org)
        say('Logged-in account : {}'.format(acct), 'Cyan')
        say('Organization      : {}'.format(org), 'Cyan')
    say('Target card folder: {}'.format(dest), 'Cyan')
    os.makedirs(dest, exist_ok=True)

    # 3) Back up the entire card index
    if not a.no_backup and os.path.isdir(APP_BASE):
        bk = APP_BASE + '_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copytree(APP_BASE, bk)
        say('Backed up Code-tab index -> {}'.format(bk), 'Green')

    # 4) Template for model/effort/MCP defaults (clone an existing card if present)
    all_cards = sorted(cards(APP_BASE, True), key=os.path.getsize)
    tmpl = (load_json(all_cards[0]) if all_cards else None) or {}
    def_model = tmpl.get('model') or 'claude-opus-4-8'
    def_effort = tmpl.get('effort') or 'high'
    def_chrome = tmpl.get('chromePermissionMode') or 'default'
    def_mcp = tmpl.get('remoteMcpServersConfig')

    # 5) cliSessionIds already carded in dest
    have = set()
    for p in cards(dest, False):
        o = load_json(p)
        if isinstance(o, dict) and o.get('cliSessionId'):
            have.add(str(o['cliSessionId']).lower())

    # 6) Copy cards from OTHER account/org folders into dest
    copied = 0
    dest_real = os.path.realpath(dest)
    for p in all_cards:
        if os.path.realpath(os.path.dirname(p)) == dest_real:
            continue
        o = load_json(p)
        if not isinstance(o, dict) or not o.get('cliSessionId'):
            continue
        key = str(o['cliSessionId']).lower()
        if key in have:
            continue
        target = os.path.join(dest, os.path.basename(p))
        if os.path.exists(target):
            target = os.path.join(dest, 'local_{}.json'.format(uuid.uuid4()))
        shutil.copy2(p, target)
        have.add(key)
        copied += 1
    say('Copied {} card(s) from other account folders.'.format(copied), 'Green')

    # 7) Generate cards for transcripts that still have none (unless --existing-cards-only)
    generated = skipped = 0
    if a.existing_cards_only:
        say('--existing-cards-only set: skipping generation for CLI / VS Code sessions.', 'Yellow')
    else:
        for d, _, files in os.walk(PROJ_ROOT):
            if os.path.basename(d) == 'subagents':
                continue
            for n in sorted(files):
                if not n.endswith('.jsonl'):
                    continue
                path = os.path.join(d, n)
                cli = n[:-len('.jsonl')]
                key = cli.lower()
                if key in have:
                    skipped += 1
                    continue
                cwd, created_iso, title = get_meta(path)
                cwd = cwd or ''
                st = os.stat(path)
                created = epoch_ms(created_iso, getattr(st, 'st_birthtime', st.st_mtime))
                last = int(st.st_mtime * 1000)
                if not title:
                    leaf = os.path.basename(cwd.rstrip('/\\')) if cwd else 'session'
                    title = '{} (recovered)'.format(leaf)
                guid = str(uuid.uuid4())
                rec = {
                    'sessionId': 'local_{}'.format(guid), 'cliSessionId': cli, 'cwd': cwd, 'originCwd': cwd,
                    'lastFocusedAt': last, 'createdAt': created, 'lastActivityAt': last,
                    'model': def_model, 'effort': def_effort, 'isArchived': False,
                    'title': title, 'titleSource': 'auto', 'permissionMode': 'auto',
                    'remoteMcpServersConfig': def_mcp, 'chromePermissionMode': def_chrome,
                    'completedTurns': 1, 'alwaysAllowedReasons': None, 'sessionPermissionUpdates': None,
                    'classifierSummaryEnabled': True,
                }
                # UTF-8, no BOM
                with open(os.path.join(dest, 'local_{}.json'.format(guid)), 'w', encoding='utf-8') as f:
                    json.dump(rec, f, ensure_ascii=False, separators=(',', ':'))
                have.add(key)
                generated += 1
        say('Generated {} new card(s); skipped {} already present.'.format(generated, skipped), 'Green')

    total = sum(1 for _ in cards(dest, False))
    say("DONE. This account's Code tab now has {} session card(s).".format(total), 'White')
    say('Start Claude Desktop, open the Code tab -> your sessions should be listed.', 'Cyan')
    return 0


if __name__ == '__main__':
    sys.exit(main())
