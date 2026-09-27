# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic ELF fixtures: no target kernel, root, or private binaries required."""
from pathlib import Path
import struct as s
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from klp_relocate import transform

FMT = '<IIQQQQIIQQ'


def fixture(defined=False):
    names = b'\0.data\0.rela.data\0.symtab\0.strtab\0.shstrtab\0'
    strings = b'\0init_mm\0ordinary_export\0'
    symbols = bytes(24) + s.pack('<IBBHQQ', 1, 0x10, 0, 1 if defined else 0, 0, 0)
    symbols += s.pack('<IBBHQQ', 9, 0x10, 0, 0, 0, 0)
    relas = s.pack('<QQq', 0, (1 << 32) | 257, 8) + s.pack('<QQq', 8, (2 << 32) | 257, 0)
    sections = [b'', bytes(16), relas, symbols, strings, names]
    headers = [[0] * 10,
               [names.index(b'.data'), 1, 3, 0, 0, 0, 0, 0, 8, 0],
               [names.index(b'.rela.data'), 4, 0x40, 0, 0, 0, 3, 1, 8, 24],
               [names.index(b'.symtab'), 2, 0, 0, 0, 0, 4, 1, 8, 24],
               [names.index(b'.strtab'), 3, 0, 0, 0, 0, 0, 0, 1, 0],
               [names.index(b'.shstrtab'), 3, 0, 0, 0, 0, 0, 0, 1, 0]]
    b = bytearray(64)
    b[:6] = b'\x7fELF\x02\x01'
    s.pack_into('<HH', b, 16, 1, 183)
    s.pack_into('<HHH', b, 58, 64, 6, 5)
    for h, data in zip(headers[1:], sections[1:]):
        b.extend(bytes((-len(b)) % max(h[8], 1)))
        h[4], h[5] = len(b), len(data)
        b.extend(data)
    b.extend(bytes((-len(b)) % 8))
    s.pack_into('<Q', b, 40, len(b))
    for h in headers:
        b.extend(s.pack(FMT, *h))
    return bytes(b)


def sections(raw):
    off = s.unpack_from('<Q', raw, 40)[0]
    count, names_idx = s.unpack_from('<HH', raw, 60)
    headers = [s.unpack_from(FMT, raw, off + i * 64) for i in range(count)]
    def data(h):
        return raw[h[4]:h[4]+h[5]]
    names = data(headers[names_idx])
    return {names[h[0]:].split(b'\0', 1)[0].decode(): (h, data(h)) for h in headers}


class RelocationTests(unittest.TestCase):
    def test_split_preserves_normal_relocations_and_addends(self):
        raw = fixture()
        output, count = transform(raw, ['init_mm'])
        self.assertEqual(count, 1)
        before, after = sections(raw), sections(output)
        self.assertEqual(after['.data'][1], before['.data'][1])
        self.assertEqual(after['.rela.data'][1], before['.rela.data'][1][24:])
        header, klp = after['.klp.rela.vmlinux.data']
        self.assertEqual(klp, before['.rela.data'][1][:24])
        self.assertEqual(header[2], 0x100042)
        self.assertEqual(header[6:8], (3, 1))
        symbol = s.unpack_from('<IBBHQQ', after['.symtab'][1], 24)
        self.assertEqual(symbol[3], 0xff20)
        self.assertEqual(after['.strtab'][1][symbol[0]:].split(b'\0')[0], b'.klp.sym.vmlinux.init_mm,0')
        self.assertEqual(after['.symtab'][1][48:], before['.symtab'][1][48:])

    def test_refuses_defined_missing_duplicate_or_empty_targets(self):
        for raw, targets in [(fixture(True), ['init_mm']), (fixture(), ['missing']),
                             (fixture(), []), (fixture(), ['init_mm', 'init_mm'])]:
            with self.assertRaises((AssertionError, ValueError)):
                transform(raw, targets)

    def test_refuses_signed_and_reprocessed_modules(self):
        with self.assertRaises(ValueError):
            transform(fixture() + b'~Module signature appended~\n', ['init_mm'])
        output, _ = transform(fixture(), ['init_mm'])
        with self.assertRaises(AssertionError):
            transform(output, ['init_mm'])

    def test_refuses_truncation_and_wrong_arch(self):
        wrong = bytearray(fixture())
        s.pack_into('<H', wrong, 18, 62)
        for raw in (b'', fixture()[:40], fixture()[:-8], wrong):
            with self.assertRaises(AssertionError):
                transform(raw, ['init_mm'])

    def test_cli_never_overwrites_input_or_destination(self):
        tool = Path(__file__).resolve().parents[1] / 'tools/klp_relocate.py'
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/'input.ko'
            dst = Path(tmp)/'output.ko'
            src.write_bytes(fixture())
            dst.write_bytes(b'preserve')
            for path in (src, dst):
                proc = subprocess.run([sys.executable, str(tool), str(src), str(path), 'init_mm'], capture_output=True)
                self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(src.read_bytes(), fixture())
            self.assertEqual(dst.read_bytes(), b'preserve')

    def test_optimized_python_fails_closed(self):
        tool = Path(__file__).resolve().parents[1] / 'tools/klp_relocate.py'
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/'input.ko', Path(tmp)/'output.ko'
            src.write_bytes(fixture())
            result = subprocess.run([sys.executable, '-O', str(tool), str(src), str(dst), 'init_mm'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(dst.exists())


if __name__ == '__main__':
    unittest.main()
