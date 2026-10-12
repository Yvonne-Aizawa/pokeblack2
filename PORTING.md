# Porting notes (pokeblack2)

This repo was bootstrapped from [pret/pokediamond](https://github.com/pret/pokediamond) as
a starting point. **It will not build yet.** Everything below must be ported or
acquired before the first matching build.

## What's already in place

| Path | Source | Status |
|------|--------|--------|
| `tools/` | upstream | usable as-is — universal build helpers |
| `tools/mwccarm/` (with `2.0/sp2p3`, `1.2/sp2p3`, `license.dat`) | PRET Discord (proprietary) | extracted, runs under wine, returns `Version 3.0 build 138` |
| `tools/bin/` | Nitro SDK 3.2 (proprietary) | flattened from `tools/NitroSDK-3_2-060901/tools/bin/`; verified `makerom.exe` and `ntrcomp.exe` respond under wine |
| `tools/NitroSDK-3_2-060901/` | Nitro SDK archive (proprietary) | full SDK source kept in-place as reference (170M, gitignored) |
| `arm7/ARM7-TS.lcf.template`, `arm9/ARM9-TS.lcf.template` | Nitro SDK | copied; needed by the link stage |
| `m2ctx.sh`, `format.sh` | upstream | usable as-is |
| `INSTALL.md`, `CONTRIBUTING.md` | upstream | usable, edit for B2 specifics |
| `CMakeLists.txt`, `charmap.txt`, `Makefile`, `config.mk`, `graphics_rules.mk`, `filesystem.mk`, `rom.rsf` | upstream | **inherited templates, must be ported** — see below |
| `config.mk` | edited | now defaults `GAME_VERSION=BLACK2` and adds a `WHITE2` case (Diamond/Pearl kept for reference) |
| `pokeblack2.us.sha1` | new | expected SHA1 of the source ROM (verified to match the local `pokeblack2.nds`) |
| `setvars.sh` | new | one-shot env activator — sets `DEVKITPRO`/`DEVKITARM` and exports the cross toolchain. Run `. ./setvars.sh` before building. (Untracked; add `setvars*.sh` to `.gitignore` if you want it ignored.) |
| `src/main.c`, `include/twl/*.h`, `README.md`, `.gitignore` | pre-existing | left untouched |

## Toolchain (provisioned)

- **MWCC** `tools/mwccarm/` run via `wine`. The build invokes `2.0/sp2p3` and `1.2/sp2p3` per FUNCTION; require an initial `wine tools/mwccarm/2.0/sp2p3/mwccarm.exe` run on a desktop session so it registers `license.dat` against your wineprefix. Headless runs can fail to find the registry on first invocation.
  - **B2 compiler (first test):** ARM9 `sub_0204D414` (a 20-byte Thumb table
    dispatch) matches byte-for-byte with `-O4,p -proc arm946e -thumb -enum int
    -char signed` under `2.0/sp2p3` and every `dsi/*` version tried (1.1, 1.2p1,
    1.3, 1.6sp2). `1.2/sp2p3` does **not** match (wrong prologue). The exact
    version still needs a function with more control flow to pin down.
- **Nitro SDK** at `tools/bin/` (flattened). Run `.exe` tools via wine directly. Cygwin-only unix helpers (`blxchecker`, `nitrorun`, `init2env`, `dis`, `loadrun`) require Cygwin — they will fail on Linux; pret projects reimplement them (you already have `tools/asmdiff/`, `tools/jsonproc/`, `tools/o2narc/` which cover that surface).
- **devkitARM r68 / gcc 16.1.0 / binutils 2.46.0** installed to user-prefix `~/devkitpro/opt/devkitpro/devkitARM/` (because `/opt/devkitpro/{tools,pacman/var/lib/pacman/sync}` had root-owned subtrees blocking a system install). Activated by sourcing `setvars.sh`. **GCC 16.1.0 is too new for matching**; fine for non-matching builds and for asm pre-processing via `tools/asm_processor/asm_processor.py`.

## What you must still do

### 1. ~~Acquire proprietary components~~ **(done)**
- ~~**MWCC** in `tools/mwccarm/`, license.dat present, runs under wine.~~
- ~~**Nitro SDK** flattened into `tools/bin/`, lcf templates in `arm7/` and `arm9/`.~~

### 2. ~~Decide on a toolchain~~ **(done — devkitARM installed)**

- ~~`arm-none-eabi-gcc` 16.1.0 via `dkp-pacman` install at `~/devkitpro/opt/devkitpro/devkitARM`.~~
- ~~Activated by `setvars.sh` (or by exporting `DEVKITPRO`/`DEVKITARM` in your shell rc).~~
- **Note:** GCC 16.1.0 will not produce matching output — that's what MWCC is for. The
  devkitARM install is for non-matching exploration and for asm preprocessing.

### 3. Reverse-engineer and stage the B2 binaries

Pret DS decompilation typically organises binaries into:

- `arm7/` — ARM7TDMI BIOS-call code (touch screen, RTC, mic, sound transfer).
  Comes from the **ARM7 binary** inside `pokeblack2.nds` (ROM offset 0x33A400,
  loaded at 0x02380000, 0x28F84 bytes).
- `arm9/` — main game logic. Comes from the ARM9 binary (ROM offset 0x4000,
  loaded at 0x02004000, entry 0x02004800). **The ARM9 static module is
  BLZ-compressed** (`compressed_static_end` = 0x020776A4 in its module params);
  it decompresses from 0x736A4 to 0x9AC00 bytes.
- `arm9/overlays/overlay_*.s` — 344 ARM9 overlays (IDs 0–343). 332 are
  BLZ-compressed and all 344 have the signed flag set; there are no ARM7
  overlays. The ARM7 static module is not compressed.
- `data/` — NitroFS files extracted from the ROM's dataNarcs.
- `files/`, `graphics/` — extracted assets (`.NARC`, `.NCGR`, `.NCLR`, etc.).

You will need to:
1. ~~Write `extract.py`~~ **(done)**. Run `./extract.py` from the repo root
   (needs Python's `cryptography` package). It writes, all gitignored:
   `arm9/baserom.bin`, `arm7/baserom.bin`, the overlay table
   `arm9/baserom.ovt.bin`, every decompressed overlay in
   `arm9/baserom_overlays/`, the DSi modules `arm9i/baserom.bin` and
   `arm7i/baserom.bin`, and all 318 NitroFS files under `baserom_files/`
   (272M; mostly NARCs in `a/N/N/N`, plus `.sdat` sound data and the
   download-play child ROMs in `dl_rom/`).
2. Generate an initial `pokeblack2.us.bsf` (Banjo Symbol File) using the disassembler
   of your choice (Ghidra, IDA, mwasmarm) so the asm can reference named labels.

### 4. Port the inherited makefiles

- **`Makefile`** — references `arm7/`, `arm9/`, `files/`, `graphics/` which don't
  exist yet. Wires up `$(BUILD_NAME)` = `black2.us` once the binaries are in place.
- **`graphics_rules.mk`** — lists every NCGR/NCLR/NARC by path; most names differ
  between Diamond and B2. Will be substantially rewritten.
- **`filesystem.mk`** — `NITROFS_FILES :=` list is fully Diamond-specific. Will be
  rewritten from a real B2 NARC dump.
- **`rom.rsf`** — NitroMaker Makefile. B2 uses a different SDK header layout; this
  needs verification against the real ARM7/ARM9 binaries.
- **`config.mk`** — `SECURE_CRC` for `CPUIE`/`CPVIE` is left as `0x0000` placeholder;
  you must read the secure-area CRC from the actual B2 binary before release builds.

### 5. Decide on matching vs. non-matching mode

- Start in `SHIFTED=1` (no hash comparison) to iterate quickly.
- Once individual functions recompile byte-for-byte under MWCC, switch to
  `COMPARE=1 SHIFTED=0` to enforce hash matching.

## Honest scope warning

There is **no publicly released Black 2 / White 2 decompilation** yet. Every other
entry in `pret/` (Diamond, Pearl, Platinum, HG/SS, BW1, B2W2, etc.) is non-trivial;
B2/W2 in particular uses a compressed ARM9 module, an expanded NitroFS
layout, and is a DSi-enhanced title: the `pokeblack2.nds` header has unit code
0x02 (NDS+DSi) and the ARM9 module params report SDK version 0x0503757C (TWL
SDK 5.x). The DSi-only modules are ARM9i (loaded at 0x02400000, its first
0x4000 bytes modcrypt-encrypted with the retail key, then BLZ-compressed) and
ARM7i (loaded at 0x02E80000, plain). Their compression info lives in "ltd"
module params inside the ARM9/ARM7 static modules (magic 0xDEC01463).

The scaffold above gives you the universal build helpers and a porting starting
point. Most of the work — baserom extractor, BSF symbols, ARM7/ARM9/overlay
split, NitroFS reverse-engineering, individual function matches — is project
work that nobody has published yet.
