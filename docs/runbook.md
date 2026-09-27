# Manual runtime procedure

This procedure modifies the running kernel on an **idle, headless, explicitly
supported target**. Read the design and recovery documents first. A bad ownership
assumption can corrupt unrelated allocations after release. Have SSH and a
physical recovery path. Do not use a production workload as the first test.

Commands run locally on the target. Each phase is a checkpoint: stop on any
unexpected result. Do not paste the entire document into a shell. There is no
one-command activation or boot installer.

## 1. Inspect and build as an ordinary user

Prerequisites: the exact supported kernel and firmware, Ubuntu headers for that
kernel, NVIDIA 580.173.02 user space/open driver, CUDA 13 with `nvcc` supporting
`sm_121`, GCC 13, make, binutils, git, Python 3, OpenSSL, mokutil, and psmisc.
For the reviewed Ubuntu image, missing host build dependencies can be installed
with the following; review the package transaction before accepting it:

```sh
sudo apt-get install build-essential gcc-13 binutils git python3 openssl mokutil \
  psmisc linux-headers-$(uname -r)
```

Use the vendor-provided CUDA installation matching the tested system; this
repository does not install CUDA, firmware, or a different kernel.

```sh
make test
sudo python3 tools/preflight.py
make build
```

Preflight checks the exact kernel image/config hashes, hardware/BIOS, driver,
4 KiB pages, RM regions, and absence of reclamation helpers. It refuses replay on
an already-reclaimed boot. It does not stop workloads or prove page ownership. Its NVIDIA queries can
initialize the GPU or trigger normal installed-driver autoload; run it with the
working stock driver before stopping consumers.

The build clones public NVIDIA tag `580.173.02`, verifies commit
`20e4e6e19cc26ba47b5cbe23130a396be100c427`, applies only the supplied guard patch,
and builds in ignored `build/`. It refuses a different tracked source diff.
`JOBS=2 make build` limits build parallelism. `NVCC=/path/to/nvcc` overrides the
compiler location. It does not run `modules_install`, `depmod`, or load anything.

The three reclaim modules intentionally reference eight unexported kernel symbols.
`modpost` warnings for these exact names precede the ELF livepatch transformation:
`init_mm`, `fixmap_lock`, `pgd_pgtable_alloc_init_mm`,
`__create_pgd_mapping_locked`, `unmap_hotplug_range`, `free_empty_tables`,
`memblock_clear_nomap`, `memblock_mark_nomap`. Investigate any other unresolved
symbol. BTF skipping without a local vmlinux is expected on this image.

## 2. Create/enroll a local key, then sign

Follow [signing.md](signing.md). The MOK step requires a physical boot-time action.
After enrollment, verify `nvidia-smi` works with stock modules. Do not proceed
through GSP/SEC2 initialization errors; see [recovery](recovery.md).

If a monitor was connected for enrollment, disconnect it before the experiment.
Return to this repository and rerun preflight on the new boot.

## 3. Establish baseline and audit the pages

For the following commands, enter a root shell **from the repository directory**:

```sh
sudo -s
repo=$PWD
stage=/root/.local/share/gb10-ram-reclaim/signed
run=/run/gb10-ram-reclaim
mkdir -m 0700 "$run"
mkdir -p "$repo/build/run"
cat /proc/meminfo > "$repo/build/run/meminfo-before.txt"
dmesg > "$repo/build/run/dmesg-before.txt"
python3 "$repo/tools/preflight.py"
(cd "$stage" && sha256sum -c SHA256SUMS)
insmod "$stage/gb10_carveout_audit.ko" acknowledge_read_only=1
dmesg | tail -10
rmmod gb10_carveout_audit
```

If `/run/gb10-ram-reclaim` already exists, investigate the earlier attempt instead
of overwriting its state. Expected audit: 523776 valid/reserved/ref1/ZONE_NORMAL
pages, zero invalid/mapped/other-reference pages. This module does not read or
write the reserved physical memory.

Check ordinary stock allocation behavior (temporary 64 KiB allocations, no mapping):

```sh
"$repo/build/allocation_probe"
"$repo/build/allocation_probe" iso
```

Both should print `status=0x0`. The probe's process exit code reports transport
success; **inspect the printed RM status**, which is what this comparison tests.

## 4. Stop consumers and block display autoload for this boot

Stop inference services/containers, GPU tools, graphical sessions, and monitoring
agents that open NVIDIA devices. Record which local services you stopped so they
can be restored; their names vary. `nvidia-smi` showing no compute process does
not rule out display/monitoring consumers. On the tested image:

```sh
for unit in gdm.service gdm3.service nvidia-persistenced.service \
  dgx-dashboard.service dgx-dashboard-admin.service \
  nvidia-cdi-refresh.path nvidia-cdi-refresh.service; do
  if systemctl is-active --quiet "$unit"; then printf '%s\n' "$unit"; fi
done > "$run/previously-active-services"
systemctl stop gdm.service gdm3.service nvidia-persistenced.service \
  dgx-dashboard.service dgx-dashboard-admin.service \
  nvidia-cdi-refresh.path nvidia-cdi-refresh.service
systemctl mask --runtime gdm.service gdm3.service nvidia-persistenced.service \
  dgx-dashboard.service dgx-dashboard-admin.service \
  nvidia-cdi-refresh.path nvidia-cdi-refresh.service
install -d /run/modprobe.d
cat > /run/modprobe.d/gb10-reclaim-test.conf <<'CONF'
install nvidia /bin/false
install nvidia_drm /bin/false
install nvidia_modeset /bin/false
CONF
fuser -v /dev/nvidia*
```

