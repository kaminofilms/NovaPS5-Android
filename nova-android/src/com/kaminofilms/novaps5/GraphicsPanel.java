package com.kaminofilms.novaps5;

import android.app.Activity;
import android.app.Dialog;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.*;

/** Nova's small, controller-friendly graphics sheet. Renderer details stay in Advanced. */
final class GraphicsPanel {
    static final String[] RESOLUTIONS = {"Native", "1080p", "720p", "540p", "360p"};
    static final String[] FILTERS = {"Bilinear", "Bicubic", "ScaleForce-style (sharp)"};
    static final String[] FRAMES = {"Off", "2x", "3x", "4x"};
    static final String[] LIMITS = {"Game default", "30 FPS", "40 FPS", "60 FPS", "90 FPS", "120 FPS", "Unlimited"};
    private static final int WHITE = 0xfff4f7ff, MUTED = 0xffafbdd3, BLUE = 0xff91c6ff;
    static int dp(Activity a, int n) { return Math.round(n*a.getResources().getDisplayMetrics().density); }
    static GradientDrawable shape(int color, int stroke) {
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(18);
        if(stroke!=0)d.setStroke(2,stroke);return d;
    }
    static StateListDrawable background() {
        StateListDrawable s=new StateListDrawable();
        s.addState(new int[]{android.R.attr.state_focused},shape(0xff263c5a,WHITE));
        s.addState(new int[]{android.R.attr.state_pressed},shape(0xff304f73,BLUE));
        s.addState(new int[]{},shape(0x66223857,0));return s;
    }
    static TextView text(Activity a,String value,int size,int color) {
        TextView t=new TextView(a);t.setText(value);t.setTextSize(size);t.setTextColor(color);return t;
    }
    static void gap(Activity a,LinearLayout box,int size){View v=new View(a);box.addView(v,new LinearLayout.LayoutParams(1,dp(a,size)));}
    static Button action(Activity a,String label) {
        Button b=new Button(a);b.setText(label);b.setTextSize(14);b.setTextColor(WHITE);b.setAllCaps(false);
        b.setBackground(background());b.setPadding(dp(a,18),dp(a,8),dp(a,18),dp(a,8));return b;
    }
    static Dialog dialog(Activity a,LinearLayout content,boolean full) {
        Dialog d=new Dialog(a);d.requestWindowFeature(Window.FEATURE_NO_TITLE);d.setContentView(content);
        Window w=d.getWindow();if(w!=null){w.setBackgroundDrawableResource(android.R.color.transparent);
            w.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);WindowManager.LayoutParams lp=w.getAttributes();lp.dimAmount=.68f;w.setAttributes(lp);}
        d.setOnShowListener(v->{Window window=d.getWindow();if(window!=null){
            android.util.DisplayMetrics m=a.getResources().getDisplayMetrics();
            window.setLayout((int)(m.widthPixels*(full?.92f:.74f)),(int)(m.heightPixels*(full?.90f:.86f)));
            window.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        }});return d;
    }
    static LinearLayout panel(Activity a) {
        LinearLayout box=new LinearLayout(a);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(a,24),dp(a,18),dp(a,24),dp(a,18));
        GradientDrawable bg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{0xff14243d,0xff090f20});bg.setCornerRadius(dp(a,22));bg.setStroke(dp(a,1),0xff354764);box.setBackground(bg);return box;
    }
    static final class Setting {
        final Activity a;final String label;final String[] values;final TextView current;int index;
        Setting(Activity a,LinearLayout box,String label,String hint,String[] values,int selected) {
            this.a=a;this.label=label;this.values=values;this.index=Math.max(0,Math.min(values.length-1,selected));
            LinearLayout row=new LinearLayout(a);row.setOrientation(LinearLayout.HORIZONTAL);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(a,18),dp(a,12),dp(a,18),dp(a,12));row.setBackground(background());row.setFocusable(true);row.setClickable(true);
            LinearLayout left=new LinearLayout(a);left.setOrientation(LinearLayout.VERTICAL);
            TextView name=text(a,label,17,WHITE);name.setTypeface(null,Typeface.BOLD);left.addView(name);
            if(!hint.isEmpty()){TextView detail=text(a,hint,12,MUTED);detail.setPadding(0,dp(a,4),dp(a,8),0);left.addView(detail);}
            row.addView(left,new LinearLayout.LayoutParams(0,-2,1));
            current=text(a,values[index]+"  ›",17,BLUE);current.setGravity(Gravity.RIGHT|Gravity.CENTER_VERTICAL);row.addView(current);
            row.setContentDescription(label+": "+values[index]);
            LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);rp.setMargins(0,0,0,dp(a,10));row.setMinimumHeight(dp(a,68));box.addView(row,rp);
            row.setOnClickListener(v->{LinearLayout options=panel(a);TextView heading=text(a,label,23,WHITE);options.addView(heading);gap(a,options,12);
                ScrollView scroll=new ScrollView(a);LinearLayout list=new LinearLayout(a);list.setOrientation(LinearLayout.VERTICAL);scroll.addView(list);options.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
                Dialog chooser=dialog(a,options,false);Button selectedButton=null;
                for(int i=0;i<values.length;i++){final int selectedIndex=i;Button b=action(a,values[i]+(i==index?"   ✓":""));LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,dp(a,52));bp.bottomMargin=dp(a,8);list.addView(b,bp);if(i==index)selectedButton=b;b.setOnClickListener(w->{index=selectedIndex;current.setText(values[index]+"  ›");row.setContentDescription(label+": "+values[index]);chooser.dismiss();row.requestFocus();});}
                Button back=action(a,"Back");options.addView(back);back.setOnClickListener(w->chooser.dismiss());chooser.show();if(selectedButton!=null)selectedButton.requestFocus();
            });
        }
    }
    static void show(Activity a,String title,String gameName) {
        SharedPreferences p=a.getSharedPreferences("graphics",0);GraphicsSettings.migrateDeadCellsCap(p,title);
        LinearLayout box=panel(a);
        TextView titleView=text(a,"Graphics",27,WHITE);titleView.setTypeface(null,Typeface.BOLD);box.addView(titleView);
        TextView subtitle=text(a,title.isEmpty()?"Default settings for your games":gameName,13,MUTED);subtitle.setSingleLine(true);subtitle.setEllipsize(android.text.TextUtils.TruncateAt.END);box.addView(subtitle);gap(a,box,14);
        ScrollView scroll=new ScrollView(a);scroll.setFillViewport(false);LinearLayout settings=new LinearLayout(a);settings.setOrientation(LinearLayout.VERTICAL);scroll.addView(settings);box.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        Setting res=new Setting(a,settings,"Render resolution","Lower = faster. Higher = sharper.",RESOLUTIONS,GraphicsSettings.value(p,title,"render_height_v70",0));
        Setting filter=new Setting(a,settings,"Upscaling filter","How the image is stretched to your screen. Sharp keeps edges crisp at lower resolutions.",FILTERS,GraphicsSettings.value(p,title,"present_filter_v111",0));
        boolean dll=GraphicsSettings.lsfgDll(a).isFile();
        Setting fg=new Setting(a,settings,"Frame generation",dll?"Adds frames for smoother motion.":"Requires your Lossless Scaling DLL in Settings.",FRAMES,GraphicsSettings.value(p,title,"fg_v58",0));
        Setting power=new Setting(a,settings,"Power & heat","Automatic adapts. Cooler limits extra frames. Performance keeps your choices until hot.",ThermalController.MODES,GraphicsSettings.value(p,title,"power_mode_v71",0));
        Setting limit=new Setting(a,settings,"FPS limit","Limits output frames.",LIMITS,GraphicsSettings.value(p,title,"cap",0));
        TextView note=text(a,"Changes apply when you restart the game. Render resolution is the height the game\u2019s main passes are drawn at (4K games too); some passes stay native.",12,MUTED);settings.addView(note);gap(a,settings,12);
        Button advanced=action(a,"Advanced options  ›");settings.addView(advanced,new LinearLayout.LayoutParams(-1,dp(a,48)));
        gap(a,box,12);LinearLayout footer=new LinearLayout(a);footer.setGravity(Gravity.RIGHT|Gravity.CENTER_VERTICAL);box.addView(footer);
        Button reset=action(a,title.isEmpty()?"Reset":"Use defaults"),cancel=action(a,"Cancel"),save=action(a,"Save");
        for(Button b:new Button[]{reset,cancel,save}){LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-2,dp(a,48));bp.leftMargin=dp(a,8);footer.addView(b,bp);}
        Dialog d=dialog(a,box,true);advanced.setOnClickListener(v->{d.dismiss();GraphicsSettings.showAdvanced(a,title);});cancel.setOnClickListener(v->d.dismiss());
        reset.setOnClickListener(v->{SharedPreferences.Editor e=p.edit();for(String name:new String[]{"power_mode_v71","render_height_v70","rescale_v64","raster_scale_v54","fg_v58","cap","present_filter_v111"})e.remove(GraphicsSettings.key(title,name));e.apply();d.dismiss();show(a,title,gameName);});
        save.setOnClickListener(v->{if(fg.index>0&&!GraphicsSettings.lsfgDll(a).isFile()){Toast.makeText(a,"Import your Lossless Scaling DLL in Settings, or choose Off.",Toast.LENGTH_LONG).show();return;}
            p.edit().putInt(GraphicsSettings.key(title,"render_height_v70"),res.index).putInt(GraphicsSettings.key(title,"present_filter_v111"),filter.index).putInt(GraphicsSettings.key(title,"fg_v58"),fg.index).putInt(GraphicsSettings.key(title,"cap"),limit.index).putInt(GraphicsSettings.key(title,"power_mode_v71"),power.index)
                .putInt(GraphicsSettings.key(title,"raster_scale_v54"),0).putInt(GraphicsSettings.key(title,"rescale_v64"),1).putInt(GraphicsSettings.key(title,"video_out_v63"),0)
                .putInt(GraphicsSettings.key(title,"fg_flow_v58"),2).putInt(GraphicsSettings.key(title,"fg_perf_v58"),1).apply();d.dismiss();Toast.makeText(a,"Saved · applies on next launch",Toast.LENGTH_SHORT).show();});
        d.show();save.requestFocus();
    }
}
