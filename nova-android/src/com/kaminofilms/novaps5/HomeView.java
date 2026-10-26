package com.kaminofilms.novaps5;

import android.animation.ValueAnimator;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.view.*;
import android.view.animation.DecelerateInterpolator;
import java.text.SimpleDateFormat;
import java.util.*;

/** Landscape welcome hub. Artwork and capabilities come from the local library. */
final class HomeView extends View {
 final MainActivity app;
 final Paint p=new Paint(3);
 final ArrayList<Hit> hits=new ArrayList<>();
 final android.content.SharedPreferences prefs;
 int selected=0,focus=0,page=0,libraryPage=0,slide=0;
 boolean library=false,showcase=false,attached=false;
 float scale=1,ox,oy,downX,downY,blend=1,menuBlend=1;
 String menu="";
 Bitmap oldArt,wallpaper;
 ValueAnimator artAnim,menuAnim;
 long wallpaperGeneration;
 static final int WHITE=0xfff6f7fc,MUTED=0xffc2c9dc;
 static final class Hit {RectF r;Runnable action;Hit(RectF r,Runnable a){this.r=r;action=a;}}
 final Runnable tick=new Runnable(){public void run(){
  if(!attached)return;
  if(prefs.getInt("background",0)==2&&menu.isEmpty()) {oldArt=art();slide++;fade();}
  invalidate();schedule();
 }};
 HomeView(MainActivity a){super(a);app=a;prefs=a.getSharedPreferences("welcome_hub",0);setFocusable(true);setContentDescription("NovaPS5 Welcome Hub");loadWallpaper();}
 ArrayList<GameStore.Entry> games(){return app.store.snapshot();}
 GameStore.Entry chosen(){ArrayList<GameStore.Entry> g=games();selected=Math.max(0,Math.min(selected,g.size()));return selected==0?null:g.get(selected-1);}
 Bitmap art(){
  if(prefs.getInt("background",0)==3&&wallpaper!=null)return wallpaper;
  ArrayList<GameStore.Entry> g=games();
  if(prefs.getInt("background",0)==2&&!g.isEmpty()){
   for(int n=0;n<g.size();n++){Bitmap b=g.get(Math.floorMod(slide+n,g.size())).hero;if(b!=null&&!b.isRecycled())return b;}
  }
  if(prefs.getInt("background",0)==1){int i=prefs.getInt("art_index",0);if(i<g.size()&&i>=0)return g.get(i).hero;}
  GameStore.Entry e=chosen();return e==null?null:e.hero;
 }
 void loadWallpaper(){
  final long generation=++wallpaperGeneration;String uri=prefs.getString("wallpaper","");
  if(uri.isEmpty())return;
  app.io.execute(()->{Bitmap result=null;
   try{BitmapFactory.Options o=new BitmapFactory.Options();o.inJustDecodeBounds=true;
    try(java.io.InputStream in=app.getContentResolver().openInputStream(Uri.parse(uri))){BitmapFactory.decodeStream(in,null,o);}
    o.inSampleSize=1;while(o.outWidth/o.inSampleSize>2560||o.outHeight/o.inSampleSize>1440)o.inSampleSize*=2;
    o.inJustDecodeBounds=false;o.inPreferredConfig=Bitmap.Config.RGB_565;
    try(java.io.InputStream in=app.getContentResolver().openInputStream(Uri.parse(uri))){result=BitmapFactory.decodeStream(in,null,o);}
   }catch(Exception ignored){}
   final Bitmap b=result;app.ui(()->{if(generation==wallpaperGeneration){wallpaper=b;invalidate();}});
  });
 }
 void schedule(){removeCallbacks(tick);if(attached&&getWindowVisibility()==VISIBLE)postDelayed(tick,prefs.getInt("duration",30)*1000L);}
 @Override protected void onAttachedToWindow(){super.onAttachedToWindow();attached=true;schedule();}
 @Override protected void onDetachedFromWindow(){attached=false;removeCallbacks(tick);if(artAnim!=null)artAnim.cancel();if(menuAnim!=null)menuAnim.cancel();oldArt=null;super.onDetachedFromWindow();}
 @Override protected void onWindowVisibilityChanged(int visibility){super.onWindowVisibilityChanged(visibility);if(prefs!=null)schedule();}
 void fade(){blend=0;if(artAnim!=null)artAnim.cancel();if(!ValueAnimator.areAnimatorsEnabled()){blend=1;oldArt=null;invalidate();return;}
  artAnim=ValueAnimator.ofFloat(0,1);artAnim.setDuration(260);artAnim.setInterpolator(new DecelerateInterpolator());artAnim.addUpdateListener(a->{blend=(float)a.getAnimatedValue();if(blend==1)oldArt=null;invalidate();});artAnim.start();}
 void select(int i){int next=Math.max(0,Math.min(games().size(),i));if(next==selected)return;oldArt=art();selected=next;focus=0;fade();announceForAccessibility(chosen()==null?"Welcome Hub":chosen().name);}
 void open(String name){menu=name;focus=0;menuBlend=0;if(menuAnim!=null)menuAnim.cancel();if(!ValueAnimator.areAnimatorsEnabled()){menuBlend=1;invalidate();return;}
  menuAnim=ValueAnimator.ofFloat(0,1);menuAnim.setDuration(220);menuAnim.setInterpolator(new DecelerateInterpolator());menuAnim.addUpdateListener(a->{menuBlend=(float)a.getAnimatedValue();invalidate();});menuAnim.start();}
 boolean back(){if(!menu.isEmpty()){menu="";focus=0;invalidate();return true;}if(showcase){showcase=false;invalidate();return true;}if(library){library=false;focus=0;invalidate();return true;}return false;}
 void text(Canvas c,String s,float x,float y,float size,int color,boolean bold){p.setShader(null);p.setStyle(Paint.Style.FILL);p.setColor(color);p.setTextSize(size);p.setTypeface(Typeface.create("sans-serif",bold?1:0));c.drawText(s,x,y,p);}
 void fit(Canvas c,String s,float x,float y,float width,float size,int color){p.setTextSize(size);p.setTypeface(Typeface.create("sans-serif",0));while(s.length()>2&&p.measureText(s)>width)s=s.substring(0,s.length()-2)+"…";text(c,s,x,y,size,color,false);}
 void box(Canvas c,RectF r,int color,float radius){p.setShader(null);p.setStyle(Paint.Style.FILL);p.setColor(color);c.drawRoundRect(r,radius,radius,p);}
 void image(Canvas c,Bitmap b,RectF r){if(b==null||b.isRecycled())return;float factor=Math.max(r.width()/b.getWidth(),r.height()/b.getHeight());float w=r.width()/factor,h=r.height()/factor;Rect src=new Rect((int)((b.getWidth()-w)/2),(int)((b.getHeight()-h)/2),(int)((b.getWidth()+w)/2),(int)((b.getHeight()+h)/2));p.setColor(WHITE);p.setShader(null);c.drawBitmap(b,src,r,p);}
 void hit(RectF r,Runnable action){hits.add(new Hit(r,action));}
 void outline(Canvas c,RectF r){p.setShader(null);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(2);p.setColor(WHITE);c.drawRoundRect(r,14,14,p);p.setStyle(Paint.Style.FILL);}
 void button(Canvas c,String label,float x,float y,float w,Runnable a){RectF r=new RectF(x,y,x+w,y+48);box(c,r,0xd9f5f6fc,24);fit(c,label,x+20,y+31,w-35,18,0xff111826);hit(r,a);}
 void card(Canvas c,String title,String value,String detail,float x,float y,float w,Runnable action){RectF r=new RectF(x,y,x+w,y+155);box(c,r,0xc4141e35,16);text(c,title,x+22,y+32,16,MUTED,false);fit(c,value,x+22,y+82,w-44,29,WHITE);fit(c,detail,x+22,y+122,w-44,15,MUTED);hit(r,action);}
 @Override protected void onDraw(Canvas c){super.onDraw(c);float w=getWidth(),h=getHeight();Bitmap b=art();p.setShader(new LinearGradient(0,0,w,h,new int[]{0xff0c142a,0xff213659,0xff11182e},null,Shader.TileMode.CLAMP));c.drawRect(0,0,w,h,p);p.setShader(null);RectF full=new RectF(0,0,w,h);
  if(oldArt!=null&&blend<1){int oldLayer=c.saveLayerAlpha(full,b==null?(int)(255*(1-blend)):255);image(c,oldArt,full);c.restoreToCount(oldLayer);}if(b!=null){int save=c.saveLayerAlpha(full,(int)(255*blend));image(c,b,full);c.restoreToCount(save);}
  p.setShader(new LinearGradient(0,0,0,h,new int[]{0x70070d1b,0x10070d1b,0xe6070d1b},new float[]{0,.45f,1},Shader.TileMode.CLAMP));c.drawRect(0,0,w,h,p);p.setShader(null);
  int left=0,right=0,top=0,bottom=0;WindowInsets in=getRootWindowInsets();if(in!=null&&in.getDisplayCutout()!=null){DisplayCutout d=in.getDisplayCutout();left=d.getSafeInsetLeft();right=d.getSafeInsetRight();top=d.getSafeInsetTop();bottom=d.getSafeInsetBottom();}
  scale=Math.min((w-left-right)/1280f,(h-top-bottom)/720f);ox=left+(w-left-right-1280*scale)/2;oy=top+(h-top-bottom-720*scale)/2;c.save();c.translate(ox,oy);c.scale(scale,scale);hits.clear();
  if(showcase){hit(new RectF(0,0,1280,720),()->{showcase=false;invalidate();});c.restore();return;}
  GameStore.Entry e=chosen();ArrayList<GameStore.Entry> g=games();
  text(c,"Games",54,53,24,library?MUTED:WHITE,true);hit(new RectF(35,18,155,73),()->{library=false;focus=0;invalidate();});text(c,"Library",177,53,24,library?WHITE:MUTED,false);hit(new RectF(161,18,290,73),()->{library=true;focus=0;invalidate();});
  text(c,"Search",864,50,17,WHITE,false);hit(new RectF(846,18,941,73),()->open("Search"));text(c,"Settings",960,50,17,WHITE,false);hit(new RectF(948,18,1053,73),()->open("Settings"));text(c,new SimpleDateFormat("HH:mm",Locale.getDefault()).format(new Date()),1120,52,23,WHITE,false);
  int first=Math.max(0,selected-7),end=Math.min(g.size()+1,first+10);
  for(int i=first;i<end;i++){float x=56+(i-first)*98;boolean active=i==selected;RectF r=new RectF(x,92,x+80,172);box(c,r,0xd01b2944,13);if(i==0)text(c,"N",x+24,145,37,WHITE,true);else if(g.get(i-1).cover!=null){c.save();Path path=new Path();path.addRoundRect(r,13,13,Path.Direction.CW);c.clipPath(path);image(c,g.get(i-1).cover,r);c.restore();}else text(c,"PS5",x+14,141,19,WHITE,true);if(active)outline(c,new RectF(x-5,87,x+85,177));final int index=i;hit(r,()->select(index));}
  button(c,"+ Import",1090,105,140,()->app.addGame());
  if(library){
   text(c,"Your collection",56,239,32,WHITE,false);text(c,g.size()+" games",1050,238,19,MUTED,false);int start=libraryPage*10;
   for(int i=start;i<Math.min(g.size(),start+10);i++){final GameStore.Entry game=g.get(i);int k=i-start;float x=56+(k%5)*238,y=268+(k/5)*180;RectF r=new RectF(x,y,x+218,y+135);box(c,r,0xc21a2944,12);image(c,game.cover,r);fit(c,game.name,x,y+161,216,17,WHITE);hit(r,()->app.entry(game));}
   if(g.isEmpty())text(c,"Import a game folder to begin.",56,320,22,MUTED,false);
   if(libraryPage>0)button(c,"Previous",56,652,150,()->{libraryPage--;invalidate();});if(start+10<g.size())button(c,"Next",1060,652,150,()->{libraryPage++;invalidate();});
  }else if(e!=null){
   fit(c,e.name,56,395,900,48,WHITE);fit(c,e.id+(e.version.isEmpty()?"":" · "+e.version),58,437,700,18,MUTED);
   button(c,"Play game",56,490,190,()->app.launchGame(e));button(c,"Graphics",262,490,174,()->app.graphics(e));button(c,"Game options",452,490,210,()->app.entry(e));
   text(c,"NovaPS5",58,645,20,WHITE,true);fit(c,app.gpu,58,676,850,15,MUTED);
  }else{
   text(c,"Welcome Hub",56,248,34,WHITE,false);text(c,"Your games. Your space.",58,283,19,MUTED,false);
   button(c,"Change background",742,219,244,()->open("Background"));button(c,"Customize",1002,219,218,()->open("Customize"));
   boolean large=prefs.getBoolean("large",false);float cw=large?566:368;float y=prefs.getBoolean("upper",false)?314:455;
   card(c,"Your collection",Integer.toString(g.size()),"Installed games",56,y,cw,()->{library=true;invalidate();});
   card(c,"Controller",controller(),"Touch controls available",large?650:452,y,cw,()->open("Settings"));
   if(!large)card(c,"Session", "Logs & diagnostics","View the latest game session",848,y,368,()->app.diagnostics());
   text(c,"NOVA PS5",58,657,16,WHITE,true);fit(c,app.gpu,58,685,1010,15,MUTED);text(c,"Native Android",1070,685,14,MUTED,false);
  }
  if(!menu.isEmpty())drawMenu(c,g);
  if(!hits.isEmpty()&&focus>0)outline(c,hits.get(Math.min(focus-1,hits.size()-1)).r);
  c.restore();
 }
 String controller(){for(int id:InputDevice.getDeviceIds()){InputDevice d=InputDevice.getDevice(id);if(d!=null&&(d.getSources()&InputDevice.SOURCE_GAMEPAD)==InputDevice.SOURCE_GAMEPAD)return d.getName();}return "Touch controls";}
 void row(Canvas c,String label,String value,int i,Runnable a){float y=200+i*62;RectF r=new RectF(708,y,1218,y+54);box(c,r,0x263f5378,10);fit(c,label,726,y+33,value.isEmpty()?460:320,18,WHITE);if(!value.isEmpty())fit(c,value,1060,y+33,142,16,MUTED);hit(r,a);}
 void mode(int n){oldArt=art();prefs.edit().putInt("background",n).apply();slide=0;fade();schedule();}
 void drawMenu(Canvas c,ArrayList<GameStore.Entry> g){
  hits.clear();box(c,new RectF(0,0,1280,720),(int)(130*menuBlend)<<24,0);hit(new RectF(0,0,672,720),()->back());c.save();c.translate(60*(1-menuBlend),0);box(c,new RectF(672,82,1250,705),0xf2121c30,22);text(c,menu,708,145,29,WHITE,false);text(c,"×",1190,145,30,WHITE,false);hit(new RectF(1162,105,1232,160),()->back());
  if(menu.equals("Background")){
   row(c,"Follow selected game",prefs.getInt("background",0)==0?"Selected":"",0,()->mode(0));row(c,"Game artwork","Choose",1,()->open("Game artwork"));row(c,"Slideshow",prefs.getInt("background",0)==2?"On":"Off",2,()->mode(prefs.getInt("background",0)==2?0:2));row(c,"Slideshow duration",prefs.getInt("duration",30)+" seconds",3,()->open("Duration"));row(c,"Your photo","Import",4,()->{Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE);app.startActivityForResult(intent,16);});row(c,"Saved photo",wallpaper==null?"Not imported":"Use",5,()->{if(wallpaper!=null)mode(3);});row(c,"Showcase mode","Full screen",6,()->{showcase=true;menu="";invalidate();});
  }else if(menu.equals("Duration")){int[] durations={15,30,60,300};for(int i=0;i<durations.length;i++){final int d=durations[i];row(c,d<60?d+" seconds":(d/60)+" minute(s)",prefs.getInt("duration",30)==d?"Selected":"",i,()->{prefs.edit().putInt("duration",d).apply();schedule();open("Background");});}
  }else if(menu.equals("Customize")){
   row(c,"Large layout",prefs.getBoolean("large",false)?"On":"Off",0,()->toggle("large"));row(c,"Widgets position",prefs.getBoolean("upper",false)?"Upper":"Lower",1,()->toggle("upper"));row(c,"Change background","",2,()->open("Background"));row(c,"Showcase mode","",3,()->{showcase=true;menu="";invalidate();});row(c,"Restore hub layout","",4,()->{prefs.edit().putBoolean("large",false).putBoolean("upper",false).apply();invalidate();});
  }else if(menu.equals("Settings")){
   row(c,"App settings","",0,()->app.settings());row(c,"Graphics & GPU driver","",1,()->app.gpuDriver());row(c,"Welcome Hub settings","",2,()->open("Customize"));row(c,"Library & imports","",3,()->{library=true;menu="";invalidate();});row(c,"Session diagnostics","",4,()->app.diagnostics());row(c,"Change background","",5,()->open("Background"));
  }else if(menu.equals("Search")){
   row(c,"Search your collection","Open search",0,()->{final android.widget.EditText input=new android.widget.EditText(app);input.setSingleLine(true);new android.app.AlertDialog.Builder(app).setTitle("Search games").setView(input).setPositiveButton("Search",(dialog,which)->{String query=input.getText().toString().toLowerCase(Locale.ROOT);for(int n=0;n<g.size();n++)if(g.get(n).name.toLowerCase(Locale.ROOT).contains(query)){select(n+1);menu="";library=false;invalidate();return;}android.widget.Toast.makeText(app,"No matching game",0).show();}).setNegativeButton("Cancel",null).show();});
  }else if(menu.equals("Game artwork")){
   int start=page*7;for(int i=start;i<Math.min(g.size(),start+7);i++){final int index=i;row(c,g.get(i).name,"",i-start,()->{prefs.edit().putInt("art_index",index).apply();mode(1);open("Background");});}
   if(g.isEmpty())text(c,"Import games to add artwork.",710,240,19,MUTED,false);
   if(page>0)button(c,"Previous",710,645,150,()->{page--;invalidate();});if(start+7<g.size())button(c,"Next",1040,645,150,()->{page++;invalidate();});
  }
  c.restore();
 }
 void toggle(String key){prefs.edit().putBoolean(key,!prefs.getBoolean(key,false)).apply();invalidate();}
 void move(int d){if(!menu.isEmpty()||focus>0){focus=Math.max(1,Math.min(hits.size(),focus+d));invalidate();}else select(selected+d);}
 void vertical(int d){focus=Math.max(1,Math.min(hits.size(),focus+d));invalidate();}
 void activate(){if(focus>0&&focus<=hits.size()){hits.get(focus-1).action.run();return;}GameStore.Entry e=chosen();if(e!=null)app.entry(e);else{focus=1;invalidate();}}
 void tab(){library=!library;menu="";focus=0;invalidate();}
 @Override public boolean onTouchEvent(MotionEvent e){float x=(e.getX()-ox)/scale,y=(e.getY()-oy)/scale;if(e.getActionMasked()==MotionEvent.ACTION_DOWN){downX=x;downY=y;return true;}if(e.getActionMasked()==MotionEvent.ACTION_UP){focus=0;if(Math.abs(x-downX)>60&&downY<190&&menu.isEmpty()){move(x<downX?1:-1);return true;}if(Math.abs(x-downX)<28&&Math.abs(y-downY)<28){for(int i=hits.size()-1;i>=0;i--)if(hits.get(i).r.contains(x,y)){performClick();hits.get(i).action.run();invalidate();break;}}return true;}return true;}
 @Override public boolean performClick(){super.performClick();return true;}
}
