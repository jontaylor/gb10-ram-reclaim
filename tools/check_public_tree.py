#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Heuristic publication check of Git's index; never reads private home files.

This supplements source selection and human review, not a general secret detector.
Only filenames and rule names are reported, never matching secret contents.
"""
from pathlib import Path
import re
import subprocess
import sys

PATTERNS = {
    'PEM key or certificate': re.compile(rb'^-----BEGIN (?:[A-Z ]*PRIVATE KEY|CERTIFICATE)-----', re.M),
    'GitHub token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'OpenAI key': re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b'),
    'private IPv4 address': re.compile(rb'\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b'),
    'personal home path': re.compile(rb'/(?:home|Users)/[a-zA-Z][a-zA-Z0-9_.-]*/'),
    'machine MAC address': re.compile(rb'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b'),
    'UUID or boot identifier': re.compile(rb'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b'),
}
FORBIDDEN_SUFFIXES = {'.key', '.pem', '.der', '.crt', '.cer', '.p12', '.pfx', '.ko', '.o', '.log'}


def inspect(path, content):
    errors = []
    p = Path(path)
    if p.suffix.lower() in FORBIDDEN_SUFFIXES or p.name in {'.env', 'auth.json', 'hosts.yml'}:
        errors.append('private/binary/raw-log file type')
    if p.parts[0] in {'build', 'artifacts', 'private'}:
        errors.append('generated/private directory')
    if len(content) > 1024 * 1024 or b'\x00' in content:
        errors.append('unexpected binary or large blob')
    errors.extend(name for name, pattern in PATTERNS.items() if pattern.search(content))
    return errors


def main():
    root = Path(__file__).resolve().parents[1]
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).split(b'\x00')
    failed, count = False, 0
    for raw in filter(None, paths):
        path = raw.decode()
        content = subprocess.check_output(['git', 'show', ':' + path], cwd=root)
        errors = inspect(path, content)
        count += 1
        if errors:
            failed = True
            print(f'{path}: {", ".join(errors)}', file=sys.stderr)
    if not count:
        print('No indexed files: git add the intended sources before checking.', file=sys.stderr)
        return 2
    print(f'Checked {count} indexed files; contents were not printed.')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
