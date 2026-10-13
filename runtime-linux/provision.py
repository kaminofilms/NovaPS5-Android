#!/usr/bin/env python3
"""Provision pinned FEX ARM64 + separate Ubuntu x86-64 libraries, without Wine."""
import argparse, concurrent.futures, hashlib, json, os, shutil, subprocess, tarfile
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parent
CORE_SHA='e594d71bb9c60ff47d2ac1e1ee4b9c21eca7ad1ba949d1943a7644eabc2f846c'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fetch(pin,cache):
    path=cache/(pin['sha256']+'.deb')
    if path.exists() and digest(path)==pin['sha256']:return path
    temporary=path.with_suffix('.part')
    for attempt in range(3):
        subprocess.run(['curl','--fail','--location','--silent','--show-error','--retry','3',pin['url'],'-o',str(temporary)],check=True)
        if digest(temporary)==pin['sha256']:
            temporary.replace(path);break
        temporary.unlink()
    else: raise RuntimeError('Checksum mismatch: '+pin['url'])
    return path
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,default=ROOT.parent/'build/linux-debs');a=p.parse_args()
    a.cache.mkdir(parents=True,exist_ok=True);work=a.cache/'overlay';shutil.rmtree(work,ignore_errors=True)
    host=work/'host';guest=work/'guest';host.mkdir(parents=True);guest.mkdir()
    pins=json.loads((ROOT/'dependencies.json').read_text());allpins=[pins['fex']]+pins['guest']
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: paths=list(pool.map(lambda x:fetch(x,a.cache),allpins))
    for i,path in enumerate(paths):subprocess.run(['dpkg-deb','-x',str(path),str(host if i==0 else guest)],check=True)
    # Debian packages use merged-/usr paths; provide the root aliases explicitly.
    for name in ['lib','lib64','bin','sbin']:
        (guest/name).symlink_to('usr/'+name)
    # Keep all archive symlinks relative to the packaged root so Android's
    # extractor and Python's safe tar filter agree on their sandbox boundaries.
    for path in work.rglob('*'):
        if path.is_symlink() and os.readlink(path).startswith('/'):
            root=host if path.is_relative_to(host) else guest
            target=root/os.readlink(path).lstrip('/')
            path.unlink();path.symlink_to(os.path.relpath(target,path.parent))
    # Use a directory rootfs: FUSE mounts and binfmt_misc registration are unnecessary.
    # Preserve licenses and exact upstream package provenance in the distributable.
    (work/'dependencies.json').write_text(json.dumps(pins,indent=2)+'\n')
    subprocess.run(['gcc','-O2',str(ROOT/'probe.c'),'-ldl','-o',str(guest/'nova-probe')],check=True)
    for path,machine in [(guest/'nova-probe',62),(host/'usr/bin/FEX',183),(host/'usr/bin/FEXServer',183),(host/'usr/share/fex-emu/GuestThunks/libvulkan-guest.so',62),(host/'usr/lib/aarch64-linux-gnu/fex-emu/HostThunks/libvulkan-host.so',183)]:
        data=path.read_bytes();assert data[:6]==b'\x7fELF\x02\x01' and int.from_bytes(data[18:20],'little')==machine,str(path)
    (work/'Config.json').write_text(json.dumps({'Config':{'Env':['LD_PRELOAD=','LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu']}})+'\n')
    (work/'thunks.json').write_text(json.dumps({'ThunksDB':{'Vulkan':1,'asound':1,'WaylandClient':1}})+'\n')
    shutil.copyfile(host/'usr/share/fex-emu/ThunksDB.json',work/'ThunksDB.json')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('wb') as raw:
        import gzip
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w') as out:
                for path in sorted(work.rglob('*')):
                    info=out.gettarinfo(str(path),path.relative_to(work).as_posix());info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
                    if info.isfile():
                        with path.open('rb') as stream:out.addfile(info,stream)
                    else:out.addfile(info)
    manifest={'revision':'linux-fex-2610-r1','archive_sha256':digest(a.output),'core_sha256':CORE_SHA,'files':{p.relative_to(work).as_posix():digest(p) for p in work.rglob('*') if p.is_file() and not p.is_symlink()}}
    a.output.with_suffix('.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Linux runtime:',a.output,a.output.stat().st_size,manifest['archive_sha256'])
if __name__=='__main__':main()
