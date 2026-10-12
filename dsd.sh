#!/usr/bin/env bash
# Run ds-decomp (dsd) on the B2 ROM.
#
# Usage: ./dsd.sh extract|init|verify
#   extract  Extract pokeblack2.nds into extract/black2.us/ (gitignored).
#   init     Generate config/black2.us/ (symbols, relocations, delinks) from
#            the extracted ROM. Refuses to overwrite an existing config, since
#            that would throw away any symbols renamed by hand.
#   verify   Rebuild a ROM from extract/black2.us/ and check it against
#            pokeblack2.us.sha1.
#
# Environment:
#   DSD   dsd binary to use (default: dsd-dsi). B2 needs a dsd built against
#         ds-rom with DSi-enhanced support (AetiasHax/ds-rom PR #30) until
#         that is released.
#   BIOS7 Nintendo DS ARM7 BIOS dump, needed by verify to hash the encrypted
#         secure area (default: ../bios7.bin). Never commit it.

set -euo pipefail
cd "$(dirname "$0")"

DSD=${DSD:-dsd-dsi}
BIOS7=${BIOS7:-../bios7.bin}
ROM=pokeblack2.nds
NAME=black2.us
EXTRACT=extract/$NAME
CONFIG=config/$NAME
BUILD=build/$NAME

case "${1:-}" in
  extract)
    "$DSD" rom extract -r "$ROM" -o "$EXTRACT"
    ;;
  init)
    [[ -e $CONFIG ]] && { echo "$CONFIG already exists; delete it first to regenerate" >&2; exit 1; }
    [[ -e $EXTRACT/config.yaml ]] || { echo "run '$0 extract' first" >&2; exit 1; }
    # Some functions are only reached by calls that dsd's analysis does not
    # follow (e.g. 234 in overlay 36); keep them as size-0 "unknown" symbols
    # instead of aborting.
    "$DSD" init -r "$EXTRACT/config.yaml" -o "$CONFIG" -b "$BUILD" --allow-unknown-function-calls
    ;;
  verify)
    [[ -f $BIOS7 ]] || { echo "ARM7 BIOS not found at $BIOS7 (set BIOS7)" >&2; exit 1; }
    mkdir -p "$BUILD"
    "$DSD" rom build -c "$EXTRACT/config.yaml" -7 "$BIOS7" -o "$BUILD/rebuilt.nds"
    (cd "$BUILD" && sed "s|pokeblack2.nds|rebuilt.nds|" ../../pokeblack2.us.sha1 | sha1sum -c -)
    ;;
  *)
    sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
