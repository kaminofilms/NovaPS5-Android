#!/usr/bin/env python3
"""Read-only ELF64/clear SELF inspection. Addresses are module-relative, never host PCs.

Dependencies for --xrefs: numpy and capstone. Does not decrypt encrypted SELF,
execute guest code, patch files, or infer a live object from a string match.
"""
import argparse
import hashlib
import json
import mmap
import struct
from pathlib import Path


class Image:
    def __init__(self, path):
        self.file = None
        self.data = None
        try:
            self._load(path)
        except BaseException:
            self.close()
            raise

    def _load(self, path):
        self.file = open(path, 'rb')
        self.data = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.self_entries = []
        self.is_self = self.data[:4] in (b'\x54\x14\xf5\xee', b'\x4f\x15\x3d\x1d')
        self.header_offset = 0
        if self.is_self:
            count = struct.unpack_from('<H', self.data, 24)[0]
            if count > 512 or 32 + count * 32 + 64 > len(self.data):
                raise ValueError('Invalid SELF table')
            self.self_entries = [struct.unpack_from('<QQQQ', self.data, 32 + i * 32) for i in range(count)]
            self.header_offset = 32 + count * 32
        h = struct.unpack_from('<16sHHIQQQIHHHHHH', self.data, self.header_offset)
        if h[0][:7] != b'\x7fELF\x02\x01\x01' or h[2] != 62 or h[9] != 56:
            raise ValueError('Expected little-endian ELF64 x86-64')
        self.elf_type, self.entry, self.section_offset = h[1], h[4], h[6]
        if not 0 < h[10] <= 512:
            raise ValueError('Invalid program-header count')
        self.ph = [struct.unpack_from('<IIQQQQQQ', self.data, self.header_offset + h[5] + i * 56) for i in range(h[10])]
        self.blocks = []
        if self.is_self:
            for flags, offset, stored, expanded in self.self_entries:
                if not flags & 0x800:
                    continue
                idx = (flags >> 20) & 0xfff
                if idx >= len(self.ph) or flags & 0xa or stored != expanded or expanded != self.ph[idx][5]:
                    raise ValueError('Encrypted/compressed/unsupported SELF payload; no decryption attempted')
                if offset + stored > len(self.data):
                    raise ValueError('Truncated SELF payload')
                self.blocks.append((self.ph[idx][2], stored, offset, idx))
        self.tags = {}
        for p in self.ph:
            if p[0] != 2:
                continue
            raw = self.read_offset(p[2], p[5])
            for tag, value in struct.iter_unpack('<qQ', raw):
                if not tag:
                    break
                self.tags.setdefault(tag, []).append(value)

    def close(self):
        if self.data is not None:
            self.data.close()
            self.data = None
        if self.file is not None:
            self.file.close()
            self.file = None

    def read_offset(self, offset, size):
        if offset < 0 or size < 0:
            raise ValueError('Negative file range')
        if not self.is_self:
            if offset + size <= len(self.data):
                return self.data[offset:offset + size]
        else:
            for logical, length, physical, _ in self.blocks:
                if logical <= offset and offset + size <= logical + length:
                    start = physical + offset - logical
                    return self.data[start:start + size]
        raise ValueError(f'Unbacked ELF file range {offset:#x}+{size:#x}')

    def file_offset(self, address, size=1):
        for p in self.ph:
            if p[0] == 1 and p[3] <= address and address + size <= p[3] + p[5]:
                return p[2] + address - p[3]
        raise ValueError(f'Unbacked virtual range {address:#x}+{size:#x}')

    def read_va(self, address, size):
        return self.read_offset(self.file_offset(address, size), size)

    def tag(self, key, default=0):
        return self.tags.get(key, [default])[0]

    def relocations(self):
        seen = set()
        for table, size, stride in ((7, 8, 9), (23, 2, 9)):
            if not self.tag(size):
                continue
            if self.tag(stride, 24) != 24 or self.tag(size) % 24:
                raise ValueError('Unsupported RELA entry size')
            raw = self.read_va(self.tag(table), self.tag(size))
            for offset, info, addend in struct.iter_unpack('<QQq', raw):
                key = (offset, info, addend)
                if key in seen:
                    continue
                seen.add(key)
                yield offset, info & 0xffffffff, info >> 32, addend

    def strings(self, needle):
        found = []
        for p in self.ph:
            if p[0] != 1:
                continue
            data = self.read_offset(p[2], p[5])
            for encoding in ('ascii', 'utf-16-le'):
                raw = needle.encode(encoding)
                position = 0
                while (position := data.find(raw, position)) >= 0:
                    terminator = b'\0' if encoding == 'ascii' else b'\0\0'
                    found.append({'rva': p[3] + position, 'elf_file_offset': p[2] + position, 'encoding': encoding,
                                  'followed_by_terminator': data[position + len(raw):position + len(raw) + len(terminator)] == terminator})
                    position += len(raw)
        return found

    def rip_xrefs(self, targets):
        # Vector scan proposes disp32 locations; Capstone validates each candidate
        # as an instruction with a real RIP-relative memory operand. Full function
        # control-flow boundaries still require manual confirmation.
        import numpy as np
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        from capstone.x86 import X86_OP_MEM, X86_REG_RIP
        decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        decoder.detail = True
        result = []
        unique = set()
        for p in self.ph:
            if p[0] != 1 or not p[1] & 1:
                continue
            code = self.read_offset(p[2], p[5])
            for chunk in range(0, len(code), 1 << 20):
                stop = min(len(code), chunk + (1 << 20))
                for alignment in range(4):
                    start = chunk + alignment
                    count = max(0, (stop - start) // 4)
                    if not count:
                        continue
                    values = np.frombuffer(code, dtype='<i4', count=count, offset=start).astype(np.int64)
                    positions = start + np.arange(count, dtype=np.int64) * 4
                    endpoints = p[3] + positions + 4
                    for target in targets:
                        for index in np.flatnonzero(values + endpoints == target):
                            disp = int(positions[index])
                            for instruction_start in range(max(0, disp - 11), disp):
                                instruction = next(decoder.disasm(code[instruction_start:disp + 4], p[3] + instruction_start, count=1), None)
                                if instruction is None or instruction.address + instruction.size != p[3] + disp + 4:
                                    continue
                                if any(op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and
                                       instruction.address + instruction.size + op.mem.disp == target for op in instruction.operands):
                                    key = (instruction.address, target)
                                    if key not in unique:
                                        unique.add(key)
                                        result.append({'instruction_rva': instruction.address, 'target_rva': target,
                                                       'instruction': instruction.mnemonic + ' ' + instruction.op_str,
                                                       'boundary_status': 'candidate; confirm containing function'})
        return sorted(result, key=lambda x: (x['target_rva'], x['instruction_rva']))


def analyze(image, needle, xrefs=False):
    matches = image.strings(needle)
    targets = {x['rva'] for x in matches}
    refs, relative, counts = [], {}, {}
    for offset, kind, symbol, addend in image.relocations():
        counts[str(kind)] = counts.get(str(kind), 0) + 1
        if kind == 8 and symbol == 0:
            relative[offset] = addend
        if addend in targets:
            refs.append({'slot_rva': offset, 'type': kind, 'symbol_index': symbol, 'addend': addend})
    initializers = []
    for address_tag, size_tag, name in ((25, 27, 'init_array'), (32, 33, 'preinit_array')):
        address, size = image.tag(address_tag), image.tag(size_tag)
        if size % 8:
            raise ValueError('Misaligned initialization array')
        for i in range(size // 8):
            slot = address + i * 8
            raw = struct.unpack('<Q', image.read_va(slot, 8))[0]
            initializers.append({'array': name, 'slot_rva': slot, 'raw_value': raw,
                                 'relative_target_rva': relative.get(slot),
                                 'status': 'relative relocation' if slot in relative else 'raw/unresolved'})
    return {
        'format': 'clear SELF containing ELF64 x86-64' if image.is_self else 'ELF64 x86-64',
        'input_sha256': hashlib.sha256(image.data).hexdigest(),
        'elf_type': hex(image.elf_type), 'entry_rva': image.entry,
        'section_header_offset': image.section_offset,
        'section_headers_recovered': False,
        'address_convention': 'module-relative virtual address; runtime address = actual load bias + RVA',
        'dt_init_rva': image.tag(12), 'dt_init_array_rva': image.tag(25),
        'dt_init_array_bytes': image.tag(27), 'dt_preinit_array_bytes': image.tag(33),
        'initializer_entries': initializers, 'relocation_counts': counts,
        'needle': needle, 'string_matches': matches, 'relocations_to_strings': refs,
        'rip_relative_string_xrefs': image.rip_xrefs(targets) if xrefs else [],
        'verified_live_object': False,
        'limits': ['String/code/data references do not establish a live object or layout.',
                   'RIP scan covers disp32 operands ending at the instruction end, not trailing-immediate forms.',
                   'REL, RELR and Sony-specific-only dynamic-table variants are not decoded by this tool.',
                   'No runtime load bias is assumed and no guest instruction is executed.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--needle', default='CheckpointName')
    parser.add_argument('--xrefs', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    image = None
    try:
        image = Image(args.binary)
        report = analyze(image, args.needle, args.xrefs)
        output = json.dumps(report, indent=2) + '\n'
        if args.output:
            args.output.write_text(output)
        else:
            print(output, end='')
    except (ValueError, OSError, struct.error, ImportError) as exc:
        parser.exit(1, f'Inspection failed: {exc}\n')
    finally:
        if image:
            image.close()


if __name__ == '__main__':
    main()
