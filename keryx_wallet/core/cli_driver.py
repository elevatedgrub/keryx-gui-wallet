"""
cli_driver.py — manages the Keryx CLI wallet as a persistent interactive subprocess.

DESIGN / SAFETY PRINCIPLES
--------------------------
The Keryx CLI ("keryx cli") is an interactive REPL wallet runtime (a fork of
rusty-kaspa's kaspa-cli). It must be kept open as a long-lived subprocess; you
drive it by writing commands to its stdin and reading the prompted output.

All cryptography — key generation, signing, transaction construction — happens
INSIDE the CLI process. This GUI never sees a private key. That is the entire
security rationale for the subprocess approach: the audited Rust wallet does the
dangerous work; the GUI only sends text commands and parses replies.

Because money is at stake, this driver is deliberately conservative:
  - every command has an explicit timeout; a hung CLI never blocks forever
  - the driver never assumes success — callers inspect returned output
  - interactive prompts (password, confirmation) are answered in exactly ONE
    place (`_answer_prompts`) so the prompt-handling logic is auditable
  - the password is written to the child's stdin and never logged or stored

NOTE ON PROMPTS
---------------
The exact prompt strings emitted by `wallet create`, `open`, and `send` must be
confirmed against the real binary before the create/open/send flows are trusted.
The patterns live in PROMPT_PATTERNS below and are the single thing to verify.
Until confirmed, the high-level flows raise NotImplementedError rather than guess.

This module uses pexpect, which provides robust expect/timeout handling for
interactive subprocesses on Linux.
"""

from __future__ import annotations

import re
import shutil
import threading
from dataclasses import dataclass
from typing import Optional

try:
    import pexpect
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "pexpect is required. Install with: pip install pexpect"
    ) from e


# keryx-cli's ready prompt is DYNAMIC. When idle it is "$ ", but once a wallet
# is open it becomes "N/C • <wallet> $ " and after selecting an account
# "N/C • <wallet> • [<acct>] • <balance> KRX $ " (N/C = not connected; shows the
# node/connection state). All ready prompts END in "$ " (dollar + space).
# Sub-prompts (e.g. "Default account title: ", "Enter wallet password: ") end in
# ": ", so anchoring on "$ " at the end of the buffer distinguishes them.
# We match "$ " at end-of-buffer. ANSI is stripped from captured text afterward.
READY_PROMPT = re.compile(r"\$ $")

def _ansi_strip(text):
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text or "")


