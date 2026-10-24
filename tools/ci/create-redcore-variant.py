#!/usr/bin/env python3
"""Change Android application identity without renaming Java/JNI classes or Nova branding."""
from pathlib import Path
import argparse,struct,subprocess,tempfile,zipfile,copy
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--tools',type=Path,required=True);p.add_argument('--keystore',type=Path,required=True);a=p.parse_args()
new_package='com.kurogame.wutheringwaves.global';old_package='com.kaminofilms.novaps5'
with tempfile.TemporaryDirectory() as td,zipfile.ZipFile(a.source) as original:
 xml=original.read('AndroidManifest.xml');kind,header,size=struct.unpack_from('<HHI',xml,8)
 count,styles,flags,start,style_start=struct.unpack_from('<5I',xml,16)
 assert kind==1 and not styles and not style_start and not flags&0x100
 offsets=struct.unpack_from('<'+'I'*count,xml,8+header);strings=[]
 for offset in offsets:
  at=8+start+offset;length=struct.unpack_from('<H',xml,at)[0];at+=2
  if length&0x8000:length=((length&0x7fff)<<16)|struct.unpack_from('<H',xml,at)[0];at+=2
  strings.append(xml[at:at+length*2].decode('utf-16le'))
 for old,new in {old_package:new_package,'.MainActivity':old_package+'.MainActivity','.GameActivity':old_package+'.GameActivity',old_package+'.game':new_package+'.game'}.items():
  assert strings.count(old)==1,(old,strings.count(old));strings[strings.index(old)]=new
 assert strings.count('NovaPs5')==1
 data=bytearray();offsets=[]
 for value in strings:
  offsets.append(len(data));encoded=value.encode('utf-16le');assert len(encoded)//2<0x8000
  data+=struct.pack('<H',len(encoded)//2)+encoded+b'\0\0'
 data+=b'\0'*(-len(data)%4);pool=bytearray(xml[8:8+start]);struct.pack_into('<I',pool,4,len(pool)+len(data));struct.pack_into('<'+'I'*count,pool,header,*offsets)
 manifest=bytearray(xml[:8]+pool+data+xml[8+size:]);struct.pack_into('<I',manifest,4,len(manifest))
 resources=bytearray(original.read('resources.arsc'));at=struct.unpack_from('<H',resources,2)[0];packages=0
 while at<len(resources):
  kind,header,size=struct.unpack_from('<HHI',resources,at);assert size>=header>=8 and at+size<=len(resources)
  if kind==0x200:
   assert bytes(resources[at+12:at+268]).decode('utf-16le').split('\0')[0]==old_package
   value=new_package.encode('utf-16le');resources[at+12:at+268]=value+b'\0'*(256-len(value));packages+=1
  at+=size
 assert packages==1
 unsigned=Path(td)/'unsigned.apk';aligned=Path(td)/'aligned.apk'
 with zipfile.ZipFile(unsigned,'w') as output:
  for entry in original.infolist():
   if entry.filename.startswith('META-INF/'):continue
   value=manifest if entry.filename=='AndroidManifest.xml' else resources if entry.filename=='resources.arsc' else original.read(entry.filename)
   output.writestr(copy.copy(entry),value)
 subprocess.run([str(a.tools/'zipalign'),'-P','16','-f','4',str(unsigned),str(aligned)],check=True)
 subprocess.run([str(a.tools/'apksigner'),'sign','--ks',str(a.keystore),'--ks-key-alias','novaps5dev','--ks-pass','pass:android','--key-pass','pass:android','--out',str(a.output),str(aligned)],check=True)
 with zipfile.ZipFile(a.output) as result:
  names=[n for n in original.namelist() if not n.startswith('META-INF/')]
  assert set(names)==set(n for n in result.namelist() if not n.startswith('META-INF/'))
  assert {n for n in names if original.read(n)!=result.read(n)}=={'AndroidManifest.xml','resources.arsc'}
 print('PASS NovaPs5 label, absolute activity classes, resource identity, byte-identical runtime/DEX/assets')
