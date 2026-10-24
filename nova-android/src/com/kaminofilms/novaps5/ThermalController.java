package com.kaminofilms.novaps5;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;

/** App-level output control. Android retains all clock/voltage/thermal authority. */
final class ThermalController {
    static final String[] MODES = {"Automatic", "Cooler", "Performance"};
    private static final Handler handler = new Handler(Looper.getMainLooper());
    private static Context context;
    private static String title="";
    private static boolean paused;
    private static long lastHeadroom = -1;
    private static int status = -1, mode, lastLevel = -1;
    private static volatile float headroom = Float.NaN;
    private static ThermalPolicy policy = new ThermalPolicy();
    private static final Runnable poll = () -> tick();
    static void start(Context c,String id) {
        stop();context=c.getApplicationContext();title=id;paused=false;policy=new ThermalPolicy();lastLevel=-1;
        // Headroom's process-wide polling guard survives pause/resume and restarts.
        handler.post(poll);
    }
    static void stop() { handler.removeCallbacks(poll);context=null; }
    static void background(boolean value) {
        paused=value;if(value)policy.pause();NovaPad.workload(Math.max(0,lastLevel),paused);
        if(!value&&context!=null){handler.removeCallbacks(poll);handler.post(poll);}
    }
    private static void tick() {
        if(context==null)return;
        long now=SystemClock.elapsedRealtime();
        if(!paused) {
            PowerManager pm=(PowerManager)context.getSystemService(Context.POWER_SERVICE);
            try { status=pm==null?-1:pm.getCurrentThermalStatus(); } catch(RuntimeException e){status=-1;}
            if(lastHeadroom<0||now-lastHeadroom>=10000){
                lastHeadroom=now;
                try { headroom=pm==null?Float.NaN:pm.getThermalHeadroom(10); } catch(RuntimeException e){headroom=Float.NaN;}
                if(!Float.isFinite(headroom)||headroom<0)headroom=Float.NaN;
            }
            mode=GraphicsSettings.value(context.getSharedPreferences("graphics",0),title,"power_mode_v71",0);
            mode=Math.max(0,Math.min(2,mode));
            int level=policy.update(now,mode,status,headroom);
            NovaPad.workload(level,false);
            if(level!=lastLevel){
                BootLog.write(context,"NOVA_POWER: mode="+MODES[mode]+" level="+level+
                    " output_cap="+(level>=2?"30":level==1?"60":"user")+
                    " framegen="+(level==0?"user":"temporarily off")+
                    " thermal="+status+" headroom="+headroom+"; Android manages clocks");
                lastLevel=level;
            }
        }
        handler.postDelayed(poll,10000);
    }
    static float headroom() { return headroom; }
}
