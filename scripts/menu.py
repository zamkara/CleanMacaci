#!/usr/bin/env python3
"""Owned, reversible JSONC menu integration. No system source modifications."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

PLUGIN_ID = 'cleaner.zamkara.ati'
KEY = 'setup.cleanmacaci'
ACTION = 'omarchy-shell shell summon ' + PLUGIN_ID
ENTRY = {'icon': '󰃢', 'label': 'System Cleaner',
         'description': 'Inspect and clean regenerable caches with CleanMacaci',
         'action': ACTION,
         'when': 'python3 "$HOME/.config/omarchy/plugins/' + PLUGIN_ID + '/scripts/menu.py" --available'}

def parse(text):
    # Keep offsets intact so edits preserve comments and unrelated formatting.
    pattern = r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/'
    mask = re.sub(pattern, lambda m: m.group(1) or re.sub(r'[^\n]', ' ', m.group()), text)
    mask = re.sub(r'("(?:\\.|[^"\\])*")|,(?=\s*[}\]])',
                  lambda m: m.group(1) or ' ', mask)
    data = json.loads(mask)
    if not isinstance(data, dict):
        raise ValueError('Menu extension must be an object.')
    decoder = json.JSONDecoder()
    spans = {}
    pos = mask.index('{') + 1
    while True:
        while mask[pos].isspace() or mask[pos] == ',':
            pos += 1
        if mask[pos] == '}':
            return data, spans, pos
        start = pos
        key, pos = decoder.raw_decode(mask, pos)
        while mask[pos].isspace():
            pos += 1
        if mask[pos] != ':':
            raise ValueError('Invalid menu property.')
        pos += 1
        while mask[pos].isspace():
            pos += 1
        value_start = pos
        _, pos = decoder.raw_decode(mask, pos)
        if key in spans:
            raise ValueError('Duplicate menu key: ' + key)
        spans[key] = (start, value_start, pos)

def update(text, remove=False, key=KEY, definition=ENTRY):
    data, spans, end = parse(text)
    old = data.get(key)
    if old is not None and (not isinstance(old, dict) or old.get('action') != definition['action']):
        raise ValueError('System Cleaner menu entry belongs to another tool; preserved.')
    if remove:
        if old is None:
            return text
        start, _, stop = spans[key]
        # Remove only our property and one comma; retain neighboring comments.
        mask_text = re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/',
                           lambda m: m.group(1) or re.sub(r'[^\n]', ' ', m.group()), text)
        following = stop
        while mask_text[following].isspace():
            following += 1
        if mask_text[following] == ',':
            return text[:start] + text[stop:following] + text[following + 1:]
        previous = start - 1
        while mask_text[previous].isspace():
            previous -= 1
        if mask_text[previous] == ',':
            return text[:previous] + text[previous + 1:start] + text[stop:]
        return text[:start] + text[stop:]
    entry = {**(old or {}), **definition}
    if old == entry:
        return text
    payload = json.dumps(entry, ensure_ascii=False, indent=2)
    if old is not None:
        _, start, stop = spans[key]
        return text[:start] + payload + text[stop:]
    # Existing trailing comma is legal JSONC: detect it without stripping comments.
    last_stop = max((span[2] for span in spans.values()), default=0)
    tail = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/', '', text[last_stop:end])
    separator = '' if not data or re.match(r'\s*,', tail) else ','
    return text[:last_stop] + separator + text[last_stop:end] + '\n  ' + json.dumps(key) + ': ' + payload + '\n' + text[end:]

def available():
    try:
        config = Path.home() / '.config/omarchy/shell.json'
        data, _, _ = parse(config.read_text())
        if PLUGIN_ID in data.get('disabledPlugins', []):
            return False
        return any(p.get('id') == PLUGIN_ID and p.get('enabled', True) is not False
                   for p in data.get('plugins', []) if isinstance(p, dict))
    except (OSError, ValueError):
        return False

def integrate_file(config, remove=False, key=KEY, definition=ENTRY):
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'CleanMacaci'
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'menu.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original = config.read_text() if config.exists() else '{}\n'
        result = update(original, remove, key, definition)
        parse(result)
        if result == original:
            return
        config.parent.mkdir(parents=True, exist_ok=True)
        if config.exists():
            stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            shutil.copy2(config, state / ('menu-before-' + stamp + '.jsonc'))
        fd, temporary = tempfile.mkstemp(prefix='.cleanmacaci-', dir=config.parent)
        try:
            with os.fdopen(fd, 'w') as output:
                output.write(result)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, config.stat().st_mode & 0o777 if config.exists() else 0o600)
            os.replace(temporary, config)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

def integrate(remove=False):
    directory = Path.home() / '.config/omarchy/extensions'
    integrate_file(directory / 'omarchy-menu.jsonc', remove)
    custom_entry = {**ENTRY, 'command': ['omarchy-shell', 'shell', 'summon', PLUGIN_ID], 'plugin': PLUGIN_ID}
    integrate_file(directory / 'system-menu.json', remove, PLUGIN_ID, custom_entry)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--install', action='store_true')
    group.add_argument('--remove', action='store_true')
    group.add_argument('--available', action='store_true')
    group.add_argument('--remove-legacy', action='store_true')
    args = parser.parse_args()
    if args.available:
        raise SystemExit(0 if available() else 1)
    if args.remove_legacy:
        integrate_file(Path.home()/'.config/omarchy/extensions/omarchy-menu.jsonc', True, 'setup.cleaner', {'action':'omarchy-shell shell summon zam.cleaner'})
    else:
        integrate(args.remove)
