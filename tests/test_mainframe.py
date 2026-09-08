# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
"""Tests for engine/mainframe.py: Mainframe.screen()/send_key() graceful degradation to
EMPTY_SCREEN on connection errors, timeouts, and non-200/malformed responses (mocking
requests.get/requests.post -- no real hercules_runtime container involved).
"""

from __future__ import annotations

import requests

from engine.mainframe import EMPTY_SCREEN, Mainframe


class _FakeResponse:
    def __init__(self, json_body=None, status_code=200, raise_json_error=False):
        self._json_body = json_body
        self.status_code = status_code
        self._raise_json_error = raise_json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def json(self):
        if self._raise_json_error:
            raise ValueError("not json")
        return self._json_body


_CONNECTED_SCREEN = {
    "connected": True,
    "rows": ["Welcome to the TSO system on TK4-"] + [""] * 23,
    "cursor": {"row": 0, "col": 0},
}


# ---------------------------------------------------------------------------
# screen()
# ---------------------------------------------------------------------------


def test_screen_returns_parsed_response_on_success(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(_CONNECTED_SCREEN))
    mainframe = Mainframe()
    assert mainframe.screen() == _CONNECTED_SCREEN


def test_screen_degrades_to_empty_on_connection_error(monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(requests, "get", _raise)
    mainframe = Mainframe()
    assert mainframe.screen() == EMPTY_SCREEN


def test_screen_degrades_to_empty_on_timeout(monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "get", _raise)
    mainframe = Mainframe()
    assert mainframe.screen() == EMPTY_SCREEN


def test_screen_degrades_to_empty_on_non_200(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(status_code=503))
    mainframe = Mainframe()
    assert mainframe.screen() == EMPTY_SCREEN


def test_screen_degrades_to_empty_on_malformed_json(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(raise_json_error=True))
    mainframe = Mainframe()
    assert mainframe.screen() == EMPTY_SCREEN


# ---------------------------------------------------------------------------
# send_key()
# ---------------------------------------------------------------------------


def test_send_key_forwards_payload_and_returns_response(monkeypatch):
    captured = {}

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(_CONNECTED_SCREEN)

    monkeypatch.setattr(requests, "post", _fake_post)
    mainframe = Mainframe(host="hercules_runtime", port=3271)
    result = mainframe.send_key({"text": "logon herc01"})

    assert captured["url"] == "http://hercules_runtime:3271/key"
    assert captured["json"] == {"text": "logon herc01"}
    assert result == _CONNECTED_SCREEN


def test_send_key_degrades_to_empty_on_connection_error(monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(requests, "post", _raise)
    mainframe = Mainframe()
    assert mainframe.send_key({"enter": True}) == EMPTY_SCREEN
