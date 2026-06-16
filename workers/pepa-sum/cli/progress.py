"""Animated step/progress spinners that collapse to a ✓ line; no-op off-TTY."""
import sys, threading, time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CHECK = "✓"
_LABEL_W = 22


def _fmt_secs(seconds):
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class StepSpinner:
    """Animated spinner for a single step. No-op when stdout is not a TTY."""

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
        safe = summary.encode("ascii", "replace").decode("ascii")
        suffix = f"  {safe}" if safe else ""
        if sys.stdout.isatty():
            try:
                sys.stdout.write(f"\r  {_CHECK}  {self._label:<{_LABEL_W}}{suffix}\n")
            except UnicodeEncodeError:
                sys.stdout.write(f"\r  *  {self._label:<{_LABEL_W}}{suffix}\n")
            sys.stdout.flush()
        else:
            print(f"  {self._label}... {safe}")


class ProgressSpinner:
    """Animated spinner backed by real [i/N] progress + ETA, for a phase whose
    items complete incrementally (e.g. the local read stage).

    Call advance() as each item finishes. On a TTY a background thread redraws a
    single line; off-TTY animation is suppressed and a plain line is printed every
    few items so logs still show progress. Always close with done()."""

    _CLEAR = "\r" + " " * 78 + "\r"

    def __init__(self, label, total):
        self._label = label
        self._total = max(1, total)
        self._count = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._t0 = None
        self._tty = sys.stdout.isatty()

    def _line(self, frame):
        with self._lock:
            i = self._count
        elapsed = time.time() - self._t0
        eta = (elapsed / i) * (self._total - i) if i else 0.0
        return (f"\r  {frame}  {self._label}  [{i}/{self._total}]  "
                f"{_fmt_secs(elapsed)} elapsed, ~{_fmt_secs(eta)} left")

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            try:
                sys.stdout.write(self._line(_FRAMES[i % len(_FRAMES)]))
                sys.stdout.flush()
            except Exception:
                pass
            time.sleep(0.1)
            i += 1

    def start(self):
        self._t0 = time.time()
        if self._tty:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()

    def advance(self, n=1):
        with self._lock:
            self._count += n
            count = self._count
        if not self._tty and (count % 25 == 0 or count == self._total):
            print(f"  {self._label} {count}/{self._total}")

    def log(self, msg):
        """Print a persistent line above the live progress line; the spinner
        redraws beneath it on its next tick. Lets a phase show per-item results
        (which paper just finished/failed) while the [i/N]+ETA bar stays pinned
        at the bottom. Off-TTY it just prints the line."""
        with self._lock:
            if self._tty:
                try:
                    sys.stdout.write(self._CLEAR + msg + "\n")
                except UnicodeEncodeError:
                    sys.stdout.write(self._CLEAR
                                     + msg.encode("ascii", "replace").decode("ascii") + "\n")
                sys.stdout.flush()
            else:
                print(msg)

    def done(self, summary=""):
        self._stop.set()
        if self._thread:
            self._thread.join()
        elapsed = time.time() - self._t0 if self._t0 else 0.0
        safe = (summary or f"{self._count}/{self._total} in {_fmt_secs(elapsed)}")
        safe = safe.encode("ascii", "replace").decode("ascii")
        if self._tty:
            try:
                sys.stdout.write(f"{self._CLEAR}  {_CHECK}  {self._label}  {safe}\n")
            except UnicodeEncodeError:
                sys.stdout.write(f"{self._CLEAR}  *  {self._label}  {safe}\n")
            sys.stdout.flush()
        else:
            print(f"  {self._label}... {safe}")
