# Working on gb10-ram-reclaim

Read README.md and docs/design.md before changing kernel or driver code.
Run `make test` for host-side checks; these do not load kernel modules.
Use `make build` only on the documented target with its exact headers.
Keep activation an explicit manual operation. Never add boot services, initramfs
hooks, DKMS installation, unattended enrollment, automatic reboots, or broad
memory-range autodetection. Reboot is the rollback after pages are released.
Do not load modules or disrupt devices as part of ordinary repository work.
Preserve the guarded-driver reference and all kernel/page/range/expiry checks.
Keep certificates, keys, credentials, signed modules, raw machine logs, network
addresses and machine identifiers out of Git. Use synthetic test fixtures and
sanitized evidence. Do not claim a host-side test proves hardware safety.
