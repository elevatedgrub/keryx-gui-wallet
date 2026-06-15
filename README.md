# Keryx GUI Wallet

A graphical desktop wallet for the Keryx network. It drives the official
`keryx-cli` interactive wallet as a subprocess — **all key handling, signing,
and transaction construction stay inside `keryx-cli`**. The GUI only sends
verified commands and displays results; it never touches a private key.

## Requirements

- Python 3.10+
- The `keryx-cli` binary, which **you provide** (see below)
- System Qt libraries for PyQt6

## The node you connect to (important)

The wallet connects to a Keryx node over **wRPC/borsh on port 23110**. The node
**must be started with the borsh RPC listener enabled**, or the wallet cannot
connect:

```bash
keryxd --utxoindex --rpclisten-borsh=NODE_IP:23110
```

- `--rpclisten-borsh` is what exposes the wRPC endpoint the wallet speaks to.
- `--utxoindex` is required for wallet balance/UTXO queries.
- Replace `NODE_IP` with the node's reachable bind address (e.g. `0.0.0.0` to
  listen on all interfaces, or a specific IP). In the wallet's connection
  screen, enter that node's IP — keryx-cli applies the `ws://` scheme and
  `:23110` port automatically.

If you run a public node for others, make sure port `23110` is reachable.

## Providing keryx-cli

This wallet is a front-end for the official `keryx-cli` binary. It does not
bundle keryx-cli — you supply it. The wallet locates it in this order:

1. `--cli-path /full/path/to/keryx-cli` on launch
2. the `KERYX_CLI` environment variable
3. `keryx-cli` on your system `PATH`

Build keryx-cli from source if you don't already have it:

```bash
git clone https://github.com/Keryx-Labs/keryx-node
cd keryx-node
cargo build --release --bin keryx-cli
# binary: target/release/keryx-cli
```

## Install & run (from source)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 run.py
# or point at the CLI explicitly:
python3 run.py --cli-path /path/to/keryx-cli
```

## Build a single executable

To produce one self-contained app, build on the machine/OS where it will run
(the executable is OS/arch-specific):

```bash
./build_executable.sh
./dist/keryx-wallet
```

keryx-cli is still **not** bundled; the executable locates your user-supplied
keryx-cli at runtime via `--cli-path`, `$KERYX_CLI`, or `PATH`.

## Usage

1. **Connect** — choose the network and enter your node's IP, then Connect.
2. **Open, create, or import a wallet.**
3. **Dashboard** — view balance, receive (address + QR), send, consolidate
   UTXOs, and browse transaction history. The interface is available in several
   languages (switch via the button in the top-right corner).

## License

This project's own code is MIT-licensed. Note that PyQt6 is GPL v3 — distributing
a built binary that links PyQt6 carries GPL obligations. The source itself is
clean; if you distribute binaries and want a permissive path, PySide6 (LGPL) is
a drop-in alternative worth considering.
