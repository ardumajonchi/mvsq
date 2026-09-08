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
python3 control_server.py &
exec hercules -f conf/tk4-.cnf
