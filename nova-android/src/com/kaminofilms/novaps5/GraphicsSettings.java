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
    static void show(Activity a, String title) {
        SharedPreferences p = a.getSharedPreferences("graphics", 0);
        LinearLayout box = new LinearLayout(a); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(32, 16, 32, 16);
        TextView note = new TextView(a);
        note.setText("Applies on next game launch. Per-game values override defaults. Unsupported presentation modes fall back to FIFO. These settings do not raise a game's native FPS limit."); box.addView(note);
        Spinner mode = choice(a, box, "Presentation", MODES, value(p,title,"present",0));
        Spinner cap = choice(a, box, "Presentation FPS cap", CAPS, value(p,title,"cap",0));
        Switch cache = toggle(a, box, "Disk shader cache (recommended)", value(p,title,"cache",1)!=0);
        Switch gpl = toggle(a, box, "Pipeline libraries when supported", value(p,title,"gpl",1)!=0);
        TextView unavailable = new TextView(a);
        unavailable.setText("Internal resolution scaling and asynchronous shader compilation require additional renderer support and are not available yet."); box.addView(unavailable);
        ScrollView scroll = new ScrollView(a); scroll.addView(box);
        new AlertDialog.Builder(a).setTitle(title.isEmpty()?"Graphics defaults":"Graphics · "+title).setView(scroll)
            .setPositiveButton("Save",(d,w)->p.edit().putInt(key(title,"present"),mode.getSelectedItemPosition())
                .putInt(key(title,"cap"),cap.getSelectedItemPosition()).putInt(key(title,"cache"),cache.isChecked()?1:0)
                .putInt(key(title,"gpl"),gpl.isChecked()?1:0).apply())
            .setNeutralButton(title.isEmpty()?"Reset defaults":"Use global defaults",(d,w)->{
                SharedPreferences.Editor e=p.edit(); for(String n:new String[]{"present","cap","cache","gpl"})e.remove(key(title,n)); e.apply();
            }).setNegativeButton("Close",null).show();
    }
    static void apply(Context c, String title) throws android.system.ErrnoException {
        SharedPreferences p=c.getSharedPreferences("graphics",0);
        int mode=value(p,title,"present",0); if(mode<0||mode>2)mode=0;
        int cap=value(p,title,"cap",0); int[] limits={-1,30,40,60,90,120,0};
        Os.setenv("NOVA_PRESENT_MODE",new String[]{"mailbox","fifo","immediate"}[mode],true);
        boolean cache=value(p,title,"cache",1)!=0, gpl=value(p,title,"gpl",1)!=0;
        Os.setenv("NOVA_SHADER_CACHE",cache?"1":"0",true);
        Os.setenv("MESA_SHADER_CACHE_DISABLE",cache?"false":"true",true);
        Os.setenv("NOVA_PIPELINE_LIBRARIES",gpl?"1":"0",true);
        if(cap>0&&cap<limits.length)Os.setenv("NOVA_FPS_CAP",Integer.toString(limits[cap]),true);
        BootLog.write(c,"Graphics profile "+title+": present="+mode+" cap="+cap+" shader_cache="+cache+" pipeline_libraries="+gpl);
    }
}
