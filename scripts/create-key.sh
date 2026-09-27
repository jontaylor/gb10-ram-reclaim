#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Creates a fresh local module-only key; never enrolls it or changes boot settings.
set -euo pipefail
umask 077
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
keydir=${1:-/root/.local/share/gb10-ram-reclaim/keys}
[[ $EUID == 0 ]] || { echo 'Run as root so the key stays root-only.' >&2; exit 2; }
[[ $keydir == /* ]] || { echo 'Use an absolute key directory outside the checkout.' >&2; exit 2; }
keydir=$(realpath -m -- "$keydir")
case "$keydir/" in "$repo/"*) echo 'Key directory must be outside the checkout.' >&2; exit 2;; esac
# Refuse existing directories, including symlinks. Do not overwrite a trusted key.
[[ ! -e $keydir && ! -L $keydir ]] || { echo 'Key directory already exists; refusing overwrite.' >&2; exit 2; }
install -d -m 0700 -- "$keydir"
openssl req -new -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
    -subj '/CN=GB10 RAM Reclaim Local Module Key/' \
    -addext 'basicConstraints=critical,CA:FALSE' \
    -addext 'keyUsage=critical,digitalSignature' \
    -addext 'extendedKeyUsage=1.3.6.1.4.1.2312.16.1.2' \
    -keyout "$keydir/module.key" -outform DER -out "$keydir/module.der"
chmod 0600 "$keydir/module.key" "$keydir/module.der"
openssl x509 -inform DER -in "$keydir/module.der" -noout -subject -fingerprint -sha256
echo "Created root-only key in $keydir. Review docs/signing.md before enrollment."
