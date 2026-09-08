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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
# wotho.pebble-beach.ch's cert chain is broken -- confirmed independently by the community's
# skunklabz/tk4-hercules Dockerfile, which fetches this exact same URL the exact same insecure
# way. tk4- ("Tur(n)key MVS") bundles the public-domain MVS 3.8j DASD volumes + Hercules config
# needed to IPL a real, legally-redistributable IBM S/370 OS.
RUN curl -skL -o tk4-.zip https://wotho.pebble-beach.ch/tk4-/tk4-_v1.00_current.zip \
    && unzip -q tk4-.zip -d /opt \
    && rm tk4-.zip

WORKDIR /opt/tk4-

# Config-file substitution (${VAR:=default} inside conf/tk4-.cnf) works fine on this build, but
# the same substitution syntax is broken inside .rc/HAO-script contexts -- mvsq_boot.rc avoids it
# entirely by using literal values and a single-line `hao cmd` (no nested `script <file>` call).
COPY scripts/mvsq_boot.rc scripts/mvsq_boot.rc
COPY entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh \
    && useradd -u 1000 -m -d /home/mvsq mvsq \
    && chown -R 1000:1000 /opt/tk4-

USER 1000:1000
ENV HOME=/home/mvsq
ENV HERCULES_RC=scripts/mvsq_boot.rc

# 3270: the local VTAM/TSO terminal pool (devices 00C0-00C7) that python/engine's s3270/py3270
# bridge connects to. The system operator console (device 0009, a 3215-C) is NOT a network
# device -- it's driven entirely by the HAO automation baked into mvsq_boot.rc, so it needs no
# exposed port.
EXPOSE 3270
ENTRYPOINT ["/opt/tk4-/entrypoint.sh"]
