#!/usr/bin/env python3
"""Extract binaries from pokeblack2.nds.

Writes, relative to OUTDIR (default: the current directory):
  arm9/baserom.bin                    ARM9 static module, BLZ-decompressed
  arm7/baserom.bin                    ARM7 static module
  arm9/baserom.ovt.bin                ARM9 overlay table, as stored in the ROM
  arm9/baserom_overlays/overlay_NNNN.bin
                                      every ARM9 overlay, BLZ-decompressed

All of these are gitignored. B2 has no ARM7 overlays.

Usage: extract.py [-o OUTDIR] [ROM]   (ROM defaults to pokeblack2.nds)
"""

import argparse
import os
import struct
import sys

NITROCODE_MAGIC = struct.pack('<2I', 0xDEC00621, 0x2106C0DE)


def blz_decompress(buf):
    """Decompress a BLZ-compressed buffer (as produced by the SDK's compstatic).

    The footer is two words: (header_len << 24 | enc_len), inc_len. Data is
    decoded from the end of the buffer towards the start, growing the output by
    inc_len bytes. Bytes before (len - enc_len) are stored uncompressed.
    """
    enc_len_hdr, inc_len = struct.unpack_from('<II', buf, len(buf) - 8)
    hdr_len = enc_len_hdr >> 24
    enc_len = enc_len_hdr & 0xFFFFFF
    out = bytearray(buf) + bytearray(inc_len)
    src = len(buf) - hdr_len
    dst = len(out)
    stop = len(buf) - enc_len
    while src > stop:
        src -= 1
        flags = out[src]
        for _ in range(8):
            if src <= stop:
                break
            if flags & 0x80:
                src -= 2
                v = out[src] | (out[src + 1] << 8)
                n = (v >> 12) + 3
                disp = (v & 0xFFF) + 3
                for _ in range(n):
                    dst -= 1
                    out[dst] = out[dst + disp]
            else:
                src -= 1
                dst -= 1
                out[dst] = out[src]
            flags = (flags << 1) & 0xFF
    return out


def extract_static(rom, header_off, name):
    off, entry, ram, size = struct.unpack_from('<4I', rom, header_off)
    module = bytearray(rom[off:off + size])

    # The module params block sits right before the nitrocode magic words:
    # autoload_list, autoload_list_end, autoload_start, static_bss_start,
    # static_bss_end, compressed_static_end, sdk_version, magic[2]
    magic = module.find(NITROCODE_MAGIC)
    if magic < 0:
        sys.exit(f'error: {name} module params not found')
    params = magic - 0x1C
    comp_end = struct.unpack_from('<I', module, params + 0x14)[0]
    sdk = struct.unpack_from('<I', module, params + 0x18)[0]
    print(f'{name}: ram {ram:#010x} entry {entry:#010x} size {size:#x} '
          f'sdk {sdk:#010x} compressed_static_end {comp_end:#010x}')

    if comp_end:
        cut = comp_end - ram
        module = blz_decompress(module[:cut]) + module[cut:]
        # The loader clears this once it has decompressed the module.
        struct.pack_into('<I', module, params + 0x14, 0)
    return module


def extract_overlays(rom, table_off_field):
    """Yield (id, overlay table entry, decompressed data) for each overlay.

    Entry layout: id, ram_start, ram_size, bss_size, sinit_start, sinit_end,
    file_id, flags. flags bits 0-23 are the compressed size and bit 24 marks
    the overlay as BLZ-compressed.
    """
    table_off, table_size = struct.unpack_from('<2I', rom, table_off_field)
    fat_off = struct.unpack_from('<I', rom, 0x48)[0]
    for i in range(table_size // 32):
        entry = struct.unpack_from('<8I', rom, table_off + 32 * i)
        ov_id, ram, ram_size, _, _, _, file_id, flags = entry
        start, end = struct.unpack_from('<2I', rom, fat_off + 8 * file_id)
        data = bytearray(rom[start:end])
        if flags & (1 << 24):
            comp_size = flags & 0xFFFFFF
            data = blz_decompress(data[:comp_size]) + data[comp_size:]
        if len(data) != ram_size:
            sys.exit(f'error: overlay {ov_id} is {len(data):#x} bytes, '
                     f'expected {ram_size:#x}')
        yield ov_id, entry, data


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def main():
    parser = argparse.ArgumentParser(description='Extract binaries from the B2 ROM.')
    parser.add_argument('rom', nargs='?', default='pokeblack2.nds')
    parser.add_argument('-o', '--outdir', default='.')
    args = parser.parse_args()
    with open(args.rom, 'rb') as f:
        rom = f.read()
    out = lambda *p: os.path.join(args.outdir, *p)

    write(out('arm9', 'baserom.bin'), extract_static(rom, 0x20, 'ARM9'))
    write(out('arm7', 'baserom.bin'), extract_static(rom, 0x30, 'ARM7'))

    table_off, table_size = struct.unpack_from('<2I', rom, 0x50)
    write(out('arm9', 'baserom.ovt.bin'), rom[table_off:table_off + table_size])
    count = compressed = 0
    for ov_id, entry, data in extract_overlays(rom, 0x50):
        write(out('arm9', 'baserom_overlays', f'overlay_{ov_id:04d}.bin'), data)
        count += 1
        compressed += bool(entry[7] & (1 << 24))
    print(f'ARM9 overlays: {count} ({compressed} compressed)')
    if struct.unpack_from('<I', rom, 0x5C)[0]:
        print('warning: ROM has ARM7 overlays, which are not extracted')


if __name__ == '__main__':
    main()
