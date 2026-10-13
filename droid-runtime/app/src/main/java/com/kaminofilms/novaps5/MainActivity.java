package com.kaminofilms.novaps5;
import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import android.database.Cursor;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;

public final class MainActivity extends Activity {
    RuntimeEngine engine;
    static final int FOLDER=10,FIRMWARE=11,EXPORT=12,DRIVER=13;
    // Nova launches through the DroidDeck session in "run" mode, which draws with the desktop (lxqt) driver choice.
    static final String DRIVER_MODE="lxqt",TURNIP_RELEASES="https://github.com/The412Banner/Banners-Turnip/releases/tag/v26.3.0-20260923";
    static final String FIRMWARE_URL="https://pc.ps5.update.playstation.net/update/ps5/official/tJMRE80IbXnE9YuG0jzTXgKEjIMoabr6/image/2026_0928/sys_c17384946df6e5c85b2d72cbeee2057b165bf90279d9e2a86d527d0778cdaaf6/PS5UPDATE.PUP";
    final ExecutorService io=Executors.newSingleThreadExecutor();
    GameStore store;HomeView home;FrameLayout screen;SurfaceView surface;TouchControls controls;
    volatile String gpu="Checking Vulkan…",cpu="Not tested",report="";String exportText="";
    boolean testing=false,paused=false;int hardwareButtons=0;float hx,hy,hrx,hry,hl2,hr2;
    void ui(Runnable r){runOnUiThread(()->{if(!isFinishing()&&!isDestroyed())r.run();});}
    @Override public void onCreate(Bundle b){super.onCreate(b);BootLog.install(this);BootLog.write(this,"NovaPs5 0.4.5-native started; Android "+Build.VERSION.SDK_INT);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);immersive();store=new GameStore(this);engine=new RuntimeEngine(this);showHome();
        if(android.os.Build.VERSION.SDK_INT>=23&&checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)!=android.content.pm.PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{android.Manifest.permission.READ_EXTERNAL_STORAGE,android.Manifest.permission.WRITE_EXTERNAL_STORAGE},20);
        io.execute(()->{try{if(NativeBridge.AVAILABLE){report=NativeBridge.vulkanReport();JSONObject j=new JSONObject(report);gpu=j.optBoolean("available")?j.optString("gpu")+" · Vulkan "+j.optString("vulkan"):"Vulkan unavailable";cpu=NativeBridge.cpuTest();}else{gpu="Native runtime unavailable for this architecture";cpu="ARM64 native library unavailable";}}catch(Throwable e){gpu="Vulkan check failed";report=e.toString();}store.loadImages();ui(()->home.invalidate());});
    }
    void immersive(){getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);}
    void showHome(){testing=false;hardwareButtons=0;hx=hy=hrx=hry=hl2=hr2=0;if(NativeBridge.AVAILABLE)NativeBridge.stopRenderer();home=new HomeView(this);setContentView(home);immersive();}
    @Override public void onConfigurationChanged(Configuration c){super.onConfigurationChanged(c);immersive();if(home!=null)home.invalidate();}
    @Override protected void onResume(){super.onResume();paused=false;immersive();if(testing&&surface!=null&&surface.getHolder().getSurface().isValid()&&NativeBridge.AVAILABLE)NativeBridge.startRenderer(surface.getHolder().getSurface());}
    @Override protected void onPause(){paused=true;if(NativeBridge.AVAILABLE)NativeBridge.stopRenderer();if(controls!=null)controls.release();super.onPause();}
    @Override protected void onDestroy(){if(NativeBridge.AVAILABLE)NativeBridge.stopRenderer();io.shutdownNow();super.onDestroy();}
    @Override public void onBackPressed(){if(testing)showHome();else super.onBackPressed();}
    void folder(){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);startActivityForResult(i,FOLDER);}
    void firmwarePicker(){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");startActivityForResult(i,FIRMWARE);}
    void info(String title,String message){TextView t=new TextView(this);t.setText(message);t.setTextSize(16);t.setTextColor(Color.WHITE);t.setPadding(28,24,28,20);t.setTextIsSelectable(true);ScrollView s=new ScrollView(this);s.addView(t);new AlertDialog.Builder(this).setTitle(title).setView(s).setPositiveButton("Close",null).show();}
    interface Work {String run()throws Exception;}
    void busy(String title,Work work,java.util.function.Consumer<String> done){ProgressDialog p=new ProgressDialog(this);p.setTitle(title);p.setMessage("Working with local files…");p.setIndeterminate(true);p.setCancelable(false);p.show();io.execute(()->{try{String value=work.run();ui(()->{p.dismiss();done.accept(value);});}catch(Exception e){ui(()->{p.dismiss();info(title,"Could not complete this operation.\n\n"+e.getMessage());});}});}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri uri=data.getData();
        if(request==FOLDER){try{int flags=data.getFlags()&Intent.FLAG_GRANT_READ_URI_PERMISSION;getContentResolver().takePersistableUriPermission(uri,flags);}catch(SecurityException e){info("Folder access","This provider cannot retain access. Choose a local folder using Android Files.");return;}
            busy("Importing game folder",()->{List<GameStore.Entry> found=store.scan(uri);store.addAll(found);store.loadImages();return found.size()+" game folder(s) found.";},value->{showHome();info("Library updated",value+"\n\nGames appear with their own metadata and artwork. Select a game and press Play to prepare its engine.");});
        }else if(request==FIRMWARE){busy("Importing PS5 update",()->copyFirmware(uri),value->{home.invalidate();info("Firmware file retained",value+"\n\nThis alpha stores the original update package. It does not decrypt, install or boot PS5 system software.");});}
        else if(request==DRIVER){busy("Importing GPU driver",()->importDriver(uri),value->info("Linux GPU driver",value));}
        else if(request==EXPORT){final String content=exportText;busy("Exporting diagnostics",()->{try(OutputStream out=getContentResolver().openOutputStream(uri,"wt")){if(out==null)throw new IOException("No writable document returned");out.write(content.getBytes("UTF-8"));}return "Diagnostic report saved.";},value->Toast.makeText(this,value,Toast.LENGTH_SHORT).show());}
    }
    String copyFirmware(Uri uri)throws Exception {
        String name="PS5UPDATE.PUP";long declared=-1;try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE},null,null,null)){if(c!=null&&c.moveToFirst()){name=c.getString(0);if(!c.isNull(1))declared=c.getLong(1);}}
        if(name==null||!name.toLowerCase(Locale.ROOT).endsWith(".pup"))throw new IOException("Select the original PS5UPDATE.PUP file.");
        if(declared>3L*1024*1024*1024)throw new IOException("Update exceeds the 3 GiB import limit");if(declared>0&&getFilesDir().getUsableSpace()<declared+64L*1024*1024)throw new IOException("Not enough free storage for the firmware file");
        File dir=new File(getFilesDir(),"firmware");if(!dir.exists()&&!dir.mkdirs())throw new IOException("Cannot create private firmware directory");File temp=new File(dir,"import.tmp"),target=new File(dir,"PS5UPDATE.PUP");long bytes=0;MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try(InputStream in=getContentResolver().openInputStream(uri);FileOutputStream out=new FileOutputStream(temp)){
            if(in==null)throw new IOException("Cannot open update file");byte[] header=new byte[64];new DataInputStream(in).readFully(header);if(header[0]!=0x53||header[1]!=0x4c||header[2]!=0x42||header[3]!=0x32)throw new IOException("Expected a PS5 SLB2 update container. This alpha retains the package without installing it.");out.write(header);digest.update(header);bytes=64;byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))>0){if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Import canceled");bytes+=n;if(bytes>3L*1024*1024*1024)throw new IOException("Update exceeds import limit");out.write(buffer,0,n);digest.update(buffer,0,n);}out.getFD().sync();
        }catch(Exception e){temp.delete();throw e;}
        if(bytes<64){temp.delete();throw new IOException("Update file is truncated");}
        // Atomic rename on the app's private filesystem; the old import survives a failed copy.
        try{android.system.Os.rename(temp.getAbsolutePath(),target.getAbsolutePath());}catch(Exception e){temp.delete();throw new IOException("Cannot retain imported update file",e);}
        StringBuilder hash=new StringBuilder();for(byte b:digest.digest())hash.append(String.format(Locale.ROOT,"%02x",b&255));
        getSharedPreferences("nova",0).edit().putString("firmware_sha256",hash.toString()).putLong("firmware_bytes",bytes).apply();return "PS5UPDATE.PUP\n"+(bytes/1048576)+" MiB\nSHA-256: "+hash;
    }
    void firmware(){long bytes=getSharedPreferences("nova",0).getLong("firmware_bytes",0);new AlertDialog.Builder(this).setTitle("PS5 firmware file").setMessage((bytes>0?"Retained update: "+bytes/1048576+" MiB\n\n":"")+"You can retain Sony’s original PS5 update in app storage. Firmware installation and system-software boot are not implemented in this alpha.\n\nThe supplied official download is about 1.2 GB.")
        .setPositiveButton("Import PUP",(d,w)->firmwarePicker()).setNeutralButton("Official download",(d,w)->{try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(FIRMWARE_URL)));}catch(ActivityNotFoundException e){info("Official firmware",FIRMWARE_URL);}}).setNegativeButton("Close",null).show();}
    String driverLabel(){return com.droiddeck.launcher.gpu.LinuxVulkanDriver.optionLabel(this,com.droiddeck.launcher.session.SessionPrefs.INSTANCE.linuxDriver(this,DRIVER_MODE));}
    void gpuDriver(){
        final List<String> ids=com.droiddeck.launcher.gpu.LinuxVulkanDriver.optionValues(this);String current=com.droiddeck.launcher.session.SessionPrefs.INSTANCE.linuxDriver(this,DRIVER_MODE);
        final String[] labels=new String[ids.size()];int selected=0;for(int i=0;i<labels.length;i++){labels[i]=com.droiddeck.launcher.gpu.LinuxVulkanDriver.optionLabel(this,ids.get(i));if(ids.get(i).equals(current))selected=i;}
        new AlertDialog.Builder(this).setTitle("Linux GPU driver (Turnip)").setSingleChoiceItems(labels,selected,(d,w)->{com.droiddeck.launcher.session.SessionPrefs.INSTANCE.setLinuxDriver(this,DRIVER_MODE,ids.get(w));BootLog.write(this,"Linux GPU driver selected: "+labels[w]);d.dismiss();Toast.makeText(this,"Kyty will use: "+labels[w],Toast.LENGTH_SHORT).show();})
            .setPositiveButton("Import Turnip zip",(d,w)->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");startActivityForResult(i,DRIVER);})
            .setNeutralButton("Get Turnip",(d,w)->{try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(TURNIP_RELEASES)));}catch(ActivityNotFoundException x){info("Turnip releases",TURNIP_RELEASES);}})
            .setNegativeButton("Close",null).show();}
    String importDriver(Uri uri)throws Exception {
        String name="Turnip";try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){if(c!=null&&c.moveToFirst()&&c.getString(0)!=null)name=c.getString(0);}
        String id=new com.droiddeck.launcher.gpu.LinuxVulkanDriverManager(this).installDriver(uri,name.replaceAll("(?i)\\.zip$",""));
        com.droiddeck.launcher.session.SessionPrefs.INSTANCE.setLinuxDriver(this,DRIVER_MODE,id);BootLog.write(this,"Imported Linux GPU driver "+id+" from "+name);
        return "Installed and selected: "+com.droiddeck.launcher.gpu.LinuxVulkanDriver.optionLabel(this,id)+"\n\nIt takes effect at the next game launch. Use a \"-Linux\" Turnip build (for Adreno 8xx: Turnip-v26.3.0-20260923-A8xx-Linux.zip). Android-only drivers cannot load inside the Linux runtime.";
    }
    void launchGame(GameStore.Entry e){
        try{engine.resolveGame(e);}catch(Exception x){info("Game access",x.getMessage());return;}
        Runnable prepare=()->{ProgressDialog p=new ProgressDialog(this);p.setTitle("Preparing NovaPs5 engine");p.setMessage("Preparing runtime…");p.setCancelable(false);p.show();io.execute(()->{
            try{BootLog.write(this,"Prepare requested: "+e.name);engine.prepare((stage,percent)->ui(()->p.setMessage(stage+(percent>=0?" · "+percent+"%":""))));String game=engine.resolveGame(e);ui(()->{p.dismiss();try{engine.launch(game,e.name);}catch(Throwable x){BootLog.rethrowFatal(x);info("Engine launch failed",BootLog.failure(this,"Starting the runtime session",x));}});}
            catch(Throwable x){BootLog.rethrowFatal(x);String message=BootLog.failure(this,"Preparing the engine",x);ui(()->{p.dismiss();info("Engine preparation failed",message);});}
        });};
        if(!engine.ready())new AlertDialog.Builder(this).setTitle("Prepare game engine").setMessage("The first launch downloads about 790 MB of runtime files and needs at least 6 GB free. Kyty is included in the APK. No Steam account is required.\n\nThis is an experimental boot build; a 60 FPS frame limit does not guarantee 60 FPS gameplay.").setPositiveButton("Prepare and launch",(d,w)->prepare.run()).setNegativeButton("Cancel",null).show();else prepare.run();
    }
    void entry(GameStore.Entry e){new AlertDialog.Builder(this).setTitle(e.name).setMessage(e.id+(e.version.isEmpty()?"":" · "+e.version)+"\n\nLaunch this extracted game with the full Kyty core through standalone Linux FEX. Compatibility and performance are experimental.")
        .setPositiveButton("Play",(d,w)->launchGame(e)).setNeutralButton("Inspect executable",(d,w)->busy("Inspecting executable",()->NativeBridge.AVAILABLE?NativeBridge.inspectElf(store.executableHeader(e.eboot)):"Diagnostic native library unavailable",value->info(e.name,value))).setNegativeButton("Close",null).show();}
    String fullReport(){return "NovaPs5 0.4.5-native\nKyty snapshot df5b9b9\nDevice: "+Build.MANUFACTURER+" "+Build.MODEL+"\nAndroid "+Build.VERSION.RELEASE+" / API "+Build.VERSION.SDK_INT+"\nABIs: "+Arrays.toString(Build.SUPPORTED_ABIS)+"\n\nCPU smoke test:\n"+cpu+"\n\nVulkan capabilities:\n"+pretty(report)+"\n\nFull Kyty Linux x86-64 core is packaged; standalone Linux FEX execution is experimental. Game boot and FPS require device validation.\nIncluded: bounded integer-block translation test, native Vulkan triangle, diagnostic touch input, game-folder metadata and firmware-file retention.\nRuntime status: "+engine.status()+".\n\n"+(NativeBridge.AVAILABLE?NativeBridge.rendererStatus():"")+"\n\nEngine preparation log:\n"+BootLog.read(this)+"\n\nLatest session log:\n"+engine.latestBootLog();}
    String pretty(String json){try{return new JSONObject(json).toString(2);}catch(Exception e){return json;}}
    void diagnostics(){String value=fullReport();TextView text=new TextView(this);text.setText(value);text.setTextSize(14);text.setTextIsSelectable(true);text.setPadding(28,20,28,20);ScrollView scroll=new ScrollView(this);scroll.addView(text);new AlertDialog.Builder(this).setTitle("Device and core diagnostics").setView(scroll).setPositiveButton("Vulkan + control test",(d,w)->test()).setNeutralButton("Export",(d,w)->{exportText=fullReport();Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType("text/plain");i.addCategory(Intent.CATEGORY_OPENABLE);i.putExtra(Intent.EXTRA_TITLE,"NovaPs5-diagnostics.txt");startActivityForResult(i,EXPORT);}).setNegativeButton("Close",null).show();}
    void settings(){LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(32,18,32,12);android.content.SharedPreferences prefs=getSharedPreferences("nova",0);
        TextView opacity=new TextView(this);opacity.setText("Touch control opacity");box.addView(opacity);SeekBar alpha=new SeekBar(this);alpha.setMax(65);alpha.setProgress(prefs.getInt("opacity",75)-35);box.addView(alpha);
        TextView sensitivity=new TextView(this);sensitivity.setText("Right stick sensitivity");box.addView(sensitivity);SeekBar sense=new SeekBar(this);sense.setMax(15);sense.setProgress(prefs.getInt("sensitivity",10)-5);box.addView(sense);
        CheckBox sticks=new CheckBox(this);sticks.setText("Show L3 and R3 buttons");sticks.setChecked(prefs.getBoolean("stick_clicks",true));box.addView(sticks);
        android.widget.Button driver=new android.widget.Button(this);driver.setText("GPU driver: "+driverLabel());driver.setAllCaps(false);driver.setOnClickListener(v->gpuDriver());box.addView(driver);
        TextView state=new TextView(this);state.setText("0.4.5 Native ARM64 Kyty preview\nLinux GPU driver: "+driverLabel()+" • ARM64\nNative emulator, game code via embedded FEX");state.setTextColor(0xffa8b6d2);state.setPadding(0,16,0,8);box.addView(state);
        new AlertDialog.Builder(this).setTitle("NovaPs5 settings").setView(box).setPositiveButton("Save",(d,w)->{prefs.edit().putInt("opacity",alpha.getProgress()+35).putInt("sensitivity",sense.getProgress()+5).putBoolean("stick_clicks",sticks.isChecked()).apply();if(controls!=null)controls.invalidate();}).setNeutralButton("Firmware",(d,w)->firmware()).setNegativeButton("Close",null).show();}
    void test(){if(!NativeBridge.AVAILABLE){info("Native runtime","This APK contains an ARM64 backend. A compatible ARM64 device is required.");return;}testing=true;screen=new FrameLayout(this);surface=new SurfaceView(this);screen.addView(surface,new FrameLayout.LayoutParams(-1,-1));controls=new TouchControls(this);screen.addView(controls,new FrameLayout.LayoutParams(-1,-1));setContentView(screen);immersive();
        surface.getHolder().addCallback(new SurfaceHolder.Callback(){public void surfaceCreated(SurfaceHolder h){if(!paused&&testing)NativeBridge.startRenderer(h.getSurface());}public void surfaceChanged(SurfaceHolder h,int f,int w,int height){if(!paused&&testing){NativeBridge.stopRenderer();NativeBridge.startRenderer(h.getSurface());}}public void surfaceDestroyed(SurfaceHolder h){NativeBridge.stopRenderer();}});
    }
    void sendInput(int touchButtons,float lx,float ly,float rx,float ry,float l2,float r2,int touches,float tx,float ty){if(NativeBridge.AVAILABLE){float rs=getSharedPreferences("nova",0).getInt("sensitivity",10)/10f;NativeBridge.setPad(touchButtons|hardwareButtons,Math.abs(lx)>.001f?lx:hx,Math.abs(ly)>.001f?ly:hy,clamp((Math.abs(rx)>.001f?rx:hrx)*rs),clamp((Math.abs(ry)>.001f?ry:hry)*rs),Math.max(l2,hl2),Math.max(r2,hr2),touches,tx,ty);}}
    float clamp(float x){return Math.max(-1,Math.min(1,x));}
    int mask(int code){switch(code){case KeyEvent.KEYCODE_BUTTON_A:return 0x4000;case KeyEvent.KEYCODE_BUTTON_B:return 0x2000;case KeyEvent.KEYCODE_BUTTON_X:return 0x8000;case KeyEvent.KEYCODE_BUTTON_Y:return 0x1000;case KeyEvent.KEYCODE_BUTTON_L1:return 0x400;case KeyEvent.KEYCODE_BUTTON_R1:return 0x800;case KeyEvent.KEYCODE_BUTTON_L2:return 0x100;case KeyEvent.KEYCODE_BUTTON_R2:return 0x200;case KeyEvent.KEYCODE_BUTTON_THUMBL:return 2;case KeyEvent.KEYCODE_BUTTON_THUMBR:return 4;case KeyEvent.KEYCODE_BUTTON_START:return 8;case KeyEvent.KEYCODE_BUTTON_SELECT:return 0;case KeyEvent.KEYCODE_DPAD_UP:return 0x10;case KeyEvent.KEYCODE_DPAD_DOWN:return 0x40;case KeyEvent.KEYCODE_DPAD_LEFT:return 0x80;case KeyEvent.KEYCODE_DPAD_RIGHT:return 0x20;default:return 0;}}
    @Override public boolean dispatchKeyEvent(KeyEvent e){int key=e.getKeyCode();if((e.getSource()&(InputDevice.SOURCE_GAMEPAD|InputDevice.SOURCE_JOYSTICK|InputDevice.SOURCE_DPAD))!=0){
        if(testing){if(key==KeyEvent.KEYCODE_BUTTON_MODE&&e.getAction()==KeyEvent.ACTION_DOWN){controls.release();settings();return true;}if(key==KeyEvent.KEYCODE_BUTTON_SELECT&&e.getAction()==KeyEvent.ACTION_DOWN){controls.release();diagnostics();return true;}int bit=mask(key);if(bit!=0){if(e.getAction()==KeyEvent.ACTION_DOWN)hardwareButtons|=bit;else if(e.getAction()==KeyEvent.ACTION_UP)hardwareButtons&=~bit;controls.send();controls.invalidate();return true;}}
        else if(e.getAction()==KeyEvent.ACTION_DOWN&&e.getRepeatCount()==0){if(key==KeyEvent.KEYCODE_DPAD_LEFT){home.move(-1);return true;}if(key==KeyEvent.KEYCODE_DPAD_RIGHT){home.move(1);return true;}if(key==KeyEvent.KEYCODE_BUTTON_A||key==KeyEvent.KEYCODE_DPAD_CENTER){home.activate();return true;}if(key==KeyEvent.KEYCODE_BUTTON_START){settings();return true;}}
    }return super.dispatchKeyEvent(e);}
    @Override public boolean onGenericMotionEvent(MotionEvent e){if(testing&&(e.getSource()&InputDevice.SOURCE_JOYSTICK)==InputDevice.SOURCE_JOYSTICK&&e.getAction()==MotionEvent.ACTION_MOVE){hx=dead(e,MotionEvent.AXIS_X);hy=dead(e,MotionEvent.AXIS_Y);hrx=dead(e,MotionEvent.AXIS_Z);hry=dead(e,MotionEvent.AXIS_RZ);hl2=Math.max(e.getAxisValue(MotionEvent.AXIS_LTRIGGER),e.getAxisValue(MotionEvent.AXIS_BRAKE));hr2=Math.max(e.getAxisValue(MotionEvent.AXIS_RTRIGGER),e.getAxisValue(MotionEvent.AXIS_GAS));hardwareButtons&=~0xf0;float hatX=e.getAxisValue(MotionEvent.AXIS_HAT_X),hatY=e.getAxisValue(MotionEvent.AXIS_HAT_Y);if(hatX<-.5)hardwareButtons|=0x80;if(hatX>.5)hardwareButtons|=0x20;if(hatY<-.5)hardwareButtons|=0x10;if(hatY>.5)hardwareButtons|=0x40;controls.send();controls.invalidate();return true;}return super.onGenericMotionEvent(e);}
    float dead(MotionEvent e,int axis){float value=e.getAxisValue(axis);InputDevice d=e.getDevice();InputDevice.MotionRange range=d==null?null:d.getMotionRange(axis,e.getSource());float dead=range==null?.13f:Math.max(.13f,range.getFlat());return Math.abs(value)<=dead?0:value;}
}


