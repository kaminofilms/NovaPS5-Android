#!/usr/bin/env python3
"""Compile and execute production GraphicsSettings with lightweight Android stubs."""
from pathlib import Path
import shutil, subprocess, tempfile

repo=Path(__file__).resolve().parents[1]
package='com/kaminofilms/novaps5'
activity=(repo/'nova-android/src'/package/'GameActivity.java').read_text()
a=activity.index('    static boolean unrealGame(File dir, int depth) {')
b=activity.index('\n    }',a)+6
detector=activity[a:b]
stubs={
'android/R.java':'package android; public class R {public static class layout {public static int simple_spinner_dropdown_item=1;}}',
'android/content/DialogInterface.java':'package android.content; public interface DialogInterface {interface OnClickListener {void onClick(DialogInterface d,int w);}}',
'android/content/SharedPreferences.java':'''package android.content; public interface SharedPreferences {
 int getInt(String k,int d);boolean getBoolean(String k,boolean d);boolean contains(String k);Editor edit();
 interface Editor {Editor putInt(String k,int v);Editor putBoolean(String k,boolean v);Editor remove(String k);void apply();}}
''',
'android/content/Context.java':'''package android.content; import java.io.*;import java.util.*;
 public class Context {private final Map<String,SharedPreferences> prefs=new HashMap<>();
 public SharedPreferences getSharedPreferences(String n,int m){return prefs.computeIfAbsent(n,k->new P());}
 public File getFilesDir(){return new File(System.getProperty("java.io.tmpdir"),"nova-rescale-no-dll");}
 static class P implements SharedPreferences {Map<String,Object> values=new HashMap<>();
 public int getInt(String k,int d){return values.containsKey(k)?(Integer)values.get(k):d;}
 public boolean getBoolean(String k,boolean d){return values.containsKey(k)?(Boolean)values.get(k):d;}
 public boolean contains(String k){return values.containsKey(k);}public Editor edit(){return new E();}
 class E implements Editor {Map<String,Object> changes=new HashMap<>();
 public Editor putInt(String k,int v){changes.put(k,v);return this;}public Editor putBoolean(String k,boolean v){changes.put(k,v);return this;}
 public Editor remove(String k){changes.put(k,null);return this;}public void apply(){for(var e:changes.entrySet()){if(e.getValue()==null)values.remove(e.getKey());else values.put(e.getKey(),e.getValue());}}}}}
''',
'android/app/Dialog.java':'package android.app;public class Dialog {public void show(){}public void dismiss(){}}',
'android/view/Gravity.java':'package android.view;public class Gravity {public static int RIGHT=1;}',
package+'/GraphicsPanel.java':'''package com.kaminofilms.novaps5;import android.app.*;import android.widget.*;final class GraphicsPanel {static void show(Activity a,String t,String n){}static int dp(Activity a,int v){return v;}static LinearLayout panel(Activity a){return new LinearLayout(a);}static TextView text(Activity a,String s,int z,int c){return new TextView(a);}static Dialog dialog(Activity a,LinearLayout p,boolean b){return new Dialog();}static Button action(Activity a,String s){return new Button(a);}}''',
'android/app/Activity.java':'package android.app; public class Activity extends android.content.Context {}',
'android/view/View.java':'package android.view; public class View {public interface OnClickListener{void onClick(View v);}public void setOnClickListener(OnClickListener l){}}',
'android/widget/TextView.java':'package android.widget;public class TextView extends android.view.View {public TextView(android.content.Context c){}public void setText(String s){}}',
'android/widget/Button.java':'package android.widget;public class Button extends TextView {public Button(android.content.Context c){super(c);}}',
'android/widget/Switch.java':'package android.widget;public class Switch extends TextView {boolean v;public Switch(android.content.Context c){super(c);}public void setChecked(boolean b){v=b;}public boolean isChecked(){return v;}}',
'android/widget/LinearLayout.java':'package android.widget;public class LinearLayout extends android.view.View {public static int VERTICAL=1;public LinearLayout(android.content.Context c){}public void setOrientation(int x){}public void setPadding(int a,int b,int c,int d){}public void addView(android.view.View v){}public void addView(android.view.View v,LayoutParams p){}public void setGravity(int v){}public static class LayoutParams {public int leftMargin;public LayoutParams(int w,int h){}public LayoutParams(int w,int h,float f){}}}',
'android/widget/ScrollView.java':'package android.widget;public class ScrollView extends android.view.View {public ScrollView(android.content.Context c){}public void addView(android.view.View v){}}',
'android/widget/Spinner.java':'package android.widget;public class Spinner extends android.view.View {int selected;public Spinner(android.content.Context c){}public void setAdapter(Object a){}public void setSelection(int v){selected=v;}public int getSelectedItemPosition(){return selected;}}',
'android/widget/ArrayAdapter.java':'package android.widget;public class ArrayAdapter<T> {public ArrayAdapter(android.content.Context c,int l,T[] values){}}',
'android/app/AlertDialog.java':'''package android.app;import android.content.*;public class AlertDialog {
 public static class Builder {public Builder(Context c){}public Builder setTitle(String s){return this;}public Builder setView(android.view.View v){return this;}
 public Builder setPositiveButton(String s,DialogInterface.OnClickListener l){return this;}
 public Builder setNeutralButton(String s,DialogInterface.OnClickListener l){return this;}
 public Builder setNegativeButton(String s,DialogInterface.OnClickListener l){return this;}public AlertDialog show(){return new AlertDialog();}}}
''',
'android/system/ErrnoException.java':'package android.system; public class ErrnoException extends Exception {}',
'android/system/Os.java':'''package android.system;import java.util.*;public class Os {static Map<String,String> env=new HashMap<>();
 public static void setenv(String k,String v,boolean o)throws ErrnoException{env.put(k,v);}
 public static void unsetenv(String k)throws ErrnoException{env.remove(k);}public static String getenv(String k){return env.get(k);}}
''',
package+'/BootLog.java':'package com.kaminofilms.novaps5;final class BootLog {static void write(android.content.Context c,String s){}}'
}
harness='''package com.kaminofilms.novaps5;
import java.io.*;import java.nio.file.*;import android.content.*;import android.system.Os;
public class RescaleTest {
 static void eq(Object a,Object b){if(!a.equals(b))throw new AssertionError(a+" != "+b);}
'''+detector+'''
 public static void main(String[] args)throws Exception {
  android.app.Activity c=new android.app.Activity();SharedPreferences p=c.getSharedPreferences("graphics",0);
  p.edit().putInt("PPSA27841:cap",1).putInt("PPSA27841:fg_v58",1).putInt("PPSA27841:tu_debug_v57",1).apply();
  GraphicsSettings.migrateDeadCellsCap(p,"PPSA27841");
  eq(GraphicsSettings.value(p,"PPSA27841","cap",0),3);
  eq(GraphicsSettings.value(p,"PPSA27841","fg_v58",9),0);
  eq(GraphicsSettings.value(p,"PPSA27841","tu_debug_v57",9),0);
  GraphicsSettings.apply(c,"PPSA27841");eq(Os.getenv("NOVA_FPS_CAP"),"60");
  eq(Os.getenv("NOVA_STABLE_DEPTH"),"1");
  eq(Os.getenv("NOVA_PRESENT_MODE"),"mailbox");
  if(Os.getenv("TU_DEBUG")!=null)throw new AssertionError("nolrz must be cleared");

  eq(GraphicsSettings.surfacePermille(p,"PPSA31162",true),1000);
  eq(GraphicsSettings.surfacePermille(p,"PPSA04703",false),1000);
  p.edit().putInt(":render_height_v70",2).apply();
  eq(GraphicsSettings.surfacePermille(p,"PPSA31162",true),666);
  p.edit().putInt("PPSA31162:render_height_v70",1).apply();
  eq(GraphicsSettings.surfacePermille(p,"PPSA31162",true),1000);
  p.edit().putInt("PPSA31162:render_height_v70",99).apply();
  eq(GraphicsSettings.surfacePermille(p,"PPSA31162",true),1000);
  p.edit().putInt("PPSA04703:render_height_v70",3).putInt("PPSA04703:raster_scale_v54",5).apply();
  Os.setenv("NOVA_GAME_UNREAL","0",true);GraphicsSettings.apply(c,"PPSA04703");
  eq(Os.getenv("NOVA_STABLE_DEPTH"),"0");
  eq(Os.getenv("NOVA_RESCALE_PERMILLE"),"1000");eq(Os.getenv("NOVA_RESCALE_TARGET_HEIGHT"),"540");eq(Os.getenv("NOVA_RASTER_SCALE_PCT"),"100");
  p.edit().putInt("PPSA04703:render_height_v70",1).apply();GraphicsSettings.apply(c,"PPSA04703");
  eq(Os.getenv("NOVA_RESCALE_PERMILLE"),"1000");eq(Os.getenv("NOVA_RESCALE_TARGET_HEIGHT"),"1080");
  p.edit().putInt("PPSA27841:sync_v56",1).putInt("PPSA27841:readback_v56",2).apply();
  p.edit().putInt("PPSA27841:cap",1).putInt("PPSA27841:present",1).putInt("PPSA27841:gpu_turbo_v62",1).apply();GraphicsSettings.apply(c,"PPSA27841");
  eq(Os.getenv("NOVA_FPS_CAP"),"30");eq(Os.getenv("NOVA_PRESENT_MODE"),"fifo");
  eq(Os.getenv("NOVA_GPU_TURBO"),"0");eq(Os.getenv("NOVA_VRS"),"2");
  eq(Os.getenv("NOVA_REAL_GPU_TIME"),"1");eq(Os.getenv("NOVA_VIDEO_OUT_4K"),"0");
  eq(Os.getenv("NOVA_RESCALE_PERMILLE"),"1000");
  eq(p.getInt("PPSA27841:sync_v56",0),1);eq(p.getInt("PPSA27841:readback_v56",0),2);
  if(Os.getenv("NOVA_FRAMEGEN")!=null)throw new AssertionError("framegen must be off");
  GraphicsSettings.show(c,"PPSA27841");
  File game=Files.createTempDirectory("nova-unreal-detection").toFile();
  new File(game,"sample.pak").createNewFile();eq(unrealGame(game,0),false);
  File marker=new File(game,"UE4CommandLine.txt");marker.createNewFile();eq(unrealGame(game,0),true);marker.delete();
  File engine=new File(game,"Engine");engine.mkdir();eq(unrealGame(game,0),true);engine.delete();
  File content=new File(game,"Project/Content/Paks");content.mkdirs();new File(content,"data.pak").createNewFile();eq(unrealGame(game,0),true);
 }
}
'''
with tempfile.TemporaryDirectory() as tmp:
    t=Path(tmp)
    for name,text in stubs.items():
        p=t/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    shutil.copyfile(repo/'nova-android/src'/package/'GraphicsSettings.java',t/package/'GraphicsSettings.java')
    (t/package/'RescaleTest.java').write_text(harness)
    compiler=[shutil.which('javac')] if shutil.which('javac') else ['java','com.sun.tools.javac.Main']
    subprocess.run([*compiler,'-d',str(t/'classes'),*map(str,t.rglob('*.java'))],check=True)
    subprocess.run(['java','-cp',str(t/'classes'),'com.kaminofilms.novaps5.RescaleTest'],check=True)
print('Nova rescale settings: production Java compilation, inheritance, current v70 inheritance, legacy turbo rejection, explicit caps and Unreal detection passed')

