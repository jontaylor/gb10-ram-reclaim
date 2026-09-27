#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Convert explicit undefined AArch64 ELF symbols to kernel livepatch relocations.

The kernel resolves addresses; no guessed addresses or function redirections.
Always transform BEFORE signing. See docs/design.md for the narrow support scope.
"""
import argparse
import struct
from pathlib import Path


def transform(raw, targets):
    if not __debug__:
        raise ValueError('Do not run this transformer with Python optimization enabled')
    if not targets or len(set(targets)) != len(targets):
        raise ValueError('Supply unique, explicit target symbols')
    if raw.endswith(b'~Module signature appended~\n'):
        raise ValueError('Input is signed; transform the unsigned module before signing')
    b = bytearray(raw)
    assert len(b) >= 64, 'truncated ELF header'
    assert b[:6] == b'\x7fELF\x02\x01', 'requires ELF64 little-endian'
    assert struct.unpack_from('<H', b, 18)[0] == 183, 'requires AArch64'
    assert struct.unpack_from('<H', b, 16)[0] == 1, 'requires relocatable ELF'
    off = struct.unpack_from('<Q', b, 40)[0]
    entsz, n, shstridx = struct.unpack_from('<HHH', b, 58)
    assert entsz == 64 and n and shstridx < n
    assert off + n * 64 <= len(b), 'truncated section table'
    fmt = '<IIQQQQIIQQ'
    headers = [list(struct.unpack_from(fmt, b, off + i * 64)) for i in range(n)]
    assert all(h[1] == 8 or h[4] + h[5] <= len(b) for h in headers), 'truncated section'
    data = [bytes(b[h[4]:h[4] + h[5]]) if h[1] != 8 else b'' for h in headers]
    def zstring(x, pos):
        return x[pos:x.index(b'\0', pos)].decode()
    names = [zstring(data[shstridx], h[0]) for h in headers]
    symidx = names.index('.symtab')
    stridx = headers[symidx][6]
    strings = bytearray(data[stridx])
    symbols = bytearray(data[symidx])
    assert headers[symidx][9] == 24
    chosen = {}
    for i in range(len(symbols) // 24):
        no, info, other, ndx, value, size = struct.unpack_from('<IBBHQQ', symbols, i * 24)
        name = zstring(strings, no)
        if name in targets:
            assert ndx == 0 and value == 0, 'target must be undefined: ' + name
            chosen[i] = name
            newname = f'.klp.sym.vmlinux.{name},0'.encode() + b'\0'
            struct.pack_into('<I', symbols, i * 24, len(strings))
            struct.pack_into('<H', symbols, i * 24 + 6, 0xff20)
            strings.extend(newname)
    assert set(chosen.values()) == set(targets), 'missing target symbol'
    data[symidx], data[stridx] = bytes(symbols), bytes(strings)
    shnames = bytearray(data[shstridx])
    count = 0
    for i in range(n):
        h = headers[i]
        if h[1] != 4:
            continue
        assert h[9] == 24 and len(data[i]) % 24 == 0
        assert h[7] < n
        normal, klp = bytearray(), bytearray()
        for pos in range(0, len(data[i]), 24):
            entry = data[i][pos:pos+24]
            _, info, _ = struct.unpack('<QQq', entry)
            (klp if info >> 32 in chosen else normal).extend(entry)
        if not klp:
            continue
        assert h[6] == symidx
        data[i] = bytes(normal)
        name = '.klp.rela.vmlinux.' + names[h[7]].lstrip('.')
        newh = h.copy()
        newh[0] = len(shnames)
        newh[2] = 0x100000 | 0x40 | 0x2  # LIVEPATCH | INFO_LINK | ALLOC
        shnames.extend(name.encode() + b'\0')
        headers.append(newh)
        data.append(bytes(klp))
        count += len(klp) // 24
    data[shstridx] = bytes(shnames)
    assert count
    # Append rebuilt sections. Existing debug and alloc section indexes stay fixed.
    for i, h in enumerate(headers):
        if i == 0 or h[1] == 8:
            continue
        alignment = max(h[8], 1)
        b.extend(b'\0' * ((-len(b)) % alignment))
        h[4], h[5] = len(b), len(data[i])
        b.extend(data[i])
    b.extend(b'\0' * ((-len(b)) % 8))
    new_off = len(b)
    for h in headers:
        b.extend(struct.pack(fmt, *h))
    struct.pack_into('<Q', b, 40, new_off)
    struct.pack_into('<H', b, 60, len(headers))
    return bytes(b), count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('symbols', nargs='+')
    args = parser.parse_args()
    if args.source.resolve() == args.destination.resolve() or args.destination.exists():
        parser.error('Destination must be a new file, distinct from input')
    try:
        result, count = transform(args.source.read_bytes(), args.symbols)
    except (AssertionError, ValueError, IndexError, struct.error) as error:
        parser.error(str(error) or 'Malformed or unsupported ELF')
    with args.destination.open('xb') as output:
        output.write(result)
    print(f'Encoded {count} livepatch relocations for {sorted(args.symbols)}')


if __name__ == '__main__':
    main()
