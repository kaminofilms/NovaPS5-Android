package com.kaminofilms.novaps5;

import android.app.Activity;
import android.app.AlertDialog;
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
    static final String[] SCALES = {"Native (100%)", "75%", "67%", "50%", "33%", "25% (fastest)"};
    static final int[] SCALE_PCT = {100, 75, 67, 50, 33, 25};
    // 0.9.57: Mesa Turnip TU_DEBUG workarounds for Adreno GPU hangs (no effect on the system driver).
    static final String[] TURNIP = {"Off", "Disable LRZ (nolrz; try if the GPU hangs)", "System-memory rendering (sysmem)", "Both (nolrz,sysmem)"};
    static final String[] TURNIP_FLAGS = {"", "nolrz", "sysmem", "nolrz,sysmem"};
    // 0.9.58: Lossless Scaling frame generation with the user's own Lossless.dll (never bundled).
    static final String[] FRAMEGEN = {"Off", "2x (one generated frame per real frame)", "3x", "4x"};
    static final String[] FLOW = {"100% (sharpest motion, slowest)", "75%", "50% (recommended)", "35%", "25% (fastest)"};
    static final String[] FLOW_VALUES = {"1.0", "0.75", "0.5", "0.35", "0.25"};
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
        if ("PPSA15552".equals(title) && !p.getBoolean("deadcells_cap_v50", false)) {
            // Owner-requested 60 FPS profile. One migration only; later edits remain user-controlled.
            p.edit().putInt(key(title,"cap"),3).putBoolean("deadcells_cap_v50",true).apply();
        }
    }
    static void show(Activity a, String title) {
        SharedPreferences p = a.getSharedPreferences("graphics", 0);
        migrateDeadCellsCap(p,title);
        LinearLayout box = new LinearLayout(a); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(32, 16, 32, 16);
        TextView note = new TextView(a);
        note.setText("Applies on next game launch. Per-game values override defaults. Unsupported presentation modes fall back to FIFO. These settings do not raise a game's native FPS limit."); box.addView(note);
        Spinner mode = choice(a, box, "Presentation", MODES, value(p,title,"present",0));
        Spinner cap = choice(a, box, "Presentation FPS cap", CAPS, value(p,title,"cap",0));
        Switch cache = toggle(a, box, "Disk shader cache (recommended)", value(p,title,"cache",1)!=0);
        Switch gpl = toggle(a, box, "Pipeline libraries when supported", value(p,title,"gpl",1)!=0);
        if (safe(title)) { TextView safeNote = new TextView(a); safeNote.setText("Safe profile: this game starts with the settings it booted with on 0.9.52 (Accurate sync, Precise readback, 4K output, no background shaders). Change them here to experiment."); box.addView(safeNote); }
        Spinner sync = choice(a, box, "GPU sync", SYNC, syncValue(p,title));
        Spinner readback = choice(a, box, "GPU memory readback", READBACK, value56(p,title,"readback_v56",1,2));
        Switch window = toggle(a, box, "Write-fault window (faster uploads)", value56(p,title,"fault_window_v56",1,0)!=0);
        Switch async = toggle(a, box, "Background shader compilation (no shader stutter; objects can pop in briefly)", value56(p,title,"async_v56",1,0)!=0);
        Spinner video = choice(a, box, "Console video output", VIDEO_OUT, value56(p,title,"video_out_v56",0,1));
        Spinner turnip = choice(a, box, "Turnip driver workaround", TURNIP, value(p,title,"tu_debug_v57",0));
        boolean haveDll = lsfgDll(a).isFile();
        Spinner framegen = choice(a, box, "Frame generation (Lossless Scaling)", FRAMEGEN, value(p,title,"fg_v58",0));
        Spinner flow = choice(a, box, "Frame generation flow scale", FLOW, value(p,title,"fg_flow_v58",2));
        Switch fgPerf = toggle(a, box, "Frame generation performance mode (faster, softer)", value(p,title,"fg_perf_v58",1)!=0);
        TextView fgNote = new TextView(a);
        fgNote.setText((haveDll ? "Lossless.dll imported. " : "Import your Lossless.dll first (Settings → Lossless Scaling DLL); until then this stays off. ")
            + "Generated frames are shown between real ones, so motion looks smoother but input lag rises slightly. Presentation switches to VSync while it is on. Turn it off if the picture shows artefacts or the game gets slower."); box.addView(fgNote);
        final Spinner resolution = choice(a, box, "Internal resolution", SCALES, value(p,title,"raster_scale_v54",0));
        TextView scaleNote = new TextView(a);
        scaleNote.setText("Lower values render eligible 16:9 colour/depth passes at a smaller size and are faster. Compute, shadow and unsupported passes stay native. Try Native if the picture breaks."); box.addView(scaleNote);
        ScrollView scroll = new ScrollView(a); scroll.addView(box);
        new AlertDialog.Builder(a).setTitle(title.isEmpty()?"Graphics defaults":"Graphics · "+title).setView(scroll)
            .setPositiveButton("Save",(d,w)->{
                SharedPreferences.Editor e=p.edit().putInt(key(title,"present"),mode.getSelectedItemPosition())
                    .putInt(key(title,"cap"),cap.getSelectedItemPosition()).putInt(key(title,"cache"),cache.isChecked()?1:0)
                    .putInt(key(title,"gpl"),gpl.isChecked()?1:0)
                    .putInt(key(title,"sync_v56"),sync.getSelectedItemPosition())
                    .putInt(key(title,"readback_v56"),readback.getSelectedItemPosition())
                    .putInt(key(title,"fault_window_v56"),window.isChecked()?1:0)
                    .putInt(key(title,"async_v56"),async.isChecked()?1:0);
                e.putInt(key(title,"raster_scale_v54"),resolution.getSelectedItemPosition());
                e.putInt(key(title,"video_out_v56"),video.getSelectedItemPosition());
                e.putInt(key(title,"tu_debug_v57"),turnip.getSelectedItemPosition());
                e.putInt(key(title,"fg_v58"),framegen.getSelectedItemPosition());
                e.putInt(key(title,"fg_flow_v58"),flow.getSelectedItemPosition());
                e.putInt(key(title,"fg_perf_v58"),fgPerf.isChecked()?1:0);
                e.apply();
            })
            .setNeutralButton(title.isEmpty()?"Reset defaults":"Use global defaults",(d,w)->{
                SharedPreferences.Editor e=p.edit(); for(String n:new String[]{"present","cap","cache","gpl","raster_scale_v54","sync_v56","readback_v56","fault_window_v56","video_out_v56","async_v56","tu_debug_v57","fg_v58","fg_flow_v58","fg_perf_v58"})e.remove(key(title,n)); e.apply();
            }).setNegativeButton("Close",null).show();
    }
    static void apply(Context c, String title) throws android.system.ErrnoException {
        SharedPreferences p=c.getSharedPreferences("graphics",0);
        migrateDeadCellsCap(p,title);
        int mode=value(p,title,"present",0); if(mode<0||mode>2)mode=0;
        int cap=value(p,title,"cap",0); int[] limits={-1,30,40,60,90,120,0};
        int ri=value(p,title,"raster_scale_v54",0); if(ri<0||ri>=SCALE_PCT.length)ri=0;
        Os.setenv("NOVA_UNITY_RESOLUTION","0",true);
        Os.setenv("NOVA_INTERNAL_RESOLUTION","0",true);
        Os.setenv("NOVA_RASTER_SCALE_PCT",Integer.toString(SCALE_PCT[ri]),true);
        int vo=value56(p,title,"video_out_v56",0,1); if(vo<0||vo>1)vo=0;
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
        // Accurate mode keeps the 0.9.52 GPU-label and ordered-wait paths.
        Os.setenv("NOVA_GPU_LABELS","1",true);
        Os.setenv("NOVA_GPU_ORDERED_WAITS","1",true);
        if(cap>0&&cap<limits.length)Os.setenv("NOVA_FPS_CAP",Integer.toString(limits[cap]),true);
        BootLog.write(c,"Graphics profile "+title+": present="+mode+" cap="+cap+" shader_cache="+cache+" pipeline_libraries="+gpl+" sync="+(sync==0?"fast":"accurate")+" readback="+READBACK_MODES[readback]+" fault_window="+window+" scale="+SCALE_PCT[ri]+"% video="+(vo==1?"4k":"1080p")+" async_shaders="+async+" safe_profile="+safe+" tu_debug="+(tu==0?"off":TURNIP_FLAGS[tu])+" framegen="+(fg==0?"off":(fg+1)+"x flow="+FLOW_VALUES[flow]+(fgPerf?" performance":" quality")));
    }
}
