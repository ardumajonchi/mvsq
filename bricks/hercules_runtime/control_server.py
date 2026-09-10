# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
"""Sidecar HTTP control API for the hercules_runtime Brick. Runs inside the SAME container as
Hercules (see entrypoint.sh) so it can shell out to the apt-installed `s3270` client and have it
connect to Hercules's local 3270 terminal pool over 127.0.0.1:3270 -- no cross-container 3270
traffic is needed at all. The main app container has neither the `s3270` binary nor a route to
speak raw TN3270 itself (it's the non-root, non-apt-privileged python-apps-base image); its
python/engine/mainframe.py is a thin HTTP client for the two routes below instead.

Endpoints:
  GET  /healthz -- 200 once s3270 can actually reach Hercules's 3270 listener (not just "the
                   control server process is up"); 503 otherwise. This is what brick_compose.yaml's
                   healthcheck polls -- see its start_period comment for why a cold MVS 3.8j IPL
                   needs ~20-30s before this ever returns 200.
  GET  /screen  -- {"connected": bool, "rows": [...] (24 lines, empty if disconnected),
                    "cursor": {"row": int, "col": int}}
  POST /key     -- body is one action dict, the exact same shape as the app's own WebUI "key"
                   event (see python/main.py's docstring): {"text": "..."} / {"enter": true} /
                   {"tab": true} / {"backtab": true} / {"clear": true} / {"pf": 1-24} /
                   {"up": true} / {"down": true} / {"left": true} / {"right": true} /
                   {"reset": true}. Executes it against the live 3270 session, then returns the
                   updated /screen snapshot. "reset" sends s3270's Reset() action, which clears a
                   locally-locked keyboard (status line's "L"/"E" indicator) left behind by a
                   benign operator-error condition -- distinct from "clear", which sends the
                   host-facing CLEAR AID and doesn't touch a purely local lock.

s3270 scripting protocol: one action per stdin line; each gets back zero-or-more "data: <line>"
rows, one status line, then a closing "ok"/"error" line -- see
http://x3270.bgp.nu/Man3270.html for the full action/status grammar. Reused directly here rather
than through the py3270 PyPI wrapper, which hasn't been updated in years and isn't confirmed to
work on this container's Python version.
"""

from __future__ import annotations

import select
import subprocess
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

HERCULES_HOST = "127.0.0.1"
HERCULES_PORT = 3270
CONTROL_PORT = 3271
_ACTION_TIMEOUT = 15.0

