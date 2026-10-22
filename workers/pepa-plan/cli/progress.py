"""Animated single-step spinner that collapses to a ✓ line; no-op off-TTY."""
import sys
import threading
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CHECK = "✓"
_LABEL_W = 22


class StepSpinner:
    """Animated spinner for a single step. No-op when stderr is not a TTY."""

    def __init__(self, label: str):
        self._label = label
        self._stop = threading.Event()
        self._thread = None

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = _FRAMES[i % len(_FRAMES)]
            try:
                sys.stderr.write(f"\r  {frame}  {self._label:<{_LABEL_W}}")
                sys.stderr.flush()
            except Exception:
                pass
            time.sleep(0.08)
            i += 1

    def start(self) -> None:
        if sys.stderr.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()

    def done(self, summary: str = "") -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        safe = summary.encode("ascii", "replace").decode("ascii")
        suffix = f"  {safe}" if safe else ""
        if sys.stderr.isatty():
            try:
                sys.stderr.write(f"\r  {_CHECK}  {self._label:<{_LABEL_W}}{suffix}\n")
            except UnicodeEncodeError:
                sys.stderr.write(f"\r  *  {self._label:<{_LABEL_W}}{suffix}\n")
            sys.stderr.flush()
        else:
            print(f"  {self._label}... {safe}", file=sys.stderr)
