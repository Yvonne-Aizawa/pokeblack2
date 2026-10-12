#!/usr/bin/env python3
"""Extract binaries from pokeblack2.nds.

Writes, relative to OUTDIR (default: the current directory):
  arm9/baserom.bin                    ARM9 static module, BLZ-decompressed
  arm7/baserom.bin                    ARM7 static module
  arm9/baserom.ovt.bin                ARM9 overlay table, as stored in the ROM
  arm9/baserom_overlays/overlay_NNNN.bin
                                      every ARM9 overlay, BLZ-decompressed
  arm9i/baserom.bin                   DSi ARM9i module, modcrypt-decrypted
                                      and BLZ-decompressed
  arm7i/baserom.bin                   DSi ARM7i module
  baserom_files/...                   every NitroFS file, at its ROM path

All of these are gitignored. B2 has no ARM7 overlays.

Usage: extract.py [-o OUTDIR] [ROM]   (ROM defaults to pokeblack2.nds)
"""

import argparse
import os
import struct
import sys

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

NITROCODE_MAGIC = struct.pack('<2I', 0xDEC00621, 0x2106C0DE)
# Marks the TWL SDK's "ltd" module params, which describe the DSi-only
# ARM9i/ARM7i modules and live in the ARM9/ARM7 static modules respectively.
LTD_MAGIC = struct.pack('<2I', 0xDEC01463, 0x6314C0DE)


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


def modcrypt_key(rom):
    """Derive the retail modcrypt AES key from the DSi header.

    KeyX is "Nintendo" + gamecode + reversed gamecode, KeyY is the first 16
    bytes of the ARM9i HMAC, and the DSi key scrambler combines them as
    ((KeyX ^ KeyY) + C) rol 42 on little-endian 128-bit values.
    """
    if rom[0x1C] & 4:
        sys.exit('error: ROM uses the debug modcrypt key, which is not supported')
    gamecode = rom[0xC:0x10]
    key_x = int.from_bytes(b'Nintendo' + gamecode + gamecode[::-1], 'little')
    key_y = int.from_bytes(rom[0x350:0x360], 'little')
    mask = (1 << 128) - 1
    key = ((key_x ^ key_y) + 0xFFFEFB4E295902582A680F5F1A4F3E79) & mask
    key = ((key << 42) | (key >> 86)) & mask
    return key.to_bytes(16, 'little')


def modcrypt_decrypt(rom):
    """Return a copy of the ROM with its modcrypt areas decrypted.

    Modcrypt is AES-CTR, but the DSi AES engine works on byte-reversed
    blocks: reversing the key, the counter and every 16-byte block turns it
    into standard AES-CTR.
    """
    rom = bytearray(rom)
    if not rom[0x1C] & 2:
        return rom
    key = modcrypt_key(rom)[::-1]
    reverse_blocks = lambda b: b''.join(b[i:i + 16][::-1] for i in range(0, len(b), 16))
    area1_off, area1_size, area2_off, area2_size = struct.unpack_from('<4I', rom, 0x220)
    if area2_size:
        sys.exit('error: ROM has a second modcrypt area, which is not supported')
    if area1_size:
        iv = bytes(rom[0x300:0x310])[::-1]
        dec = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor()
        data = rom[area1_off:area1_off + area1_size]
        rom[area1_off:area1_off + area1_size] = reverse_blocks(dec.update(reverse_blocks(data)))
    return rom


def extract_ltd(rom, header_off, static, name):
    """Extract the DSi ARM9i/ARM7i module described at header_off.

    Its compressed end comes from the ltd module params in the matching
    static module: autoload_list, autoload_list_end, autoload_start,
    compressed_static_end, magic[2].
    """
    off, _, ram, size = struct.unpack_from('<4I', rom, header_off)
    module = bytearray(rom[off:off + size])
    magic = static.find(LTD_MAGIC)
    if magic < 0:
        sys.exit(f'error: {name} ltd module params not found')
    comp_end = struct.unpack_from('<I', static, magic - 4)[0]
    print(f'{name}: ram {ram:#010x} size {size:#x} compressed_static_end {comp_end:#010x}')
    if comp_end:
        cut = comp_end - ram
        module = blz_decompress(module[:cut]) + module[cut:]
    return module


def walk_nitrofs(rom):
    """Yield (path, data) for every file in the NitroFS file name table."""
    fnt_off, _, fat_off = struct.unpack_from('<3I', rom, 0x40)

    def walk(dir_id, prefix):
        sub_off, file_id = struct.unpack_from('<IH', rom, fnt_off + 8 * (dir_id & 0xFFF))
        pos = fnt_off + sub_off
        while True:
            length = rom[pos]
            pos += 1
            if length == 0:
                return
            name = rom[pos:pos + (length & 0x7F)].decode('ascii')
            pos += length & 0x7F
            if name in ('.', '..') or '/' in name or '\\' in name:
                sys.exit(f'error: unsafe NitroFS name {name!r}')
            if length & 0x80:
                sub_dir = struct.unpack_from('<H', rom, pos)[0]
                pos += 2
                yield from walk(sub_dir, prefix + name + '/')
            else:
                start, end = struct.unpack_from('<2I', rom, fat_off + 8 * file_id)
                yield prefix + name, rom[start:end]
                file_id += 1

    yield from walk(0xF000, '')


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

    arm9 = extract_static(rom, 0x20, 'ARM9')
    arm7 = extract_static(rom, 0x30, 'ARM7')
    write(out('arm9', 'baserom.bin'), arm9)
    write(out('arm7', 'baserom.bin'), arm7)

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

    if rom[0x12] & 2:
        twl = modcrypt_decrypt(rom)
        write(out('arm9i', 'baserom.bin'), extract_ltd(twl, 0x1C0, arm9, 'ARM9i'))
        write(out('arm7i', 'baserom.bin'), extract_ltd(twl, 0x1D0, arm7, 'ARM7i'))

    count = size = 0
    for path, data in walk_nitrofs(rom):
        write(out('baserom_files', *path.split('/')), data)
        count += 1
        size += len(data)
    print(f'NitroFS: {count} files, {size:#x} bytes')


if __name__ == '__main__':
    main()
