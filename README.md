# Keryx Wallet (Desktop GUI)

A thin, safe desktop GUI for the Keryx wallet on Ubuntu 26.04. It drives the
audited `keryx-cli` interactive wallet as a subprocess — **all key handling,
signing, and transaction construction stay inside `keryx-cli`**. The GUI only
sends verified commands and displays results; it never touches a private key.

## Security model

- **Private keys never leave keryx-cli.** The GUI shells out to the CLI and
  parses its text output. There is no key material in the Python process.
- **Wallet creation always uses an explicit name.** The GUI never issues a bare
  `wallet create`, and if the CLI's overwrite warning ever appears it declines
  (`n`) and aborts. Existing wallets cannot be overwritten through the GUI.
- **Send is a two-step, point-of-no-return flow.** `keryx-cli send` broadcasts
  immediately after the password. The GUI therefore shows a confirmation dialog
  with destination, amount, fee, and total **before** collecting the password.
  Only after explicit confirmation is the password entered and the tx broadcast.
- Every CLI call has an explicit timeout and runs off the UI thread.

## Requirements

- Ubuntu 26.04
- Python 3.11+
- The `keryx-cli` binary, which **you provide** (see below)
- System Qt libraries for PyQt6

## Install

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip libgl1 libegl1 libxkbcommon0 \
    libdbus-1-3
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Providing keryx-cli (required)

This wallet is a **front-end** for the official `keryx-cli` binary. It does not
bundle or build keryx-cli — you supply it. This keeps the project pure
open-source Python with no redistributed third-party binaries.

The wallet finds keryx-cli in this order:

1. `--cli-path /full/path/to/keryx-cli` on launch
2. the `KERYX_CLI` environment variable
3. `keryx-cli` on your system `PATH`

If none is found, the wallet shows guidance and a "Locate keryx-cli…" file
picker so you can point at it.

### Getting keryx-cli

If you already run a Keryx node you likely already have it. Otherwise build it
from source:

```bash
git clone https://github.com/Keryx-Labs/keryx-node
cd keryx-node
cargo build --release --bin keryx-cli
# binary is then at: target/release/keryx-cli
```

Point the wallet at it, e.g.:

```bash
export KERYX_CLI="$PWD/target/release/keryx-cli"
# or: python3 run.py --cli-path "$PWD/target/release/keryx-cli"
```

## Build a single executable (recommended for distribution)

To produce one self-contained, double-clickable app, build on your Ubuntu 26.04
machine (the executable is OS/arch-specific and must be built where it runs):

```bash
cd keryx-wallet-gui
./build_executable.sh
```

This creates `dist/keryx-wallet` — a single file bundling the Python wallet and
its libraries. **keryx-cli is not bundled**; the executable still locates your
user-supplied keryx-cli at runtime via `PATH`, `$KERYX_CLI`, or `--cli-path`
(Option A is preserved).

Run it:

```bash
./dist/keryx-wallet
# or
./dist/keryx-wallet --cli-path /path/to/keryx-cli
```

### Install system-wide (optional)

```bash
sudo mkdir -p /opt/keryx-wallet
sudo cp dist/keryx-wallet /opt/keryx-wallet/
# optional icon:
# sudo cp assets/keryx.png /opt/keryx-wallet/
sudo cp keryx-wallet-installed.desktop /usr/share/applications/keryx-wallet.desktop
```

It then appears in your applications menu. For the menu launcher to find
keryx-cli, either put keryx-cli on PATH or add a line to the .desktop Exec, e.g.
`Exec=env KERYX_CLI=/path/to/keryx-cli /opt/keryx-wallet/keryx-wallet`.

## Run (from source, without building)

```bash
source .venv/bin/activate
python3 run.py
# or: python3 -m keryx_wallet
```

## Usage flow

1. **Connect** — enter your remote node wRPC URL and network, click Connect.
   (Connecting is required before balances or sending.)
2. **Open or create a wallet** — open with name + password, or create a new
   *named* wallet.
3. **Dashboard** — view accounts/balances, show a receive address (with QR),
   send (review dialog → password → broadcast), and load history.

## Status

All flows are wired to the verified `keryx-cli` command set and prompt sequences:
connect/server, wallet **create** (full flow with mnemonic backup), wallet
**open**, balances (`list`), receive (`address` + QR), **send** (review →
password → broadcast), and history.

### Create flow
`wallet create <name>` is driven end to end through its verified prompts
(account title → phishing hint → encryption password ×2 → optional BIP39
passphrase), then the mnemonic and deposit address are shown in a backup dialog
gated behind an explicit "I have written this down" acknowledgement. The phrase
is shown once and is never stored by the app.

## Appearance

The UI uses a dark "Keryx terminal" theme (phosphor-green on near-black,
monospace) matching the keryx-labs.com aesthetic. For the intended look, install
a good monospace font; the stack falls back to DejaVu/Ubuntu Mono which ship with
Ubuntu:

```bash
sudo apt install -y fonts-jetbrains-mono   # optional, best match
```

## Project layout

```
keryx_wallet/
  core/
    cli_driver.py   # keryx-cli subprocess manager (verified commands/prompts)
    worker.py       # off-thread execution for the UI
    qr.py           # receive-address QR
  ui/
    main_window.py  # screens: connect, wallet, dashboard
    send_dialog.py  # two-step safe send (review → password)
  __main__.py
run.py
requirements.txt
```
