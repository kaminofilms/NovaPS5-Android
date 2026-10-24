package com.kaminofilms.novaps5;

/** Pure policy: output workload only. No guest time, voltage or render-size changes. */
final class ThermalPolicy {
    int level;
    private long coolSince = -1, lastRecovery;
    void pause(){coolSince=-1;}
    int update(long now, int mode, int status, float headroom) {
        boolean known = status >= 0 || !Float.isNaN(headroom);
        boolean hot = status >= 3 || (!Float.isNaN(headroom) && headroom >= 1.0f);
        float warmPoint = mode == 2 ? .95f : .85f;
        boolean warm = status >= 2 || (!Float.isNaN(headroom) && headroom >= warmPoint);
        int floor = mode == 1 ? 1 : 0;
        int wanted = Math.max(floor, hot ? 2 : warm ? 1 : 0);
        if (wanted > level) { level = wanted; coolSince = -1; lastRecovery = now; }
        else if (wanted < level) {
            boolean cool = known && (status < 0 || status <= 1) &&
                (Float.isNaN(headroom) || headroom <= .65f);
            if (!cool) coolSince = -1;
            else {
                if (coolSince < 0) coolSince = now;
                if (now-coolSince >= 60000 && now-lastRecovery >= 30000) {
                    level = Math.max(floor, level-1);lastRecovery=now;
                }
            }
        } else coolSince = -1;
        return level;
    }
}
