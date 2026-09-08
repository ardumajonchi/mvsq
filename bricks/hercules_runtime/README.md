# hercules_runtime Brick

A custom Brick that runs [Hercules](http://www.hercules-390.eu/) (an open-source System/370,
System/390, and z/Architecture emulator) auto-IPLing MVS 3.8j — the public-domain, freely
redistributable 1970s IBM mainframe OS — via the community [tk4-](https://wotho.pebble-beach.ch/tk4-/)
("Tur(n)key MVS") distribution. There's no official mainframe-emulator Brick, so this one is
built and maintained in this repo, following the same "custom runtime Brick" shape as
`scummvm-q`'s emulator Brick and `techaq`'s `ocr_runtime`.

## Why wrap Hercules instead of writing a CPU emulator

Hercules is a mature, actively maintained emulator that can boot a **real guest OS** and run
**real mainframe software** — JCL batch jobs, Assembler F/COBOL compiles, a TSO interactive
session, JES2 spooling. A from-scratch z/Architecture emulator (`progq`'s approach, applied to a
vastly larger modern ISA) would only ever run toy programs written for it. MVS 3.8j is the
standard "real mainframe apps" target for Hercules hobbyists specifically because it's
public-domain and needs no license, unlike modern z/OS.

## Why a separate container

The main app container runs as a non-root, non-apt-privileged user on a shared
`python-apps-base` image — it cannot `apt-get install` anything, and neither `hercules` nor
`s3270` is part of that base image. `brick_compose.yaml`'s `build:` directive instead builds
this Brick's own image locally from `Dockerfile`, which *can* run as root at build time. That's
the only place in this app `apt-get install` ever runs. Once built, the resulting container
drops to a fixed non-root user (`1000:1000`) before starting Hercules — root is only ever used to
install packages and fetch/unpack the tk4- distribution, never to run the emulator itself.

## Architecture

- **`Dockerfile`** — `debian:trixie-slim` base; installs the native-arm64 `hercules` and `s3270`
  apt packages (confirmed available on Debian 13/trixie — no cross-compilation or emulation
  needed), plus `curl`/`unzip`/`ca-certificates`; fetches and unpacks the tk4- distribution
  (public-domain MVS 3.8j DASD volumes + Hercules config) at build time via `curl -skL`
  (`wotho.pebble-beach.ch`'s TLS cert chain is broken — confirmed independently by the community's
  `skunklabz/tk4-hercules` Dockerfile, which fetches this exact same URL the exact same insecure
  way); copies in `scripts/mvsq_boot.rc` and `entrypoint.sh`; creates a fixed `uid 1000` user and
  `chown`s `/opt/tk4-` to it before switching `USER 1000:1000`.
- **`entrypoint.sh`** — the container's PID 1. **Always invokes the apt-installed
  `/usr/bin/hercules` directly** rather than tk4-'s own bundled `start_herc`/`mvs` launcher
  scripts — tk4-'s bundled `hercules/linux/{32,64,arm,arm_softfloat}` binaries have no native
  aarch64 build, and those scripts' arch-detection is buggy for `aarch64` (they'd try to exec an
  incompatible x86 or 32-bit-ARM binary). Runs `hercules -f conf/tk4-.cnf` in the foreground so
  Docker/App Lab can supervise it and its logs land in `docker logs`/`arduino-app-cli app logs`.
- **`scripts/mvsq_boot.rc`** — fed in via the `HERCULES_RC` environment variable (this Hercules
  build has no `-r`/`-s` CLI flag for it). Auto-IPLs on every container start:
  ```
  hao tgt IEA101A
  hao cmd /R 00,CMD=02
  ipl 148
  ```
  Uses Hercules's Automatic Operator (HAO) to pattern-match the `IEA101A SPECIFY SYSTEM
  PARAMETERS` prompt NIP posts partway through IPL and auto-reply with the standard tk4- system
  parameters reply, so boot time isn't a hardcoded guess. **Deliberately avoids
  `${VAR:=default}`-style substitution** — it resolves fine inside `conf/tk4-.cnf` on this
  Hercules build, but is silently broken inside `.rc`/HAO-script contexts (confirmed: a `pause
  ${IPL_PAUSE:=4}` line resolved to "0 seconds", and a nested `script
  ${SCR101A:=scripts}/SCR101A_...` reference failed to resolve at all). Every value here is a
  hardcoded literal instead. Device `0009` (the operator console, a 3215-C) is not a network
  device — HAO drives it internally, so no extra port needs exposing for this.
- **`brick_config.yaml`** — declares `id: hercules_runtime`, `category: emulation`,
  `supported_boards: ["unoq"]`, `requires_container: true`, and the single external port `3270`.
- **`brick_compose.yaml`** — builds the image from this directory's `Dockerfile` and wires up a
  healthcheck that opens a raw TCP connection to `127.0.0.1:3270` (via bash's `/dev/tcp`, no extra
  package needed) rather than an HTTP probe, since there's no control API yet — it proves
  Hercules is not just running but actually listening for terminal connections. `start_period` is
  a generous 45s: a cold MVS IPL (`ipl 148` → `IEA101A` reply → JES2/VTAM/TCAS init) takes
  ~20-30s end to end on-device.

## The 3270 device pool

`conf/tk4-.cnf` (from tk4-, unmodified) defines a local 3270 device pool at `00C0`-`00C7` for
VTAM/TSO terminal sessions — this is what `python/engine`'s `s3270`/`py3270` bridge (Phase 2)
connects to on port `3270`, and it's confirmed working end-to-end: connect → see the tk4- IPL
banner → `logon herc01` → password `cul8tr` → TSO ready, using tk4-'s default seeded users
(`HERC01`-`HERC04`, password `CUL8TR`).

## Degradation

If this container is missing, still booting, or a connection attempt times out, `python/engine`'s
mainframe bridge (Phase 2) is expected to report "mainframe offline" in the UI rather than
crashing the app — the same defensive-wrapper discipline used for every hardware/service Brick in
these apps (`progq`'s `hw.py`, `techaq`'s LLM wrapper and `ocr.py`).

## Open items

- tk4-'s exact redistribution terms for bundling/downloading its MVS 3.8j DASD volumes at build
  time haven't been formally confirmed — this build-time-download approach mirrors the
  independently-published `skunklabz/tk4-hercules` Dockerfile, a precedent in the same hobbyist
  community, but isn't a license grant.
- tk4-'s bundled compiler set beyond Assembler F (COBOL/RPG/PL/I) is unconfirmed.
- The three `HHCCF008E ... Syntax error: HTTP` lines this Hercules build logs for
  `conf/tk4-.cnf`'s `HTTP PORT`/`HTTP ROOT`/`HTTP START` directives are confirmed harmless (they
  only disable Hercules's own built-in web console) but the modern equivalent directive syntax
  hasn't been tracked down.