_EMPTY_SCREEN = {"connected": False, "rows": [], "cursor": {"row": 0, "col": 0}}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class Mainframe:
    """One persistent s3270 subprocess for the container's lifetime. s3270's scripting protocol
    is strictly one-action-in/one-block-out, so every call is serialized behind a single lock --
    there's no benefit to concurrency here, only risk of interleaving two actions' output."""

    def __init__(self, host: str = HERCULES_HOST, port: int = HERCULES_PORT):
        self._host = host
        self._port = port
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._connected = False

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _spawn(self) -> None:
        self._proc = subprocess.Popen(
            ["s3270"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._connected = False

    def _run_action(self, action: str) -> tuple[list[str], str, bool]:
        if not self._alive():
            self._spawn()
        assert self._proc and self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(action + "\n")
        self._proc.stdin.flush()
        data_lines: list[str] = []
        status_line = ""
        first_line = True
        while True:
            # A wedged s3270 (e.g. Hercules stops responding mid-action) would otherwise block
            # readline() forever, holding _lock and wedging every future request -- found live:
            # /healthz itself hung indefinitely instead of just returning 503. select() with a
            # timeout turns that hang into a raised exception, which releases the lock and lets
            # the next connect() kill+respawn a clean subprocess instead of deadlocking forever.
            # Only guard the FIRST line of each response: once s3270 starts replying, the whole
            # block (data lines + status + ok/error) is already generated and typically arrives
            # in one OS-level read, so readline() serves the rest straight out of TextIOWrapper's
            # own internal buffer with no further OS read -- select() on the raw fd would then
            # see "nothing new" and falsely report not-ready for those lines (found live: this
            # produced a reconnect storm on any multi-line response, e.g. Ascii's full screen).
            if first_line:
                ready, _, _ = select.select([self._proc.stdout], [], [], _ACTION_TIMEOUT)
                if not ready:
                    self._proc.kill()
                    raise TimeoutError(f"s3270 did not respond to {action!r} within {_ACTION_TIMEOUT}s")
                first_line = False
            line = self._proc.stdout.readline()
            if line == "":
                raise ConnectionError("s3270 subprocess ended unexpectedly")
            line = line.rstrip("\n")
            if line in ("ok", "error"):
                return data_lines, status_line, line == "ok"
            if line.startswith("data: "):
                data_lines.append(line[len("data: "):])
            else:
                status_line = line

    def connect(self) -> bool:
        """Idempotent -- a no-op fast path once already connected, so the Compose healthcheck
        (which calls this every 10s via /healthz) doesn't reconnect on every poll."""
        with self._lock:
            if self._connected:
                return True
            try:
                # Always start from a fresh subprocess when reconnecting -- a stale-but-alive
                # s3270 process that already has an open TN3270 connection will itself error out
                # on a second Connect(), permanently wedging recovery (found live: a benign
                # action-level error used to flip _connected False with the process still
                # attached to its old device, and every subsequent reconnect attempt then failed
                # the same way forever).
                if self._alive():
                    self._proc.kill()
                self._spawn()
                _, _, ok = self._run_action(f"Connect({self._host}:{self._port})")
                if not ok:
                    return False
                self._connected = True
                try:
                    self._run_action("Wait(5,InputField)")
                except Exception:
                    pass  # best-effort settle; a slow/unusual screen state shouldn't fail connect()
                return True
            except Exception as exc:
                print(f"[hercules_runtime] Mainframe.connect() failed: {exc!r}")
                self._connected = False
                return False

    @staticmethod
    def _parse_cursor(status_line: str) -> tuple[int, int]:
        try:
            fields = status_line.split()
            return int(fields[8]), int(fields[9])
        except (IndexError, ValueError):
            return 0, 0

    def snapshot(self) -> dict:
        with self._lock:
            if not self._connected:
                return dict(_EMPTY_SCREEN)
            try:
                data_lines, status_line, ok = self._run_action("Ascii")
                if not ok:
                    self._connected = False
                    return dict(_EMPTY_SCREEN)
                row, col = self._parse_cursor(status_line)
                return {"connected": True, "rows": data_lines, "cursor": {"row": row, "col": col}}
            except Exception as exc:
                print(f"[hercules_runtime] Mainframe.snapshot() failed: {exc!r}")
                self._connected = False
                return dict(_EMPTY_SCREEN)

    def act(self, action: str) -> bool:
        with self._lock:
            if not self._connected:
                return False
            try:
                _, status_line, ok = self._run_action(action)
                # An "error" status here (e.g. "Keyboard locked") means THIS action was
                # rejected -- routine during screen transitions -- not that the TN3270
                # connection itself is down. Treating it as a hard disconnect (as this used to)
                # tore down a perfectly live session on a single benign hiccup, and reconnecting
                # a still-alive-but-already-connected s3270 subprocess then failed the same way
                # forever with no recovery. Only an actual exception below means the connection
                # is really gone.
                if not ok:
                    print(f"[hercules_runtime] Mainframe action {action!r} rejected: {status_line!r}")
                return ok
            except Exception as exc:
                print(f"[hercules_runtime] Mainframe action {action!r} failed: {exc!r}")
                self._connected = False
                return False

    def send_text(self, text: str) -> bool:
        return self.act(f'String("{_escape(text)}")')

    def press_enter(self) -> bool:
        return self.act("Enter()")

    def press_tab(self) -> bool:
        return self.act("Tab()")

    def press_backtab(self) -> bool:
        return self.act("BackTab()")

    def press_clear(self) -> bool:
        return self.act("Clear()")

    def press_pf(self, n: int) -> bool:
        if not 1 <= n <= 24:
            return False
        return self.act(f"PF({n})")

    def press_up(self) -> bool:
        return self.act("Up()")

    def press_down(self) -> bool:
        return self.act("Down()")

    def press_left(self) -> bool:
        return self.act("Left()")

    def press_right(self) -> bool:
        return self.act("Right()")

    def press_reset(self) -> bool:
        # Clears a locked keyboard (status line's "L"/"E" indicator) left behind by an
        # operator-error condition (e.g. TSO's IKJ56429A REENTER prompt) -- found live: without
        # this, a locked keyboard rejected every subsequent action forever, with no recovery
        # short of restarting the whole container.
        return self.act("Reset()")


mainframe = Mainframe()
app = FastAPI(title="hercules_runtime control")


@app.get("/healthz")
def healthz():
    if mainframe.connect():
        return {"status": "ok"}
    return JSONResponse({"status": "not ready"}, status_code=503)


@app.get("/screen")
def screen():
    mainframe.connect()
    return mainframe.snapshot()


@app.post("/key")
async def key(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    data = data or {}

    if mainframe.connect():
        if "text" in data:
            mainframe.send_text(str(data["text"]))
        elif data.get("enter"):
            mainframe.press_enter()
        elif data.get("tab"):
            mainframe.press_tab()
        elif data.get("backtab"):
            mainframe.press_backtab()
        elif data.get("clear"):
            mainframe.press_clear()
        elif "pf" in data:
            try:
                mainframe.press_pf(int(data["pf"]))
            except (TypeError, ValueError):
                pass
        elif data.get("up"):
            mainframe.press_up()
        elif data.get("down"):
            mainframe.press_down()
        elif data.get("left"):
            mainframe.press_left()
        elif data.get("right"):
            mainframe.press_right()
        elif data.get("reset"):
            mainframe.press_reset()

    return mainframe.snapshot()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=CONTROL_PORT)
