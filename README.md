# 23rd October 2026 Update

There is now a firmware update that allows reducing the memory reservation to just 0.5GB.

Therefore I now recommend using that firmware feature over this repository, the
additional gain is only 500mb.

# GB10 RAM reclaim

An experimental, manually activated way to return the **2046 MiB display
reservation to ordinary Linux RAM** on a narrowly specified, headless ASUS GX10.
Existing malloc and CUDA allocations can then use that RAM without a special
application allocator.

The experiment succeeded on two GX10 systems. Each gained 2046 MiB in Linux
`MemTotal`, and CUDA exercised confirmed reclaimed physical pages. **This is
experimental kernel code, not a supported NVIDIA feature or a universal GB10
installer.** Returning physical pages to Linux can corrupt memory if another
owner still uses them. Read the support boundary and runbook before loading it.

## What this does

1. Identify the display reservation using NVIDIA RM metadata.
2. Load a signed, patched NVIDIA driver that rejects both reviewed display
   carveout allocation paths.
3. Check reserved-page state and normal page-table mappings, exercise the memory
   with CPU patterns, then release it to the normal Linux page allocator.
4. Pin the reclamation helpers and guarded driver until reboot, preventing normal
   unload from reintroducing the stock allocator over reclaimed RAM.
5. Validate ordinary RAM registration with CUDA and count reclaimed physical
   pages in the tested allocation.

**Nothing installs itself at boot. Reboot restores the installed stock driver
and original reservation.** Certificate enrollment persists but runs no code.
The tools do not disable Secure Boot, flash firmware, change GRUB, install DKMS,
modify initramfs, or create a startup service. No binaries, keys, certificates,
passwords, or machine logs are distributed.

## Reviewed configuration

| Component | Tested value |
| --- | --- |
| Hardware | ASUS GX10, NVIDIA GB10, headless |
| BIOS | `GX10DGX.0105.2026.0505.1153` |
| Kernel | Ubuntu `6.17.0-1032-nvidia`, source version `6.17.0-1032.32` |
| Architecture / pages | AArch64 / 4096 bytes |
| NVIDIA open driver | `580.173.02` |
| Display reservation | `[0x280200000, 0x300000000)` — 2046 MiB |
| Separate UEFI reservation | `[0x300000000, 0x303000000)` — untouched |

The compatibility tool refuses other configurations, including a changed BIOS,
kernel image/config, or memory layout. A different GB10 product or even a kernel
patch level needs a new source and hardware review. Passing compatibility alone
does not establish exclusive ownership or long-term safety.

## Start here

Run these on the target machine; they do **not** activate reclamation:

```sh
git clone https://github.com/jontaylor/gb10-ram-reclaim.git
cd gb10-ram-reclaim
make test
sudo python3 tools/preflight.py
```

Then follow these in order:

1. [Prerequisites, build, and manual runtime procedure](docs/runbook.md)
2. [Creating, enrolling, and using your own signing key](docs/signing.md)
3. [Validation, results, and limits](docs/validation.md)
4. [Recovery and troubleshooting](docs/recovery.md)

For implementation details, see [design and review notes](docs/design.md).
Do not activate the experiment automatically from boot scripts or unattended jobs.

## Results

| Test machine | Extra ordinary RAM | Reclaimed RAM actually exercised by CUDA |
| --- | ---: | ---: |
| GX10 A | 2046 MiB | 380 MiB |
| GX10 B | 2046 MiB | 998 MiB |

Every reclaimed byte passed CPU pattern tests. GPU coverage above was established
from `/proc/self/pagemap` **after** normal CUDA host registration. It is not a
claim that every reclaimed page received GPU testing. A separate ordinary
`cudaMalloc` fill/copyback check passed, but its physical backing was not counted.
No memory-bandwidth or long-duration stability claims are made.

## Attribution

**emihuang (emi), GitHub [coolbho3k](https://github.com/coolbho3k)**, published the
original discovery that headless GB10 display-reserved memory can be used by CUDA:
[original NVIDIA forum post](https://forums.developer.nvidia.com/t/383583/1) and
[original implementation](https://github.com/coolbho3k/DeepSeek-v4.1-Flash-2x-DGX-Spark/blob/878e0eecd893fadc69ad2d58b2df0fabb0fae2ee/release/runtime/sources/display_kv.c).
That work uses a DRM display-buffer allocation registered with CUDA, and supplied
the crucial clue for this project. This project takes a different, more invasive
approach: handing the region to Linux's ordinary allocator with a guarded driver.
The forum author did not author or endorse this kernel-reclamation approach.

**OpenAI Codex** developed the kernel investigation, driver guard, reclamation
helpers, validation tools, and initial documentation in collaboration with
**Jon Taylor**, who proposed the ordinary-RAM goal, supplied the hardware,
performed physical enrollment/recovery, and directed the experiment.

Thanks also to NVIDIA's open GPU kernel module project, Linux contributors, and
Ubuntu's kernel maintainers. See [NOTICE](NOTICE) for upstream licensing.
Original project code is licensed under [GPL-2.0-only](LICENSE), except the
NVIDIA patch additions, which follow the patched files' MIT license. No NVIDIA
or OpenAI endorsement or support commitment is implied.
