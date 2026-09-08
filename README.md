# MVS-Q

A real IBM mainframe you can use from a browser, running on an Arduino UNO Q. [Hercules](http://www.hercules-390.eu/)
emulates a System/370, IPLs [MVS 3.8j](https://en.wikipedia.org/wiki/MVS) — the public-domain,
freely redistributable 1970s IBM mainframe OS — via the community
[tk4-](https://wotho.pebble-beach.ch/tk4-/) distribution, and the app drives it over a scriptable
TN3270 client so you can log on to TSO, submit JCL, and watch real mainframe software run.

Built on the official `arduino:web_ui` Brick, plus a custom `hercules_runtime` Brick (Hercules +
tk4-).

## Status: work in progress

This project is being built in phases. **Phase 0 (feasibility), Phase 1 (app scaffolding), and
Phase 2 (engine + control-API plumbing) are done**; Phase 3 (the browser frontend) is next.
Confirmed so far, end-to-end, on the physical board's native arm64 Linux:

- `hercules` and `s3270` install natively via `apt` — no cross-compilation or emulation needed.
- MVS 3.8j fully IPLs under the apt-packaged Hercules build (auto-IPL, no manual console
  babysitting — see [`bricks/hercules_runtime/README.md`](bricks/hercules_runtime/README.md) for
  exactly how).
- A headless `s3270` client can connect, read the IPL banner, log on to TSO (`logon herc01` /
  `cul8tr`), and land at the "Welcome to the TSO system on TK4-" prompt.
- The `hercules_runtime` Brick now runs a small sidecar HTTP control API
  (`control_server.py`) alongside Hercules, driving that same `s3270` session and exposing it as
  `GET /screen` / `POST /key` for the main app to call — `python/engine/mainframe.py` is a thin
  HTTP client for it, and `python/main.py` wires that up to the `arduino:web_ui` Brick's
  Socket.IO layer (a background thread polls the screen and broadcasts changes; browser keys
  forward straight through). Unit-tested (`tests/test_mainframe.py`) for graceful degradation
  when the Brick container is missing/unreachable; not yet verified on the physical board or in a
  browser — that's part of Phase 3/6.

There is no browser UI yet — that's Phase 3.

## Architecture

```
┌─────────────┐  Socket.IO   ┌──────────────────┐  HTTP (screen/key) ┌────────────────────────┐
│  Browser UI │◄────────────►│ python/main.py   │◄───────────────────►│ hercules_runtime brick │
│ (3270 grid) │  screen+keys │ + engine/        │  :3271              │ control_server.py      │
└─────────────┘              │   mainframe.py   │                     │   │ s3270 (127.0.0.1)  │
   (Phase 3)                 └──────────────────┘                     │   ▼                    │
                                  done (Phase 2)                      │ Hercules + tk4- (MVS)  │
                                                                        └────────────────────────┘
                                                                            done (Phase 0/1)
```

See [`bricks/hercules_runtime/README.md`](bricks/hercules_runtime/README.md) for the emulator
Brick's internals (including the control API), and the project plan for the full phased roadmap.

## Running it

Deploy with the Arduino App CLI like any other app Brick bundle (`app.yaml` declares the Bricks
above and exposes port 7000). The `hercules_runtime` Brick auto-IPLs MVS 3.8j on container start;
give it ~30-45 seconds after the app restarts before expecting a TSO logon to succeed.

Run the unit tests (main app container's Python code only — no board/Docker required):
```
cd python && pip install -r requirements.txt
cd .. && python3 -m pytest tests/
```

## License

MPL-2.0 — see [`LICENSE`](LICENSE). tk4- and MVS 3.8j are separate, independently-distributed
community works fetched at Docker build time (see the `hercules_runtime` Brick's README for
details); this repo's own code is MPL-2.0.
