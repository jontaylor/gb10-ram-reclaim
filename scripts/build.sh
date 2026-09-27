#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build="$repo/build"
kernel=6.17.0-1032-nvidia
commit=20e4e6e19cc26ba47b5cbe23130a396be100c427
if [[ $(uname -m) != aarch64 || $(uname -r) != "$kernel" ]]; then
    echo "Build only on aarch64 running $kernel with matching headers." >&2; exit 2
fi
if [[ $EUID == 0 ]]; then echo 'Build as an ordinary user, not root.' >&2; exit 2; fi
[[ -d /lib/modules/$kernel/build ]]
for tool in git make gcc-13 python3; do command -v "$tool" >/dev/null; done
mkdir -p "$build/unsigned" "$build/modules"
if [[ ! -d "$build/driver" ]]; then
    git clone --depth 1 --branch 580.173.02 https://github.com/NVIDIA/open-gpu-kernel-modules.git "$build/driver"
fi
[[ $(git -C "$build/driver" rev-parse HEAD) == "$commit" ]] || { echo 'Wrong driver source revision' >&2; exit 2; }
# Refuse modified sources; retain the build for inspection instead of overwriting it.
if git -C "$build/driver" diff --quiet; then
    git -C "$build/driver" apply --check "$repo/patches/nvidia-580.173.02-headless-guard.patch"
    git -C "$build/driver" apply "$repo/patches/nvidia-580.173.02-headless-guard.patch"
fi
git -C "$build/driver" diff --binary > "$build/driver.diff"
cmp "$build/driver.diff" "$repo/patches/nvidia-580.173.02-headless-guard.patch"
make -C "$build/driver" -j"${JOBS:-4}" modules CC=gcc-13
cp "$build/driver/kernel-open/nvidia.ko" "$build/unsigned/nvidia-guarded.ko"
symbols=(init_mm fixmap_lock pgd_pgtable_alloc_init_mm __create_pgd_mapping_locked
         unmap_hotplug_range free_empty_tables memblock_clear_nomap memblock_mark_nomap)
for pair in audit:gb10_carveout_audit reclaim-probe:gb10_reclaim_probe reclaim-left:gb10_reclaim_left reclaim-right:gb10_reclaim_right; do
    directory=${pair%%:*}; module=${pair#*:}
    mkdir -p "$build/modules/$directory"
    cp "$repo/modules/$directory/"*.c "$repo/modules/$directory/Makefile" "$build/modules/$directory/"
    make -C "$build/modules/$directory" CC=gcc-13
    if [[ $directory == audit ]]; then
        cp "$build/modules/$directory/$module.ko" "$build/unsigned/$module.ko"
    else
        # Transformer refuses overwrites: remove only this known generated output.
        rm -f -- "$build/unsigned/$module.ko"
        python3 "$repo/tools/klp_relocate.py" "$build/modules/$directory/$module.ko" "$build/unsigned/$module.ko" "${symbols[@]}"
    fi
done
gcc-13 -O2 -Wall -Wextra -I"$build/driver/src/common/sdk/nvidia/inc" \
    "$repo/tools/allocation_probe.c" -o "$build/allocation_probe"
nvcc=${NVCC:-/usr/local/cuda/bin/nvcc}
"$nvcc" -O2 -arch=sm_121 "$repo/tests/cuda_coverage.cu" -o "$build/cuda_coverage"
(cd "$build/unsigned" && sha256sum ./*.ko > SHA256SUMS)
echo 'Build complete. Nothing installed, signed, enrolled, or loaded.'
