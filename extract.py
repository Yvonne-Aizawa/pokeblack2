#!/usr/bin/env python3
"""Extract binaries from pokeblack2.nds.

Currently extracts the ARM9 static module, undoing its BLZ ("backwards LZ")
compression so the result matches what is loaded into RAM at 0x02004000.

Usage: extract.py [ROM] [OUT]
  ROM defaults to pokeblack2.nds, OUT to arm9/baserom.bin.
"""

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


def extract_arm9(rom):
    off, entry, ram, size = struct.unpack_from('<4I', rom, 0x20)
    arm9 = bytearray(rom[off:off + size])

    # The module params block sits right before the nitrocode magic words:
    # autoload_list, autoload_list_end, autoload_start, static_bss_start,
    # static_bss_end, compressed_static_end, sdk_version, magic[2]
    magic = arm9.find(NITROCODE_MAGIC)
    if magic < 0:
        sys.exit('error: ARM9 module params not found')
    params = magic - 0x1C
    comp_end = struct.unpack_from('<I', arm9, params + 0x14)[0]
    sdk = struct.unpack_from('<I', arm9, params + 0x18)[0]
    print(f'ARM9: ram {ram:#010x} entry {entry:#010x} size {size:#x} '
          f'sdk {sdk:#010x} compressed_static_end {comp_end:#010x}')

    if comp_end:
        cut = comp_end - ram
        arm9 = blz_decompress(arm9[:cut]) + arm9[cut:]
        # The loader clears this once it has decompressed the module.
        struct.pack_into('<I', arm9, params + 0x14, 0)
    return arm9


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else 'pokeblack2.nds'
    out_path = sys.argv[2] if len(sys.argv) > 2 else 'arm9/baserom.bin'
    with open(rom_path, 'rb') as f:
        rom = f.read()
    arm9 = extract_arm9(rom)
    with open(out_path, 'wb') as f:
        f.write(arm9)
    print(f'wrote {out_path} ({len(arm9):#x} bytes)')


if __name__ == '__main__':
    main()
