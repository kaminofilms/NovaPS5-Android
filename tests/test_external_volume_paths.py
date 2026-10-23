#!/usr/bin/env python3
"""Exercise the production Java volume resolver without Android UI dependencies."""
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='nova-volumes-') as temporary:
    root = Path(temporary)
    package = root/'com/kaminofilms/novaps5'
    package.mkdir(parents=True)
    shutil.copyfile(repo/'nova-android/src/com/kaminofilms/novaps5/VolumePaths.java', package/'VolumePaths.java')
    (package/'VolumePathsTest.java').write_text(r'''
package com.kaminofilms.novaps5;
import java.io.*;
import java.nio.file.*;
import java.util.*;
public final class VolumePathsTest {
 static void check(boolean ok) { if(!ok)throw new AssertionError(); }
 static void rejected(Map<String,File> volumes,String id)throws Exception {
  try { VolumePaths.resolve(volumes,id); throw new AssertionError("Accepted "+id); }
  catch(IOException expected) {}
 }
 public static void main(String[] args)throws Exception {
  File root=new File(args[0]);File internal=new File(root,"internal");File usb=new File(root,"USB drive");
  internal.mkdirs();usb.mkdirs();
  Map<String,File> volumes=new LinkedHashMap<>();volumes.put("primary",internal);volumes.put("ABCD-1234",usb);
  File game=VolumePaths.resolve(volumes,"abcd-1234:PS5 Games/Overdrive");
  check(game.equals(new File(usb,"PS5 Games/Overdrive").getCanonicalFile()));
  check(VolumePaths.documentId(volumes,game).equals("ABCD-1234:PS5 Games/Overdrive"));
  check(VolumePaths.resolve(volumes,"primary:Games/Ever Forward").equals(new File(internal,"Games/Ever Forward").getCanonicalFile()));
  check(VolumePaths.resolve(volumes,"ABCD-1234:").equals(usb.getCanonicalFile()));
  check(VolumePaths.documentId(volumes,usb).equals("ABCD-1234:"));
  rejected(volumes,"unknown:Games");rejected(volumes,"ABCD-1234:/etc");
  rejected(volumes,"ABCD-1234:../internal");rejected(volumes,"primary:a/../../USB drive");
  rejected(volumes,null);rejected(volumes,"primary");
  Files.createSymbolicLink(new File(usb,"escape").toPath(),internal.toPath());
  rejected(volumes,"ABCD-1234:escape/game");
  check(!VolumePaths.contains(usb.getCanonicalFile(),new File(root,"USB drive-other/game")));
  volumes.remove("ABCD-1234");rejected(volumes,"ABCD-1234:PS5 Games/Overdrive");
  volumes.put("ABCD-1234",usb);check(VolumePaths.resolve(volumes,"ABCD-1234:PS5 Games/Overdrive").equals(game));
  System.out.println("PASS: internal/USB roundtrips, volume roots, UUID case, disconnect/reconnect, traversal and symlink containment");
 }
}
''')
    subprocess.run(['javac','-d',str(root),str(package/'VolumePaths.java'),str(package/'VolumePathsTest.java')],check=True)
    subprocess.run(['java','-cp',str(root),'com.kaminofilms.novaps5.VolumePathsTest',str(root/'storage')],check=True)
