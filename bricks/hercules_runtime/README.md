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
  needed), plus `curl`/`unzip`/`ca-certificates`/`python3`/`python3-venv`; fetches and unpacks the
  tk4- distribution (public-domain MVS 3.8j DASD volumes + Hercules config) at build time via
  `curl -skL` (`wotho.pebble-beach.ch`'s TLS cert chain is broken — confirmed independently by the
  community's `skunklabz/tk4-hercules` Dockerfile, which fetches this exact same URL the exact
  same insecure way); creates a venv and `pip install`s `requirements.txt` (`fastapi`+`uvicorn`,
  for `control_server.py` below) into it, same pattern as `techaq`'s `ocr_runtime` Brick; copies
  in `scripts/mvsq_boot.rc`, `entrypoint.sh`, and `control_server.py`; creates a fixed `uid 1000`
  user and `chown`s `/opt` (the tk4- distribution's root -- its zip extracts flat, with no
  top-level `tk4-/` folder inside it) to it before switching `USER 1000:1000`.
- **`entrypoint.sh`** — starts `control_server.py` in the background, then `exec`s
  `hercules -f conf/tk4-.cnf` in the foreground as the container's PID 1 — Hercules, not the
  control server, is what Docker/App Lab supervises and what `docker logs`/
  `arduino-app-cli app logs` shows; if Hercules dies the container dies with it, taking the (now
  useless) control server down too rather than leaving a zombie API with no mainframe behind it.
  **Always invokes the apt-installed `/usr/bin/hercules` directly** rather than tk4-'s own bundled
  `start_herc`/`mvs` launcher scripts — tk4-'s bundled
  `hercules/linux/{32,64,arm,arm_softfloat}` binaries have no native aarch64 build, and those
  scripts' arch-detection is buggy for `aarch64` (they'd try to exec an incompatible x86 or
  32-bit-ARM binary).
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
- **`control_server.py`** — the sidecar HTTP control API (see its own module docstring for the
  full endpoint contract: `GET /healthz`, `GET /screen`, `POST /key`). Runs as a second process in
  this same container, alongside Hercules, so it can shell out to the also-apt-installed `s3270`
  client and have it connect to Hercules's 3270 listener over `127.0.0.1:3270` — no cross-container
  3270 traffic. Keeps one persistent `s3270` subprocess for the container's lifetime and drives it
  via its line-based scripting protocol (one action per stdin line in, `data:`/status/`ok`-or-
  `error` lines back) rather than the largely-unmaintained `py3270` PyPI wrapper. This is the only
  thing `python/engine/mainframe.py`, in the main app container, ever talks to — that container has
  neither `s3270` nor a route to speak raw TN3270 itself.
- **`brick_config.yaml`** — declares `id: hercules_runtime`, `category: emulation`,
  `supported_boards: ["unoq"]`, `requires_container: true`, and two internal ports: `3270`
  (Hercules's own 3270 listener, reachable only from `control_server.py` inside this same
  container) and `3271` (`control_server.py`'s HTTP API, reachable from the main app container
  over the Compose internal network).
- **`brick_compose.yaml`** — builds the image from this directory's `Dockerfile` and wires up a
  healthcheck against `control_server.py`'s `GET /healthz`, which only returns 200 once its s3270
  subprocess can actually connect to Hercules — proving Hercules is not just running but actually
  listening for terminal connections, the same guarantee the earlier raw-TCP check gave before this
  control API existed. `start_period` is a generous 45s: a cold MVS IPL (`ipl 148` → `IEA101A`
  reply → JES2/VTAM/TCAS init) takes ~20-30s end to end on-device.

## The 3270 device pool

`conf/tk4-.cnf` (from tk4-, unmodified) defines a local 3270 device pool at `00C0`-`00C7` for
VTAM/TSO terminal sessions — this is what `control_server.py`'s `s3270` subprocess connects to on
`127.0.0.1:3270`, and it's confirmed working end-to-end: connect → see the tk4- IPL banner →
`logon herc01` → password `cul8tr` → TSO ready, using tk4-'s default seeded users
(`HERC01`-`HERC04`, password `CUL8TR`). There's exactly one shared session for the whole app right
now — every browser tab drives the same terminal, not one each from the 8-deep pool (see
`python/main.py`'s docstring for why that's a deliberate MVP simplification).

## Recovering a wedged keyboard or a wedged s3270 subprocess

Two distinct failure modes found live, both now handled without requiring a container restart:

- **A wedged s3270 subprocess** (e.g. Hercules stops responding mid-action) used to block
  `Mainframe._run_action()`'s `readline()` forever, holding the shared lock and hanging every
  future request indefinitely — including `/healthz` itself, which should always return promptly
  (200 or 503), never hang. Fixed with a `select()`-based read timeout, but **only on the first
  line of each action's response**: s3270's protocol is strictly one-action-in/one-block-out, so
  the read buffer is guaranteed empty when a new action starts, making a timeout on that first
  read sound. Guarding every line, not just the first, was tried and reverted — Python's buffered
  `TextIOWrapper` can pull an entire multi-line response (e.g. `Ascii`'s full-screen dump) into its
  internal buffer from one OS-level read, so `select()` on the raw fd falsely reports "not ready"
  for the later lines even though `readline()` would return them instantly, causing a reconnect
  storm (endless kill+respawn+reconnect, visible as repeating `HHCTE007I`/`HHCTE009I` connect/
  disconnect pairs in Hercules's own console log) that never let the container reach healthy.
- **A locked keyboard** (the s3270 status line's `L` field), left behind by a benign
  operator-error condition (e.g. TSO's `IKJ56429A REENTER` prompt) — every subsequent action was
  rejected forever, with no way to clear it short of a full container restart. Fixed by adding
  `press_reset()` (`Reset()`, the correct 3270 action for exactly this — distinct from `Clear()`,
  which sends the CLEAR AID to the host and doesn't touch a purely local lock condition) and
  wiring it through `POST /key {"reset": true}`.

`entrypoint.sh` also launches `control_server.py` with `python3 -u` (unbuffered stdout) — without
it, none of this module's own diagnostic `print()`s (including the ones that explain *why*
`connect()`/`act()` failed) ever reached `docker logs`, since stdout is fully block-buffered by
default when piped through a shell into Docker's log driver rather than attached to a TTY. This
directly hampered diagnosing the reconnect storm above: grepping logs for its own print-statement
prefix found nothing despite the loop clearly failing.

## Degradation

If this container is missing, still booting, or a `/screen`/`/key` request times out/errors,
`python/engine/mainframe.py`'s HTTP client returns a `{"connected": false, ...}` snapshot rather
than raising, and `python/main.py` broadcasts that straight to the UI as "mainframe offline" —
the same defensive-wrapper discipline used for every hardware/service Brick in these apps
(`progq`'s `hw.py`, `techaq`'s LLM wrapper and `ocr.py`). The background poll loop in
`python/main.py` keeps retrying, so the UI recovers on its own once this container finishes
booting, with no app restart needed.

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
