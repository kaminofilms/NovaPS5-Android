package com.kaminofilms.novaps5;

import android.content.Context;
import android.util.Log;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Captures engine setup before the upstream session logger has been created. */
final class BootLog {
    private static String lastStage="";private static int lastBucket=-2;
    private static File file(Context context){return new File(context.getFilesDir(),"logs/nova-engine.log");}
    static synchronized void write(Context context,String message){
        try{File f=file(context);f.getParentFile().mkdirs();if(f.length()>1048576){File previous=new File(f.getParentFile(),"nova-engine.previous.log");previous.delete();f.renameTo(previous);}
            try(Writer out=new OutputStreamWriter(new FileOutputStream(f,true),StandardCharsets.UTF_8)){
                out.write(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS",Locale.US).format(new Date())+" "+message+"\n");
            }
        }catch(Exception ignored){Log.e("NovaPs5","Could not write engine log");}
    }
    static String failure(Context context,String stage,Throwable error){
        StringWriter trace=new StringWriter();error.printStackTrace(new PrintWriter(trace));write(context,"FAILED: "+stage+"\n"+trace);
        String message=stage+"\n"+error.getClass().getSimpleName()+": "+String.valueOf(error.getMessage());
        context.getSharedPreferences("nova",0).edit().putString("last_engine_error",message).apply();
        Log.e("NovaPs5",stage,error);return message+"\n\nThe error was saved. Diagnostics → Export includes the engine log.";
    }
    static synchronized void progress(Context context,String stage,int percent){int bucket=percent<0?-1:percent/10;if(!stage.equals(lastStage)||bucket!=lastBucket){write(context,"STAGE: "+stage+(percent>=0?" "+percent+"%":""));lastStage=stage;lastBucket=bucket;}}
    static String read(Context context){
        try(RandomAccessFile in=new RandomAccessFile(file(context),"r")){long size=in.length();byte[] bytes=new byte[(int)Math.min(size,131072)];in.seek(size-bytes.length);in.readFully(bytes);return new String(bytes,StandardCharsets.UTF_8);}
        catch(Exception ignored){return "No engine preparation log yet.";}
    }
    static void rethrowFatal(Throwable error){if(error instanceof ThreadDeath)throw (ThreadDeath)error;if(error instanceof VirtualMachineError)throw (VirtualMachineError)error;}
    static void install(Context context){
        final Context app=context.getApplicationContext();final Thread.UncaughtExceptionHandler previous=Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread,error)->{try{failure(app,"Uncaught exception on "+thread.getName(),error);}catch(Throwable ignored){}finally{if(previous!=null)previous.uncaughtException(thread,error);else android.os.Process.killProcess(android.os.Process.myPid());}});
    }
}
