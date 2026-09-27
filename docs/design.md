# Design and review notes

## Why normal RAM requires ownership changes

Firmware excludes a display region from Linux's normal memory map, and NVIDIA RM
also knows how to allocate from it. Merely overriding the Linux memory map can
create two allocators for the same physical pages. Headless operation alone does
not remove the driver's allocation capability.

The original forum technique allocates a DRM display buffer and registers its
mapping with CUDA using I/O-memory flags. It keeps that buffer under the display
allocator. This experiment instead prevents the reviewed driver allocation paths
from issuing display allocations, then gives the pages to the normal Linux buddy
allocator. Applications need no knowledge of the special region afterwards.

## Boundaries

The reviewed RM query reports:

| Type | Range, exclusive end | Size |
| --- | --- | ---: |
| DISPLAY_FRM / 0 | `[0x280200000, 0x300000000)` | 2046 MiB |
| UEFI / 2 | `[0x300000000, 0x303000000)` | 48 MiB |

A larger surrounding NOMAP reservation includes unrelated memory. Never turn
that entire reservation into RAM. The UEFI region includes firmware framebuffer
memory and is deliberately untouched. The modules contain fixed ranges; they do
not accept arbitrary physical addresses from a command line.

## Driver guard

The patch targets NVIDIA open driver commit
`20e4e6e19cc26ba47b5cbe23130a396be100c427` (tag `580.173.02`). Both
`memmgrAllocScanoutCarveoutRegionResources_GB10B` and
`memmgrAllocFromScanoutCarveoutRegion_GB10B` return `NV_ERR_NOT_SUPPORTED` before
allocating. Explicit carveout and ISO allocation probes verified both routes.

An exported `gb10_display_carveout_disabled()` marker is acquired via
`__symbol_get` before committing. The resulting module reference is retained,
and each helper calls `__module_get(THIS_MODULE)` before freeing pages. Normal
unloading cannot remove the helpers or replace the guarded driver during that
boot. This is an interlock against mistakes, not protection against malicious
root or force-unload. The marker is meaningful only with the reviewed patch.

This audit covers these driver allocation paths. It does not prove no firmware,
DMA engine, alternate driver version, suspend/resume path, or future display code
can ever touch the region. Keep the device headless, modeset/DRM unloaded, and
avoid suspend/hibernate, GPU reset, driver upgrades/reloads, concurrent memory
hotplug, and firmware changes while the experiment is active. Reboot first.

## Kernel ownership and mapping

These pages already have valid `struct page` entries inside online memory blocks.
Ordinary `add_memory` is unsuitable: it would overlap memory blocks already
present. On the reviewed kernel, present-page accounting already includes the
NOMAP range. Increasing `present_pages` again would double count it.

The helper checks the exact release string and 4 KiB page size, then each page's
validity, Reserved flag, reference count, and absence from kernel page tables.
A committing load additionally requires the driver marker. It then:

1. Creates ordinary cached `PAGE_KERNEL` direct mappings using the exact arm64
   mapping implementation and fixmap mutex. Flags `7` are the reviewed
   `NO_BLOCK_MAPPINGS | NO_CONT_MAPPINGS | NO_EXEC_MAPPINGS` combination.
2. Checks mapping presence and writes/verifies four address-dependent patterns,
   cleaning/invalidating to the point of coherency. Zeros the range afterwards.
3. Inserts an `IORESOURCE_SYSTEM_RAM | IORESOURCE_BUSY` resource. The exact
   kernel's resource walker descends nested resources, so the entry is usable
   beneath the existing reserved parent.
4. Clears `MEMBLOCK_NOMAP` and rechecks Reserved/refcount/ZONE_NORMAL/mapping.
5. Pins the helper, calls `free_reserved_page` for each page, and reports the
   exact `totalram_pages` change. That API updates managed-page and total-RAM
   accounting; there is no second manual increment.

