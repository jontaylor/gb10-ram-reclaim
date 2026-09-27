# Recovery and troubleshooting

## After any successful release: reboot

```sh
sudo systemctl reboot
```

The installed stock driver, original reservation, and original boot configuration
remain in place. Reboot discards experimental mappings, allocator changes,
loaded modules, and temporary `/run` masks/autoload overrides. The extra RAM goes
away. The enrolled signing certificate and local build files persist but execute
nothing. Do not use force-rmmod, restore a stock NVIDIA module live, free the same
pages again, or start a display session while the experiment is active.

If SSH is gone, use the physical console/power controls to recover. As with any
kernel experiment, a crash can lose unsaved data. No startup hook will repeat the
experiment on the next boot. An expires timestamp gates a single module load;
it is not a timer that reverses the release.

## Before commit

The audit changes no memory. A successful `map_test=1` maps/tests/unmaps without
releasing pages. If the reversible test fails, or NOMAP/resource rollback reports
an error, stop and reboot. Do not infer that all state was repaired merely because
insmod failed. If only services were stopped/masked, their original active-state
record is in `/run/gb10-ram-reclaim/previously-active-services`; reboot also clears
those temporary overrides.

## Key rejected / unknown symbols

- `Key was rejected by service`: verify the intended public certificate is
  enrolled, its key matches the signature, and transformation happened before
  signing. Do not disable Secure Boot to work around it.
- `Unknown symbol`, livepatch lookup failure, or incompatible vermagic: stop.
  Confirm the exact kernel/driver/source versions. Do not substitute addresses
  from `/proc/kallsyms` or remove guards to make a module load.
- Busy NVIDIA module: inspect consumers using `fuser`. Check GUI sessions,
  persistence, metrics agents, containers, and CDI refresh. Never force unload.
- A reclaim module with a nonzero pinned reference after commit is intentional.
  Reboot, rather than trying to remove it.

## SEC2/GSP timeout after enrollment or a warm reboot

One tested GX10, with **stock NVIDIA modules and before any memory write/release**,
reported `SEC2 secure boot partition timed out`, `Cannot initialize GSP firmware
RM`, and `RmInitAdapter failed`. A normal stock-driver unload/reload did not fix
it. A clean shutdown, roughly 20 seconds with power physically disconnected,
and a headless cold boot restored normal GPU operation. The cause was not proven.

Do not proceed with reclamation while the stock GPU cannot initialize. Save logs
privately, shut down cleanly, then power-cycle if appropriate for your machine.
Recheck `nvidia-smi` and preflight after recovery. If the fault persists, investigate
the stock platform first. This observation is not a reason to flash firmware or
change its security settings.

## No monitor output / unexpectedly long boot

A headless Linux configuration may have no desktop output even with a working
firmware console. MOK enrollment is a pre-boot operation. A tested physical
monitor/keyboard or remote KVM is needed; SSH cannot drive that screen. Serial
console access was not validated.

One machine's firmware tried PXE before the Ubuntu boot entry, adding a timeout.
That order was observed, not changed by this project. Wait for the normal boot
sequence rather than assuming the kernel failed. If HDMI remains attached, a
graphical session may start after boot; stop both applicable display-manager
units and verify remaining device users before experimentation.

## Reporting problems

Report the public hardware/BIOS/kernel/driver versions, stage, exact error, and
sanitized memory totals. Review logs before sharing: remove addresses, serials,
boot IDs, machine/user names, local paths, and unrelated workload information.
Never attach private keys, certificates, enrollment passwords, tokens, entire
home directories, or signed modules. Prefer a small redacted excerpt.
