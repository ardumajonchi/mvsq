# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
"""Test bootstrap: puts python/ on sys.path so `from engine.mainframe import Mainframe` resolves
the same way it does inside the app container. Unlike techaq's conftest.py, no arduino.app_bricks
stub is needed here -- engine/mainframe.py only imports `requests`, never the App Lab SDK
(main.py is the only module that touches arduino.app_bricks, and it isn't unit tested directly,
same as techaq's main.py).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
