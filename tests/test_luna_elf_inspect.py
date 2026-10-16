#!/usr/bin/env python3
"""Synthetic ELF/SELF cases; never requires or distributes a game executable."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('luna_inspect', Path(__file__).resolve().parents[1] / 'tools/analysis/inspect_luna_elf.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def elf():
    data = bytearray(0x1500)
    ident = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<16sHHIQQQIHHHHHH', data, 0, ident, 3, 62, 1, 0x40, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0x1000, 0, 0, 0x500, 0x500, 0x1000)
    struct.pack_into('<IIQQQQQQ', data, 120, 2, 4, 0x1400, 0x400, 0, 96, 96, 8)
    data[0x1100:0x110f] = b'CheckpointName\0'
    wide = 'CheckpointName: %s\0'.encode('utf-16-le')
    data[0x1120:0x1120 + len(wide)] = wide
    struct.pack_into('<QQq', data, 0x1300, 0x200, 8, 0x40)
    for i, (tag, value) in enumerate([(25, 0x200), (27, 8), (7, 0x300), (8, 24), (9, 24), (0, 0)]):
        struct.pack_into('<qQ', data, 0x1400 + i * 16, tag, value)
    return data


class Tests(unittest.TestCase):
    def inspect(self, data):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'fixture.bin'
            p.write_bytes(data)
            image = tool.Image(p)
            try:
                return tool.analyze(image, 'CheckpointName')
            finally:
                image.close()

    def test_sectionless_relocated_init_and_wide_string(self):
        report = self.inspect(elf())
        self.assertEqual(report['initializer_entries'][0]['raw_value'], 0)
        self.assertEqual(report['initializer_entries'][0]['relative_target_rva'], 0x40)
        self.assertEqual([(s['rva'], s['encoding'], s['followed_by_terminator']) for s in report['string_matches']],
                         [(0x100, 'ascii', True), (0x120, 'utf-16-le', False)])
        self.assertFalse(report['verified_live_object'])

    def test_self_mapping_is_not_embedded_elf_header_offset(self):
        raw = elf()
        data = bytearray(0x1500)
        data[:4] = b'\x54\x14\xf5\xee'
        struct.pack_into('<H', data, 24, 1)
        struct.pack_into('<QQQQ', data, 32, 0x804, 0x1000, 0x500, 0x500)
        data[64:64 + 176] = raw[:176]
        data[0x1000:] = raw[0x1000:]
        report = self.inspect(data)
        self.assertEqual(report['initializer_entries'][0]['relative_target_rva'], 0x40)
        self.assertEqual(report['string_matches'][0]['elf_file_offset'], 0x1100)

    def test_truncated_program_data_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(elf()[:0x1000])

    def test_wrong_architecture_rejected(self):
        data = elf()
        struct.pack_into('<H', data, 18, 183)
        with self.assertRaises(ValueError):
            self.inspect(data)


if __name__ == '__main__':
    unittest.main()
