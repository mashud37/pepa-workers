"""Run the orchestration TUI: a command tree, live log, and reactive
sidebar. Picking a command spawns the child as a subprocess and streams
its stderr live; children are never imported.
"""
import time
from collections.abc import Sequence

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, RichLog, Static, Tree

from registry import APPS, KIND_SYMBOL, Command
from runner import run_command

STATUS_STYLE = {"running": "yellow", "ok": "green", "failed": "red", "idle": "dim"}
STATUS_SYMBOL = {"running": "▶", "ok": "✓", "failed": "✗", "idle": "·"}


class Confirm(ModalScreen[bool]):
    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Grid(id="confirm"):
            yield Label(self.prompt, id="confirm-text")
            yield Button("Run", variant="warning", id="yes")
            yield Button("Cancel", variant="default", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class Sidebar(Static):
    app_name = reactive("-")
    command = reactive("-")
    kind = reactive("-")
    pid = reactive(0)
    status = reactive("idle")
    elapsed = reactive(0.0)
    exit_code = reactive[int | None](None)
    last_line = reactive("")

    def render(self) -> Text:
        s = self.status
        t = Text()
        t.append("JOB\n", style="bold")
        t.append(f"{self.app_name}\n", style="bold white")
        t.append(f"{self.command}\n\n", style="cyan")
        t.append(f"{STATUS_SYMBOL[s]} {s}\n", style=f"bold {STATUS_STYLE[s]}")
        t.append("kind     ", style="dim")
        t.append(f"{self.kind}\n", style="white")
        t.append("pid      ", style="dim")
        t.append(f"{self.pid or '-'}\n", style="white")
        t.append("elapsed  ", style="dim")
        t.append(f"{self.elapsed:5.1f}s\n", style="white")
        t.append("exit     ", style="dim")
        if self.exit_code is None:
            t.append("-\n", style="white")
        else:
            t.append(f"{self.exit_code}\n", style="green" if self.exit_code == 0 else "red")
        t.append("\nlast\n", style="dim")
        t.append(self.last_line[-220:] or "-", style="dim white")
        return t


def _app_tree() -> Tree:
    """The picker tree: every app, with the commands it offers under it."""
    tree: Tree = Tree("apps")
    tree.root.expand()
    for app in APPS:
        branch = tree.root.add(app.name, expand=True)
        for cmd in app.commands:
            label = f"{KIND_SYMBOL[cmd.kind]} {cmd.name}  "
            leaf = branch.add_leaf(label, data=(app.name, cmd))
            if cmd.kind == "interactive":
                leaf.label = Text(label, style="dim strike")
    return tree


class ConsoleApp(App):
    CSS = """
    Tree { width: 46; border: round $primary; padding: 0 1; }
    RichLog { border: round $secondary; padding: 0 1; }
    Sidebar { width: 34; dock: right; border: round $accent; background: $panel; padding: 1 2; }
    #confirm { align: center middle; grid-size: 2; grid-rows: auto auto; padding: 1 2;
               width: 60; height: auto; border: thick $warning; background: $surface; }
    #confirm-text { column-span: 2; padding-bottom: 1; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("x", "clear", "Clear log")]
    TITLE = "pepa-console"
    SUB_TITLE = "orchestrating pepa-worker/*"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield _app_tree()
            yield RichLog(id="log", markup=True, wrap=True, highlight=False)
            yield Sidebar()
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.25, self._tick)
        self._running_since: float | None = None
        self._pending = None
        self._log("· pick a command on the left. safe (·) run immediately, "
                  "heavy (▶) confirm first, interactive (✗) open in a terminal.")

    # ---- Helpers ----
    def _log(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    def _tick(self) -> None:
        if self._running_since is not None:
            self.query_one(Sidebar).elapsed = time.monotonic() - self._running_since

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data:
            return
        app_name, cmd = data
        if cmd.kind == "interactive":
            self._log(f"⚠ [yellow]{app_name} {cmd.name}[/] is interactive-only, "
                      f"run it in a terminal: [dim]python {app_name}/manage.py {cmd.name}[/]")
            return
        if cmd.kind == "heavy":
            prompt = f"Run {app_name} {cmd.name}? This does real work and may cost money."
            self._pending = (app_name, cmd)
            self.push_screen(Confirm(prompt), self._on_confirm)
            return
        self.launch(app_name, cmd)

    def _on_confirm(self, confirmed: bool) -> None:
        """Launch the command the confirmation screen was asking about."""
        app_name, cmd = self._pending
        self._pending = None
        if confirmed:
            self.launch(app_name, cmd)

    # ---- Job lifecycle ----
    def _job_line(self, line: str) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.last_line = line
        self._log(f"  [dim]{sidebar.app_name}[/] {line}")

    def _job_start(self, pid: int) -> None:
        self.query_one(Sidebar).pid = pid

    def launch(self, app_name: str, cmd: Command, extra_flags: Sequence[str] = ()) -> None:
        sb = self.query_one(Sidebar)
        sb.app_name, sb.command, sb.kind = app_name, cmd.name, cmd.kind
        sb.status, sb.pid, sb.exit_code, sb.last_line = "running", 0, None, ""
        self._running_since = time.monotonic()
        shown = " ".join([cmd.name, *cmd.default_flags, *extra_flags])
        self._log(f"\n▶ [bold]{app_name}[/] {shown}")
        self._run_job(app_name, cmd, tuple(extra_flags))

    @work(exclusive=False)
    async def _run_job(self, app_name: str, cmd: Command, extra_flags: tuple[str, ...]) -> None:
        sb = self.query_one(Sidebar)
        try:
            result = await run_command(app_name, cmd.name, self._job_line, self._job_start,
                                       extra_flags)
        except Exception as exc:  # noqa: BLE001 (surface any spawn failure in the log)
            sb.status, sb.last_line = "failed", str(exc)
            self._log(f"  [red]✗ {exc}[/]")
            self._running_since = None
            return

        self._running_since = None
        sb.exit_code = result.returncode
        if result.returncode == 0:
            sb.status = "ok"
            self._log(f"  [green]✓ {app_name} {cmd.name} done[/]")
        else:
            sb.status = "failed"
            self._log(f"  [red]✗ {app_name} {cmd.name} exited {result.returncode}[/], "
                      f"[dim]try: python {app_name}/manage.py install[/]")
        if result.stdout.strip():
            self._log(f"  [dim]stdout:[/]\n{result.stdout.rstrip()}")

    def action_clear(self) -> None:
        self.query_one("#log", RichLog).clear()


def run() -> None:
    ConsoleApp().run()
