# SPDX-FileCopyrightText: Copyright (C) mvsq contributors
#
# SPDX-License-Identifier: MPL-2.0
#
# Built locally via brick_compose.yaml's `build:` directive -- hercules/s3270 aren't in the
# shared python-apps-base image, and the tk4- MVS 3.8j distribution has to be fetched and
# unpacked at build time (see the curl step below). Mirrors techaq's ocr_runtime pattern: this
# is the one place in the app where `apt-get install` can run as root, at image-build time.
FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        hercules \
        s3270 \
        curl \
        unzip \
        ca-certificates \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# control_server.py -- the sidecar HTTP control API (see its own docstring) -- runs in a venv so
# `pip install` lands outside the system Python, same as techaq's ocr_runtime Brick.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt

WORKDIR /opt
# wotho.pebble-beach.ch's cert chain is broken -- confirmed independently by the community's
# skunklabz/tk4-hercules Dockerfile, which fetches this exact same URL the exact same insecure
# way. tk4- ("Tur(n)key MVS") bundles the public-domain MVS 3.8j DASD volumes + Hercules config
# needed to IPL a real, legally-redistributable IBM S/370 OS. The zip extracts its contents FLAT
# into whatever -d directory is given (conf/, dasd/, hercules/, mvs, start_herc, ... land directly
# in /opt, there's no top-level "tk4-/" folder inside it) -- so /opt itself is the tk4- root,
# confirmed by inspecting a built image; don't add a WORKDIR /opt/tk4- expecting one.
RUN curl -skL -o tk4-.zip https://wotho.pebble-beach.ch/tk4-/tk4-_v1.00_current.zip \
    && unzip -q tk4-.zip -d /opt \
    && rm tk4-.zip

# Config-file substitution (${VAR:=default} inside conf/tk4-.cnf) works fine on this build, but
# the same substitution syntax is broken inside .rc/HAO-script contexts -- mvsq_boot.rc avoids it
# entirely by using literal values and a single-line `hao cmd` (no nested `script <file>` call).
# scripts/ already exists (tk4-'s own bundled scripts live there); mvsq_boot.rc is just added
# alongside them.
COPY scripts/mvsq_boot.rc scripts/mvsq_boot.rc
COPY entrypoint.sh entrypoint.sh
COPY control_server.py control_server.py
RUN chmod +x entrypoint.sh \
    && useradd -u 1000 -m -d /home/mvsq mvsq \
    && chown -R 1000:1000 /opt

USER 1000:1000
ENV HOME=/home/mvsq
ENV HERCULES_RC=scripts/mvsq_boot.rc

# 3270: the local VTAM/TSO terminal pool (devices 00C0-00C7) that control_server.py's s3270
# subprocess connects to (over 127.0.0.1, from inside this same container). The system operator
# console (device 0009, a 3215-C) is NOT a network device -- it's driven entirely by the HAO
# automation baked into mvsq_boot.rc, so it needs no exposed port.
# 3271: control_server.py's own HTTP API -- the main app container's python/engine/mainframe.py
# is the only intended caller, over the Compose internal network (no app.yaml port entry needed,
# same as techaq's internal-only ocr_runtime Brick).
EXPOSE 3270 3271
ENTRYPOINT ["/opt/entrypoint.sh"]