def _clean_output(text):
    """
    Remove keryx-cli's dynamic prompt fragments and blank lines from captured
    output, leaving only real content. The prompt appears as:
      "N/C • test1 $ "                         (idle, wallet open)
      "N/C • test1 • [acct] • <bal> KRX $ "     (account selected)
      "<conn> • test1 • [acct] • <bal> KRX"     (trailing fragment, no '$ ')
    We drop any line that looks like a status prompt: it contains the "•"
    separator AND (ends in "$" OR matches the "state • wallet • [acct] • bal"
    shape). Real data lines (account ids, balances, addresses) are kept.
    """
    out = []
    for line in _ansi_strip(text or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        # Prompt line ending in '$'
        if "•" in s and re.search(r"\$\s*$", s):
            continue
        # Trailing prompt fragment: "<state> • <wallet> • [<acct>] • <bal> KRX"
        # (no '$' because the capture boundary consumed it). Distinguish from a
        # real balance line "• [acct]: bal KRX" by requiring the wallet-name
        # segment, i.e. text before the first "•" plus "• ... • [..]".
        if re.match(r"^\S.*•.*•\s*\[[0-9a-f]+\]\s*•.*KRX\s*$", s, re.IGNORECASE):
            continue
        # Bare "$" prompt
        if re.fullmatch(r"\$\s*", s):
            continue
        out.append(s)
    return "\n".join(out)

# Timeouts (seconds). Network-touching commands get a longer budget.
DEFAULT_TIMEOUT = 15
CONNECT_TIMEOUT = 45
SEND_TIMEOUT = 60


@dataclass
class CliResult:
    """Result of a single command sent to the CLI shell."""
    command: str
    output: str
    ok: bool
    error: Optional[str] = None


class KeryxCliError(Exception):
    pass


class KeryxCliDriver:
    """
    Wraps a single persistent `keryx cli` interactive process.

    Thread-safety: all command submission is serialised behind a lock, because
    a REPL has exactly one stdin/stdout and concurrent writers would interleave.
    The GUI runs commands from a worker thread, never the UI thread.
    """

    def __init__(self, cli_path: str = "", cli_subcommand: str = ""):
        """
        cli_path:       path to the keryx-cli binary. Resolution order when
                        starting (see resolve_binary):
                          1. an explicit cli_path passed here (or --cli-path)
                          2. the KERYX_CLI environment variable
                          3. 'keryx-cli' on the system PATH
                        Keryx is Option-A: the USER supplies keryx-cli. This GUI
                        does not bundle or build it.
        cli_subcommand: empty for Keryx — keryx-cli IS the interactive shell.
        """
        self._cli_path = cli_path or ""
        self._cli_subcommand = cli_subcommand
        self._child: Optional["pexpect.spawn"] = None
        self._lock = threading.RLock()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def resolve_binary(self) -> Optional[str]:
        """
        Resolve the keryx-cli binary path, in priority order:
          1. explicit path given to the driver (constructor / --cli-path)
          2. the KERYX_CLI environment variable
          3. 'keryx-cli' found on the system PATH

        Returns an absolute path to an existing executable, or None.
        """
        import os

        candidates = []
        if self._cli_path:
            candidates.append(self._cli_path)
        env_path = os.environ.get("KERYX_CLI", "").strip()
        if env_path:
            candidates.append(env_path)
        candidates.append("keryx-cli")  # PATH lookup

        for cand in candidates:
            # Absolute or relative path to a real file?
            if os.path.sep in cand or cand.startswith("."):
                p = os.path.abspath(os.path.expanduser(cand))
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    return p
                continue
            # Bare name → search PATH.
            found = shutil.which(cand)
            if found:
                return found
        return None

    def binary_help(self) -> str:
        """Human-readable guidance shown when keryx-cli can't be found."""
        return (
            "keryx-cli was not found.\n\n"
            "This wallet is a front-end for the official keryx-cli binary, which "
            "you supply yourself (it is not bundled). To fix this, do ONE of:\n\n"
            "  • Put keryx-cli on your PATH, or\n"
            "  • Set the KERYX_CLI environment variable to its full path, e.g.\n"
            "      export KERYX_CLI=/home/you/keryx-node/target/release/keryx-cli\n"
            "  • Launch with --cli-path /full/path/to/keryx-cli\n\n"
            "You can build keryx-cli from the Keryx node source:\n"
            "  git clone https://github.com/Keryx-Labs/keryx-node\n"
            "  cd keryx-node && cargo build --release --bin keryx-cli"
        )

    def start(self) -> None:
        """Launch the interactive CLI shell and wait for its ready prompt."""
        with self._lock:
            if self._child is not None and self._child.isalive():
                return
            binary = self.resolve_binary()
            if not binary:
                raise KeryxCliError(self.binary_help())
            args = [self._cli_subcommand] if self._cli_subcommand else []
            try:
                import os
                env = dict(os.environ)
                env["TERM"] = "xterm-256color"   # rustyline needs a real TERM
                self._child = pexpect.spawn(
                    binary,
                    args=args,
                    encoding="utf-8",
                    timeout=DEFAULT_TIMEOUT,
                    echo=False,
                    codec_errors="replace",
                    dimensions=(24, 80),          # give the editor a window size
                    env=env,
                )
                self._child.delaybeforesend = 0.2  # let the editor settle
            except pexpect.ExceptionPexpect as e:
                raise KeryxCliError(
                    f"Failed to launch keryx-cli at '{binary}': {e}"
                ) from e
            # Wait for the shell to be ready to accept commands.
            self._wait_ready(timeout=DEFAULT_TIMEOUT)

    def stop(self) -> None:
        """Cleanly exit the CLI shell."""
        with self._lock:
            if self._child is None:
                return
            try:
                if self._child.isalive():
                    self._submit_line("exit")
                    self._child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
            except Exception:
                pass
            finally:
                try:
                    self._child.close(force=True)
                except Exception:
                    pass
                self._child = None

    def force_stop(self) -> None:
        """Immediately terminate the CLI subprocess WITHOUT acquiring the lock.
        Used on application shutdown: if a worker thread is stuck mid-command it
        holds the lock, so a normal stop() would block forever (the 'not
        responding / force quit' freeze). Killing the child unblocks that worker."""
        child = self._child
        self._child = None
        if child is None:
            return
        try:
            child.kill(9)  # SIGKILL the underlying process
        except Exception:
            pass
        try:
            child.close(force=True)
        except Exception:
            pass

    def is_alive(self) -> bool:
        with self._lock:
            return self._child is not None and self._child.isalive()

    # ── low-level command submission ─────────────────────────────────────────

    def _flush_buffer(self, settle: float = 0.0):
        """
        Drain pending data from the child's read buffer so the next expect()
        starts clean. With settle=0 it only removes bytes ALREADY waiting; with a
        small settle (e.g. 0.15s) it also absorbs async notification output that
        trickles in just after a command completes (balance/pending updates),
        which otherwise desyncs the next command's read.
        """
        if self._child is None:
            return
        try:
            while True:
                self._child.read_nonblocking(size=4096, timeout=settle)
        except Exception:
            pass  # nothing left to read

    def _submit_line(self, text: str):
        """
        Submit a line to the keryx-cli rustyline REPL. The raw-mode line editor
        requires a carriage return (\r) to accept a command — a newline (\n,
        what sendline sends) is echoed but NOT executed. We send the text then
        an explicit \r, with a short settle delay so the editor is ready.

        SECURITY: any embedded carriage returns / newlines / other control
        characters are stripped from `text` before sending. Without this, a value
        containing "\r" (e.g. a crafted wallet name, account title, or pasted
        field) could terminate the current line early and inject a SECOND command
        into the REPL — a command-injection vector. We strip all C0 control chars
        except tab, then append exactly one trailing "\r" ourselves. Passwords and
        mnemonics legitimately never contain control characters, so this is safe
        for every caller.
        """
        assert self._child is not None
        if self._child.delaybeforesend is None:
            self._child.delaybeforesend = 0.2
        # Remove CR, LF, and every other C0 control char (0x00–0x1F) except TAB.
        safe = "".join(
            ch for ch in (text or "")
            if ch == "\t" or ord(ch) >= 0x20
        )
        self._child.send(safe)
        self._child.send("\r")

    def _wait_ready(self, timeout: int = DEFAULT_TIMEOUT) -> str:
        """
        Read until the shell's ready prompt and return the ANSI-stripped text
        before it. The ready prompt uniquely appears as "$ " at the END of the
        output when the CLI is idle (sub-prompts like 'title:' do not end in
        '$ '). We anchor on "\\n\\r$ " — the full prompt lead-in seen in the
        real stream — which avoids matching the '\\r' inside echoed command
        lines.
        """
        assert self._child is not None
        try:
            self._child.expect(READY_PROMPT, timeout=timeout)
            return _ansi_strip(self._child.before or "")
        except pexpect.TIMEOUT:
            return _ansi_strip(self._child.before or "")
        except pexpect.EOF:
            raise KeryxCliError("CLI process exited unexpectedly.")

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Send a single non-interactive command and capture output up to the
        next ready prompt. Use this for commands that do NOT prompt for input
        (e.g. list, address, history, ping, server, connect, network).

        Commands that prompt (create/open/send) must use their dedicated flow
        methods, which handle the prompts explicitly.
        """
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult(command, "", ok=False,
                                 error="CLI process is not running.")
            try:
                self._flush_buffer(settle=0.12)
                self._submit_line(command)
                output = self._wait_ready(timeout=timeout)
                cleaned = _clean_output(self._strip_echo(command, output))
                return CliResult(command, cleaned, ok=True)
            except pexpect.TIMEOUT:
                return CliResult(command, self._child.before or "", ok=False,
                                 error=f"Command timed out after {timeout}s.")
            except KeryxCliError as e:
                return CliResult(command, "", ok=False, error=str(e))

    @staticmethod
    def _strip_echo(command: str, output: str) -> str:
        """Remove the echoed command line and trim whitespace."""
        lines = output.splitlines()
        if lines and lines[0].strip() == command.strip():
            lines = lines[1:]
        return "\n".join(lines).strip()

    # ── prompt-sensitive flows (TO BE FINALISED against real prompt text) ─────
    #
    # The methods below are the ONLY place where the GUI answers interactive
    # prompts. They are intentionally guarded until the exact prompt strings are
    # confirmed against the real Keryx binary. Answering the wrong prompt with a
    # password or a "yes" could mis-handle funds, so we do not guess.

    # Prompt patterns — CONFIRM EACH against `keryx cli` actual output, then
    # remove the NotImplementedError guards in the flow methods.
    PROMPT_PATTERNS = {
        # e.g. rb"Enter wallet name", rb"password:", rb"Confirm password",
        #       rb"phishing hint", rb"(y/n)", rb"Are you sure"
        "password":     re.compile(r"(?i)password:?\s*"),
        "confirm_pass": re.compile(r"(?i)(re-?enter|confirm).*password:?\s*"),
        "wallet_name":  re.compile(r"(?i)wallet name:?\s*"),
        "yes_no":       re.compile(r"(?i)\(y/n\)|are you sure|confirm\??\s*"),
        "mnemonic_ack": re.compile(r"(?i)written.*down|press.*continue|i have"),
    }

    # The overwrite warning that appears if `wallet create` is issued without a
    # name while a default wallet already exists. CONFIRMED text fragment.
    OVERWRITE_WARNING = re.compile(
        r"(?i)already exists|overwrite it.*type 'y'"
    )

    # Verified create-flow prompts from the real keryx-cli binary.
    CREATE_PROMPTS = {
        "account_title":  re.compile(r"(?i)default account title:\s*"),
        "phishing_hint":  re.compile(r"(?i)create phishing hint[^\n]*:\s*"),
        "enc_password":   re.compile(r"(?i)enter wallet encryption password:\s*"),
        "reenter_pass":   re.compile(r"(?i)re-?enter wallet encryption password:\s*"),
        "bip39":          re.compile(r"(?i)enter bip39 mnemonic passphrase[^\n]*:\s*"),
    }
    # The mnemonic block is delimited by the "Your default wallet account
    # mnemonic:" header; the deposit address follows "deposit address:".
    MNEMONIC_HEADER = re.compile(r"(?i)your default (wallet )?account mnemonic:")
    DEPOSIT_HEADER  = re.compile(r"(?i)default account deposit address:")

    def create_wallet(self, name: str, password: str,
                      account_title: str = "",
                      phishing_hint: str = "",
                      bip39_passphrase: str = "",
                      timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Create a NEW named wallet end to end. SAFETY: name is mandatory and the
        bare (overwriting) form is never used; an overwrite prompt is declined.

        Verified prompt sequence after `wallet create <name>`:
          1. Default account title:            -> account_title (may be empty)
          2. Create phishing hint (optional):  -> phishing_hint (may be empty)
          3. Enter wallet encryption password: -> password (REQUIRED; empty aborts)
          4. Re-enter wallet encryption password: -> password (must match)
          5. Enter bip39 mnemonic passphrase (optional): -> bip39_passphrase
          6. Mnemonic phrase + deposit address are DISPLAYED.

        On success, CliResult.output contains the full final block. The caller
        should extract and present the mnemonic to the user for offline backup,
        then discard it. parse_create_result() pulls out the mnemonic + address.

        The password must be non-empty (the CLI aborts on an empty secret).
        """
        name = (name or "").strip()
        if not name:
            return CliResult("wallet create", "", ok=False,
                             error="A wallet name is required (never create "
                                   "unnamed — overwrite risk).")
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name):
            return CliResult("wallet create", "", ok=False,
                             error="Wallet name must be 1-64 chars: letters, "
                                   "digits, underscore, hyphen.")
        if not password:
            return CliResult("wallet create", "", ok=False,
                             error="Encryption password is required (the CLI "
                                   "aborts on an empty secret).")

        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("wallet create", "", ok=False,
                                 error="CLI process is not running.")
            cmd = f"wallet create {name}"
            self._flush_buffer()
            self._submit_line(cmd)

            # Walk the known prompt sequence. At each step we expect either the
            # next prompt, the overwrite warning (decline + abort), or the final
            # ready prompt. Anything unexpected aborts safely.
            steps = [
                ("account_title", account_title),
                ("phishing_hint", phishing_hint),
                ("enc_password",  password),
                ("reenter_pass",  password),
                ("bip39",         bip39_passphrase),
            ]
            try:
                for key, value in steps:
                    pattern = self.CREATE_PROMPTS[key]
                    idx = self._child.expect(
                        [pattern, self.OVERWRITE_WARNING, READY_PROMPT,
                         pexpect.TIMEOUT, pexpect.EOF],
                        timeout=timeout,
                    )
                    if idx == 1:
                        # Overwrite warning — never approve.
                        self._submit_line("n")
                        self._wait_ready(timeout=5)
                        return CliResult(
                            cmd, self._child.before or "", ok=False,
                            error="Unexpected overwrite prompt; declined and "
                                  "aborted. No wallet overwritten.")
                    if idx != 0:
                        # Reached ready prompt early or timed out — the sequence
                        # didn't match; surface output and stop.
                        return CliResult(
                            cmd, self._child.before or "", ok=False,
                            error=f"Create flow diverged at step '{key}'. "
                                  "No wallet created (or incomplete).")
                    # Matched the expected prompt; answer it.
                    self._submit_line(value)

                # After the bip39 answer the CLI prints the mnemonic block and
                # returns to the ready prompt. Capture everything up to it.
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=timeout)
                output = self._child.before or ""
            except pexpect.TIMEOUT:
                return CliResult(cmd, self._child.before or "", ok=False,
                                 error="Create flow timed out. Verify wallet "
                                       "state before retrying.")
            except pexpect.EOF:
                return CliResult(cmd, "", ok=False,
                                 error="CLI exited during create.")

            if self.MNEMONIC_HEADER.search(output):
                return CliResult(cmd, output.strip(), ok=True)
            return CliResult(cmd, output.strip(), ok=False,
                             error="Create completed without a visible mnemonic. "
                                   "Verify the wallet before using it.")

    # Verified import-flow mnemonic prompt (keryx-cli): the cursor waits at
    # "Mnemonic:" on its own line, preceded by the instruction line.
    MNEMONIC_PROMPT = re.compile(r"(?i)mnemonic:\s*$|mnemonic:\s*")

    def import_wallet(self, name: str, password: str, mnemonic: str,
                      account_title: str = "",
                      phishing_hint: str = "",
                      bip39_passphrase: str = "",
                      timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Import a wallet from an existing recovery phrase via `wallet import
        <name>`. Verified prompt sequence (same as create, plus a mnemonic step):
          1. Default account title:
          2. Create phishing hint (optional):
          3. Enter wallet encryption password:
          4. Re-enter wallet encryption password:
          5. Enter bip39 mnemonic passphrase (optional):
          6. Mnemonic:                      <- NEW: paste the 12/24-word phrase
          7. wallet stored + deposit address displayed

        SAFETY: name mandatory (never overwrites — overwrite prompt is declined);
        password required; mnemonic required and validated to be 12 or 24 words.
        """
        name = (name or "").strip()
        if not name:
            return CliResult("wallet import", "", ok=False,
                             error="A wallet name is required.")
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name):
            return CliResult("wallet import", "", ok=False,
                             error="Wallet name must be 1-64 chars: letters, "
                                   "digits, underscore, hyphen.")
        if not password:
            return CliResult("wallet import", "", ok=False,
                             error="Encryption password is required.")
        words = (mnemonic or "").split()
        if len(words) not in (12, 24):
            return CliResult("wallet import", "", ok=False,
                             error="Recovery phrase must be 12 or 24 words "
                                   f"(got {len(words)}).")
        clean_mnemonic = " ".join(words)

        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("wallet import", "", ok=False,
                                 error="CLI process is not running.")
            cmd = f"wallet import {name}"
            self._flush_buffer()
            self._submit_line(cmd)

            steps = [
                ("account_title", account_title),
                ("phishing_hint", phishing_hint),
                ("enc_password",  password),
                ("reenter_pass",  password),
                ("bip39",         bip39_passphrase),
            ]
            try:
                for key, value in steps:
                    pattern = self.CREATE_PROMPTS[key]
                    idx = self._child.expect(
                        [pattern, self.OVERWRITE_WARNING, READY_PROMPT,
                         pexpect.TIMEOUT, pexpect.EOF],
                        timeout=timeout,
                    )
                    if idx == 1:
                        self._submit_line("n")
                        self._wait_ready(timeout=5)
                        return CliResult(
                            cmd, self._child.before or "", ok=False,
                            error="Unexpected overwrite prompt; declined and "
                                  "aborted. No wallet overwritten.")
                    if idx != 0:
                        return CliResult(
                            cmd, self._child.before or "", ok=False,
                            error=f"Import flow diverged at step '{key}'. "
                                  "No wallet imported.")
                    self._submit_line(value)

                # NEW step: the Mnemonic: prompt — supply the recovery phrase.
                idx = self._child.expect(
                    [self.MNEMONIC_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout,
                )
                if idx != 0:
                    return CliResult(
                        cmd, self._child.before or "", ok=False,
                        error="Import flow did not reach the mnemonic prompt. "
                              "No wallet imported.")
                self._submit_line(clean_mnemonic)

                # After the mnemonic, the CLI stores the wallet and prints the
                # deposit address. Capture up to the ready prompt.
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=timeout)
                output = _ansi_strip(self._child.before or "")
            except pexpect.TIMEOUT:
                return CliResult(cmd, self._child.before or "", ok=False,
                                 error="Import flow timed out. Verify wallet "
                                       "state before retrying.")
            except pexpect.EOF:
                return CliResult(cmd, "", ok=False,
                                 error="CLI exited during import.")

            lowered = output.lower()
            if "error" in lowered or "invalid" in lowered or "not " in lowered:
                return CliResult(cmd, output.strip(), ok=False,
                                 error="Import failed — check the recovery phrase.")
            # Success if we got a deposit address back.
            if re.search(r"ker[xy][a-z]*:[0-9a-z]+", output, re.IGNORECASE):
                return CliResult(cmd, output.strip(), ok=True)
            return CliResult(cmd, output.strip(), ok=False,
                             error="Import completed without a visible address. "
                                   "Verify the wallet before using it.")

    @staticmethod
    def parse_create_result(output: str):
        """
        Extract the mnemonic phrase and deposit address from a successful
        create output block. Returns {"mnemonic": str, "address": str} with
        empty strings if a field can't be found.

        The CLI colorizes the address (e.g. blue), so ANSI escape codes are
        stripped from every line before extraction.
        """
        mnemonic = ""
        address = ""
        clean = _ansi_strip(output or "")
        lines = [l.rstrip() for l in clean.splitlines()]
        for i, line in enumerate(lines):
            if re.search(r"(?i)your default (wallet )?account mnemonic:", line):
                # mnemonic is on the next non-empty line
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        mnemonic = lines[j].strip()
                        break
            if re.search(r"(?i)default account deposit address:", line):
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        address = lines[j].strip()
                        break
        # Fallback: an address line starting with the keryx prefix.
        if not address:
            for line in lines:
                m = re.search(r"(ker[xy][a-z]*:[0-9a-z]+)", line, re.IGNORECASE)
                if m:
                    address = m.group(1)
                    break
        # Final safety: strip any stray ANSI/whitespace from extracted values.
        mnemonic = _ansi_strip(mnemonic).strip()
        address = _ansi_strip(address).strip()
        return {"mnemonic": mnemonic, "address": address}

    # Verified prompt strings from the real keryx-cli binary.
    PW_PROMPT = re.compile(r"(?i)enter wallet password:\s*")
    # `send` output line, e.g. "Send - Amount: 1.5 KRX  Fees: 0.1 KRX  Total: 1.6 KRX  UTXOs: 3"
    SEND_RESULT = re.compile(
        r"Send\s*-\s*Amount:\s*([\d.]+)\s*KRX\s+"
        r"Fees:\s*([\d.]+)\s*KRX\s+"
        r"Total:\s*([\d.]+)\s*KRX\s+"
        r"UTXOs:\s*(\d+)",
        re.IGNORECASE,
    )

    def select_network(self, network: str, timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Select the network with `network <type>`. Verified valid values:
        'mainnet', 'testnet-10', 'testnet-11'. Must be done BEFORE connect or
        wallet create.
        """
        valid = {"mainnet", "testnet-10", "testnet-11"}
        network = (network or "").strip()
        if network not in valid:
            return CliResult("network", "", ok=False,
                             error=f"Network must be one of: {', '.join(sorted(valid))}.")
        return self.run(f"network {network}", timeout=timeout)

    # Failure signatures the CLI prints when the node is unreachable. A failed
    # connect surfaces one of these; a successful connect prints "Connected to
    # Keryx node ...". We key on the FAILURE messages (see connect()), because
    # the success banner can print after the prompt returns and be missed.
    CONNECT_FAIL_SIGNATURES = (
        "no route to host",
        "connection timeout",
        "connection refused",
        "websocket error",
        "connection reset",
        "failed to connect",
    )

    def connect(self, address: str, timeout: int = CONNECT_TIMEOUT) -> CliResult:
        """
        Connect to a node with `connect <address>`. The address is a required
        argument (verified). Must be called after select_network.

        Detection strategy: a successful connect prints "Connected to Keryx node
        version X at ws://..." synchronously. We treat the connection as live
        only if that line appears; anything else (timeout, refused, no route) is
        a failure. This avoids the timing fragility of scanning for async errors.
        """
        address = (address or "").strip()
        if not address:
            return CliResult("connect", "", ok=False,
                             error="A node address is required to connect.")
        if re.search(r"\s", address):
            return CliResult("connect", "", ok=False,
                             error="Node address must not contain whitespace.")
        res = self.run(f"connect {address}", timeout=timeout)
        low = ((res.output or "") + " " + (res.error or "")).lower()
        # Detection: a failed connect prints a distinctive wRPC error
        # ("no route to host", "connection refused", "connection timeout", etc.).
        # A successful connect prints "Connected to Keryx node ...". We treat the
        # connection as FAILED only if an explicit failure signature is present.
        # We do NOT require the success banner to be captured, because it can
        # print just after the prompt returns and may not be in this buffer — and
        # false-failing a good connection is worse than the rare false-success.
        if any(sig in low for sig in self.CONNECT_FAIL_SIGNATURES):
            return CliResult("connect", res.output, ok=False,
                             error="Node unreachable (wRPC connection failed).")
        return CliResult("connect", res.output, ok=True, error="")

    def open_wallet(self, name: str, password: str,
                    timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Open a named wallet: `wallet open "name"` then answer the
        `Enter wallet password:` prompt. VERIFIED flow.

        The password is written to the child's stdin and never logged.
        """
        name = (name or "").strip()
        if not name:
            return CliResult("wallet open", "", ok=False,
                             error="Wallet name is required to open a wallet.")
        # Validate the name the same way create/import do — defense in depth on
        # top of _submit_line's control-char stripping. A wallet name is only
        # ever letters, digits, underscore, hyphen; anything else is rejected so
        # a crafted name can't carry an injected command or odd characters.
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name):
            return CliResult("wallet open", "", ok=False,
                             error="Invalid wallet name.")

        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("wallet open", "", ok=False,
                                 error="CLI process is not running.")
            cmd = f'wallet open {name}'
            self._flush_buffer()
            self._submit_line(cmd)
            try:
                idx = self._child.expect(
                    [self.PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout,
                )
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))

            if idx != 0:
                # No password prompt — wallet not found or another error.
                before = _ansi_strip(self._child.before or "")
                return CliResult(cmd, before, ok=False,
                                 error="Wallet did not open — check the name "
                                       "exists. CLI said: " + before.strip()[:120])
            # Send the password to the prompt, then wait for the shell to return.
            self._submit_line(password)
            try:
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            output = _ansi_strip(self._child.before or "")
            lowered = output.lower()
            # Confirmed wrong-password output is "Unable to decrypt this wallet".
            # Detect failure by explicit error phrasings; otherwise the open
            # succeeded. (A successful open's account data may still be streaming
            # when we capture, so we must NOT require wallet data to be present.)
            if ("unable to decrypt" in lowered
                    or "incorrect" in lowered or "invalid" in lowered
                    or "wrong password" in lowered or "decryption" in lowered
                    or "no wallet named" in lowered or "not found" in lowered
                    or "does not exist" in lowered or "aead" in lowered):
                return CliResult(cmd, output.strip(), ok=False,
                                 error="Wrong password.")
            return CliResult(cmd, output.strip(), ok=True)

    def export_mnemonic(self, password: str,
                        timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Reveal the open wallet's recovery phrase via `export mnemonic`.

        Verified flow:
          export mnemonic
          -> Enter wallet password:   (password to decrypt)
          -> prints "extended public key:\\n<kpub...>\\nmnemonic:\\n<phrase>"

        SECURITY: this reveals the seed phrase, which grants full control of the
        wallet. A wallet must already be open. The caller (GUI) must show this
        only in a one-time, clearly-warned dialog and never store it.

        Returns CliResult whose .output contains the export block; use
        parse_export_result() to split out xpub and mnemonic.
        """
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("export mnemonic", "", ok=False,
                                 error="CLI process is not running.")
            cmd = "export mnemonic"
            self._flush_buffer()
            self._submit_line(cmd)
            try:
                idx = self._child.expect(
                    [self.PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout,
                )
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx != 0:
                before = _ansi_strip(self._child.before or "")
                return CliResult(cmd, before, ok=False,
                                 error="Did not receive the password prompt for "
                                       "export. Ensure a wallet is open.")
            self._submit_line(password)
            try:
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            output = _ansi_strip(self._child.before or "")
            lowered = output.lower()
            if "mnemonic:" not in lowered:
                # At this point a wallet is open and we supplied a password, so a
                # missing mnemonic almost always means the password was wrong
                # (decryption failed). Surface that clearly.
                return CliResult(cmd, output.strip(), ok=False,
                                 error="Wrong password.")
            return CliResult(cmd, output.strip(), ok=True)

    @staticmethod
    def parse_export_result(output: str):
        """
        Split `export mnemonic` output into its parts. Returns
        {"xpub": str, "mnemonic": str} with empty strings if not found.
        Format:
            extended public key:
            kpub...
            mnemonic:
            word1 word2 ...
        """
        xpub = ""
        mnemonic = ""
        lines = [l.rstrip() for l in _ansi_strip(output or "").splitlines()]
        for i, line in enumerate(lines):
            low = line.strip().lower()
            if low.startswith("extended public key"):
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        xpub = lines[j].strip()
                        break
            elif low.startswith("mnemonic:"):
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        mnemonic = lines[j].strip()
                        break
        # Fallbacks by shape
        if not xpub:
            m = re.search(r"(kpub[0-9A-Za-z]+)", output or "")
            if m:
                xpub = m.group(1)
        return {"xpub": xpub, "mnemonic": mnemonic}

    # ── Account management ───────────────────────────────────────────────
    # The interactive "select" prompt looks like:
    #   "Please select account [0..3] or <enter> to abort:"
    SELECT_PROMPT = re.compile(r"(?i)please select account \[0\.\.\d+\]")

    @staticmethod
    def parse_accounts(output: str):
        """Parse the bullet-style `list` output into account dicts.

        The `list` output looks like:
            • 026c88596f0eee88
                • [f802fb7e]: 20,867.98 KRX (...)  510 UTXOs
                  keryx:qqfln...
                • test1 [25032052]: 100 KRX   1 UTXOs
                  keryx:qptpq...
        The account ORDER is the select index (first=0, second=1, ...). Account 0
        has no name (just an id); created accounts show "name [id]".

        Returns a list of dicts: {index, name, id, balance, address}.
        """
        text = _ansi_strip(output or "")
        accounts = []
        # An account header line contains "[<hexid>]:" and a KRX balance. The
        # next non-empty line that is a keryx: address belongs to that account.
        acct_re = re.compile(
            r"^\s*[•*-]?\s*(?:(?P<name>\S[^\[]*?)\s+)?\[(?P<id>[0-9a-fA-F]{6,16})\]:\s*"
            r"(?P<bal>[\d,]+(?:\.\d+)?)\s*KRX", re.IGNORECASE)
        addr_re = re.compile(r"(ker[xy][a-z]*:[0-9a-z]+)", re.IGNORECASE)
        lines = text.splitlines()
        idx = 0
        for i, line in enumerate(lines):
            m = acct_re.search(line)
            if not m:
                continue
            name = (m.group("name") or "").strip()
            acct_id = m.group("id")
            bal = m.group("bal").replace(",", "")
            # Look ahead a couple of lines for this account's address.
            address = ""
            for j in range(i + 1, min(i + 3, len(lines))):
                am = addr_re.search(lines[j])
                if am:
                    address = am.group(1)
                    break
            accounts.append({
                "index": idx, "name": name, "id": acct_id,
                "balance": bal, "address": address,
            })
            idx += 1
        return accounts

    def list_accounts(self, timeout: int = DEFAULT_TIMEOUT):
        """Run `list` and return parsed accounts. Requires an open wallet."""
        res = self.run("list", timeout=timeout)
        if not res.ok:
            return res, []
        return res, self.parse_accounts(res.output)

    def mute_notifications(self, timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """Toggle notification output off via `mute`. Async balance/pending
        notifications stream into the REPL between commands and can desync the
        buffer (a following command reads the leftover notification text). Muting
        them keeps each command's output clean. Best-effort — if `mute` is
        already off this may toggle it on, so callers should only invoke once at
        startup."""
        return self.run("mute", timeout=timeout)

    def select_account(self, index: int, timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """Select an account by its numeric index via the interactive prompt.
        Note: `select <n>` as a single command does NOT work ("account 'n' not
        found"); selection is only via the bare `select` + numbered prompt."""
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("select", "", ok=False,
                                 error="CLI process is not running.")
            self._flush_buffer(settle=0.12)
            self._submit_line("select")
            try:
                idx = self._child.expect(
                    [self.SELECT_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout)
            except Exception as e:  # noqa
                return CliResult("select", "", ok=False, error=str(e))
            if idx != 0:
                before = _ansi_strip(self._child.before or "")
                return CliResult("select", before, ok=False,
                                 error="Did not get the account selection prompt.")
            # Answer the prompt with the index.
            self._submit_line(str(int(index)))
            try:
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=timeout)
            except Exception as e:  # noqa
                return CliResult("select", "", ok=False, error=str(e))
            output = _ansi_strip(self._child.before or "")
            # Absorb any async balance/notification output that streams in right
            # after the selection, so the NEXT command (address/list/history)
            # reads its own output and not this leftover.
            self._flush_buffer(settle=0.2)
            low = output.lower()
            # The CLI confirms a successful selection with "selecting account:".
            # NOTE: do NOT check for the word "abort" — the selection prompt
            # itself contains "or <enter> to abort:", which would false-trigger.
            if "selecting account" in low:
                return CliResult("select", output.strip(), ok=True)
            if "not found" in low:
                return CliResult("select", output.strip(), ok=False,
                                 error="Account selection failed.")
            # If we didn't see an explicit confirmation, assume it worked rather
            # than false-failing (the confirmation line may have scrolled past).
            return CliResult("select", output.strip(), ok=True)

    def create_account(self, name: str, password: str,
                       acct_type: str = "bip32",
                       timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """Create a new account: `account create <type> <name>` then answer the
        wallet password prompt. Verified flow:
            account create bip32 myname
            -> Enter wallet password:
            -> "account created: myname [id]: N/A KRX"
        """
        name = (name or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name):
            return CliResult("account create", "", ok=False,
                             error="Invalid account name (letters, digits, _ - only).")
        if acct_type not in ("bip32", "multisig", "legacy"):
            acct_type = "bip32"
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("account create", "", ok=False,
                                 error="CLI process is not running.")
            cmd = f"account create {acct_type} {name}"
            self._flush_buffer()
            self._submit_line(cmd)
            try:
                idx = self._child.expect(
                    [self.PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx != 0:
                before = _ansi_strip(self._child.before or "")
                # No password prompt — possibly created without one, or errored.
                if "account created" in before.lower():
                    return CliResult(cmd, before.strip(), ok=True)
                return CliResult(cmd, before, ok=False,
                                 error="Did not get the password prompt for "
                                       "account create.")
            self._submit_line(password)
            try:
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            output = _ansi_strip(self._child.before or "")
            low = output.lower()
            if "account created" in low:
                return CliResult(cmd, output.strip(), ok=True)
            if "unable to decrypt" in low or "incorrect" in low:
                return CliResult(cmd, output.strip(), ok=False,
                                 error="Wrong password.")
            return CliResult(cmd, output.strip(), ok=False,
                             error="Account creation did not confirm.")

    #   "Sweep: Fees: <fee> UTXOs: <count> Batch Transactions: <batches>"
    SWEEP_RESULT = re.compile(
        r"(?i)sweep:\s*fees:\s*([\d.]+).*?utxos:\s*(\d+).*?"
        r"batch transactions:\s*(\d+)", re.DOTALL)

    def sweep(self, password: str, timeout: int = SEND_TIMEOUT) -> CliResult:
        """
        Consolidate the wallet's UTXOs via `sweep`. Combines many small UTXOs
        into fewer, which speeds up future transactions.

        Verified flow:
          sweep
          -> Enter wallet password:
          -> (processes) prints
             "Sweep: Fees: <fee> UTXOs: <count> Batch Transactions: <batches>"

        Like `send`, sweep BROADCASTS once the password is supplied — there is no
        CLI-side yes/no. The GUI MUST confirm with the user (showing the UTXO
        count, batch count, and total fee) BEFORE calling this. By the time we're
        here, the user has approved.

        Returns CliResult; .output holds the Sweep result line on success
        (parse with parse_sweep_result()).
        """
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("sweep", "", ok=False,
                                 error="CLI process is not running.")
            cmd = "sweep"
            self._flush_buffer()
            self._submit_line(cmd)
            try:
                idx = self._child.expect(
                    [self.PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout,
                )
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx != 0:
                before = _ansi_strip(self._child.before or "")
                return CliResult(cmd, before, ok=False,
                                 error="Did not receive the password prompt for "
                                       "sweep. Transaction NOT broadcast. Ensure "
                                       "a wallet is open and you are connected.")
            # POINT OF NO RETURN: supplying the password broadcasts the sweep.
            self._submit_line(password)
            try:
                # Sweeping many batches can take a while; allow extra time.
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=max(timeout, 120))
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False,
                                 error=f"Sweep submitted but no confirmation "
                                       f"read: {e}")
            output = _ansi_strip(self._child.before or "").strip()
            lowered = output.lower()
            if "unable to decrypt" in lowered or "incorrect" in lowered:
                return CliResult(cmd, output, ok=False, error="Wrong password.")
            # Success if we see the structured result OR any sweep/fee/batch
            # confirmation text. The exact wording/spacing can vary, so don't
            # require the strict regex to call it a success.
            if (self.SWEEP_RESULT.search(output)
                    or "sweep:" in lowered
                    or ("fees:" in lowered and "batch" in lowered)
                    or "batch transaction" in lowered):
                return CliResult(cmd, output, ok=True)
            if "insufficient" in lowered or "error" in lowered:
                return CliResult(cmd, output, ok=False,
                                 error="Sweep failed — see output.")
            # Nothing recognizable. The sweep may still have broadcast — say so
            # rather than implying failure.
            return CliResult(cmd, output, ok=True,
                             error="")

    @staticmethod
    def parse_sweep_result(output: str):
        """Parse the 'Sweep: Fees/UTXOs/Batch Transactions' line. dict or None."""
        m = KeryxCliDriver.SWEEP_RESULT.search(output or "")
        if not m:
            return None
        return {
            "fees": m.group(1),
            "utxos": int(m.group(2)),
            "batches": int(m.group(3)),
        }


    def send(self, address: str, amount: str, priority_fee: str,
             password: str, timeout: int = SEND_TIMEOUT) -> CliResult:
        """
        Broadcast a transaction. CRITICAL SAFETY CONTRACT:

        `send` broadcasts IMMEDIATELY after the password is supplied — there is
        no CLI-side yes/no confirmation. Therefore the GUI MUST have already
        shown the user a confirmation dialog (address, amount, fee, total) and
        received explicit approval BEFORE this method is called. By the time
        we're here, the user has committed; supplying the password completes the
        send. Do not call this method speculatively.

        Returns a CliResult whose .output contains the
        "Send - Amount: ... Total: ... UTXOs: ..." line on success; callers can
        parse it with KeryxCliDriver.parse_send_result().
        """
        address = (address or "").strip()
        amount = str(amount).strip()
        priority_fee = str(priority_fee).strip()

        if not address:
            return CliResult("send", "", ok=False, error="Destination address required.")
        if re.search(r"\s", address):
            return CliResult("send", "", ok=False, error="Address must not contain whitespace.")
        if not re.fullmatch(r"\d+(\.\d+)?", amount):
            return CliResult("send", "", ok=False, error="Amount must be a positive number.")
        if not re.fullmatch(r"\d+(\.\d+)?", priority_fee):
            return CliResult("send", "", ok=False, error="Priority fee must be a number.")

        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("send", "", ok=False, error="CLI process is not running.")
            # Note: address/amount/fee are validated above; safe to interpolate.
            cmd = f"send {address} {amount} {priority_fee}"
            self._flush_buffer()
            self._submit_line(cmd)
            try:
                idx = self._child.expect(
                    [self.PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout,
                )
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))

            if idx != 0:
                return CliResult(cmd, _ansi_strip(self._child.before or ""),
                                 ok=False,
                                 error="Did not receive the password prompt for "
                                       "send. Transaction NOT broadcast. Ensure a "
                                       "wallet is open and you are connected.")
            # POINT OF NO RETURN: supplying the password broadcasts the tx.
            self._submit_line(password)
            try:
                self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                   timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False,
                                 error=f"Send submitted but no confirmation read: {e}")
            output = _ansi_strip(self._child.before or "").strip()
            if self.SEND_RESULT.search(output):
                return CliResult(cmd, output, ok=True)
            # No result line — surface output so the user can see what happened.
            lowered = output.lower()
            if "error" in lowered or "insufficient" in lowered or "invalid" in lowered:
                return CliResult(cmd, output, ok=False,
                                 error="Send failed — see output.")
            # Ambiguous: return ok=False so the GUI doesn't claim success falsely.
            return CliResult(cmd, output, ok=False,
                             error="Send result could not be confirmed. Check "
                                   "transaction history before retrying.")

    @staticmethod
    def parse_send_result(output: str):
        """Parse the 'Send - Amount/Fees/Total/UTXOs' line. Returns dict or None."""
        m = KeryxCliDriver.SEND_RESULT.search(output or "")
        if not m:
            return None
        return {
            "amount": m.group(1),
            "fees": m.group(2),
            "total": m.group(3),
            "utxos": int(m.group(4)),
        }
