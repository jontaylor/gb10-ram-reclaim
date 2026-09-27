#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only compatibility gate; this does not prove exclusive memory ownership."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from query_carveout import query

KERNEL = '6.17.0-1032-nvidia'
DRIVER = '580.173.02'
CONFIG_SHA256 = 'd7308f98799d0296b78f4f683794912385b028162712cd521f994af4f9cf7f3b'
IMAGE_SHA256 = '04454e481d9082e07a975535f485b1bc205b75115bbf4c8b3f0518dc06a00e11'
DISPLAY = dict(base=0x280200000, size=0x7fe00000, type=0)
UEFI = dict(base=0x300000000, size=0x3000000, type=2)


def validate(info):
    expected = dict(arch='aarch64', page_size=4096, kernel=KERNEL,
                    driver=DRIVER, product='GX10', vendor='ASUSTeK COMPUTER INC.',
                    bios='GX10DGX.0105.2026.0505.1153', config_sha256=CONFIG_SHA256,
                    image_sha256=IMAGE_SHA256)
    errors = [f'{key}: expected {value!r}, got {info.get(key)!r}'
              for key, value in expected.items() if info.get(key) != value]
    regions = info.get('regions', [])
    if len(regions) != 2 or DISPLAY not in regions or UEFI not in regions:
        errors.append('RM regions differ from the reviewed display + UEFI layout')
    if info.get('reclaim_loaded') is not False:
        errors.append('reclamation already loaded or state unknown; do not replay')
    return errors


def collect():
    kernel = platform.release()
    def dmi(name):
        return Path('/sys/class/dmi/id', name).read_text().strip()
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    # This also fails if GPU firmware cannot initialize. No raw host identifiers.
    driver = subprocess.check_output(['nvidia-smi', '--query-gpu=driver_version',
                                     '--format=csv,noheader'], text=True).strip()
    return dict(arch=platform.machine(), page_size=os.sysconf('SC_PAGE_SIZE'),
                kernel=kernel, driver=driver, product=dmi('product_name'),
                vendor=dmi('sys_vendor'), bios=dmi('bios_version'),
                config_sha256=sha(f'/boot/config-{kernel}'),
                image_sha256=sha(f'/boot/vmlinuz-{kernel}'), regions=query(),
                reclaim_loaded=any(Path('/sys/module', m).exists() for m in
                                   ['gb10_reclaim_probe', 'gb10_reclaim_left', 'gb10_reclaim_right']))


def main():
    try:
        info = collect()
        errors = validate(info)
        print(json.dumps(dict(observed=info, compatible=not errors, errors=errors), indent=2))
        if errors:
            return 2
        print('Compatibility matches. Still requires idle/headless ownership checks and module audit.', file=sys.stderr)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Preflight refused: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
