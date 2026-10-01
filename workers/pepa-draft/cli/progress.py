import sys
import threading
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CHECK = "✓"
_LABEL_W = 22
_BAR_W = 20


class StepSpinner:
    """Animated spinner for a single pipeline step. No-op when stdout is not a TTY."""

    def __init__(self, label: str):
        self._label = label
        self._stop = threading.Event()
        self._thread = None

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = _FRAMES[i % len(_FRAMES)]
            try:
                sys.stdout.write(f"\r  {frame}  {self._label:<{_LABEL_W}}")
                sys.stdout.flush()
            except Exception:
                pass
            time.sleep(0.08)
            i += 1

    def start(self) -> None:
        if sys.stdout.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()

    def done(self, summary: str = "") -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        safe_summary = summary.encode("ascii", "replace").decode("ascii")
        suffix = f"  {safe_summary}" if safe_summary else ""
        if sys.stdout.isatty():
            try:
                sys.stdout.write(f"\r  {_CHECK}  {self._label:<{_LABEL_W}}{suffix}\n")
            except UnicodeEncodeError:
                sys.stdout.write(f"\r  *  {self._label:<{_LABEL_W}}{suffix}\n")
            sys.stdout.flush()
        else:
            print(f"  {self._label}... {safe_summary}")
