"""Drive a child app as a subprocess in its own directory, passing
`--no-input` when supported and never a secret in argv, streaming stderr
line by line as it arrives.
"""
import asyncio
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from registry import Command, get_app, get_command


@dataclass
class Result:
    returncode: int
    stdout: str


async def _stream_lines(stream, handle_line) -> None:  # lint-style: ignore FN004
    """Hand every line the stream produces to `handle_line` as it arrives."""
    async for raw in stream:
        handle_line(raw.decode(errors="replace").rstrip("\n"))


async def _read_all(stream) -> str:
    """Everything the stream produces, decoded once at the end."""
    chunks = []
    async for raw in stream:
        chunks.append(raw)
    return b"".join(chunks).decode(errors="replace")


def _to_stderr(line: str) -> None:  # lint-style: ignore FN004
    print(line, file=sys.stderr)


def build_argv(command: Command, extra_flags: Sequence[str] = ()) -> list[str]:
    argv = [sys.executable, "manage.py"]
    if command.no_input:
        argv.append("--no-input")
    argv.extend([command.name, *command.default_flags, *extra_flags])
    return argv


async def run_command(
    app_name: str,
    command_name: str,
    on_stderr: Callable[[str], None],
    on_start: Callable[[int], None] | None = None,
    extra_flags: Sequence[str] = (),
) -> Result:
    """Spawn `app_name`'s `command_name`, streaming stderr to `on_stderr`.

    Args:
        on_stderr: called once per stderr line as it arrives (live log).
        on_start: called with the child PID once it has spawned.
        extra_flags: extra argv appended after the command's default flags.

    Returns:
        Result(returncode, stdout): stdout captured whole as the payload.

    Raises:
        ValueError: the app/command is unknown or interactive-only.
    """
    app = get_app(app_name)
    command = get_command(app_name, command_name)
    if app is None or command is None:
        raise ValueError(f"unknown command: {app_name} {command_name}")
    if command.kind in ("interactive", "terminal", "service"):
        raise ValueError(f"{app_name} {command_name} does not finish on its own, run it in a terminal")

    proc = await asyncio.create_subprocess_exec(
        *build_argv(command, extra_flags),
        cwd=str(app.path),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if on_start and proc.pid:
        on_start(proc.pid)

    try:
        _, stdout = await asyncio.gather(
            _stream_lines(proc.stderr, on_stderr),
            _read_all(proc.stdout),
        )
        returncode = await proc.wait()
    except asyncio.CancelledError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
        raise

    return Result(returncode, stdout)


def run_blocking(app_name: str, command_name: str, extra_flags: Sequence[str] = ()) -> int:
    """Headless face: stream stderr to our stderr, stdout to our stdout, return code."""
    result = asyncio.run(
        run_command(app_name, command_name, on_stderr=_to_stderr, extra_flags=extra_flags)
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    return result.returncode
