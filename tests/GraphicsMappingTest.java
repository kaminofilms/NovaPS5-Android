package com.kaminofilms.novaps5;
import android.content.SharedPreferences;
import java.lang.reflect.Proxy;
import java.util.*;
public class GraphicsMappingTest {
 public static void main(String[] args) {
  Map<String,Integer> data=new HashMap<>();
  SharedPreferences prefs=(SharedPreferences)Proxy.newProxyInstance(SharedPreferences.class.getClassLoader(),new Class[]{SharedPreferences.class},(p,m,a)->{
   if(m.getName().equals("getInt"))return data.getOrDefault((String)a[0],(Integer)a[1]);
   if(m.getName().equals("contains"))return data.containsKey((String)a[0]);
   throw new UnsupportedOperationException(m.getName());
  });
  if(GraphicsSettings.surfacePermille(prefs,"GAME",true)!=1000)throw new AssertionError("engine default must be native");
  int[] want={1000,1000,666,500,333};
  for(int i=0;i<want.length;i++){data.put(":render_height_v70",i);if(GraphicsSettings.surfacePermille(prefs,"GAME",true)!=want[i])throw new AssertionError("global mapping "+i);}
  data.put("GAME:render_height_v70",2);if(GraphicsSettings.surfacePermille(prefs,"GAME",false)!=666)throw new AssertionError("per-game override");
  data.put("GAME:render_height_v70",999);if(GraphicsSettings.surfacePermille(prefs,"GAME",false)!=1000)throw new AssertionError("invalid value");
  if(!Arrays.equals(GraphicsPanel.FRAMES,new String[]{"Off","2x","3x","4x"}))throw new AssertionError("frame multipliers");
  System.out.println("PASS resolution inheritance, per-game overrides, native engine default, invalid settings, frame multipliers");
 }
}
