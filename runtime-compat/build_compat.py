#!/usr/bin/env python3
"""Build a reproducible Wine memory bridge and the pinned core import overlay."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
from patch_imports import patch

CORE_EXE_SHA='ad1b5fc61f511b0f77c6ab30ba47443f02a2e89514e273efc1a5983cc47aacd3'

def build(ndk,windows_sdk,core_zip,destination,work):
    root=Path(__file__).resolve().parent
    work.mkdir(parents=True,exist_ok=True);destination.mkdir(parents=True,exist_ok=True)
    clang=ndk/'toolchains/llvm/prebuilt/linux-x86_64/bin/clang'
    if not (windows_sdk/'include/windows.h').is_file():
        raise RuntimeError('Install mingw-w64-x86-64-dev or pass --windows-sdk with the MinGW headers and import libraries')
    run=lambda *args:subprocess.run([str(a) for a in args],check=True)
    run(clang,'--target=x86_64-w64-windows-gnu','--sysroot='+str(windows_sdk),'-fuse-ld=lld',
        '-O2','-shared','-nostdlib','-Wl,--entry,DllMainStartup','-Wl,--no-insert-timestamp',
        root/'novamemory.c','-lkernel32','-o',work/'novamemory.dll')
    run(clang,'--target=aarch64-linux-gnu','-fuse-ld=lld','-O2','-ffreestanding',
        '-fno-stack-protector','-nostdlib','-static','-Wl,-e,_start','-Wl,-z,max-page-size=16384',
        root/'host-va-limit.c','-o',work/'host-va-limit')
    with zipfile.ZipFile(core_zip) as archive:
        (work/'kyty-original.exe').write_bytes(archive.read('kyty_emulator.exe'))
    provenance=patch(work/'kyty-original.exe',work/'kyty_emulator-nova.exe',CORE_EXE_SHA)
    names=['kyty_emulator-nova.exe','novamemory.dll','host-va-limit']
    hashes={name:hashlib.sha256((work/name).read_bytes()).hexdigest() for name in names}
    archive_path=destination/'memory-compat.zip'
    with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name in names:
            entry=zipfile.ZipInfo(name,date_time=(2026,10,12,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,(work/name).read_bytes())
    manifest={'revision':'nova-memory-2','archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
              'files':hashes,'core_overlay':provenance,'android_game_boot_verified':False}
    (destination/'memory-compat.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