A service missing on your image is not permission to ignore another failure.
Resolve remaining device users before continuing. Watch both `gdm` and `gdm3`:
masking one alias alone was insufficient in one observed boot. `/run` overrides
are temporary. Do not put these files in `/etc` or change the boot target.

Unload dependent modules in order; never force unload:

```sh
for module in nvidia_drm nvidia_modeset nvidia_uvm nvidia; do
  if test -d "/sys/module/$module"; then rmmod "$module" || break; fi
done
lsmod | grep nvidia
```

**All four must be absent.** A busy module is a stop condition. Keep the autoload
block in place. Do not run GPU tools during the next reversible test.

## 5. Reversible 2 MiB mapping test

```sh
insmod "$stage/gb10_reclaim_probe.ko" map_test=1 expires=$(($(date +%s)+60))
dmesg | tail -5
rmmod gb10_reclaim_probe
```

Expected: `direct-map test result=0; pages remain reserved`. This maps, exercises,
zeros, and unmaps 2 MiB. It releases no pages. Stop on anything else.

## 6. Load and verify the guarded driver

```sh
insmod "$stage/nvidia-guarded.ko"
nvidia-smi
"$repo/build/allocation_probe"
"$repo/build/allocation_probe" iso
```

Both allocation routes must now print **`status=0x56`** (`NV_ERR_NOT_SUPPORTED`).
If either succeeds, stop: memory must not be handed to Linux with that driver.
These intentional rejections generate expected NOT_SUPPORTED kernel messages.

CUDA tools may already have autoloaded UVM. Load it only if absent:

```sh
if ! test -d /sys/module/nvidia_uvm; then insmod "$(modinfo -n nvidia_uvm)"; fi
```

Inspect each range without writing or releasing:

```sh
for module in gb10_reclaim_probe gb10_reclaim_left gb10_reclaim_right; do
  insmod "$stage/$module.ko" expires=$(($(date +%s)+60)) || break
  rmmod "$module" || break
done
dmesg | tail -10
```

Expected: each range passes kernel-page-table inspection and is still reserved.

## 7. Release incrementally — irreversible until reboot

The following three commands are **separate decisions**. Each checks page state,
creates normal mappings, runs four CPU pattern passes, and only then releases
pages. Check the log and exact `MemTotal` delta after each. No timeout or failure
of your SSH client undoes a successful release. Do not retry a partially completed
sequence blindly; consult `lsmod`, the logs, and `/proc/iomem` or reboot.

First 2 MiB:

```sh
insmod "$stage/gb10_reclaim_probe.ko" gb10_commit=1 expires=$(($(date +%s)+60))
dmesg | tail -3
head -3 /proc/meminfo
nvidia-smi
```

Expected: 512 pages released; `MemTotal` grows by 2048 KiB.

Next 1022 MiB:

```sh
insmod "$stage/gb10_reclaim_left.ko" gb10_commit=1 expires=$(($(date +%s)+60))
dmesg | tail -3
head -3 /proc/meminfo
nvidia-smi
```

Expected: 261632 pages released; another 1046528 KiB.

Final 1022 MiB:

```sh
insmod "$stage/gb10_reclaim_right.ko" gb10_commit=1 expires=$(($(date +%s)+60))
dmesg | tail -3
head -3 /proc/meminfo
nvidia-smi
```

Expected: another 261632 pages; cumulative **2095104 KiB = 2046 MiB**.
Each helper pins itself and the guarded driver. Do not run rmmod on them.
The deadline is checked at initialization; it does not revoke released memory.

## 8. Validate and restore non-display services

```sh
"$repo/build/cuda_coverage" 1024
cat /proc/meminfo > "$repo/build/run/meminfo-after.txt"
cat /proc/iomem > "$repo/build/run/iomem-after.txt"
dmesg > "$repo/build/run/dmesg-after.txt"
```

Require a successful GPU/CPU comparison **and** nonzero `display_pool_pages`.
Exit 5 means correctness passed but the allocation missed reclaimed pages. See
[validation.md](validation.md) for interpreting results or increasing the bounded
allocation. Any new Xid, oops, firmware timeout, or data mismatch is a stop
condition: save logs privately and reboot to stock.

Keep gdm/gdm3 masked and modeset/DRM unloaded for the rest of this boot. Unmask
only the non-display services masked above, then restart only those previously
active. For example:

```sh
systemctl unmask --runtime nvidia-persistenced.service dgx-dashboard.service \
  dgx-dashboard-admin.service nvidia-cdi-refresh.path nvidia-cdi-refresh.service
while IFS= read -r unit; do
  case "$unit" in gdm.service|gdm3.service) continue;; esac
  systemctl start "$unit"
done < "$run/previously-active-services"
```

Restore any additional monitoring you stopped and verify it. Keep the module
loader overrides until reboot. Do not restore display sessions or replace the
pinned guard. Validate your own applications separately before relying on this
experiment. Exit the root shell when finished.
