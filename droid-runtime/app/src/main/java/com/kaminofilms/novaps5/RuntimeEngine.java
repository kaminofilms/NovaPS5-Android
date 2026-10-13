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

/** Linux x86-64 Kyty runs through standalone ARM64 FEX inside DroidDeck. */
final class RuntimeEngine {
    interface Progress {void update(String stage,int percent);}
    static final String RUNTIME_URL="https://github.com/The412Banner/winlator-contents/releases/download/linuxfs-r9/linuxfs.tar.zst";
    static final String RUNTIME_SHA="d3240c1531531615b0dd06b6ad56e92db9015a8641eb18c3a613835ae45992e7";
    // Substituted by build-runtime-apk.py with the SHA-256 of the packaged, CI-built core.
    static final String LINUX_CORE_SHA="@NOVA_LINUX_CORE_SHA256@";
    static final android.os.Handler LAUNCH_HANDLER=new android.os.Handler(android.os.Looper.getMainLooper());
    static Runnable pendingLaunch;
    final Activity context;
    RuntimeEngine(Activity c){context=c;}
    File root(){return LinuxRuntime.rootDir(context);}
    File engine(){return new File(root(),"opt/novaps5");}
    boolean ready(){return LinuxRuntime.isInstalled(context)&&new File(engine(),"linux-kyty/kyty_emulator").isFile()&&new File(engine(),"linux-runtime/host/usr/bin/FEX").isFile()&&new File(engine(),"linux-runtime/guest/nova-probe").isFile();}
    String status(){return ready()?"Linux Kyty and standalone FEX installed; device preflight and game execution require testing":"Linux engine not yet installed; first Play downloads the DroidDeck environment";}
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
        JSONObject manifest=linuxManifest();
        File runtime=new File(base,"linux-runtime");
        File installedManifest=new File(runtime,"installed.json");
        String expected=manifest.getString("archive_sha256");
        boolean current=installedManifest.isFile()&&new String(Files.readAllBytes(installedManifest.toPath()),StandardCharsets.UTF_8).equals(expected);
        JSONObject files=manifest.getJSONObject("files");
        if(current){
            java.util.Iterator<String> names=files.keys();
            while(names.hasNext()){String name=names.next();File file=target(runtime,name);if(!file.isFile()||!sha256(file).equals(files.getString(name))){current=false;break;}}
        }
        if(!current){
            observer.update("Installing standalone FEX and x86-64 Linux libraries",-1);
            File archive=new File(context.getCacheDir(),"nova-linux-runtime.tar.gz");
            File staging=new File(base,"linux-runtime.staging");clear(staging);staging.mkdirs();
            try {
                try(InputStream in=context.getAssets().open("engine/linux-runtime.tar.gz");OutputStream out=new FileOutputStream(archive)){copy(in,out);}
                if(!sha256(archive).equals(expected))throw new IOException("Linux runtime archive checksum mismatch");
                untarGzip(archive,staging);
                java.util.Iterator<String> names=files.keys();
                while(names.hasNext()){String name=names.next();File file=target(staging,name);if(!file.isFile()||!sha256(file).equals(files.getString(name)))throw new IOException("Linux runtime component checksum mismatch: "+name);}
                Files.write(new File(staging,"installed.json").toPath(),expected.getBytes(StandardCharsets.UTF_8));
                publish(staging,runtime);
            } finally {archive.delete();clear(staging);}
        }
        File core=new File(base,"linux-kyty");core.mkdirs();File executable=new File(core,"kyty_emulator");
        if(!executable.isFile()||!sha256(executable).equals(LINUX_CORE_SHA)){
            observer.update("Installing verified Linux Kyty",-1);File staging=new File(core,"kyty_emulator.staging");
            try(InputStream in=context.getAssets().open("engine/kyty_emulator");OutputStream out=new FileOutputStream(staging)){copy(in,out);}
            if(!sha256(staging).equals(LINUX_CORE_SHA))throw new IOException("Linux Kyty checksum mismatch");
            byte[] header=new byte[20];try(InputStream in=new FileInputStream(staging)){if(in.read(header)!=20||header[0]!=127||header[1]!='E'||header[2]!='L'||header[3]!='F'||header[4]!=2||header[5]!=1||header[18]!=62||header[19]!=0)throw new IOException("Linux Kyty is not an x86-64 ELF");}
            android.system.Os.chmod(staging.getPath(),0755);
            Files.move(staging.toPath(),executable.toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING,java.nio.file.StandardCopyOption.ATOMIC_MOVE);
        }
        if(!executable.setExecutable(true,false))throw new IOException("Cannot execute Linux Kyty");
        for(String asset:new String[]{"launch-linux.sh","fex-linux.sh","session-guard.sh","host-launch.sh"}){
            File launcher=new File(base,asset.equals("launch-linux.sh")?"launch.sh":asset);try(InputStream in=context.getAssets().open("engine/"+asset);OutputStream out=new FileOutputStream(launcher)){copy(in,out);}if(!launcher.setExecutable(true,false))throw new IOException("Cannot execute "+asset);
        }
        HostKyty.writeHostEnvironment(context,base,root());
        BootLog.write(context,"Linux core verified: "+LINUX_CORE_SHA+"; FEX/runtime verified: "+expected);
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
    JSONObject linuxManifest()throws Exception {
        try(InputStream in=context.getAssets().open("engine/linux-runtime.tar.json");ByteArrayOutputStream text=new ByteArrayOutputStream()){
            copy(in,text);return new JSONObject(new String(text.toByteArray(),StandardCharsets.UTF_8));
        }
    }
    static void publish(File staging,File destination)throws Exception {
        File previous=new File(destination.getPath()+".previous");clear(previous);
        if(destination.exists()&&!destination.renameTo(previous))throw new IOException("Cannot retain previous Linux runtime");
        if(!staging.renameTo(destination)){
            if(previous.exists()&&!previous.renameTo(destination))throw new IOException("Cannot restore previous Linux runtime");
            throw new IOException("Cannot publish Linux runtime; previous installation restored");
        }
        clear(previous);
    }
    void launch(String game,String name){
        if(pendingLaunch!=null){LAUNCH_HANDLER.removeCallbacks(pendingLaunch);pendingLaunch=null;}
        if(SessionState.INSTANCE.getRunning()){
            // A previous game whose Kyty process already ended can leave the session marked running;
            // stop it instead of forcing the user to kill the whole app.
            BootLog.write(context,"Stopping the previous runtime session before launching "+name);
            try{context.startService(new Intent(context,SessionService.class).setAction(context.getPackageName()+".STOP_SESSION"));}catch(Exception x){BootLog.write(context,"Session stop failed: "+x);}
            // The session service handles the stop on this (main) thread, so never block here:
            // poll from the main looper and start the game once the old session has gone.
            final long deadline=android.os.SystemClock.uptimeMillis()+30000;
            final long forceAt=android.os.SystemClock.uptimeMillis()+4000;
            // Only the most recent request survives: tapping several games while the old session
            // closes must not start all of them at once.
            if(pendingLaunch!=null)LAUNCH_HANDLER.removeCallbacks(pendingLaunch);
            android.widget.Toast.makeText(context,"Closing the previous game…",android.widget.Toast.LENGTH_SHORT).show();
            final android.os.Handler handler=LAUNCH_HANDLER;
            pendingLaunch=new Runnable(){boolean forced=false;public void run(){
                if(!SessionState.INSTANCE.getRunning()){pendingLaunch=null;start(game,name);return;}
                if(!forced&&android.os.SystemClock.uptimeMillis()>forceAt){
                    // The session service did not let go (seen on device: minutes). End every process
                    // of the old session ourselves and clear its running flag.
                    forced=true;BootLog.write(context,"Previous session still running after 4 s; ending its processes");
                    forceEndSession();
                }
                if(android.os.SystemClock.uptimeMillis()>deadline){pendingLaunch=null;BootLog.write(context,"Previous session did not stop within 30 s");android.widget.Toast.makeText(context,"The previous game is still closing. Try again in a moment.",android.widget.Toast.LENGTH_LONG).show();return;}
                handler.postDelayed(this,200);
            }};
            handler.postDelayed(pendingLaunch,200);
            return;
        }
        start(game,name);
    }
    void forceEndSession(){
        final int me=android.os.Process.myPid();final int uid=android.os.Process.myUid();int killed=0;
        File[] entries=new File("/proc").listFiles();
        if(entries!=null)for(File entry:entries){
            String n=entry.getName();if(!n.matches("\\d+"))continue;int pid=Integer.parseInt(n);if(pid==me)continue;
            try{for(String line:Files.readAllLines(new File(entry,"status").toPath(),StandardCharsets.UTF_8)){
                if(line.startsWith("Uid:")){String[] f=line.substring(4).trim().split("\\s+");if(Integer.parseInt(f[0])==uid){android.os.Process.killProcess(pid);killed++;}break;}
            }}catch(Exception ignored){}
        }
        try{SessionState.class.getMethod("setRunning",boolean.class).invoke(SessionState.INSTANCE,false);}catch(Exception x){BootLog.write(context,"Cannot clear session flag: "+x);}
        BootLog.write(context,"Ended "+killed+" leftover session processes");
    }
    void start(String game,String name){
        HostKyty.watch(context);
        // Android 12+ "phantom process" monitor silently kills the processes a session is made of
        // (Kyty dies mid-game with nothing in any log). Only the user can turn it off.
        String phantom=null;try{phantom=android.provider.Settings.Global.getString(context.getContentResolver(),"settings_enable_monitor_phantom_procs");}catch(Exception ignored){}
        BootLog.write(context,"Phantom process monitor: "+(phantom==null?"ROM default (on)":phantom));
        if(phantom==null||!(phantom.equalsIgnoreCase("false")||phantom.equals("0")))
            android.widget.Toast.makeText(context,"Android may kill the game mid-play. Turn ON Developer options → \"Disable child process restrictions\" to stop it.",android.widget.Toast.LENGTH_LONG).show();
        // Keep the game running while Nova is in the background so it can be resumed; the default
        // policy froze the whole session and it did not come back.
        context.getSharedPreferences("session",0).edit().putString("suspendPolicy.steam","never").apply();
        BootLog.write(context,"Starting Linux Kyty/FEX session for "+name);context.getSharedPreferences("nova",0).edit().remove("last_engine_error").apply();
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
        try(InputStream in=new BufferedInputStream(c.getInputStream());OutputStream out=new FileOutputStream(destination)){byte[] data=new byte[262144];long count=0;int n;long last=0;while((n=in.read(data))!=-1){if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Download canceled");out.write(data,0,n);count+=n;long now=android.os.SystemClock.uptimeMillis();if(now-last>250){progress.update("Downloading Linux runtime",expected>0?(int)(count*100/expected):-1);last=now;}}if(expected>0&&count!=expected)throw new IOException("Runtime download was incomplete");}finally{c.disconnect();}
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
    static void clear(File f)throws IOException {if(java.nio.file.Files.isSymbolicLink(f.toPath())){if(!f.delete())throw new IOException("Cannot remove stale runtime link");return;}if(!f.exists())return;if(f.isDirectory()){File[] files=f.listFiles();if(files!=null)for(File child:files)clear(child);}if(!f.delete())throw new IOException("Cannot remove stale runtime staging file");}
}


