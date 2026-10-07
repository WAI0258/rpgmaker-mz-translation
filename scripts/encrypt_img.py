#!/usr/bin/env python3
"""RPG Maker encrypted PNG/Ogg codec (MZ .png_/.ogg_, MV .rpgmvp/.rpgmvo).

Uses the engine's 16-byte header and first-16-byte XOR. Validate in memory
before writing; atomically replace one destination file via a sibling temporary
file. This is not a multi-file transaction or a cryptographic integrity check.
"""
import argparse
import os
import re
import tempfile
from pathlib import Path

HEADER = bytes([0x52, 0x50, 0x47, 0x4D, 0x56, 0, 0, 0, 0, 3, 1, 0, 0, 0, 0, 0])
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
OGG_MAGIC = b'OggS'


def key_bytes(key_hex):
    text = key_hex.strip()
    if not re.fullmatch(r'[0-9a-fA-F]{32}', text):
        raise ValueError('encryptionKey must be exactly 32 hex chars')
    return bytes.fromhex(text)


def is_encrypted(path):
    with path.open('rb') as file:
        return file.read(16) == HEADER


def validate_plain(data, audio):
    if len(data) < 16:
        raise ValueError('payload must contain at least 16 bytes')
    if not data.startswith(OGG_MAGIC if audio else PNG_MAGIC):
        raise ValueError('invalid Ogg/PNG signature; check input type or key')


def atomic_write(dst, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=dst.parent, prefix='.' + dst.name + '.',
                                         suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, dst)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def decrypt(src, dst, key_hex, audio=False):
    data = src.read_bytes()
    if data[:16] != HEADER:
        raise ValueError('not an RPG Maker encrypted container')
    if len(data) < 32:
        raise ValueError('truncated encrypted payload')
    key = key_bytes(key_hex)
    body = bytearray(data[16:])
    for i in range(16):
        body[i] ^= key[i]
    validate_plain(body, audio)
    atomic_write(dst, body)


def encrypt(src, dst, key_hex, audio=False):
    key = key_bytes(key_hex)
    data = bytearray(src.read_bytes())
    validate_plain(data, audio)
    for i in range(16):
        data[i] ^= key[i]
    atomic_write(dst, HEADER + data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['decrypt', 'encrypt', 'sig', 'check'])
    ap.add_argument('src')
    ap.add_argument('dst', nargs='?')
    ap.add_argument('--key')
    ap.add_argument('--audio', action='store_true', help='validate Ogg instead of PNG')
    args = ap.parse_args(argv)
    if args.mode in ('decrypt', 'encrypt') and (not args.dst or not args.key):
        ap.error('encrypt/decrypt require dst and --key')
    src = Path(args.src)
    try:
        if args.mode == 'sig':
            print(src.read_bytes()[:16].hex(' '))
        elif args.mode == 'check':
            print('encrypted' if is_encrypted(src) else 'plain')
        else:
            {'decrypt': decrypt, 'encrypt': encrypt}[args.mode](src, Path(args.dst), args.key, args.audio)
            print(f'{args.mode} ok -> {args.dst}')
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
