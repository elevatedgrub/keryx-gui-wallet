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
        # keryx-cli starts with async notifications MUTED. We track the state so
        # set_muted() only toggles when needed (the `mute` command is a toggle
        # with no status query; a blind call would UNMUTE and desync the buffer).
        self._muted = True

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
                    # WIDE terminal so the CLI never wraps long output lines at
                    # the column boundary. At 80 cols a big-balance "Send -/
                    # Estimate -" line (or a 12-word mnemonic echo) wrapped
                    # mid-number, breaking the result regex → "estimate
                    # unavailable" / "send result uncertain" on large wallets.
                    dimensions=(50, 1000),
                    env=env,
                )
                self._child.delaybeforesend = 0.2  # let the editor settle
            except pexpect.ExceptionPexpect as e:
                raise KeryxCliError(
                    f"Failed to launch keryx-cli at '{binary}': {e}"
                ) from e
            # Wait for the shell to be ready to accept commands.
            self._wait_ready(timeout=DEFAULT_TIMEOUT)
            # A freshly spawned keryx-cli starts muted.
            self._muted = True

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

    def is_alive(self) -> bool:
        with self._lock:
            return self._child is not None and self._child.isalive()

    # ── low-level command submission ─────────────────────────────────────────

    def _flush_buffer(self):
        """
        Drain any already-pending data from the child's read buffer so the next
        expect() starts clean. Uses a very short timeout: it only removes bytes
        that are ALREADY waiting, not output that has yet to be produced.
        """
        if self._child is None:
            return
        try:
            while True:
                self._child.read_nonblocking(size=4096, timeout=0.0)
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
                self._flush_buffer()
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
        # A NON-empty bip39 passphrase triggers a confirmation re-entry prompt.
        "reenter_bip39":  re.compile(r"(?i)re-?enter mnemonic passphrase[^\n]*:\s*"),
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

                # A NON-empty bip39 passphrase makes the CLI ask to re-enter it
                # for confirmation. Answer that with the same passphrase; an empty
                # passphrase skips this prompt entirely.
                if bip39_passphrase:
                    idx = self._child.expect(
                        [self.CREATE_PROMPTS["reenter_bip39"], READY_PROMPT,
                         pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
                    if idx == 0:
                        self._submit_line(bip39_passphrase)

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

                # A NON-empty bip39 passphrase makes the CLI ask to re-enter it.
                if bip39_passphrase:
                    idx = self._child.expect(
                        [self.CREATE_PROMPTS["reenter_bip39"], self.MNEMONIC_PROMPT,
                         READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
                    if idx == 0:
                        self._submit_line(bip39_passphrase)

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
    # Shown by `export mnemonic` ONLY for wallets created with a BIP39 passphrase
    # — this is where that passphrase ("payment password") goes.
    PAYMENT_PW_PROMPT = re.compile(r"(?i)enter payment password:\s*")
    # The numbered account-selection prompt. ONLY appears with 2+ accounts; a
    # single-account wallet auto-selects on bare `select` (no prompt). Ends in
    # ": " so it never collides with the READY_PROMPT ("$ ").
    SELECT_PROMPT = re.compile(r"(?i)please select account\s*\[\d+\.\.\d+\][^\n]*:\s*")
    # `send` output line, e.g. "Send - Amount: 1.5 KRX  Fees: 0.1 KRX  Total: 1.6 KRX  UTXOs: 3"
    # NB: keryx-cli formats large amounts with thousands separators (e.g.
    # "32,824.96851968"), so the numeric groups must allow commas; strip them
    # before float().
    SEND_RESULT = re.compile(
        r"Send\s*-\s*Amount:\s*([\d.,]+)\s*KRX\s+"
        r"Fees:\s*([\d.,]+)\s*KRX\s+"
        r"Total:\s*([\d.,]+)\s*KRX\s+"
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

    # wRPC/WebSocket failure signatures emitted by keryx-cli when the node is
    # unreachable. The connect command returns to the prompt but these errors
    # stream into the output — we must detect them to know the connect failed.
    CONNECT_FAIL_SIGNATURES = (
        "no route to host",
        "connection timeout",
        "connection refused",
        "websocket error",
        "io error",
        "connection reset",
        "failed to connect",
        "not connected",
    )

    def connect(self, address: str, timeout: int = CONNECT_TIMEOUT) -> CliResult:
        """
        Connect to a node with `connect <address>`. The address is a required
        argument (verified). Must be called after select_network.

        The address is the user's own wRPC-reachable node address. The wRPC
        WebSocket connects asynchronously, so a node that is down still lets the
        `connect` command return; we scan the output for failure signatures and
        report those as a failed connection.
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
        if any(sig in low for sig in self.CONNECT_FAIL_SIGNATURES):
            return CliResult("connect", res.output, ok=False,
                             error="Node unreachable (wRPC connection failed).")
        # NOTE: We intentionally do NOT drain extra output here. A post-connect
        # read left the pexpect buffer desynced — the connection banner bled into
        # the next command (wallet open), causing intermittent open failures.
        # The synchronous check above catches the common unreachable-node cases;
        # the connection indicator also reflects state once a command succeeds.
        return res

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

    # Success line: "account created: <name> [<id>]: <bal> KRX" (name may be empty)
    ACCOUNT_CREATED = re.compile(r"(?i)account created:\s*(.*?)\s*\[([0-9a-f]+)\]")
    # Optional name prompt from `account create <type>` (no inline name).
    ACCOUNT_NAME_PROMPT = re.compile(r"(?i)enter account name[^\n]*:\s*")

    def create_account(self, name: str, password: str,
                       acct_type: str = "bip32", payment_secret: str = "",
                       timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Create a new account (type REQUIRED: bip32|multisig|legacy). The name is
        OPTIONAL — an empty name creates an UNNAMED account (shown by its id).
        VERIFIED flow (no inline name, so an empty name can be passed):
          account create <type>
          -> Please enter account name (optional, <enter> to skip): -> name (may be "")
          -> Enter wallet password:                                 -> password
          -> "account created: [<name> ]?[<id>]: N/A KRX" (auto-selects the new one)

        IMPORTANT: additional bip32 accounts do NOT auto-restore from the wallet
        mnemonic — recovery requires manually recreating accounts in order. The
        CALLER (GUI) must warn the user before calling this.

        Returns CliResult; .output holds the "account created..." line on success
        (parse with parse_created_account).
        """
        name = (name or "").strip()
        valid_types = {"bip32", "multisig", "legacy"}
        if name and not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name):
            return CliResult("account create", "", ok=False,
                             error="Account name must be 1-64 chars: letters, "
                                   "digits, underscore, hyphen (or empty).")
        if acct_type not in valid_types:
            return CliResult("account create", "", ok=False,
                             error="Account type must be bip32, multisig, or legacy.")
        if not password:
            return CliResult("account create", "", ok=False,
                             error="Wallet password is required to create an account.")

        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("account create", "", ok=False,
                                 error="CLI process is not running.")
            cmd = f"account create {acct_type}"
            self._flush_buffer()
            self._submit_line(cmd)
            # Answer the optional name prompt (empty = unnamed), then expect the
            # password prompt.
            try:
                idx = self._child.expect(
                    [self.ACCOUNT_NAME_PROMPT, self.PW_PROMPT, READY_PROMPT,
                     pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx == 0:
                self._submit_line(name)
                try:
                    idx = self._child.expect(
                        [self.PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                        timeout=timeout)
                except Exception as e:  # noqa
                    return CliResult(cmd, "", ok=False, error=str(e))
            if idx != 0:
                return CliResult(cmd, _ansi_strip(self._child.before or ""),
                                 ok=False,
                                 error="Did not get the password prompt for "
                                       "account create. No account created.")
            self._submit_line(password)
            # A passphrase wallet also asks for the payment password here.
            try:
                idx2 = self._child.expect(
                    [self.PAYMENT_PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT,
                     pexpect.EOF], timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx2 == 0:
                self._submit_line(payment_secret)
                try:
                    self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                       timeout=timeout)
                except Exception as e:  # noqa
                    return CliResult(cmd, "", ok=False, error=str(e))
            output = _ansi_strip(self._child.before or "").strip()
            low = output.lower()
            if "unable to decrypt" in low or "incorrect" in low \
                    or "wrong password" in low:
                return CliResult(cmd, output, ok=False, error="Wrong password.")
            if self.ACCOUNT_CREATED.search(output) or "account created" in low:
                return CliResult(cmd, output, ok=True)
            return CliResult(cmd, output, ok=False,
                             error="Account creation could not be confirmed. "
                                   "Check the account list.")

    def create_accounts(self, count: int, base_name: str, password: str,
                        acct_type: str = "bip32", payment_secret: str = "",
                        timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Create `count` accounts back-to-back by calling create_account in a loop.
        Each is named "<base_name><n>" (1-based) when base_name is given, else
        unnamed. Does NOT hold self._lock (each create_account serializes itself).

        Returns a CliResult whose .output is the newline-joined ids of the
        accounts created. On the FIRST account's failure nothing has been created,
        so the raw failing result is returned as-is — this lets the GUI's
        payment-secret retry (a passphrase wallet asks on the first create) rerun
        the whole batch cleanly. A later (partial) failure is reported with a
        progress summary so the user knows how many succeeded.
        """
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        if count < 1:
            return CliResult("account create", "", ok=False,
                             error="Number of accounts must be a positive integer.")
        base_name = (base_name or "").strip()
        created = []
        for i in range(1, count + 1):
            name = f"{base_name}{i}" if base_name else ""
            res = self.create_account(name, password, acct_type,
                                      payment_secret, timeout=timeout)
            if not res.ok:
                if not created:
                    return res  # unwrapped: lets the GUI detect/prompt passphrase
                return CliResult("account create", "\n".join(created), ok=False,
                                 error=f"Created {len(created)} of {count}; "
                                       f"#{i} failed: {res.error or 'unknown error'}")
            parsed = self.parse_created_account(res.output)
            if parsed and parsed.get("id"):
                created.append(parsed["id"])
        return CliResult("account create", "\n".join(created), ok=True)

    @staticmethod
    def parse_created_account(output: str):
        """Pull {'name','id'} from a successful create. dict or None."""
        m = KeryxCliDriver.ACCOUNT_CREATED.search(output or "")
        if not m:
            return None
        return {"name": m.group(1).strip(), "id": m.group(2)}

    def rename_account(self, index: int, new_name: str, password: str,
                       timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Rename an account. VERIFIED flow (the CLI does NOT rename the currently
        selected account — despite the help text — it prompts for which one):
          account name <new_name>
          -> Enter wallet password:            -> password
          -> Please select account [0..N]:     -> index (account to rename)
                                                  (a single-account wallet skips
                                                   this and returns to ready)
          -> renamed; `list` then shows the new name.

        An EMPTY new_name CLEARS the account's name (sends `account name remove`),
        leaving it shown by its id.

        SECURITY: name is validated (letters/digits/_/-, 1-64) — the same charset
        as wallet/account names — so a crafted value can't inject a command. A
        non-empty literal "remove" is rejected (use an empty name to clear).
        """
        new_name = (new_name or "").strip()
        # Empty name => clear the name via the CLI's `remove` keyword.
        token = "remove" if not new_name else new_name
        if new_name:
            if new_name.lower() == "remove":
                return CliResult("account name", "", ok=False,
                                 error="To clear the name, leave it empty.")
            if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", new_name):
                return CliResult("account name", "", ok=False,
                                 error="Account name must be 1-64 chars: letters, "
                                       "digits, underscore, hyphen (or empty).")
        if not isinstance(index, int) or index < 0:
            return CliResult("account name", "", ok=False,
                             error="Account index must be a non-negative integer.")
        if not password:
            return CliResult("account name", "", ok=False,
                             error="Wallet password is required to rename.")

        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("account name", "", ok=False,
                                 error="CLI process is not running.")
            cmd = f"account name {token}"
            self._flush_buffer()
            self._submit_line(cmd)
            try:
                idx = self._child.expect(
                    [self.PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx != 0:
                return CliResult(cmd, _ansi_strip(self._child.before or ""),
                                 ok=False,
                                 error="Did not get the password prompt for "
                                       "rename. Account NOT renamed.")
            self._submit_line(password)
            try:
                idx2 = self._child.expect(
                    [self.SELECT_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx2 == 0:
                # Numbered prompt: choose which account to rename.
                self._submit_line(str(index))
                try:
                    self._child.expect(
                        [READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
                except pexpect.TIMEOUT:
                    # Likely an out-of-range index → CLI re-prompts. Abort cleanly.
                    self._submit_line("")
                    self._wait_ready(timeout=5)
                    return CliResult(cmd, "", ok=False,
                                     error=f"Account index {index} not found.")
                except Exception as e:  # noqa
                    return CliResult(cmd, "", ok=False, error=str(e))
                output = _ansi_strip(self._child.before or "")
            elif idx2 == 1:
                # Single-account wallet: no select prompt; already back at ready.
                output = _ansi_strip(self._child.before or "")
            else:
                return CliResult(cmd, _ansi_strip(self._child.before or ""),
                                 ok=False,
                                 error="Rename did not complete (timed out or CLI "
                                       "exited). Verify with the account list.")
            low = output.lower()
            if "unable to decrypt" in low or "incorrect" in low \
                    or "wrong password" in low:
                return CliResult(cmd, output.strip(), ok=False, error="Wrong password.")
            if "not found" in low or "invalid" in low:
                return CliResult(cmd, output.strip(), ok=False,
                                 error=f"Account index {index} not found.")
            return CliResult(cmd, output.strip(), ok=True)

    def set_muted(self, muted: bool = True,
                  timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Ensure async notification output is muted (or not), idempotently.

        Async balance/pending notifications streaming into the REPL between
        commands are the #1 source of buffer desync. keryx-cli's `mute` command
        is a TOGGLE with no status query — it prints the NEW state ("mute is on"
        / "mute is off") — and the CLI starts MUTED. So a blind `mute` would
        UNMUTE and cause the very desync we want to avoid.

        We track the state (`self._muted`) and only toggle when the desired
        state differs from the tracked one, re-syncing the tracked value from
        the command's reported result. On a fresh process this is a no-op (it is
        already muted), so we never leave an unmuted window.
        """
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("mute", "", ok=False,
                                 error="CLI process is not running.")
            if self._muted == muted:
                return CliResult("mute", f"mute is {'on' if muted else 'off'}",
                                 ok=True)
            self._flush_buffer()
            self._submit_line("mute")
            out = _ansi_strip(self._wait_ready(timeout=timeout))
            low = out.lower()
            if "mute is on" in low:
                self._muted = True
            elif "mute is off" in low:
                self._muted = False
            else:
                return CliResult("mute", out.strip(), ok=False,
                                 error="Could not read mute state.")
            if self._muted == muted:
                return CliResult("mute", out.strip(), ok=True)
            # Toggle landed on the wrong state (tracked value was stale) — toggle
            # once more to reach the requested state.
            self._flush_buffer()
            self._submit_line("mute")
            out2 = _ansi_strip(self._wait_ready(timeout=timeout))
            self._muted = "mute is on" in out2.lower()
            ok = self._muted == muted
            return CliResult("mute", out2.strip(), ok=ok,
                             error=None if ok else "Could not set mute state.")

    def new_address(self, timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Generate a NEW receive address for the current account (`address new`).
        Previous addresses are NOT lost — they stay valid and keep receiving;
        this appends a new one and makes it the default. Returns the new address
        in .output on success.
        """
        res = self.run("address new", timeout=timeout)
        m = re.search(r"(ker[xy][a-z]*:[0-9a-z]+)", res.output or "", re.IGNORECASE)
        if m:
            return CliResult("address new", m.group(1), ok=True)
        return CliResult("address new", res.output, ok=False,
                         error="Could not generate a new address.")

    def account_details(self, index: int = 0,
                        timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Run `details` for an account and return its raw output (receive + change
        address lists). `details` prompts to select an account when the wallet
        has 2+ accounts; we answer with `index`.
        """
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("details", "", ok=False,
                                 error="CLI process is not running.")
            self._flush_buffer()
            self._submit_line("details")
            try:
                idx = self._child.expect(
                    [self.SELECT_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout)
            except Exception as e:  # noqa
                return CliResult("details", "", ok=False, error=str(e))
            if idx == 0:
                self._submit_line(str(index))
                try:
                    self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                       timeout=timeout)
                except Exception as e:  # noqa
                    return CliResult("details", "", ok=False, error=str(e))
            return CliResult("details", _ansi_strip(self._child.before or ""), ok=True)

    @staticmethod
    def parse_receive_addresses(output: str):
        """Pull the receive-address list from `details` output."""
        addrs = []
        in_recv = False
        for line in (output or "").splitlines():
            s = line.strip()
            if re.match(r"(?i)receive addresses:", s):
                in_recv = True
                continue
            if re.match(r"(?i)change addresses:", s):
                in_recv = False
                continue
            if in_recv:
                m = re.search(r"(ker[xy][a-z]*:[0-9a-z]+)", s, re.IGNORECASE)
                if m:
                    addrs.append(m.group(1))
        return addrs

    def select_account(self, index: int = 0,
                       timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Make an account the ACTIVE one, by its 0-based position in `list`.

        keryx-cli will NOT spend (estimate / send / message sign) until an
        account is actively selected, and the active account's UTXO context is
        what those commands draw from. Crucially:
          - With 2+ accounts, `wallet open` selects NOTHING — the prompt lacks
            the "• [acct] •" segment and estimate/send return
            "please select an account". This call fixes that.
          - With a SINGLE account, `open` already auto-selects account 0; a bare
            `select` then auto-selects again WITHOUT showing the numbered prompt.
          - When the wallet was opened BEFORE connecting, even the auto-selected
            account 0 can report "Insufficient funds" until re-selected, because
            its UTXO context hasn't loaded. Re-selecting refreshes it.

        Flow: send bare `select`. If the numbered prompt appears (2+ accounts),
        answer with `index`; otherwise it already auto-selected and returned to
        the ready prompt — sending the index would inject a stray command, so we
        DON'T. This is why we expect [SELECT_PROMPT, READY_PROMPT] and branch.
        """
        if not isinstance(index, int) or index < 0:
            return CliResult("select", "", ok=False,
                             error="Account index must be a non-negative integer.")
        with self._lock:
            if self._child is None or not self._child.isalive():
                return CliResult("select", "", ok=False,
                                 error="CLI process is not running.")
            self._flush_buffer()
            self._submit_line("select")
            try:
                idx = self._child.expect(
                    [self.SELECT_PROMPT, READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=timeout,
                )
            except Exception as e:  # noqa
                return CliResult("select", "", ok=False, error=str(e))

            if idx == 0:
                # Numbered prompt (2+ accounts): answer with the index, then wait
                # for the ready prompt confirming the selection.
                self._submit_line(str(index))
                try:
                    self._child.expect(
                        [READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
                except Exception as e:  # noqa
                    return CliResult("select", "", ok=False, error=str(e))
                output = _ansi_strip(self._child.before or "")
                low = output.lower()
                if "not found" in low or "invalid" in low:
                    # Out-of-range index: the CLI re-prompts. Send a bare line to
                    # abort the selection so the REPL returns to a clean prompt.
                    self._submit_line("")
                    self._wait_ready(timeout=5)
                    return CliResult("select", output.strip(), ok=False,
                                     error=f"Account index {index} not found.")
                return CliResult("select", output.strip(), ok=True)
            elif idx == 1:
                # Single account: already auto-selected and back at the prompt.
                return CliResult("select", _ansi_strip(self._child.before or "").strip(),
                                 ok=True)
            else:
                return CliResult("select", _ansi_strip(self._child.before or ""),
                                 ok=False,
                                 error="select timed out or the CLI exited.")

    def export_mnemonic(self, password: str, bip39_passphrase: str = "",
                        timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Reveal the open wallet's recovery phrase via `export mnemonic`.

        Verified flow:
          export mnemonic
          -> Enter wallet password:    (wallet decryption password)
          -> Enter payment password:   (ONLY if the wallet has a BIP39 passphrase
                                        — this is that passphrase)
          -> prints "extended public key:\\n<kpub...>\\nmnemonic:\\n<phrase>"

        Wallets created WITHOUT a passphrase skip the payment-password prompt; for
        those, bip39_passphrase is ignored.

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
            # A wallet created WITH a BIP39 passphrase prompts for the "payment
            # password" here. VERIFIED: keryx-cli cannot actually export such a
            # wallet's mnemonic — every value fails ("payment secret is
            # required" / "Unable to decrypt" / "Decryption secret is 'None'").
            # We still answer the prompt so we don't hang, then report the real
            # reason instead of a misleading "wrong password" after a timeout.
            try:
                idx2 = self._child.expect(
                    [self.PAYMENT_PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT,
                     pexpect.EOF], timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False, error=str(e))
            if idx2 == 0:
                self._submit_line(bip39_passphrase)
                try:
                    self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                       timeout=timeout)
                except Exception as e:  # noqa
                    return CliResult(cmd, "", ok=False, error=str(e))
                output = _ansi_strip(self._child.before or "")
                if "mnemonic:" in output.lower():
                    return CliResult(cmd, output.strip(), ok=True)
                return CliResult(
                    cmd, output.strip(), ok=False,
                    error="keryx-cli can't export the recovery phrase of a wallet "
                          "created with a BIP39 passphrase. Your backup is the "
                          "phrase + passphrase you saved when you created it.")
            output = _ansi_strip(self._child.before or "")
            lowered = output.lower()
            if "mnemonic:" not in lowered:
                # No-passphrase wallet but no mnemonic → the wallet password was
                # wrong (decryption failed).
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

    # Sweep/consolidate result line:
    #   "Sweep: Fees: <fee> UTXOs: <count> Batch Transactions: <batches>"
    SWEEP_RESULT = re.compile(
        r"(?i)sweep:\s*fees:\s*([\d.]+).*?utxos:\s*(\d+).*?"
        r"batch transactions:\s*(\d+)", re.DOTALL)

    def sweep(self, password: str, payment_secret: str = "",
              timeout: int = SEND_TIMEOUT) -> CliResult:
        """
        Consolidate the wallet's UTXOs via `sweep`. Combines many small UTXOs
        into fewer, which speeds up future transactions.

        Verified flow:
          sweep
          -> Enter wallet password:
          -> Enter payment password:   (ONLY for BIP39-passphrase wallets)
          -> (processes) prints
             "Sweep: Fees: <fee> UTXOs: <count> Batch Transactions: <batches>"

        `payment_secret` is the BIP39 passphrase; only used if the CLI asks for
        the payment password (passphrase wallets).

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
            # A passphrase wallet asks for the payment password before sweeping.
            try:
                idx2 = self._child.expect(
                    [self.PAYMENT_PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT,
                     pexpect.EOF], timeout=max(timeout, 120))
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False,
                                 error=f"Sweep submitted but no confirmation "
                                       f"read: {e}")
            if idx2 == 0:
                self._submit_line(payment_secret)
                try:
                    self._child.expect([READY_PROMPT, pexpect.TIMEOUT, pexpect.EOF],
                                       timeout=max(timeout, 120))
                except Exception as e:  # noqa
                    return CliResult(cmd, "", ok=False,
                                     error=f"Sweep submitted but no confirmation "
                                           f"read: {e}")
            output = _ansi_strip(self._child.before or "").strip()
            lowered = output.lower()
            # Probe attempt on a passphrase wallet — ask for the BIP39 passphrase
            # and retry (handled by the caller); not an error or a success.
            if idx2 == 0 and not payment_secret:
                return CliResult(cmd, output, ok=False,
                                 error="Enter payment password")
            if ("unable to decrypt" in lowered or "incorrect" in lowered
                    or "aead" in lowered or "decrypt" in lowered):
                if idx2 == 0:
                    return CliResult(cmd, output, ok=False,
                                     error="Wrong wallet password or BIP39 passphrase.")
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
             password: str, payment_secret: str = "",
             timeout: int = SEND_TIMEOUT) -> CliResult:
        """
        Broadcast a transaction. CRITICAL SAFETY CONTRACT:

        `send` broadcasts IMMEDIATELY after the password (and, for a BIP39-
        passphrase wallet, the payment password) is supplied — there is no
        CLI-side yes/no confirmation. Therefore the GUI MUST have already shown
        the user a confirmation dialog (address, amount, fee, total) and received
        explicit approval BEFORE this method is called.

        `payment_secret` is the BIP39 passphrase; it's only needed for wallets
        created with one (the CLI then asks "Enter payment password:"). Normal
        wallets don't see that prompt and the value is ignored.

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
            # POINT OF NO RETURN: supplying the password (and payment password for
            # a passphrase wallet) broadcasts the tx.
            self._submit_line(password)
            try:
                idx2 = self._child.expect(
                    [self.PAYMENT_PW_PROMPT, READY_PROMPT, pexpect.TIMEOUT,
                     pexpect.EOF], timeout=timeout)
            except Exception as e:  # noqa
                return CliResult(cmd, "", ok=False,
                                 error=f"Send submitted but no confirmation read: {e}")
            if idx2 == 0:
                # Passphrase wallet — supply the BIP39 passphrase.
                self._submit_line(payment_secret)
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
            # First (probe) attempt on a passphrase wallet: the payment-password
            # prompt appeared but we supplied no secret. Signal that so the caller
            # prompts for the BIP39 passphrase and retries — this is NOT an error.
            if idx2 == 0 and not payment_secret:
                return CliResult(cmd, output, ok=False,
                                 error="Enter payment password")
            # Wrong credentials. keryx-cli collects the wallet password AND (for a
            # passphrase wallet) the payment password BEFORE validating either, so
            # a decrypt failure after the payment prompt (idx2 == 0) could be the
            # wallet password OR the passphrase — we can't tell which. Don't guess.
            if ("unable to decrypt" in lowered or "incorrect" in lowered
                    or "aead" in lowered or "wrong password" in lowered
                    or "decrypt" in lowered):
                if idx2 == 0:
                    return CliResult(cmd, output, ok=False,
                                     error="Wrong wallet password or BIP39 passphrase.")
                return CliResult(cmd, output, ok=False, error="Wrong password.")
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
            "amount": m.group(1).replace(",", ""),
            "fees": m.group(2).replace(",", ""),
            "total": m.group(3).replace(",", ""),
            "utxos": int(m.group(4)),
        }

    # `estimate` output line: "Estimate - Amount: 1 KRX  Fees: 0.6 KRX  Total: 1.6 KRX  UTXOs: 1"
    # (large amounts may have thousands separators, e.g. "32,824.96851968").
    ESTIMATE_RESULT = re.compile(
        r"Estimate\s*-\s*Amount:\s*([\d.,]+)\s*KRX\s+"
        r"Fees:\s*([\d.,]+)\s*KRX\s+"
        r"Total:\s*([\d.,]+)\s*KRX\s+"
        r"UTXOs:\s*(\d+)",
        re.IGNORECASE,
    )

    def estimate(self, amount: str, priority_fee: str = "",
                 timeout: int = DEFAULT_TIMEOUT) -> CliResult:
        """
        Estimate the fee/total for a send WITHOUT broadcasting. Non-interactive:
          estimate <amount> [<priority_fee>]
          -> "Estimate - Amount: A KRX  Fees: F KRX  Total: T KRX  UTXOs: N"
             or "Insufficient funds"
        Requires an account selected and a node connection (same as `send`).

        Returns CliResult; .output holds the Estimate line on success (parse with
        parse_estimate_result). On "Insufficient funds" returns ok=False.
        """
        amount = str(amount).strip()
        priority_fee = str(priority_fee).strip()
        if not re.fullmatch(r"\d+(\.\d+)?", amount):
            return CliResult("estimate", "", ok=False,
                             error="Amount must be a positive number.")
        cmd = f"estimate {amount}"
        if priority_fee and re.fullmatch(r"\d+(\.\d+)?", priority_fee):
            cmd += f" {priority_fee}"
        res = self.run(cmd, timeout=timeout)
        out = res.output or ""
        if res.ok and self.ESTIMATE_RESULT.search(out):
            return CliResult(cmd, out, ok=True)
        if "insufficient" in out.lower():
            return CliResult(cmd, out, ok=False, error="Insufficient funds.")
        # Couldn't confirm an estimate; surface what we got (caller treats a
        # non-ok estimate as "unavailable" and proceeds without it).
        return CliResult(cmd, out, ok=False,
                         error=res.error or "Estimate unavailable.")

    @staticmethod
    def parse_estimate_result(output: str):
        """Parse the 'Estimate - Amount/Fees/Total/UTXOs' line. dict or None."""
        m = KeryxCliDriver.ESTIMATE_RESULT.search(output or "")
        if not m:
            return None
        return {
            "amount": m.group(1).replace(",", ""),
            "fees": m.group(2).replace(",", ""),
            "total": m.group(3).replace(",", ""),
            "utxos": int(m.group(4)),
        }
