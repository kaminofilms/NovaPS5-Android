#!/usr/bin/env python3
"""Route only Kyty's VirtualQuery / VirtualAlloc2 imports to the Wine bridge.

No instructions, guest binaries or original sections change. Each import gets
its own lookup table and retains its original IAT address, so existing code,
unwind data and DLL imports retain their layout. The input is SHA-256 pinned.
"""
import argparse
import hashlib
from pathlib import Path
import struct

FUNCTIONS={'VirtualQuery':'NovaVirtualQuery','VirtualAlloc2':'NovaVirtualAlloc2'}

def patch(source, target, expected):
    data=bytearray(source.read_bytes())
    if hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError('Kyty executable checksum mismatch; refusing an unknown core')
    pe=struct.unpack_from('<I',data,60)[0]
    assert data[pe:pe+4]==b'PE\0\0'
    n=struct.unpack_from('<H',data,pe+6)[0]
    osize=struct.unpack_from('<H',data,pe+20)[0]
    op=pe+24
    assert struct.unpack_from('<H',data,op)[0]==0x20b
    salign,falign=struct.unpack_from('<II',data,op+32)
    def align(v,a):return (v+a-1)&~(a-1)
    sections=[]
    for i in range(n):
        at=op+osize+i*40
        vs,va,rs,rp=struct.unpack_from('<IIII',data,at+8)
        sections.append((va,vs,rs,rp))
    def offset(rva):
        for va,vs,rs,rp in sections:
            if va<=rva<va+max(vs,rs):return rp+rva-va
        raise ValueError('RVA outside existing sections')
    def string(rva):
        at=offset(rva);return bytes(data[at:data.index(0,at)])
    imports=[]
    cursor=offset(struct.unpack_from('<I',data,op+120)[0])
    matches=[]
    while True:
        lookup,_,_,name,iat=struct.unpack_from('<5I',data,cursor)
        if not name:break
        dll=string(name)
        k=0
        while (entry:=struct.unpack_from('<Q',data,offset(lookup or iat)+8*k)[0]):
            fn=None if entry&(1<<63) else string(entry+2).decode()
            mapped=FUNCTIONS.get(fn)
            imports.append((b'novamemory.dll' if mapped else dll,
                            mapped.encode() if mapped else None,entry,iat+8*k))
            if mapped:matches.append(fn)
            k+=1
        cursor+=20
    assert sorted(matches)==sorted(FUNCTIONS),matches
    header=op+osize+n*40
    assert header+40<=min(s[3] for s in sections if s[3]),'No section-header room'
    va=align(max(a+max(b,c) for a,b,c,d in sections),salign)
    raw=align(len(data),falign)
    descriptors=bytearray((len(imports)+1)*20)
    payload=bytearray(descriptors)
    names={}
    def append(blob,alignment=1):
        while len(payload)%alignment:payload.append(0)
        rva=va+len(payload);payload.extend(blob);return rva
    for k,(dll,mapped,entry,iat) in enumerate(imports):
        if dll not in names:names[dll]=append(dll+b'\0')
        if mapped:entry=append(b'\0\0'+mapped+b'\0',2)
        lookup=append(struct.pack('<QQ',entry,0),8)
        struct.pack_into('<5I',payload,k*20,lookup,0,0,names[dll],iat)
    vsize=len(payload);rsize=align(vsize,falign)
    data.extend(b'\0'*(raw+rsize-len(data)))
    data[raw:raw+vsize]=payload
    struct.pack_into('<8s6I2HI',data,header,b'.novaimp',vsize,va,rsize,raw,0,0,0,0,0xc0000040)
    struct.pack_into('<H',data,pe+6,n+1)
    struct.pack_into('<I',data,op+56,align(va+vsize,salign))
    struct.pack_into('<I',data,op+64,0) # PE checksum recalculated by the loader as needed
    struct.pack_into('<II',data,op+120,va,len(descriptors))
    struct.pack_into('<II',data,op+112+11*8,0,0) # obsolete bound import metadata
    struct.pack_into('<II',data,op+112+4*8,0,0) # fork is no longer the upstream signed image
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(data)
    return {'input_sha256':expected,'output_sha256':hashlib.sha256(data).hexdigest(),
            'redirected_imports':matches,'original_sections_unchanged':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('target',type=Path)
    p.add_argument('--sha256',required=True)
    a=p.parse_args();print(patch(a.source,a.target,a.sha256))
