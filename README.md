# Tetris Party Deluxe Patcher

Play **Tetris Party Deluxe** (Wii) and **Tetris Party Premium** (Japan) with **GameCube controllers** in ports 1–4, completely mapped to the game's native Classic Controller support without requiring physical Classic Controllers. Supports the USA (`STEETR`), European (`STEPTR`), and Japanese (`STEJ18`) releases.

The patches are applied directly to your own clean disc image: drop a clean `.wbfs` or `.iso` onto the patcher and play the result on a Wii (via USB loader) or in Dolphin. Nothing copyrighted from the game is included in this repository.

![Tetris Party Deluxe](assets/logo.png)

## Controls

The patch bridges GameCube controller inputs directly into Nintendo RVL-SDK's Classic Controller format (`WPADStatus` ring buffer samples). Port *n* controls Player *n*.

| GameCube Input | Classic Controller Action | Game Action |
| --- | --- | --- |
| Control Stick / D-Pad Left | D-Pad Left / Analog Stick | Move Tetramino Left · Menu Left |
| Control Stick / D-Pad Right | D-Pad Right / Analog Stick | Move Tetramino Right · Menu Right |
| Control Stick / D-Pad Down | D-Pad Down / Analog Stick | Soft Drop · Menu Down |
| Control Stick / D-Pad Up | D-Pad Up / Analog Stick | Hard Drop · Menu Up |
| A | A | Rotate Clockwise · Confirm / Select |
| B | B | Rotate Counter-Clockwise · Cancel / Back |
| X | X | Rotate Clockwise |
| Y | Y | Rotate Counter-Clockwise |
| L (Digital or Analog > 50) | L / ZL | Hold Piece · Use Item |
| R (Digital or Analog > 50) | R / ZR | Hold Piece · Use Item |
| Start | + | Pause Menu |
| Z | HOME | Wii HOME Menu |

Both digital and analog triggers are supported (analog trigger pull > 50 activates Hold / Item). For players who prefer using the Control Stick over the D-Pad, stick deflection past threshold (> 48) synthesizes instant directional inputs for responsive drops and shifts.

---

## Installing

### 1. Standalone GUI Patcher (Disc Images)

You need a clean `.wbfs` or `.iso` dump of the game. Run the patcher from source (requires Python 3 and [Wiimms ISO Tool](https://wit.wiimm.de/) (`wit`) on your `PATH`):

```bash
python3 tools/gui.py
```

Drag and drop your game image onto the window (or click to browse). The patcher verifies the disc ID and pristine `main.dol` bytes, injects the controller bridge into an unused low-memory cave, updates the disc table, and rebuilds the image in place. The untouched original is preserved alongside as `<filename>.bak`.

#### CLI Patcher

A command-line tool is also provided:

```bash
python3 tools/patch_disc.py "Tetris Party Deluxe (USA) (En,Fr,Es).wbfs" --gc
```

---

### 2. Gecko Codes (Dolphin & USB Loaders)

Copy `codes/<ID>.ini` (`STEETR`, `STEPTR`, or `STEJ18`) into Dolphin's `GameSettings` directory, or use `codes/<ID>.txt` with USB Loader GX / WiiFlow.

In Dolphin:
1. Right click the game → **Properties** → **Gecko Codes**.
2. Check **GameCube controllers**.
3. Set **GameCube Port 1** (and 2–4 for multiplayer) to **Standard Controller**.

---

### 3. Riivolution

Copy `riivolution/<ID>.xml` to your SD card's `/riivolution/` folder to patch game discs on the fly without modifying disc images on storage.

---

## Supported Releases

| Release | Disc ID | Game ID | Version | Clean DOL Size |
| --- | --- | --- | --- | --- |
| USA | `STEETR` | `STEETR` | v0 | 5,010,592 bytes |
| Europe | `STEPTR` | `STEPTR` | v0 | 5,013,280 bytes |
| Japan | `STEJ18` | `STEJ18` | v0 | 5,093,536 bytes |

---

## Technical Details

For an in-depth breakdown of Serial Interface (SI) auto-polling registers, `WPADProbe` extension detection, and low-level `KPAD` ring buffer synthesis, see [docs/TECHNICAL.md](docs/TECHNICAL.md).

---

## License

MIT License. See [LICENSE](LICENSE) for details.
