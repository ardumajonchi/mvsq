#!/bin/bash
# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
#
# tk4-'s bundled hercules/linux/{32,64,arm,arm_softfloat} binaries have no native aarch64 build,
# and the stock start_herc/mvs launcher scripts mis-detect aarch64 -- always invoke the
# apt-installed /usr/bin/hercules directly instead of those scripts.
#
# control_server.py (the sidecar HTTP control API) runs in the background; Hercules itself stays
# PID 1 and runs in the foreground, so Docker/App Lab supervises Hercules specifically -- if it
# dies, the container dies with it, taking the (now-useless, nothing to control) control server
# down too, rather than leaving a zombie API up with no mainframe behind it.
set -e
cd /opt
# -u: control_server.py runs backgrounded and piped through this shell into Docker's log driver,
# not a TTY -- Python's default stdout buffering in that case is fully block-buffered, so its
# own error prints (e.g. Mainframe.connect() failures) sat invisible in-buffer for the entire
# container lifetime instead of reaching `docker logs`, which is exactly what happened while
# diagnosing a real reconnect-storm bug live.
python3 -u control_server.py &
exec hercules -f conf/tk4-.cnf
