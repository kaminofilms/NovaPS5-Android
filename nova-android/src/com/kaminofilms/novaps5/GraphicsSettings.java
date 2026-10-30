package com.kaminofilms.novaps5;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.system.Os;
import android.widget.*;

/** Launch-time renderer controls. Overrides are keyed by metadata title ID. */
final class GraphicsSettings {
    static final String[] MODES = {"Automatic (Mailbox)", "VSync (FIFO)", "Immediate (may tear)"};
    static final String[] SYNC = {"Fast (recommended)", "Accurate (slower; try if a game hangs)"};
    static final String[] READBACK = {"Off (experimental; can lose GPU data)", "Relaxed (recommended)", "Precise (most compatible; slower)"};
    static final String[] READBACK_MODES = {"off", "relaxed", "precise"};
    static final String[] VIDEO_OUT = {"1080p display (faster, recommended)", "4K display (game may render 4K)"};
    static final int[] SCALE_PCT = {100,75,67,50,33,25};
    // 0.9.92: GPU renderer per game. Kyty stays the default; AnyPS5 is experimental.
    static final String[] BACKEND = {"Kyty (default, most tested)", "AnyPS5 (experimental)"};
    static int surfacePermille(SharedPreferences p, String title, boolean unreal) {
        int selected=value(p,title,"render_height_v70",0);
        int[] targets={1000,1000,666,500,333};
        return selected>=0 && selected<targets.length ? targets[selected] : 1000;
    }
    // 0.9.57: Mesa Turnip TU_DEBUG workarounds for Adreno GPU hangs (no effect on the system driver).
    static final String[] TURNIP = {"Off", "Disable LRZ (nolrz; try if the GPU hangs)", "System-memory rendering (sysmem)", "Both (nolrz,sysmem)"};
    static final String[] TURNIP_FLAGS = {"", "nolrz", "sysmem", "nolrz,sysmem"};
    // 0.9.58: Lossless Scaling frame generation with the user's own Lossless.dll (never bundled).
    static final String[] FRAMEGEN = {"Off", "2x", "3x", "4x"};
    static final String[] FLOW_VALUES = {"1.0", "0.75", "0.5", "0.35", "0.25"};
    /** 0.9.62: titles that start with 2x2 variable-rate shading (GPU-bound on Adreno 840). */
    static boolean vrsDefault(String title) { return "PPSA04703".equals(title) || "PPSA27841".equals(title); }
    static java.io.File lsfgDll(Context c) { return new java.io.File(new java.io.File(c.getFilesDir(), "lsfg"), "Lossless.dll"); }
    static final String[] CAPS = {"Inherit existing FPS cap", "30", "40", "60", "90", "120", "Unlimited"};
    static String key(String title, String setting) { return title + ":" + setting; }
    static int value(SharedPreferences p, String title, String name, int fallback) {
        return p.getInt(key(title, name), p.getInt(key("", name), fallback));
    }
    /** 0.9.56 safe profile: Unreal titles that booted on 0.9.52 and broke with the faster defaults. */
    static boolean safe(String title) { return "PPSA36257".equals(title) || "PPSA31162".equals(title); }
    /** Versioned 0.9.56 settings: earlier saved values do not carry over; safe titles ignore global defaults. */
    static int value56(SharedPreferences p, String title, String name, int normal, int safeValue) {
        if (p.contains(key(title, name))) return p.getInt(key(title, name), normal);
        if (safe(title)) return safeValue;
        return p.getInt(key("", name), normal);
    }
    /** Titles that start with Accurate sync. Dead Cells is back on Fast (its 0.9.10 setting):
     *  its freeze was the removed WAIT_REG_MEM give-up, restored natively in 0.9.57. */
    static boolean accurateSync(String title) { return safe(title); }
    static int syncValue(SharedPreferences p, String title) {
        if (p.contains(key(title, "sync_v56"))) return p.getInt(key(title, "sync_v56"), 0);
        if (accurateSync(title)) return 1;
        return p.getInt(key("", "sync_v56"), 0);
    }
    static final String[] V56 = {"sync_v56","readback_v56","fault_window_v56","video_out_v56","async_v56"};
    static Spinner choice(Activity a, LinearLayout box, String label, String[] options, int selected) {
        TextView text = new TextView(a); text.setText(label); box.addView(text);
        Spinner s = new Spinner(a);
        s.setAdapter(new ArrayAdapter<String>(a, android.R.layout.simple_spinner_dropdown_item, options));
        s.setSelection(Math.max(0, Math.min(options.length - 1, selected))); box.addView(s); return s;
    }
    static Switch toggle(Activity a, LinearLayout box, String label, boolean selected) {
        Switch s = new Switch(a); s.setText(label); s.setChecked(selected); box.addView(s); return s;
    }
    static void migrateDeadCellsCap(SharedPreferences p, String title) {
        if ("PPSA27841".equals(title) && !p.getBoolean("wonder_native_v74",false)) {
            // One-time correction of the prior 30 FPS/native profile and saved
            // nolrz workaround. Manual changes after migration remain respected.
            p.edit().putInt(key(title,"cap"),3).putInt(key(title,"fg_v58"),0)
                .putInt(key(title,"present"),0).putInt(key(title,"tu_debug_v57"),0)
                .putInt(key(title,"render_height_v70"),0).putInt(key(title,"video_out_v63"),0)
                .putInt(key(title,"power_mode_v71"),0).putBoolean("wonder_native_v74",true).apply();
        }
        if ("PPSA15552".equals(title) && !p.getBoolean("deadcells_cap_v50", false)) {
            // Owner-requested 60 FPS profile. One migration only; later edits remain user-controlled.
            p.edit().putInt(key(title,"cap"),3).putBoolean("deadcells_cap_v50",true).apply();
        }
    }
    static void show(Activity a, String title) { GraphicsPanel.show(a,title,title.isEmpty()?"Default graphics":title); }
    static void showAdvanced(Activity a, String title) {
        SharedPreferences p = a.getSharedPreferences("graphics", 0);
        migrateDeadCellsCap(p,title);
        LinearLayout box = new LinearLayout(a); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(32, 16, 32, 16);
        TextView note = new TextView(a);
        note.setText("Leave these at their defaults unless a game has a problem. Changes apply on next launch."); box.addView(note);
        Spinner backend = choice(a, box, "GPU renderer", BACKEND, value(p,title,"gpu_backend_v92",0));
        box.addView(GraphicsPanel.text(a,"AnyPS5 uses its own shader compiler and GPU driver. It is experimental on Android: if a game fails to start or draws incorrectly, switch back to Kyty.",13,0xffafbdd3));
        Spinner mode = choice(a, box, "Presentation", MODES, value(p,title,"present",0));
        Spinner cap = choice(a, box, "Presentation FPS cap", CAPS, value(p,title,"cap",0));
        Switch cache = toggle(a, box, "Disk shader cache (recommended)", value(p,title,"cache",1)!=0);
        Switch gpl = toggle(a, box, "Pipeline libraries when supported", value(p,title,"gpl",1)!=0);
        if (safe(title)) { TextView safeNote = new TextView(a); safeNote.setText("Safe profile: this game starts with Accurate sync and Precise readback. Since 0.9.63 it reports a 1080p display like other games (4x fewer pixels than 4K). Change them here to experiment."); box.addView(safeNote); }
        Spinner sync = choice(a, box, "GPU sync", SYNC, syncValue(p,title));
        Spinner readback = choice(a, box, "GPU memory readback", READBACK, value56(p,title,"readback_v56",1,2));
        Switch window = toggle(a, box, "Write-fault window (faster uploads)", value56(p,title,"fault_window_v56",1,0)!=0);
        Switch async = toggle(a, box, "Background shader compilation (no shader stutter; objects can pop in briefly)", value56(p,title,"async_v56",1,0)!=0);
        Spinner video = choice(a, box, "Console video output", VIDEO_OUT, value(p,title,"video_out_v63",0));
        Spinner turnip = choice(a, box, "Turnip driver workaround", TURNIP, value(p,title,"tu_debug_v57",0));
        boolean haveDll = lsfgDll(a).isFile();
        Spinner framegen = choice(a, box, "Frame generation (Lossless Scaling)", FRAMEGEN, value(p,title,"fg_v58",0));


        TextView fgNote = new TextView(a);
        fgNote.setText((haveDll ? "Lossless.dll imported. " : "Import your Lossless.dll first (Settings → Lossless Scaling DLL); until then this stays off. ")
            + "Frame generation needs stable real FPS. It uses at most 1080p processing and requires timed VSync presentation. It cannot fix slow game simulation. Turn it off if the picture shows artefacts or the game gets slower."); box.addView(fgNote);
        box.addView(GraphicsPanel.text(a,"Android manages GPU clocks and thermal protection.",13,0xffafbdd3));
        Switch vrs = toggle(a, box, "Variable-rate shading (2x2; faster, slightly softer 3D image; HUD stays sharp)", value(p,title,"vrs_v62",vrsDefault(title)?1:0)!=0);
        Switch realTime = toggle(a, box, "Report real GPU time (games with dynamic resolution can lower it themselves)", value(p,title,"real_gpu_time_v62",vrsDefault(title)?1:0)!=0);
        ScrollView scroll = new ScrollView(a); scroll.addView(box);
        LinearLayout panel=GraphicsPanel.panel(a);
        panel.addView(GraphicsPanel.text(a,"Advanced graphics",24,0xfff4f7ff));
        panel.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout footer=new LinearLayout(a);footer.setGravity(android.view.Gravity.RIGHT);panel.addView(footer);
        android.app.Dialog dialog=GraphicsPanel.dialog(a,panel,true);
        Button reset=GraphicsPanel.action(a,"Reset"),close=GraphicsPanel.action(a,"Close"),save=GraphicsPanel.action(a,"Save");
        for(Button button:new Button[]{reset,close,save}){LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,GraphicsPanel.dp(a,48));lp.leftMargin=GraphicsPanel.dp(a,8);footer.addView(button,lp);}
        close.setOnClickListener(v->dialog.dismiss());
        save.setOnClickListener(v->{
                SharedPreferences.Editor e=p.edit().putInt(key(title,"present"),mode.getSelectedItemPosition())
                    .putInt(key(title,"cap"),cap.getSelectedItemPosition()).putInt(key(title,"cache"),cache.isChecked()?1:0)
                    .putInt(key(title,"gpl"),gpl.isChecked()?1:0)
                    .putInt(key(title,"sync_v56"),sync.getSelectedItemPosition())
                    .putInt(key(title,"readback_v56"),readback.getSelectedItemPosition())
                    .putInt(key(title,"fault_window_v56"),window.isChecked()?1:0)
                    .putInt(key(title,"async_v56"),async.isChecked()?1:0);


                e.putInt(key(title,"video_out_v63"),video.getSelectedItemPosition());
                e.putInt(key(title,"gpu_backend_v92"),backend.getSelectedItemPosition());
                e.putInt(key(title,"tu_debug_v57"),turnip.getSelectedItemPosition());
                e.putInt(key(title,"fg_v58"),framegen.getSelectedItemPosition());


                e.putInt(key(title,"gpu_turbo_v62"),0);
                e.putInt(key(title,"vrs_v62"),vrs.isChecked()?1:0);
                e.putInt(key(title,"real_gpu_time_v62"),realTime.isChecked()?1:0);
                e.apply();
            dialog.dismiss();
        });
        reset.setOnClickListener(v->{
                SharedPreferences.Editor e=p.edit(); for(String n:new String[]{"present","cap","cache","gpl","render_height_v70","present_filter_v111","rescale_v64","raster_scale_v54","sync_v56","readback_v56","fault_window_v56","video_out_v56","video_out_v63","async_v56","tu_debug_v57","fg_v58","fg_flow_v58","fg_perf_v58","gpu_turbo_v62","vrs_v62","real_gpu_time_v62","gpu_backend_v92"})e.remove(key(title,n)); e.apply();
            dialog.dismiss();
        });
        dialog.show();

    }
    static void apply(Context c, String title) throws android.system.ErrnoException {
        SharedPreferences p=c.getSharedPreferences("graphics",0);
        migrateDeadCellsCap(p,title);
        int backend=value(p,title,"gpu_backend_v92",0); if(backend<0||backend>=BACKEND.length)backend=0;
        Os.setenv("NOVA_GPU_BACKEND",backend==1?"anyps5":"kyty",true);
        Os.setenv("NOVA_AUDIO_PROFILE","PPSA27841".equals(title)?"1":"0",true);
        // 0.9.106: submission call sites for the CPU/GPU overlap investigation (tasks 1-4).
        Os.setenv("NOVA_SUBMIT_REASONS","PPSA27841".equals(title)?"1":"0",true);
        // 0.9.107: sampled per-draw GPU timing (1 s of every 10 s) to find what costs the frame.
        Os.setenv("NOVA_GPU_DRAW_PROFILE",("PPSA27841".equals(title)||"PPSA36257".equals(title))?"1":"0",true);
        // 0.9.114: the slowest pipelines' translated shaders are saved to Download/NovaPS5-shaders.
        String shaderDir="";
        if(("PPSA27841".equals(title)||"PPSA36257".equals(title))&&android.os.Environment.isExternalStorageManager()){
            java.io.File d=new java.io.File(android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS),"NovaPS5-shaders");
            if(d.isDirectory()||d.mkdirs())shaderDir=d.getPath();
        }
        Os.setenv("NOVA_SHADER_EXPORT_DIR",shaderDir,true);
        Os.setenv("NOVA_STABLE_DEPTH","PPSA27841".equals(title)?"1":"0",true);
        int mode=value(p,title,"present",0); if(mode<0||mode>2)mode=0;
        int cap=value(p,title,"cap",0); int[] limits={-1,30,40,60,90,120,0};
        int ri=value(p,title,"raster_scale_v54",0); if(ri<0||ri>=SCALE_PCT.length)ri=0;
        // 0.9.109: "Render resolution" is an absolute height. Taller render targets are scaled to it
        // (a 4K-rendering game set to 1080p renders 1920x1080); smaller targets stay native.
        int rh=value(p,title,"render_height_v70",0); int[] heights={0,1080,720,540,360};
        int targetHeight=rh>=0&&rh<heights.length?heights[rh]:0;
        Os.setenv("NOVA_RESCALE_PERMILLE","1000",true);
        Os.setenv("NOVA_RESCALE_TARGET_HEIGHT",Integer.toString(targetHeight),true);
        int pf=value(p,title,"present_filter_v111",0);
        Os.setenv("NOVA_PRESENT_FILTER",pf==1?"bicubic":pf==2?"sharp":"bilinear",true);
        // Surface and compatibility scaling must never multiply each other.
        ri=0;
        BootLog.write(c,"Render resolution: "+(targetHeight==0?"native":targetHeight+"p target height")+" (native fallbacks for unsupported uses)");
        Os.setenv("NOVA_UNITY_RESOLUTION","0",true);
        Os.setenv("NOVA_INTERNAL_RESOLUTION","0",true);
        Os.setenv("NOVA_RASTER_SCALE_PCT",Integer.toString(SCALE_PCT[ri]),true);
        int vo=value(p,title,"video_out_v63",0); if(vo<0||vo>1)vo=0;
        Os.setenv("NOVA_VIDEO_OUT_4K",vo==1?"1":"0",true);
        // Capture the default mode too, so a second launch can prove whether a request changed real rendering.
        Os.setenv("NOVA_TRACE_RESOLUTION","PPSA04703".equals(title)?"1":"0",true);
        BootLog.write(c,"Internal resolution: "+SCALE_PCT[ri]+"% of native for eligible 16:9 passes");
        // 0.9.58: frame generation needs every generated frame shown in order, so FIFO.
        int fg=value(p,title,"fg_v58",0); if(fg<0||fg>=FRAMEGEN.length)fg=0;
        int flow=value(p,title,"fg_flow_v58",2); if(flow<0||flow>=FLOW_VALUES.length)flow=2;
        boolean fgPerf=value(p,title,"fg_perf_v58",1)!=0;
        java.io.File dll=lsfgDll(c);
        if(fg>0&&!dll.isFile()){BootLog.write(c,"Frame generation requested but Lossless.dll is not imported; off");fg=0;}
        if(fg>0){
            Os.setenv("NOVA_FRAMEGEN",Integer.toString(fg+1),true);
            Os.setenv("NOVA_LSFG_DLL",dll.getAbsolutePath(),true);
            Os.setenv("NOVA_FRAMEGEN_FLOW",FLOW_VALUES[flow],true);
            Os.setenv("NOVA_FRAMEGEN_PERF",fgPerf?"1":"0",true);
            mode=1;
        } else {
            for(String n:new String[]{"NOVA_FRAMEGEN","NOVA_LSFG_DLL","NOVA_FRAMEGEN_FLOW","NOVA_FRAMEGEN_PERF"})Os.unsetenv(n);
        }
        Os.setenv("NOVA_PRESENT_MODE",new String[]{"mailbox","fifo","immediate"}[mode],true);
        // 0.9.62: GPU turbo (KGSL max clock) and 2x2 variable-rate shading.
        boolean turbo=false; // Legacy saved turbo must never re-enable forced clocks.
        boolean vrs=value(p,title,"vrs_v62",vrsDefault(title)?1:0)!=0;
        Os.setenv("NOVA_GPU_TURBO",turbo?"1":"0",true);
        Os.setenv("NOVA_VRS",vrs?"2":"0",true);
        boolean realTime=value(p,title,"real_gpu_time_v62",vrsDefault(title)?1:0)!=0;
        Os.setenv("NOVA_REAL_GPU_TIME",realTime?"1":"0",true);
        boolean cache=value(p,title,"cache",1)!=0, gpl=value(p,title,"gpl",1)!=0;
        Os.setenv("NOVA_SHADER_CACHE",cache?"1":"0",true);
        Os.setenv("MESA_SHADER_CACHE_DISABLE",cache?"false":"true",true);
        Os.setenv("NOVA_PIPELINE_LIBRARIES",gpl?"1":"0",true);
        // 0.9.53: native-speed defaults (KytyPS5/shadPS4-style labels, relaxed readbacks).
        // 0.9.56: Relaxed readback by default ("off" could drop GPU-written data);
        // Luna and Super Meat Boy keep their 0.9.52 behaviour unless changed.
        boolean safe=safe(title);
        int sync=syncValue(p,title); if(sync<0||sync>1)sync=0;
        int readback=value56(p,title,"readback_v56",1,2); if(readback<0||readback>2)readback=1;
        boolean window=value56(p,title,"fault_window_v56",1,0)!=0;
        boolean async=value56(p,title,"async_v56",1,0)!=0;
        Os.setenv("NOVA_ASYNC_PIPELINES",async?"1":"0",true);
        int tu=value(p,title,"tu_debug_v57",0); if(tu<0||tu>=TURNIP_FLAGS.length)tu=0;
        if(tu==0)Os.unsetenv("TU_DEBUG"); else Os.setenv("TU_DEBUG",TURNIP_FLAGS[tu],true);
        Os.setenv("NOVA_LABEL_MODE",sync==0?"fast":"accurate",true);
        Os.setenv("NOVA_READBACK_MODE",READBACK_MODES[readback],true);
        // 0.9.54: periodic submits, 80 ms audio queue, normal (not low-latency) AAudio stream.
        Os.setenv("NOVA_SUBMIT_DRAWS",safe?"0":"1024",true);
        Os.setenv("NOVA_AUDIO_LATENCY_MS","80",true);
        Os.setenv("NOVA_AUDIO_LOW_LATENCY","0",true);
        Os.setenv("SDL_ANDROID_LOW_LATENCY_AUDIO","0",true);
        Os.setenv("NOVA_FAULT_WINDOW_KB",window?"64":"0",true);
        // 0.9.108: write-fault readbacks also fetch the GPU-written neighbourhood (same switch turns it off).
        Os.setenv("NOVA_FAULT_COALESCE_KB",window?"256":"0",true);
        // Accurate mode keeps the 0.9.52 GPU-label and ordered-wait paths.
        Os.setenv("NOVA_GPU_LABELS","1",true);
        Os.setenv("NOVA_GPU_ORDERED_WAITS","1",true);
        if(cap>0&&cap<limits.length)Os.setenv("NOVA_FPS_CAP",Integer.toString(limits[cap]),true);
        else Os.unsetenv("NOVA_FPS_CAP");
        BootLog.write(c,"Graphics profile "+title+": backend="+(backend==1?"anyps5":"kyty")+" present="+mode+" cap="+cap+" shader_cache="+cache+" pipeline_libraries="+gpl+" sync="+(sync==0?"fast":"accurate")+" readback="+READBACK_MODES[readback]+" fault_window="+window+" scale="+SCALE_PCT[ri]+"% video="+(vo==1?"4k":"1080p")+" async_shaders="+async+" safe_profile="+safe+" tu_debug="+(tu==0?"off":TURNIP_FLAGS[tu])+" gpu_turbo="+turbo+" vrs="+(vrs?"2x2":"off")+" real_gpu_time="+realTime+" framegen="+(fg==0?"off":(fg+1)+"x flow="+FLOW_VALUES[flow]+(fgPerf?" performance":" quality")));
    }
}


