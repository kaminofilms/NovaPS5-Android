package com.kaminofilms.novaps5;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Environment;
import android.provider.DocumentsContract;
import com.droiddeck.launcher.session.SessionState;
import com.droiddeck.launcher.runtime.LinuxRuntime;
import com.droiddeck.launcher.runtime.LinuxRuntimeInstaller;
import com.droiddeck.launcher.session.SessionService;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.zip.*;
import org.json.JSONObject;
import org.apache.commons.compress.archivers.tar.*;
import org.apache.commons.compress.compressors.gzip.GzipCompressorInputStream;

/** Full Kyty runs as a separate Windows/x86-64 process under ARM64 Wine/FEX. */
final class RuntimeEngine {
    interface Progress {void update(String stage,int percent);}
    static final String RUNTIME_URL="https://github.com/The412Banner/winlator-contents/releases/download/linuxfs-r9/linuxfs.tar.zst";
    static final String RUNTIME_SHA="d3240c1531531615b0dd06b6ad56e92db9015a8641eb18c3a613835ae45992e7";
    static final String PROTON_URL="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton11-7/GE-Proton11-7-aarch64.tar.gz";
    static final String PROTON_SHA="b77ac906186568c2f3c66674b85c712b145ccf73ff2718a50dd7bf6248b67ba3";
    static final String CORE_SHA="d7cc6f357216fdb02f7f3a6fc50c450ffbe7a64c53a55130bebd9888eb0898dc";
    static final String PROTON_DIR="GE-Proton11-7-aarch64";
    final Activity context;
    RuntimeEngine(Activity c){context=c;}
    File root(){return LinuxRuntime.rootDir(context);}
    File engine(){return new File(root(),"opt/novaps5");}
    boolean ready(){return LinuxRuntime.isInstalled(context)&&new File(engine(),"kyty/kyty_emulator.exe").isFile()&&new File(engine(),"proton/"+PROTON_DIR+"/files/lib/wine/aarch64-unix/libarm64ecfex.so").isFile();}
    String status(){return ready()?"Kyty core and ARM64 Proton/FEX installed; game compatibility requires a launch test":"Engine not yet installed; first Play downloads runtime components";}
    String resolveGame(GameStore.Entry e)throws Exception {
        Uri uri=Uri.parse(e.uri);String doc=DocumentsContract.getDocumentId(uri);
        if(!doc.startsWith("primary:"))throw new IOException("This preview launches games from internal shared storage. Select the extracted game folder on internal storage using Android Files.");
        File base=Environment.getExternalStorageDirectory().getCanonicalFile();File game=new File(base,doc.substring(8)).getCanonicalFile();
        if(!game.getPath().startsWith(base.getPath()+File.separator))throw new IOException("Invalid game folder path");
        if(!new File(game,"eboot.bin").isFile()||!new File(game,"eboot.bin").canRead())throw new IOException("The engine cannot read eboot.bin. Allow NovaPs5 file access, then select the extracted game folder on internal shared storage.");
        return game.getAbsolutePath();
    }
    void prepare(Progress progress)throws Exception {
        final Progress observer=(stage,percent)->{BootLog.progress(context,stage,percent);progress.update(stage,percent);};
        observer.update("Checking runtime installation",-1);BootLog.write(context,"Free internal bytes: "+context.getFilesDir().getUsableSpace());
        if(!LinuxRuntime.isInstalled(context)){
            if(context.getFilesDir().getUsableSpace()<6L*1024*1024*1024)throw new IOException("At least 6 GB of free internal storage is required for the first engine installation");
            LinuxRuntimeInstaller.Release release=new LinuxRuntimeInstaller.Release("novaps5-r9",RUNTIME_URL,RUNTIME_SHA,790907606L);
            if(!LinuxRuntimeInstaller.install(context,release,(stage,percent)->observer.update("Linux runtime: "+stage,percent)))throw new IOException("Linux runtime installation failed. The existing runtime was retained; retry on a stable connection.");
        }
        File base=engine();if(!base.isDirectory()&&!base.mkdirs())throw new IOException("Cannot create engine directory");
        String expectedExe=memoryManifest().getJSONObject("core_overlay").getString("input_sha256");
        File core=new File(base,"kyty"), installedExe=new File(core,"kyty_emulator.exe");
        if(!installedExe.isFile()||!sha256(installedExe).equals(expectedExe)){
            observer.update("Installing the full Kyty core",-1);File archive=new File(context.getCacheDir(),"novaps5-kyty.zip");
            try(InputStream in=context.getAssets().open("engine/kyty-windows-df5b9b9.zip");OutputStream out=new FileOutputStream(archive)){copy(in,out);}
            // The executable digest is pinned by memory-compat.json and checked below.\n            // The ZIP container may differ across verified Kyty builds.\n            BootLog.write(context,"Packaged Kyty archive SHA-256: "+sha256(archive));
            File staging=new File(base,"kyty.staging");clear(staging);staging.mkdirs();unzip(archive,staging);
            File stagedExe=new File(staging,"kyty_emulator.exe");
            if(!stagedExe.isFile()||!sha256(stagedExe).equals(expectedExe))throw new IOException("Packaged Kyty executable checksum mismatch");
            File previous=new File(base,"kyty.previous");clear(previous);
            if(core.exists()&&!core.renameTo(previous))throw new IOException("Cannot retain the previous Kyty engine during upgrade");
            if(!staging.renameTo(core)){
                if(previous.exists()&&!previous.renameTo(core))throw new IOException("Cannot publish or restore the Kyty engine; retry installation");
                throw new IOException("Cannot publish the Kyty upgrade; previous engine restored");
            }
            clear(previous);archive.delete();
        }
        File proton=new File(base,"proton");if(!new File(proton,PROTON_DIR+"/files/lib/wine/aarch64-unix/libarm64ecfex.so").isFile()){
            File archive=new File(context.getFilesDir(),"novaps5-proton.download");download(PROTON_URL,archive,observer);
            observer.update("Verifying ARM64 Proton/FEX",-1);if(!sha256(archive).equals(PROTON_SHA)){archive.delete();throw new IOException("Proton/FEX checksum mismatch; download was removed");}
            File staging=new File(base,"proton.staging");clear(staging);staging.mkdirs();observer.update("Installing ARM64 Proton/FEX",-1);untarGzip(archive,staging);
            if(!new File(staging,PROTON_DIR+"/files/lib/wine/aarch64-unix/libarm64ecfex.so").isFile())throw new IOException("Installed Proton archive lacks the ARM64 FEX integration");
            if(!staging.renameTo(proton))throw new IOException("Cannot publish installed Proton/FEX");archive.delete();
        }
        for(String asset:new String[]{"launch.sh","session-guard.sh"}){
            File launcher=new File(base,asset);try(InputStream in=context.getAssets().open("engine/"+asset);OutputStream out=new FileOutputStream(launcher)){copy(in,out);}launcher.setExecutable(true,false);
        }
        installMemoryBridge(observer);
        // The installed root survives APK upgrades. Enforce the direct-only route
        // there as well as in the Activity, before gamescope or any client starts.
        File session=new File(root(),"usr/local/bin/bannerlator-session");
        String script=new String(Files.readAllBytes(session.toPath()),StandardCharsets.UTF_8);
        String guard="# NOVA_DIRECT_KYTY_ONLY\nsource /opt/novaps5/session-guard.sh \"$mode\" \"${1:-}\" || exit $?\n";
        if(!script.contains("# NOVA_DIRECT_KYTY_ONLY")){
            String anchor="shift || true\n";
            if(!script.contains(anchor))throw new IOException("Unrecognized session script; refusing a possible Steam fallback");
            Files.write(session.toPath(),script.replace(anchor,anchor+guard).getBytes(StandardCharsets.UTF_8));
        }
        BootLog.write(context,"Direct Kyty session guard installed; Steam launch is disabled");
        observer.update("Engine ready for launch",100);
    }
    JSONObject memoryManifest()throws Exception {
        try(InputStream in=context.getAssets().open("engine/memory-compat.json");ByteArrayOutputStream text=new ByteArrayOutputStream()){
            copy(in,text);return new JSONObject(new String(text.toByteArray(),StandardCharsets.UTF_8));
        }
    }
    void installMemoryBridge(Progress observer)throws Exception {
        JSONObject manifest=memoryManifest();
        JSONObject hashes=manifest.getJSONObject("files");
        String[] names={"kyty_emulator-nova.exe","novamemory.dll","host-va-limit"};
        File[] destinations={new File(engine(),"kyty/kyty_emulator-nova.exe"),new File(engine(),"kyty/novamemory.dll"),new File(engine(),"compat/host-va-limit")};
        boolean current=true;
        for(int i=0;i<names.length;i++)if(!destinations[i].isFile()||!sha256(destinations[i]).equals(hashes.getString(names[i])))current=false;
        if(!current){
            observer.update("Installing Wine guest memory compatibility",-1);
            File archive=new File(context.getCacheDir(),"novaps5-memory-compat.zip");
            File staging=new File(engine(),"memory-compat.staging");clear(staging);staging.mkdirs();
            try {
                try(InputStream in=context.getAssets().open("engine/memory-compat.zip");OutputStream out=new FileOutputStream(archive)){copy(in,out);}
                if(!sha256(archive).equals(manifest.getString("archive_sha256")))throw new IOException("Memory bridge archive checksum mismatch");
                unzip(archive,staging);
                for(String name:names){File file=new File(staging,name);if(!file.isFile()||!sha256(file).equals(hashes.getString(name)))throw new IOException("Memory bridge component checksum mismatch: "+name);}
                for(int i=0;i<names.length;i++){
                    destinations[i].getParentFile().mkdirs();
                    Files.move(new File(staging,names[i]).toPath(),destinations[i].toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING,java.nio.file.StandardCopyOption.ATOMIC_MOVE);
                }
            } finally {archive.delete();clear(staging);}
        }
        if(!destinations[2].setExecutable(true,false))throw new IOException("Cannot execute the host address-space probe");
        BootLog.write(context,"Wine memory compatibility installed: "+manifest.getString("revision")+"; original Kyty executable retained");
    }
    void launch(String game,String name){
        if(SessionState.INSTANCE.getRunning())throw new IllegalStateException("A runtime session is already active. End that session before launching another game.");
        BootLog.write(context,"Starting Kyty/Wine/FEX session for "+name);context.getSharedPreferences("nova",0).edit().remove("last_engine_error").apply();
        context.getSharedPreferences("session",0).edit().putInt("resolutionCap.run",720).putString("fexPreset","COMPATIBILITY").apply();
        Intent intent=new Intent(context,NovaSessionActivity.class);intent.putExtra(SessionService.EXTRA_MODE,SessionService.MODE_RUN);intent.putExtra(SessionService.EXTRA_PROGRAM,"/opt/novaps5/launch.sh");intent.putExtra(SessionService.EXTRA_PROGRAM_ARGS,new String[]{game});intent.putExtra("nova_game_path",game);intent.putExtra("nova_game_name",name);context.startActivity(intent);
    }
    String latestBootLog(){
        File dir=LinuxRuntime.debugLogDir();File[] folders=dir.listFiles();if(folders==null||folders.length==0)folders=new File(context.getFilesDir(),"logs").listFiles();if(folders==null)return "No game session log exists yet.";
        java.util.Arrays.sort(folders,(a,b)->Long.compare(b.lastModified(),a.lastModified()));
        for(File folder:folders){File[] files=folder.isDirectory()?folder.listFiles():new File[]{folder};if(files==null)continue;
            java.util.Arrays.sort(files,(a,b)->{if(a.getName().equals("session.log"))return b.getName().equals("session.log")?0:-1;if(b.getName().equals("session.log"))return 1;return Long.compare(b.lastModified(),a.lastModified());});
            for(File file:files)if(file.isFile()&&(file.getName().endsWith(".log")||file.getName().contains("session"))){try(RandomAccessFile in=new RandomAccessFile(file,"r")){long size=in.length();byte[] bytes=new byte[(int)Math.min(size,262144)];in.seek(size-bytes.length);in.readFully(bytes);return file.getName()+"\n"+new String(bytes,StandardCharsets.UTF_8);}catch(Exception ignored){}}
        }return "No readable game session log found.";
    }
    void download(String url,File destination,Progress progress)throws Exception {
        java.net.HttpURLConnection c=(java.net.HttpURLConnection)new java.net.URL(url).openConnection();c.setConnectTimeout(30000);c.setReadTimeout(60000);c.setInstanceFollowRedirects(true);int status=c.getResponseCode();if(status!=200)throw new IOException("Runtime download returned HTTP "+status);long expected=c.getContentLengthLong();
        try(InputStream in=new BufferedInputStream(c.getInputStream());OutputStream out=new FileOutputStream(destination)){byte[] data=new byte[262144];long count=0;int n;long last=0;while((n=in.read(data))!=-1){if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Download canceled");out.write(data,0,n);count+=n;long now=android.os.SystemClock.uptimeMillis();if(now-last>250){progress.update("Downloading ARM64 Proton/FEX",expected>0?(int)(count*100/expected):-1);last=now;}}if(expected>0&&count!=expected)throw new IOException("Runtime download was incomplete");}finally{c.disconnect();}
    }
    static void copy(InputStream in,OutputStream out)throws IOException {byte[] buffer=new byte[262144];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);}
    static String sha256(File file)throws Exception {MessageDigest d=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(file)){byte[] data=new byte[1048576];int n;while((n=in.read(data))!=-1)d.update(data,0,n);}StringBuilder s=new StringBuilder();for(byte b:d.digest())s.append(String.format(Locale.ROOT,"%02x",b&255));return s.toString();}
    static File target(File dir,String name)throws IOException {File file=new File(dir,name).getCanonicalFile();String base=dir.getCanonicalPath();if(!file.getPath().startsWith(base+File.separator))throw new IOException("Archive path escapes its installation directory");return file;}
    static void unzip(File archive,File dir)throws Exception {try(ZipInputStream in=new ZipInputStream(new BufferedInputStream(new FileInputStream(archive)))){ZipEntry e;while((e=in.getNextEntry())!=null){File f=target(dir,e.getName());if(e.isDirectory()){f.mkdirs();continue;}f.getParentFile().mkdirs();try(OutputStream out=new FileOutputStream(f)){copy(in,out);}}}}
    static void untarGzip(File archive,File dir)throws Exception {
        try(TarArchiveInputStream tar=new TarArchiveInputStream(new GzipCompressorInputStream(new BufferedInputStream(new FileInputStream(archive))))){TarArchiveEntry e;while((e=tar.getNextTarEntry())!=null){File f=target(dir,e.getName());if(e.isDirectory()){f.mkdirs();continue;}f.getParentFile().mkdirs();
            if(e.isSymbolicLink()){File link=e.getLinkName().startsWith("/")?new File(dir,e.getLinkName().substring(1)):new File(f.getParentFile(),e.getLinkName());if(!link.getCanonicalPath().startsWith(dir.getCanonicalPath()+File.separator))throw new IOException("Runtime symlink escapes installation directory");android.system.Os.symlink(e.getLinkName(),f.getPath());}
            else if(e.isLink()){File link=target(dir,e.getLinkName());if(!link.isFile())throw new IOException("Runtime hard link target is missing");android.system.Os.link(link.getPath(),f.getPath());}
            else if(e.isFile()){try(OutputStream out=new FileOutputStream(f)){copy(tar,out);}android.system.Os.chmod(f.getPath(),e.getMode()&0777);}
            else throw new IOException("Unsupported runtime archive member");
        }}
    }
    static void clear(File f)throws IOException {if(!f.exists())return;if(java.nio.file.Files.isSymbolicLink(f.toPath())){if(!f.delete())throw new IOException("Cannot remove stale runtime link");return;}if(f.isDirectory()){File[] files=f.listFiles();if(files!=null)for(File child:files)clear(child);}if(!f.delete())throw new IOException("Cannot remove stale runtime staging file");}
}
