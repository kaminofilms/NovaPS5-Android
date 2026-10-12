package com.kaminofilms.novaps5;
import android.view.Surface;
public final class NativeBridge {
    public static final boolean AVAILABLE;
    static { boolean ok;try{System.loadLibrary("novaps5");ok=true;}catch(UnsatisfiedLinkError e){ok=false;}AVAILABLE=ok; }
    public static native String vulkanReport();
    public static native String cpuTest();
    public static native String inspectElf(byte[] data);
    public static native void startRenderer(Surface surface);
    public static native void stopRenderer();
    public static native String rendererStatus();
    public static native String padStatus();
    public static native void setPad(int buttons,float lx,float ly,float rx,float ry,float l2,float r2,int touches,float tx,float ty);
}
