package com.kaminofilms.novaps5;

import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import com.droiddeck.launcher.SessionActivity;
import com.droiddeck.launcher.session.SessionState;
import java.io.File;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** The platform supplies display/input; this Activity only accepts a Kyty game launch. */
public final class NovaSessionActivity extends SessionActivity {
    private final ScheduledExecutorService monitor=Executors.newSingleThreadScheduledExecutor();
    private final Handler ui=new Handler(Looper.getMainLooper());
    private volatile String logTail="Waiting for the compatibility session log…";
    private String lastStep="",lastFailure="";
    private TextView boot;

    @Override protected void onCreate(Bundle state){
        Intent intent=getIntent();String game=intent.getStringExtra("nova_game_path");
        // Never inherit an upstream default mode or a saved Steam session.
        intent.putExtra("mode","run");intent.putExtra("program","/opt/novaps5/launch.sh");
        intent.putExtra("programArgs",new String[]{game==null?"":game});
        intent.removeExtra("steamUi");intent.removeExtra("steamUrl");
        boolean valid=game!=null&&game.startsWith("/storage/")&&new File(game,"eboot.bin").canRead();
        boolean active=SessionState.INSTANCE.getRunning();
        boolean sameSession=active&&"run".equals(SessionState.INSTANCE.getMode())&&"/opt/novaps5/launch.sh".equals(SessionState.INSTANCE.getProgram())&&SessionState.INSTANCE.getProgramArgs().equals(java.util.Collections.singletonList(game));
        if(!active)SessionState.INSTANCE.setMode("run");
        super.onCreate(state);
        if(!valid||(active&&!sameSession)){BootLog.write(this,"Rejected game session: "+(active?"another session already active":"invalid game path"));finish();return;}
        boot=new TextView(this);boot.setTextColor(Color.WHITE);boot.setTextSize(13);
        boot.setBackgroundColor(0xcc101a30);boot.setPadding(18,8,18,8);
        boot.setText("Starting Kyty • Boot log");boot.setOnClickListener(v->showLog());
        FrameLayout.LayoutParams layout=new FrameLayout.LayoutParams(-2,-2,Gravity.TOP|Gravity.CENTER_HORIZONTAL);layout.topMargin=12;
        addContentView(boot,layout);
        BootLog.write(this,"Direct route: run /opt/novaps5/launch.sh; game="+game);
        monitor.scheduleWithFixedDelay(this::poll,0,1,TimeUnit.SECONDS);
    }

    private void poll(){
        try{
            File log=SessionState.INSTANCE.getLogFile();if(log==null||!log.isFile())return;
            String text;try(RandomAccessFile in=new RandomAccessFile(log,"r")){
                long size=in.length();byte[] data=new byte[(int)Math.min(size,49152)];in.seek(size-data.length);in.readFully(data);text=new String(data,StandardCharsets.UTF_8);
            }
            logTail=text;String step=null,failure=null;
            for(String line:text.split("\n")){
                if(line.startsWith("== STEP "))step=line.replaceFirst("^== STEP \\S+ ","");
                if(line.startsWith("NOVA_ERROR:")||line.startsWith("NOVA_EXIT:"))failure=line;
            }
            final String next=step,problem=failure;
            ui.post(()->{
                if(isFinishing()||isDestroyed())return;
                if(next!=null&&!next.equals(lastStep)){lastStep=next;boot.setText(next+" • Boot log");BootLog.write(this,"Guest stage: "+next);}
                if(problem!=null&&!problem.equals(lastFailure)){
                    lastFailure=problem;boot.setText(problem+" • Boot log");
                    getSharedPreferences("nova",0).edit().putString("last_session_result",problem).apply();
                    BootLog.write(this,problem);showLog();
                }
            });
        }catch(Exception e){logTail="Cannot read session log: "+e;}
    }

    private void showLog(){
        TextView text=new TextView(this);text.setText(logTail);text.setTextSize(12);text.setTextIsSelectable(true);text.setPadding(20,12,20,12);
        ScrollView scroll=new ScrollView(this);scroll.addView(text,new ViewGroup.LayoutParams(-1,-2));
        new AlertDialog.Builder(this).setTitle("Kyty boot log").setView(scroll).setPositiveButton("Close",null).show();
    }

    @Override protected void onDestroy(){monitor.shutdownNow();ui.removeCallbacksAndMessages(null);super.onDestroy();}
}
