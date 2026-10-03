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

## 2. Low-Level Reverse-Engineered Hooks

The patch operates via three precision hooks in the `main.dol` binary:

### Hook 1: SI Auto-Polling (`gc_poll`)
- **Site**: Function prologue of `KPADiRead`.
- **Function**: Executes once per frame (~8 ms throttling via Time Base register `mftb`).
- **Registers & Hardware**:
  - Sets `SI_OUT(n) = 0x00400300` (standard 3-byte GameCube polling command: `CMD_GET_STATUS`).
  - Writes to `SI_SR` (`0xCD006438`) to clear error latches and latch output buffers.
  - Programs `SI_POLL` (`0xCD006430`) and updates `SI_SHADOW` so the OS VI retrace interrupt handler maintains active sampling.
  - Automatically probes disconnected ports via `SIGetType` every 0.25 s to support hot-plugging.

### Hook 2: Ring Buffer Synthesis (`gc_sample`)
- **Site**: `SampleCheck` in `KPADiRead` (instruction displaced: `lbz r27, 314(r30)`).
- **Function**: Inspects the 16-slot ring buffer (`k + 0x13C`).
- When samples are queued by an attached Wii Remote, converts unattached / basic samples into Classic Controller samples.
- If no samples are queued, generates two consecutive samples into the ring buffer (with the older holding previous buttons and the newer holding current buttons) so that edge-triggered button presses and stick deltas register reliably in the game engine.
- Formats 56-byte `WPADStatus` records:
  - `+0x28`: Extension device type (`2` = Classic Controller)
  - `+0x29`: Extension error code (`0` = OK)
  - `+0x2A`: Classic Controller button mask
  - `+0x2C / +0x2E`: Left stick X / Y (scaled to signed 16-bit range `±308`)
  - `+0x30 / +0x32`: Right stick (C-stick) X / Y
  - `+0x34 / +0x35`: Analog triggers L / R (`0–255`)

### Hook 3: Device Presence (`gc_probe`)
- **Site**: Prologue of `WPADProbe` (`stwu r1, -16(r1)`).
- **Function**: If a GameCube pad is answering on port *n*, writes `*type = 2` (Classic Controller) and returns `0` (`WPAD_ERR_OK`), allowing the game's menu logic, player select screens, and in-game loops to recognize the controller immediately.

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
| `SampleCheck` | `0x802877BC` | `0x8028770C` | `0x80298B8C` |
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
- **Retail DOL Verification**: `tools/verify.py` confirms that patched DOLs only modify designated hook sites and that all displaced instructions branch back accurately to `site + 4`.
- **Headless Dolphin Testing**: Verified against live game memory using Dolphin GDB stub remote memory protocol.
