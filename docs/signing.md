# Local signing and MOK enrollment

Secure Boot stayed enabled during the experiment. Root alone does not allow an
untrusted module to load when integrity lockdown is active. Create your own
module-only certificate, enroll its public half, and sign locally. Never use
someone else's private key or publish your own key, certificate, or signed modules.

## 1. Create a fresh key outside the checkout

From the repository, after inspecting `scripts/create-key.sh`:

```sh
sudo bash scripts/create-key.sh
```

The default directory is `/root/.local/share/gb10-ram-reclaim/keys` (0700). The
private key and DER certificate are root-owned 0600. The script refuses to
replace an existing directory or put the key inside the checkout. A custom
absolute directory outside the checkout may be passed as its first argument.

The RSA-3072 certificate uses SHA-256, digitalSignature, CA:FALSE, and shim's
module-only EKU `1.3.6.1.4.1.2312.16.1.2`. The private key is unencrypted so
`sign-file` can use it; root-only filesystem access protects it. Prefer an
encrypted offline key if your local signing policy requires one, adapting the
signing step yourself. Do not rely on certificate expiration as an activation
safeguard: kernel handling of certificate validity periods is not the guard here.

Record the displayed SHA-256 fingerprint **privately**, then inspect:

```sh
sudo openssl x509 -inform DER \
  -in /root/.local/share/gb10-ram-reclaim/keys/module.der -noout -text
```

The generic subject is `GB10 RAM Reclaim Local Module Key`. No key is shared
between users. The optional root test creates disposable keys under `/tmp`,
checks permissions/EKU/refusal to overwrite, and deletes them without enrollment:

```sh
sudo python3 -m unittest discover -s tests -p test_key_workflow.py -v
```

## 2. Enroll through the physical pre-boot screen

Ensure you can reach a monitor and keyboard or a tested remote KVM **before
rebooting**. SSH cannot operate shim's MOK screen. Firmware UART paths do not
establish an externally accessible serial console; none was validated here.

```sh
sudo mokutil --sb-state
sudo mokutil --import /root/.local/share/gb10-ram-reclaim/keys/module.der
sudo mokutil --list-new
```

`mokutil --import` asks you interactively to choose a temporary enrollment
password. Enter it directly; do not put it in shell history, scripts, issue
reports, or environment variables. If using SSH, allocate an interactive TTY.
Verify the pending certificate is the intended one. Cancel an unwanted pending
request with `sudo mokutil --revoke-import` before rebooting.

When the idle machine is ready:

```sh
sudo systemctl reboot
```

In MokManager choose **Enroll MOK → Continue → Yes**, enter your temporary
password, and reboot. Inspect the certificate identity/fingerprint where the
firmware UI permits. Menu wording can differ. Do not replace platform keys or
disable Secure Boot. Enrollment may permit other modules signed with that key;
protect the key accordingly.

After boot:

```sh
sudo mokutil --test-key /root/.local/share/gb10-ram-reclaim/keys/module.der
sudo mokutil --sb-state
sudo cat /sys/kernel/security/lockdown
nvidia-smi
```

The stock GPU must work before proceeding. A display attached during boot can
start a graphical session; stop it in the runtime procedure. The validated
machines were headless during reclamation.

## 3. Sign transformed modules

First complete `make build` as your ordinary user. The build transforms the
required ELF relocations **before signing**. Editing, stripping, or transforming
a signed `.ko` invalidates its signature.

```sh
sudo bash scripts/sign.sh
```

Defaults:

- Key directory: `/root/.local/share/gb10-ram-reclaim/keys`
- Signed module directory: `/root/.local/share/gb10-ram-reclaim/signed`

Pass those two paths as arguments to override them. The script refuses an
existing output directory, preventing accidental replacement of a reviewed
bundle. For another build, use a fresh output directory and adjust the runbook's
`stage` variable. It signs five explicit files, records checksums, and loads
nothing. A signer name from `modinfo` alone is not proof the kernel trusts it;
the read-only audit's successful load establishes that the loader accepted it.

## Removing trust later

A reboot rolls back reclamation but leaves the MOK enrolled. To remove this
specific trust entry after returning to stock, use `mokutil --delete` with your
local public certificate and complete the physical confirmation at reboot.
Keep the public certificate privately until that is done. Do not use broad
`--reset`, which would affect unrelated enrolled keys. Never remove a key or
force-unload a module as an attempted live-memory rollback.
