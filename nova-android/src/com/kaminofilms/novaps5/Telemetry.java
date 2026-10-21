package com.kaminofilms.novaps5;

import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.PowerManager;
import android.os.SystemClock;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.util.Locale;

/**
 * 0.9.56: heat and clock readout every 5 s in the engine log, so a log shows whether
 * FPS falls because the phone slows itself down (thermal throttling) or because the
 * emulator does more work. Values Android does not let apps read are logged as "n/a".
 */
final class Telemetry {
    private static final String[] STATUS = {"none", "light", "moderate", "severe", "critical", "emergency", "shutdown"};
    private static HandlerThread thread;

    static synchronized void start(Context context) {
        if (thread != null) return;
        final Context app = context.getApplicationContext();
        thread = new HandlerThread("NovaTelemetry");
        thread.start();
        final Handler handler = new Handler(thread.getLooper());
        handler.post(new Runnable() {
            long lastFrames = -1, lastTime;
            public void run() {
                try {
                    long now = SystemClock.uptimeMillis(), frames = NovaPad.frames();
                    String fps = "n/a";
                    if (lastFrames >= 0 && now > lastTime)
                        fps = String.format(Locale.US, "%.1f", (frames - lastFrames) * 1000f / (now - lastTime));
                    lastFrames = frames; lastTime = now;
                    BootLog.write(app, line(app, fps));
                } catch (Throwable ignored) {
                }
                handler.postDelayed(this, 5000);
            }
        });
    }

    static String line(Context c, String fps) {
        PowerManager pm = (PowerManager) c.getSystemService(Context.POWER_SERVICE);
        int status = pm == null ? -1 : pm.getCurrentThermalStatus();
        float headroom = pm == null ? Float.NaN : pm.getThermalHeadroom(10);
        Intent battery = c.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        int tenths = battery == null ? Integer.MIN_VALUE : battery.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Integer.MIN_VALUE);
        return String.format(Locale.US,
                "NOVA_THERMAL: fps=%s thermal=%s headroom=%s battery_c=%s gpu_mhz=%s gpu_busy=%s cpu_mhz=%s",
                fps, status >= 0 && status < STATUS.length ? STATUS[status] : "n/a",
                Float.isNaN(headroom) ? "n/a" : String.format(Locale.US, "%.2f", headroom),
                tenths == Integer.MIN_VALUE ? "n/a" : String.format(Locale.US, "%.1f", tenths / 10f),
                gpuMhz(), gpuBusy(), cpuMhz());
    }

    static String read(String path) {
        try (BufferedReader in = new BufferedReader(new FileReader(path))) {
            String s = in.readLine();
            return s == null ? null : s.trim();
        } catch (Exception e) {
            return null;
        }
    }

    static String gpuMhz() {
        String hz = read("/sys/class/kgsl/kgsl-3d0/gpuclk");
        if (hz != null) try { return Long.toString(Long.parseLong(hz) / 1000000L); } catch (NumberFormatException ignored) {}
        String mhz = read("/sys/class/kgsl/kgsl-3d0/clock_mhz");
        return mhz != null ? mhz : "n/a";
    }

    static String gpuBusy() {
        String busy = read("/sys/class/kgsl/kgsl-3d0/gpu_busy_percentage");
        return busy != null ? busy.replace(" ", "") : "n/a";
    }

    /** Current frequency of each CPU cluster's first core, e.g. "2054/3532/4320". */
    static String cpuMhz() {
        StringBuilder out = new StringBuilder();
        String lastRelated = null;
        for (int cpu = 0; cpu < 16; cpu++) {
            String base = "/sys/devices/system/cpu/cpu" + cpu + "/cpufreq/";
            if (!new File(base).isDirectory()) continue;
            String related = read(base + "related_cpus");
            if (related != null && related.equals(lastRelated)) continue;
            lastRelated = related;
            String khz = read(base + "scaling_cur_freq");
            if (khz == null) continue;
            try {
                if (out.length() > 0) out.append('/');
                out.append(Long.parseLong(khz) / 1000L);
            } catch (NumberFormatException ignored) {}
        }
        return out.length() == 0 ? "n/a" : out.toString();
    }
}
