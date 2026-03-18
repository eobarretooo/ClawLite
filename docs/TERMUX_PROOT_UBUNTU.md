# Termux + proot-distro Ubuntu

This is the recommended Android path when you want the full Linux runtime instead of native Termux packages.

## 1. Start from Termux

Install the Termux-side prerequisites:

```bash
pkg update
pkg install -y proot-distro git curl
```

Important:

- Use the F-Droid or GitHub build of Termux, not the Play Store build.
- This guide assumes you want to run ClawLite inside an Ubuntu rootfs managed by `proot-distro`.

## 2. Bootstrap Ubuntu and ClawLite

Run the wrapper installer from Termux:

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install_termux_proot.sh | bash
```

What it does:

- installs `ubuntu` with `proot-distro` if needed
- installs `git`, `curl`, `python3`, `python3-venv`, and `build-essential` inside Ubuntu
- clones or updates `ClawLite` under `/root/ClawLite`
- if the existing checkout diverged from `origin/main`, it preserves that tree as `/root/ClawLite.backup.<timestamp>` and reclones cleanly
- runs `scripts/install.sh` inside Ubuntu

The wrapper now downloads the latest repository sync helper directly from GitHub before updating the checkout. That means even an older local copy of `install_termux_proot.sh` can recover from the historical `git pull --ff-only` failure mode as long as you rerun the one-shot `curl ... | bash` command from Termux.

## 3. Enter Ubuntu and configure

```bash
proot-distro login ubuntu --shared-tmp
clawlite configure --flow quickstart
clawlite gateway
```

If `clawlite` is not on `PATH` in the first shell, reload the profile once:

```bash
source ~/.profile
```

## 4. Optional extras

Inside Ubuntu:

```bash
python3 -m pip install -e "/root/ClawLite[browser,telegram,media]"
python3 -m playwright install chromium
```

## Troubleshooting

- If `python3 -m venv` fails, install `python3-venv` inside Ubuntu and rerun the installer.
- If Playwright is not needed, skip the browser extra and the Chromium download.
- If you see `fatal: Not possible to fast-forward, aborting.`, rerun the remote wrapper from Termux instead of an old local copy:

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install_termux_proot.sh | bash
```

- If you need a manual recovery inside Ubuntu, use the same sync helper directly:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/update_checkout.sh) \
  https://github.com/eobarretooo/ClawLite.git \
  /root/ClawLite \
  main
```
- If you want to rerun the Ubuntu-side installer manually, use:

```bash
proot-distro login ubuntu --shared-tmp -- /bin/bash -lc 'cd /root/ClawLite && bash scripts/install.sh'
```
