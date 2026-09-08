# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
"""Thin HTTP client for the hercules_runtime Brick's control API
(bricks/hercules_runtime/control_server.py). The main app container has neither the `s3270`
binary nor a route to speak raw TN3270 itself (it's the non-root, non-apt-privileged
python-apps-base image) -- all of that lives in the Brick's own container instead (see that
Brick's README for why the split is there), and this module just calls it over the Docker Compose
internal network.

Every method degrades to a disconnected/empty result on any failure -- request errors, timeouts,
non-200s, malformed JSON -- and never raises, so a missing/still-booting hercules_runtime
container surfaces as "mainframe offline" in the UI instead of taking python/main.py down. Same
discipline as techaq's engine/ocr.py's call_ocr_service().
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

DEFAULT_HOST = "hercules_runtime"
DEFAULT_PORT = 3271
REQUEST_TIMEOUT_S = 10

EMPTY_SCREEN = {"connected": False, "rows": [], "cursor": {"row": 0, "col": 0}}


class Mainframe:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self._base_url = f"http://{host}:{port}"

    def screen(self) -> dict:
        """Current 3270 screen contents, or a disconnected placeholder if hercules_runtime isn't
        reachable yet."""
        try:
            resp = requests.get(f"{self._base_url}/screen", timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error("Mainframe.screen(): request to %s failed: %r", self._base_url, exc)
            return dict(EMPTY_SCREEN)

    def send_key(self, key_data: dict) -> dict:
        """Forward one WebUI "key" event payload to the Brick's POST /key, and return the updated
        screen it hands back. `key_data` uses the exact same shape documented in main.py."""
        try:
            resp = requests.post(f"{self._base_url}/key", json=key_data, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error(
                "Mainframe.send_key(%r): request to %s failed: %r", key_data, self._base_url, exc
            )
            return dict(EMPTY_SCREEN)
