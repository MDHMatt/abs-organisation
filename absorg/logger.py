"""Colored logging with simultaneous stdout + file output."""

from __future__ import annotations

import sys

# ANSI escape codes
_RED = "\033[0;31m"
_YELLOW = "\033[1;33m"
_GREEN = "\033[0;32m"
_CYAN = "\033[0;36m"
_MAGENTA = "\033[0;35m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


class AbsorgLogger:
    """Dual-output logger: colored stdout (when TTY) + plain-text log file."""

    def __init__(self, log_path: str) -> None:
        self.use_color = sys.stdout.isatty()
        # Log file is truncated at the start of each run (mode 'w'), not appended.
        import os
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        self._file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115

    # -- public helpers -------------------------------------------------------

    def bold(self, text: object) -> str:
        """Wrap *text* in bold ANSI codes when color is enabled."""
        if self.use_color:
            return f"{_BOLD}{text}{_RESET}"
        return str(text)

    def close(self) -> None:
        self._file.flush()
        self._file.close()

    # -- log methods (match the original bash helpers) ------------------------

    def log(self, msg: str = "") -> None:
        self._emit(msg)

    def logr(self, msg: str) -> None:
        """Red - errors."""
        self._emit(msg, _RED)

    def logy(self, msg: str) -> None:
        """Yellow - warnings / dry-run notes."""
        self._emit(msg, _YELLOW)

    def logg(self, msg: str) -> None:
        """Green - success / files moved."""
        self._emit(msg, _GREEN)

    def logc(self, msg: str) -> None:
        """Cyan - file paths being processed."""
        self._emit(msg, _CYAN)

    def logm(self, msg: str) -> None:
        """Magenta - deduplication events."""
        self._emit(msg, _MAGENTA)

    def logd(self, msg: str) -> None:
        """Dim - skipped / low-priority."""
        self._emit(msg, _DIM)

    # -- internals ------------------------------------------------------------

    def _emit(self, msg: str, color: str = "") -> None:
        # stdout: with color when available, handle encoding errors on Windows
        try:
            if self.use_color and color:
                print(f"{color}{msg}{_RESET}", flush=True)
            else:
                print(msg, flush=True)
        except UnicodeEncodeError:
            safe = msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8", errors="replace"
            )
            if self.use_color and color:
                print(f"{color}{safe}{_RESET}", flush=True)
            else:
                print(safe, flush=True)
        # file: always plain text (UTF-8, no encoding issues)
        self._file.write(msg + "\n")
        self._file.flush()
