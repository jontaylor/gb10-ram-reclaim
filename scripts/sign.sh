#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
umask 077
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
keydir=${1:-/root/.local/share/gb10-ram-reclaim/keys}
stage=${2:-/root/.local/share/gb10-ram-reclaim/signed}
[[ $EUID == 0 ]] || { echo 'Run as root to read the local key.' >&2; exit 2; }
[[ $stage == /* && $keydir == /* ]] || { echo 'Use absolute paths.' >&2; exit 2; }
stage=$(realpath -m -- "$stage")
case "$stage/" in "$repo/"*) echo 'Signed output must be outside the checkout.' >&2; exit 2;; esac
[[ ! -e $stage && ! -L $stage ]] || { echo 'Signing destination exists; use a new directory.' >&2; exit 2; }
[[ $(stat -c '%u:%a' "$keydir/module.key") == 0:600 ]] || { echo 'Key must be root-owned mode 0600.' >&2; exit 2; }
sign_file=/lib/modules/6.17.0-1032-nvidia/build/scripts/sign-file
[[ -x $sign_file ]]
(cd "$repo/build/unsigned" && sha256sum -c SHA256SUMS)
install -d -m 0700 -- "$stage"
for module in nvidia-guarded gb10_carveout_audit gb10_reclaim_probe gb10_reclaim_left gb10_reclaim_right; do
    install -m 0600 -- "$repo/build/unsigned/$module.ko" "$stage/$module.ko"
    "$sign_file" sha256 "$keydir/module.key" "$keydir/module.der" "$stage/$module.ko"
    modinfo -F signer "$stage/$module.ko"
done
(cd "$stage" && sha256sum ./*.ko > SHA256SUMS)
echo "Signed modules in $stage. Nothing loaded or installed into /lib/modules."
