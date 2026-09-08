#!/bin/bash
# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
#
# tk4-'s bundled hercules/linux/{32,64,arm,arm_softfloat} binaries have no native aarch64 build,
# and the stock start_herc/mvs launcher scripts mis-detect aarch64 -- always invoke the
# apt-installed /usr/bin/hercules directly instead of those scripts.
set -e
cd /opt/tk4-
exec hercules -f conf/tk4-.cnf
