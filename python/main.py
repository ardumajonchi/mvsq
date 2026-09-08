# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
"""Orchestrator: wires engine.mainframe.Mainframe (an HTTP client for the hercules_runtime Brick's
control API) to the arduino:web_ui Brick.

There is exactly one shared 3270 session for the whole app -- every open browser tab is looking
at (and typing into) the same terminal, the same way a second person walking up to a real 3270
terminal would see and affect the same session as the first, not get their own. That's a
deliberate MVP simplification; per-tab sessions would need Hercules's device pool (00C0-00C7, up
to 8 concurrent terminals) wired up individually, which is future scope, not this phase's.

A background thread polls GET /screen (via Mainframe.screen()) roughly once a second and
broadcasts a "state" message whenever it changes -- this is what surfaces MVS's own unsolicited
console/JES2 output (job completion messages, etc.) even if nobody in the browser is actively
typing, and it's also what notices hercules_runtime coming back "connected" once it finishes
booting, with no app restart needed.

WebUI message protocol:
  server -> client, event "state":
    {"connected": bool, "rows": ["...", ...] (24 lines, empty if disconnected),
     "cursor": {"row": int, "col": int}}
  client -> server, event "key": (forwarded verbatim to the Brick's POST /key)
    {"text": "..."}     -- type a literal string at the current cursor position
    {"enter": true}     -- AID Enter
    {"tab": true} / {"backtab": true}
    {"pf": 3}            -- PF1-PF24
    {"clear": true}      -- AID Clear
"""

from __future__ import annotations

import threading
import time

from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App

from engine.mainframe import Mainframe

_POLL_SECONDS = 1.0


def main():
    mainframe = Mainframe()
    ui = WebUI()

    state_lock = threading.Lock()
    last_state: dict = {}

    def broadcast_if_changed(state: dict) -> None:
        nonlocal last_state
        with state_lock:
            if state == last_state:
                return
            last_state = state
        ui.send_message("state", state)

    def _poll_loop() -> None:
        while True:
            broadcast_if_changed(mainframe.screen())
            time.sleep(_POLL_SECONDS)

    def _on_key(sid, data):
        broadcast_if_changed(mainframe.send_key(data or {}))

    def _on_connect(sid):
        broadcast_if_changed(mainframe.screen())

    ui.on_connect(_on_connect)
    ui.on_message("key", _on_key)

    ui.expose_api("GET", "/api/state", mainframe.screen)

    threading.Thread(target=_poll_loop, daemon=True).start()

    App.run()


if __name__ == "__main__":
    main()