Before commit, errors attempt to restore NOMAP/resource state and unmap. An error
or failed rollback still merits reboot and inspection; the error path is not a
substitute for physical recovery. After commit, pages can be in arbitrary process
or kernel use. There is intentionally no unload-based reverse operation.

The three files implement the same mechanism for 2 MiB, then two 1022 MiB ranges.
They remain separate to preserve the staged, hardware-tested path. The larger
helpers yield periodically during cache-maintenance loops. Mapping uses ordinary
page tables, so some memory is spent on mapping metadata: the MemTotal delta is
not a promise that application-available memory grows by exactly the same amount.

## Resolving unexported functions

The build-time ELF transformer converts only eight explicitly listed undefined
symbols into the kernel's livepatch symbol/relocation format:
`.klp.sym.vmlinux.NAME,0`, `SHN_LIVEPATCH`, and
`.klp.rela.vmlinux.SECTION` with livepatch/info-link/alloc flags. The module carries
`livepatch=Y`; the kernel loader resolves the names using its own symbol lookup.
This does not redirect functions with ftrace or use guessed numeric addresses.

This use of the loader's livepatch relocations is not an upstream-supported
memory-reclamation API. It relies on private implementation details, symbol
availability, signatures, and locking of this exact Ubuntu kernel. Out-of-tree
and livepatch taints are expected. A prior diagnostic attempt using an optimized-
away function name was rejected at load time; the released code uses the verified
constituent teardown functions instead.

The transformer refuses already signed input, missing/defined targets, malformed
ELF layouts tested by the suite, overwrite of existing destinations, and Python
optimization that would disable its assertions. It is a build tool for trusted
compiler output, not an adversarial ELF parser. Sign only after transformation.

## Exact source provenance

Reviewed Ubuntu source package: `linux-nvidia-6.17`, version `6.17.0-1032.32`.
Fetch its `.dsc`, base archive, and Debian/Ubuntu diff from the Ubuntu source
archive/Launchpad publication for that version, verifying their hashes against
the publication. No source archives are bundled here.

| Input | SHA-256 |
| --- | --- |
| `linux-nvidia-6.17_6.17.0.orig.tar.gz` | `a5623ec5af79da8807e1467e43a1888461c7a445fb1e17533fe45f0fdf4394e3` |
| Ubuntu source diff used | `5cb2514b976ad02d96dff81ce298f3e7feac6cebd11f66b17eb7a287e46805a5` |
| Installed kernel image | `04454e481d9082e07a975535f485b1bc205b75115bbf4c8b3f0518dc06a00e11` |
| Installed kernel config | `d7308f98799d0296b78f4f683794912385b028162712cd521f994af4f9cf7f3b` |

Review at least `arch/arm64/mm/mmu.c`, `mm/mm_init.c`, `mm/memblock.c`,
`mm/page_alloc.c`, `kernel/resource.c`, and `kernel/livepatch/core.c` after applying
the Ubuntu changes. Upstream Linux 6.17 alone is insufficient: Ubuntu changes the
mapping helper's return type from upstream void to int, among other differences.

The C helper checks release/page state; it does not hash its running kernel,
query BIOS, or fetch RM metadata itself. The external preflight and operator
checks are therefore required. There is no claim of portability after editing a
version string. Adding support means redoing the source/ownership review, then
reversible tests, small releases, and physical-page CUDA validation.

References:

- [Original forum discovery](https://forums.developer.nvidia.com/t/383583/1)
- [Pinned NVIDIA source](https://github.com/NVIDIA/open-gpu-kernel-modules/tree/20e4e6e19cc26ba47b5cbe23130a396be100c427)
- [Linux livepatch module ELF format](https://docs.kernel.org/livepatch/module-elf-format.html)
- [Ubuntu linux-nvidia-6.17 source publication](https://launchpad.net/ubuntu/+source/linux-nvidia-6.17/6.17.0-1032.32)
