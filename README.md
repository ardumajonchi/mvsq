# MVS-Q

A real IBM mainframe you can use from a browser, running on an Arduino UNO Q. [Hercules](http://www.hercules-390.eu/)
emulates a System/370, IPLs [MVS 3.8j](https://en.wikipedia.org/wiki/MVS) — the public-domain,
freely redistributable 1970s IBM mainframe OS — via the community
[tk4-](https://wotho.pebble-beach.ch/tk4-/) distribution, and the app drives it over a scriptable
TN3270 client so you can log on to TSO, submit JCL, and watch real mainframe software run.

Built on the official `arduino:web_ui` Brick, plus a custom `hercules_runtime` Brick (Hercules +
tk4-).

## Status: work in progress

This project is being built in phases. **Phase 0 (feasibility) and Phase 1 (app scaffolding) are
done**; Phase 2 (the browser-facing 3270 bridge) is next. Confirmed so far, end-to-end, on the
physical board's native arm64 Linux:

- `hercules` and `s3270` install natively via `apt` — no cross-compilation or emulation needed.
- MVS 3.8j fully IPLs under the apt-packaged Hercules build (auto-IPL, no manual console
  babysitting — see [`bricks/hercules_runtime/README.md`](bricks/hercules_runtime/README.md) for
  exactly how).
- A headless `s3270` client can connect, read the IPL banner, log on to TSO (`logon herc01` /
  `cul8tr`), and land at the "Welcome to the TSO system on TK4-" prompt.

There is no browser UI or `python/` engine yet — that's Phase 2/3. Right now this repo is the
`hercules_runtime` Brick plus the app manifest.

## Architecture

```
┌─────────────┐  Socket.IO   ┌──────────────────┐  s3270 script   ┌────────────────────────┐
│  Browser UI │◄────────────►│ python/main.py   │◄────────────────►│ hercules_runtime brick │
│ (3270 grid) │  screen+keys │ + engine/*.py    │  protocol (py3270)│ Hercules + tk4- (MVS)  │
└─────────────┘              └──────────────────┘                  └────────────────────────┘
   (Phase 3)                     (Phase 2)                              done (Phase 0/1)
```

See [`bricks/hercules_runtime/README.md`](bricks/hercules_runtime/README.md) for the emulator
Brick's internals, and the project plan for the full phased roadmap.

## Running it

Deploy with the Arduino App CLI like any other app Brick bundle (`app.yaml` declares the Bricks
above and exposes port 7000). The `hercules_runtime` Brick auto-IPLs MVS 3.8j on container start;
give it ~30-45 seconds after the app restarts before expecting a TSO logon to succeed.

## License

MPL-2.0 — see [`LICENSE`](LICENSE). tk4- and MVS 3.8j are separate, independently-distributed
community works fetched at Docker build time (see the `hercules_runtime` Brick's README for
details); this repo's own code is MPL-2.0.
