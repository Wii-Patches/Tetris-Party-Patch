# Technical Documentation: Tetris Party Deluxe GameCube Controller Bridge

This document details how the GameCube controller patch interfaces with the Nintendo RVL-SDK, how hardware registers are driven, and how memory layout is managed across all retail versions of *Tetris Party Deluxe* and *Tetris Party Premium*.

---

## 1. Architectural Overview

*Tetris Party Deluxe* natively includes Classic Controller support via the Nintendo Wii SDK (`WPAD` and `KPAD` libraries). However, it does not link or initialize the GameCube controller library (`PAD`). While the low-level Serial Interface (`si`) driver is linked by the OS, auto-polling of the GameCube controller ports is disabled by default.

Instead of writing a custom input engine from scratch, the patch acts as an in-flight hardware bridge:
1. **Drives Serial Interface (SI) Hardware**: Configures the hardware registers (`0xCD006400`) to auto-poll GameCube ports 1–4 every retrace.
2. **Synthesizes Classic Controller Samples**: Translates GameCube pad packets directly into `WPADStatus` ring buffer samples formatted as a connected Classic Controller (`ext_type = 2`).
3. **Intercepts Device Probing (`WPADProbe`)**: Informs the engine that an active Classic Controller is present on channel *n* whenever a GameCube controller is plugged into port *n*.

---

## 2. How the game gets its input, and the hooks

The game never polls KPAD itself. When a Wii Remote connects, WPAD calls `KPADiConnectCallback(chan, 0)`, which registers `KPADiRead` as WPAD's sampling callback and calls the game's own connect callback. From then on WPAD calls `KPADiRead(chan)` for every report the remote sends; it stores the report (`WPADRead`) in the channel's ring of 56-byte samples and calls the game's sampling callback. With no Wii Remote none of this ever happens, so a bridge that only rewrites samples inside `KPADiRead` (or polls from it) never runs. The patch therefore plays the part of the remote:

### Hook 1: Probe + poller + driver (`gc_probe` / `gc_poll` / `gc_drive`)
- **Site**: prologue of `WPADProbe`, which the game calls constantly (several thousand times a second) whether or not a controller is connected. `KPADiRead`'s prologue carries the same poller hook.
- **Poller** (`gc_poll`, throttled to ~8 ms with the Time Base): sets `SI_OUT(n) = 0x00400300`, acknowledges `SI_SR`, programs `SI_POLL` and the SDK's shadow copy so the VI retrace keeps it, probes empty ports every 0.25 s for hot-plugging, and un-wedges the SI busy flag.
- **Driver** (`gc_drive`): for each port with a valid pad answer on a channel where WPAD has no controller, calls `KPADiConnectCallback(n, 0)` once, then `KPADiRead(n)` once per poll (~125 Hz, a Wii Remote's rate). After 20 polls without a pad it calls `KPADiConnectCallback(n, -1)`.
- **Probe**: when a pad answers, `WPADProbe` reports `*type = 2` (Classic Controller) and returns `WPAD_ERR_OK`, unless the channel already has a real Nunchuk or Classic Controller.
- The poller cannot live only in `KPADiRead`: the game reaches it only after `WPADProbe` succeeds, which needs a polled pad.

### Hook 2: Sample synthesis (`gc_sample`)
- **Site**: inside `KPADiRead`, right after `WPADRead` and the status byte are stored (instruction displaced: `addi r0, r27, 1`). `r29` is the ring slot just written.
- On a channel with no remote the slot is cleared, then filled like a real Classic Controller's idle report; on a bare Wii Remote only the extension fields are filled. A real Nunchuk or Classic Controller sample is never touched.
- 56-byte `WPADStatus` fields written: `+0x07` accelerometer at rest (`0x68`), `+0x28` extension type `2`, `+0x29` error `0`, `+0x2A` Classic buttons, `+0x2C/+0x2E` left stick, `+0x30/+0x32` right stick, `+0x34/+0x35` analog triggers, `+0x36` data format `7`.

---

## 3. Memory Layout & Section Allocation

All patch code and trampolines are self-contained:

### 1. Injected Trampoline Section (`CAVE_BASE = 0x80001820`, `CAVE_LIMIT = 0x80003000`)
- Standard Wii low-memory scratch area unused after boot.
- Section injector adds a dedicated text section into `main.dol` headers.
- For Gecko codes, trampolines are emitted as standard `C2` insertion codes.
- For Riivolution, emitted as `<memory>` XML elements.

### 2. Patch State Storage (`STATE = 0x800043C0`)
- A 208-byte verified unused zero-padding alignment block in Text 0 across all 3 releases.
- Stores polling timestamps, edge button histories, and device latch state without dynamic heap allocations.

---

## 4. Release Address Cross-Reference Table

| Symbol / Anchor | USA (`STEETR`) | Europe (`STEPTR`) | Japan (`STEJ18`) |
| --- | --- | --- | --- |
| `KPADiRead` | `0x80287750` | `0x802876A0` | `0x80298B20` |
| `SampleSite` (`KPADiRead`+0xC0) | `0x80287810` | `0x80287760` | `0x80298BE0` |
| `KPADiConnectCallback` | `0x80287460` | `0x802873B0` | `0x80298830` |
| `WPADProbe` | `0x802ADDF0` | `0x802ADD40` | `0x802BF250` |
| `SIGetType` | `0x802A2B10` | `0x802A2A60` | `0x802B3F70` |
| `OSDisableInterrupts` | `0x802977F0` | `0x80297740` | `0x802A8C50` |
| `OSRestoreInterrupts` | `0x80297830` | `0x80297780` | `0x802A8C90` |
| `SiTypes` | `0x8048BF88` | `0x8048CA08` | `0x804A00C8` |
| `SiBusy` | `0x8048BF70` | `0x8048C9F0` | `0x804A00B0` |
| `SiShadow` | `0x8048BF74` | `0x8048C9F4` | `0x804A00B4` |
| `WpadTbl` | `0x80572C50` | `0x805736D0` | `0x80586E10` |
| `Kpad0` | `0x80567600` | `0x80568080` | `0x8057B7C0` |

---

## 5. Verification & Testing Methodology

- **Anchor Resolver**: Exact 1-to-1 instruction pattern verification ensures relocatable bits (branches, immediate halves) match across versions.
- **Gecko & Riivolution Roundtrip**: `tools/check.py` validates that all trampolines stay inside their allocated windows, contain no relative branches leaving their routines, and accurately parse back through the Gecko engine.
- **Debug feed**: `DEBUG_FEED=1` builds take the pad's response from `STATE+0x40+8*port` (written over the GDB stub) and keep hook call counters at `STATE+0x70`, which lets `tools/dolphin_test.py` check the whole chain deterministically.
- **Retail DOL Verification**: `tools/verify.py` confirms that patched DOLs only modify designated hook sites and that all displaced instructions branch back accurately to `site + 4`.
- **Headless Dolphin Testing**: Verified against live game memory using Dolphin GDB stub remote memory protocol.
