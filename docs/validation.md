# Validation and evidence boundaries

## Host-side checks

```sh
make test
sudo python3 -m unittest discover -s tests -p test_key_workflow.py -v
python3 tools/check_public_tree.py
```

The host suite uses synthetic ELF fixtures to verify relocation splitting,
unchanged ordinary relocations/addends, symbol renaming/index preservation,
and refusal of signed, truncated, already-transformed, wrong-architecture,
missing/defined-symbol inputs and file overwrites. It also verifies that
compatibility fails closed for unknown hardware/software, changed ranges,
large pages, extra/missing regions, and already-loaded reclamation helpers.

The optional root test generates a disposable module-only key outside the
checkout, checks permissions and EKU, and verifies overwrite/path refusals.
It never imports a MOK, loads code, or touches a GPU. GitHub CI runs these checks
on ordinary Ubuntu runners; it cannot certify kernel or hardware safety.

## Native package verification

The initial public package was built from a fresh pinned NVIDIA checkout on the
reviewed AArch64 target. All four helper modules, the guarded driver, the RM probe,
and CUDA test compiled. The transformed release modules each contained 15
livepatch relocations for the eight reviewed symbols. Their transformed bytes
matched the original experiment transformer on the same native build inputs.
The packaged preflight was also checked on an already-reclaimed machine and
refused replay for that reason, with all other compatibility fields matching. The kernel C release code
is the mechanism exercised in the original two-machine experiment; packaging
adds preflight, reproducible builds, signing helpers, tests, and documentation.

All five native modules were also signed with a disposable, module-only key;
signer metadata and refusal to overwrite the bundle were checked. That key was
not enrolled, and the temporary key/signing output was removed.

Freshly packaged binaries were not reloaded into the already-reclaimed machines.
Reclaiming the same region twice would be wrong. A compilation or signature test
is not another hardware activation pass.

## Hardware observations from 2026-09-27

| Observation | GX10 A | GX10 B |
| --- | ---: | ---: |
| Baseline MemTotal (KiB) | 127535016 | 127535336 |
| After 2 MiB (KiB) | 127537064 | 127537384 |
| After next 1022 MiB (KiB) | 128583592 | 128583912 |
| Final MemTotal (KiB) | 129630120 | 129630440 |
| Total added (MiB) | 2046 | 2046 |
| CUDA-reported total (bytes) | 132741242880 | 132741570560 |
| Reclaimed pages in 1 GiB pinned allocation | 97280 | 255488 |
| Reclaimed CUDA coverage (MiB) | 380 | 998 |

Both machines passed the read-only page audit, reversible mapping test, all four
CPU pattern passes across the released ranges, explicit/ISO guard checks, normal
pinned-memory GPU writes/CPU verification, and ordinary cudaMalloc fill/copyback.
No new kernel faults or Xids appeared in the successful runs. GX10 B first needed
a cold power cycle for a stock-driver firmware startup failure after enrollment;
that failure preceded reclamation and is documented in recovery.md.

These are sanitized observations, not raw logs. Raw logs, hostnames, addresses,
boot identifiers, certificates, private keys, and signing artifacts are excluded.

## Proving reclaimed-page GPU coverage

The CUDA test uses normal `posix_memalign`, faults pages, calls
`cudaHostRegisterMapped`, and then reads `/proc/self/pagemap` as root. It counts
physical pages inside the precise display interval while the allocation is
pinned. The GPU XORs every 64-bit word; the CPU verifies every result. It also
performs a separate normal 64 MiB cudaMalloc GPU-fill/copyback test.

Run manually after successful reclamation:

```sh
sudo ./build/cuda_coverage 1024
```

Expected output includes `display_pool_pages` greater than zero and PASS.
`reclaimed_test_pages` counts only the original tiny 2 MiB center range; it may
be zero even with extensive reclaimed-pool coverage.

| Exit code | Meaning |
| --- | --- |
| 0 | Correctness checks passed and reclaimed-page coverage was nonzero |
| 1 | Host allocation, argument, or pagemap failure |
| 2 | CUDA API or kernel failure |
| 3 | GPU-written pinned RAM mismatch |
| 4 | cudaMalloc/copyback mismatch |
| 5 | Correctness passed, but zero reclaimed-page coverage |

A zero-coverage run is inconclusive for the reclaimed pages, not a hardware pass.
If plenty of memory is free, try a bounded larger allocation, such as 4096 MiB.
The accepted allocation range is 64–16384 MiB, but the operator must check free
memory and workload state; the test does not reserve headroom or prevent OOM.
Do not exhaust RAM to force coverage. Stop if any data mismatch, Xid, kernel
fault, or firmware error appears.

## What is not established

No long-term burn-in, suspend/resume, GPU reset, memory hotplug, firmware-update,
production inference, bandwidth, or arbitrary-kernel validation is claimed.
CPU testing covered the whole region; GPU testing covered the physical pages
listed above. cudaMalloc's physical pages were not independently inspected.
The observed guard covers reviewed driver allocation paths, not a proof that
firmware or every possible DMA client has relinquished the memory forever.
