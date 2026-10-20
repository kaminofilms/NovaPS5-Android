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
    static final String[] CAPS = {"Inherit existing FPS cap", "30", "40", "60", "90", "120", "Unlimited"};
    static String key(String title, String setting) { return title + ":" + setting; }
    static int value(SharedPreferences p, String title, String name, int fallback) {
        return p.getInt(key(title, name), p.getInt(key("", name), fallback));
    }
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
        Switch labels = toggle(a, box, "Fast GPU completion (recommended; turn off if a game hangs or flickers)", value(p,title,"gpu_labels",1)!=0);
        Switch ordered = toggle(a, box, "Ordered GPU waits (faster queues; turn off if visuals glitch)", value(p,title,"gpu_ordered",1)!=0);
        final Spinner resolution = "PPSA04703".equals(title) ? choice(a, box,
            "Internal raster resolution (experimental)",
            new String[]{"Game default", "1920 × 1080", "1280 × 720", "960 × 540", "640 × 360"},
            value(p,title,"raster_resolution_v2",0)) : null;
        TextView unavailable = new TextView(a);
        unavailable.setText("Ever Forward starts at native resolution after this update. Lower raster resolutions remain experimental. Eligible color/depth passes scale; compute, shadows and unsupported passes stay native."); box.addView(unavailable);
        ScrollView scroll = new ScrollView(a); scroll.addView(box);
        new AlertDialog.Builder(a).setTitle(title.isEmpty()?"Graphics defaults":"Graphics · "+title).setView(scroll)
            .setPositiveButton("Save",(d,w)->{
                SharedPreferences.Editor e=p.edit().putInt(key(title,"present"),mode.getSelectedItemPosition())
                    .putInt(key(title,"cap"),cap.getSelectedItemPosition()).putInt(key(title,"cache"),cache.isChecked()?1:0)
                    .putInt(key(title,"gpl"),gpl.isChecked()?1:0)
                    .putInt(key(title,"gpu_labels"),labels.isChecked()?1:0)
                    .putInt(key(title,"gpu_ordered"),ordered.isChecked()?1:0);
                if(resolution!=null)e.putInt(key(title,"raster_resolution_v2"),resolution.getSelectedItemPosition());
                e.apply();
            })
            .setNeutralButton(title.isEmpty()?"Reset defaults":"Use global defaults",(d,w)->{
                SharedPreferences.Editor e=p.edit(); for(String n:new String[]{"present","cap","cache","gpl","gpu_labels","gpu_ordered","raster_resolution_v2"})e.remove(key(title,n)); e.apply();
            }).setNegativeButton("Close",null).show();
    }
    static void apply(Context c, String title) throws android.system.ErrnoException {
        SharedPreferences p=c.getSharedPreferences("graphics",0);
        migrateDeadCellsCap(p,title);
        int mode=value(p,title,"present",0); if(mode<0||mode>2)mode=0;
        int cap=value(p,title,"cap",0); int[] limits={-1,30,40,60,90,120,0};
        int ri=value(p,title,"raster_resolution_v2",0); int[] heights={0,1080,720,540,360};
        if(ri<0||ri>=heights.length||!"PPSA04703".equals(title))ri=0;
        Os.setenv("NOVA_UNITY_RESOLUTION","0",true);
        Os.setenv("NOVA_INTERNAL_RESOLUTION",Integer.toString(heights[ri]),true);
        // Capture the default mode too, so a second launch can prove whether a request changed real rendering.
        Os.setenv("NOVA_TRACE_RESOLUTION","PPSA04703".equals(title)?"1":"0",true);
        BootLog.write(c,"Internal raster resolution: "+(heights[ri]==0?"native":heights[ri]+"p; eligible raster passes"));
        Os.setenv("NOVA_PRESENT_MODE",new String[]{"mailbox","fifo","immediate"}[mode],true);
        boolean cache=value(p,title,"cache",1)!=0, gpl=value(p,title,"gpl",1)!=0;
        Os.setenv("NOVA_SHADER_CACHE",cache?"1":"0",true);
        Os.setenv("MESA_SHADER_CACHE_DISABLE",cache?"false":"true",true);
        Os.setenv("NOVA_PIPELINE_LIBRARIES",gpl?"1":"0",true);
        boolean labels=value(p,title,"gpu_labels",1)!=0;
        Os.setenv("NOVA_GPU_LABELS",labels?"1":"0",true);
        boolean ordered=value(p,title,"gpu_ordered",1)!=0;
        Os.setenv("NOVA_GPU_ORDERED_WAITS",ordered?"1":"0",true);
        if(cap>0&&cap<limits.length)Os.setenv("NOVA_FPS_CAP",Integer.toString(limits[cap]),true);
        BootLog.write(c,"Graphics profile "+title+": present="+mode+" cap="+cap+" shader_cache="+cache+" pipeline_libraries="+gpl+" gpu_labels="+labels+" ordered_waits="+ordered);
    }
}
