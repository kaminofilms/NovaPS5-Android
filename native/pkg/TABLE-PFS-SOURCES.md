# Table-based PFS support (Nova 0.9.69)

Format and algorithm references checked on 2026-10-23:
- https://github.com/Coder787-source/KytyPlus/blob/main/src/package/naps/GameImage.cs
  (SPDX-License-Identifier: MIT), PfsGameTree and PfscGameImage.
- https://github.com/shadps4-emu/shadPS4/blob/main/src/core/file_format/pfs.h
  (GPL-2.0-or-later), inode and PFSC header layouts.

The Android C++ implementation is in package/tablePfs.cpp. It reads the inode
metadata immediately after the declared superblock while resolving file blocks
against the segment base. It supports unsigned 32-bit, signed 32-bit and signed
64-bit inode records, direct/indirect and contiguous chains, PFSC zlib/stored
blocks and nested PFS images. Files are streamed, with bounded metadata reads.
Existing legacy/superblock-first paths and the emulator core remain unchanged.
No keys, executable carving or heuristic inode scans are used. Encrypted data
and unrecognized nested image formats still fail explicitly. Update/DLC merging
and SELF-to-ELF conversion are not added. The existing decrypted ELF eboot.bin
validation remains mandatory before publication.

Synthetic regressions include a full data-first FIH install, signed 64-bit
inodes, fragmented files, nested image, compressed file, traversal, invalid
records/extents, missing table, encrypted image and malformed PFSC offsets.
These are host tests; no owner's real package/device runtime result is claimed.

MIT notice for the KytyPlus reference/derived algorithm:
Copyright (c) KytyPlus contributors.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
