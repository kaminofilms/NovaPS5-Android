#!/usr/bin/env python3
"""Verify the import bridge does not change Kyty's instructions or DLL ABI."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime-compat'))
from patch_imports import patch
from build_compat import CORE_EXE_SHA

def parse(data):
    pe=struct.unpack_from('<I',data,60)[0];op=pe+24
    count=struct.unpack_from('<H',data,pe+6)[0];opts=struct.unpack_from('<H',data,pe+20)[0]
    sections=[]
    for i in range(count):
        at=op+opts+i*40
        name=data[at:at+8];vs,va,rs,rp=struct.unpack_from('<IIII',data,at+8)
        sections.append((name,va,vs,rs,rp))
    def offset(rva):
        for _,va,vs,rs,rp in sections:
            if va<=rva<va+max(vs,rs):return rp+rva-va
        raise ValueError(rva)
    def text(rva):
        p=offset(rva);return data[p:data.index(0,p)].decode()
    cursor=offset(struct.unpack_from('<I',data,op+120)[0]);imports=[]
    while True:
        lookup,_,_,name,iat=struct.unpack_from('<5I',data,cursor)
        if not name:break
        j=0
        while(v:=struct.unpack_from('<Q',data,offset(lookup or iat)+8*j)[0]):
            symbol=('ordinal',v&0xffff) if v&(1<<63) else text(v+2)
            imports.append((text(name),symbol,iat+8*j));j+=1
        cursor+=20
    return sections,imports

class Overlay(unittest.TestCase):
    def test_instruction_data_and_iat_addresses_preserved(self):
        with zipfile.ZipFile(ROOT/'droid-runtime/app/src/main/assets/engine/kyty-windows-df5b9b9.zip') as archive:
            original=archive.read('kyty_emulator.exe')
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'original.exe';target=Path(d)/'patched.exe';source.write_bytes(original)
            patch(source,target,CORE_EXE_SHA);updated=target.read_bytes()
        before_sections,before_imports=parse(original);after_sections,after_imports=parse(updated)
        self.assertEqual(before_sections,after_sections[:-1])
        for _,_,_,size,offset in before_sections:
            self.assertEqual(original[offset:offset+size],updated[offset:offset+size])
        replacement={'VirtualQuery':'NovaVirtualQuery','VirtualAlloc2':'NovaVirtualAlloc2'}
        expected=[('novamemory.dll',replacement[fn],iat) if fn in replacement else (dll,fn,iat)
                  for dll,fn,iat in before_imports]
        self.assertEqual(expected,after_imports)
        self.assertEqual(len(after_imports),len(before_imports))

    def test_unknown_core_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'unknown.exe';target=Path(d)/'result.exe';source.write_bytes(b'unknown')
            with self.assertRaises(ValueError):patch(source,target,CORE_EXE_SHA)
            self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
