package com.kaminofilms.novaps5;
import android.graphics.*;
import android.view.*;
import java.text.SimpleDateFormat;
import java.util.*;
final class HomeView extends View {
    final MainActivity app;final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);final ArrayList<Hit> hits=new ArrayList<>();
    int selected=0;float scale=1,ox=0,oy=0,downX,downY;boolean library=false;
    static final class Hit{final RectF rect;final Runnable action;Hit(RectF r,Runnable a){rect=r;action=a;}}
    HomeView(MainActivity a){super(a);app=a;setFocusable(true);setContentDescription("NovaPs5 game library. Development alpha. Commercial PS5 game execution is unavailable.");}
    void text(Canvas c,String value,float x,float y,float size,int color,boolean bold){paint.setColor(color);paint.setTextSize(size);paint.setTypeface(Typeface.create("sans-serif",bold?Typeface.BOLD:Typeface.NORMAL));paint.setStyle(Paint.Style.FILL);paint.setShader(null);c.drawText(value,x,y,paint);}
    void fit(Canvas c,String value,float x,float y,float max,float size,int color,boolean bold){paint.setTextSize(size);paint.setTypeface(Typeface.create("sans-serif",bold?Typeface.BOLD:Typeface.NORMAL));while(value.length()>2&&paint.measureText(value)>max)value=value.substring(0,value.length()-2)+"…";text(c,value,x,y,size,color,bold);}
    void box(Canvas c,RectF r,int color,float radius){paint.setShader(null);paint.setColor(color);paint.setStyle(Paint.Style.FILL);c.drawRoundRect(r,radius,radius,paint);}
    void hit(RectF r,Runnable action){hits.add(new Hit(r,action));}
    void button(Canvas c,String label,float x,float y,float width,boolean primary,Runnable action){RectF r=new RectF(x,y,x+width,y+56);box(c,r,primary?0xfff7f9ff:0x30c9daff,28);text(c,label,x+22,y+36,20,primary?0xff101a32:Color.WHITE,true);hit(r,action);}
    void image(Canvas c,Bitmap bitmap,RectF target){if(bitmap==null||bitmap.isRecycled())return;float ratio=Math.max(target.width()/bitmap.getWidth(),target.height()/bitmap.getHeight());float sw=target.width()/ratio,sh=target.height()/ratio;Rect src=new Rect((int)((bitmap.getWidth()-sw)/2),(int)((bitmap.getHeight()-sh)/2),(int)((bitmap.getWidth()+sw)/2),(int)((bitmap.getHeight()+sh)/2));paint.setColor(Color.WHITE);paint.setShader(null);c.drawBitmap(bitmap,src,target,paint);}
    @Override protected void onDraw(Canvas c){super.onDraw(c);float width=getWidth(),height=getHeight();paint.setShader(new LinearGradient(0,0,width,height,new int[]{0xff090b18,0xff10214b,0xff251638},null,Shader.TileMode.CLAMP));c.drawRect(0,0,width,height,paint);paint.setShader(null);
        float safeL=0,safeR=0,safeT=0,safeB=0;WindowInsets in=getRootWindowInsets();if(in!=null&&in.getDisplayCutout()!=null){DisplayCutout cut=in.getDisplayCutout();safeL=cut.getSafeInsetLeft();safeR=cut.getSafeInsetRight();safeT=cut.getSafeInsetTop();safeB=cut.getSafeInsetBottom();}
        scale=Math.min((width-safeL-safeR)/1280f,(height-safeT-safeB)/720f);ox=safeL+(width-safeL-safeR-1280*scale)/2;oy=safeT+(height-safeT-safeB-720*scale)/2;c.save();c.translate(ox,oy);c.scale(scale,scale);hits.clear();
        ArrayList<GameStore.Entry> games=app.store.snapshot();selected=Math.min(selected,games.size());GameStore.Entry chosen=selected>0?games.get(selected-1):null;
        if(chosen!=null&&chosen.hero!=null){image(c,chosen.hero,new RectF(0,0,1280,720));paint.setShader(new LinearGradient(0,0,1080,0,new int[]{0xeb080d20,0xc0080d20,0x35080d20},null,Shader.TileMode.CLAMP));c.drawRect(0,0,1280,720,paint);paint.setShader(new LinearGradient(0,350,0,720,new int[]{0x00080d20,0xfc080d20},null,Shader.TileMode.CLAMP));c.drawRect(0,0,1280,720,paint);paint.setShader(null);}
        else{paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);for(int i=0;i<6;i++){paint.setColor(0x157599ee);c.drawOval(new RectF(675-i*72,80+i*36,1245+i*92,625+i*20),paint);}paint.setStyle(Paint.Style.FILL);paint.setShader(new RadialGradient(1020,320,270,new int[]{0x555070ca,0x006476ff},null,Shader.TileMode.CLAMP));c.drawCircle(1020,320,270,paint);paint.setShader(null);}
        text(c,"Games",58,59,25,!library?Color.WHITE:0xff8b9ab6,true);hit(new RectF(40,22,150,76),()->{library=false;invalidate();});text(c,"Library",178,59,25,library?Color.WHITE:0xff8b9ab6,false);hit(new RectF(164,22,275,76),()->{library=true;invalidate();});
        text(c,"NovaPs5",882,58,20,0xffced9ee,true);text(c,"⚙",1042,59,28,Color.WHITE,false);hit(new RectF(1025,20,1083,76),()->app.settings());String time=new SimpleDateFormat("h:mm a",Locale.US).format(new Date());text(c,time,1110,58,23,0xffd2daec,false);
        int first=Math.max(0,selected-6),end=Math.min(games.size()+1,first+8);float rowY=104;
        for(int i=first;i<end;i++){float x=60+(i-first)*105;RectF r=new RectF(x,rowY,x+84,rowY+84);if(i==selected){box(c,new RectF(x-6,rowY-6,x+90,rowY+90),0x90eff5ff,22);box(c,new RectF(x-3,rowY-3,x+87,rowY+87),0xff111c34,19);}box(c,r,i==0?0xff173d73:0xff182640,16);
            if(i==0){text(c,"N",x+24,rowY+55,44,Color.WHITE,true);}else{GameStore.Entry e=games.get(i-1);if(e.cover!=null){c.save();Path clip=new Path();clip.addRoundRect(r,16,16,Path.Direction.CW);c.clipPath(clip);image(c,e.cover,r);c.restore();}else text(c,"PS5",x+15,rowY+49,21,0xffa9caff,true);}
            final int index=i;hit(new RectF(x-3,rowY-3,x+87,rowY+87),()->{selected=index;invalidate();});}
        RectF add=new RectF(946,103,1030,187);box(c,add,0x22d0e4ff,16);text(c,"+",970,159,42,Color.WHITE,false);hit(add,()->app.folder());
        text(c,chosen==null?"Core diagnostics":chosen.name,60,229,20,0xffc3cfe1,false);
        if(!library){
            text(c,chosen==null?"YOUR LIBRARY. YOUR DEVICE.":"LOCAL GAME FOLDER",60,297,14,0xff89b6f0,true);
            if(chosen==null){text(c,"A new orbit",60,365,57,Color.WHITE,true);text(c,"for your library.",60,425,57,Color.WHITE,true);text(c,"PS5-inspired navigation. Native Android controls.",62,466,21,0xffc0cee3,false);button(c,"Add game folder",60,497,208,true,()->app.folder());button(c,"Test controls",284,497,184,false,()->app.test());}
            else{fit(c,chosen.name,60,366,680,51,Color.WHITE,true);fit(c,chosen.id+(chosen.version.isEmpty()?"":" · "+chosen.version),62,411,680,19,0xffafc3df,false);text(c,"Imported • game runtime not available yet",62,452,21,0xffc0cee3,false);button(c,"Inspect game",60,482,183,true,()->app.entry(chosen));button(c,"Device diagnostics",259,482,242,false,()->app.diagnostics());}
        }else{
            text(c,"Game library",60,306,40,Color.WHITE,true);text(c,games.isEmpty()?"Add a folder containing your extracted eboot.bin game dumps.":games.size()+" imported game folder(s)",62,344,19,0xffb8c9e0,false);
            int start=Math.max(0,selected-1);for(int i=start;i<Math.min(games.size(),start+4);i++){final GameStore.Entry e=games.get(i);float x=60+(i-start)*235;RectF r=new RectF(x,370,x+216,538);box(c,r,0x60244166,18);if(e.cover!=null){c.save();Path p=new Path();p.addRoundRect(r,18,18,Path.Direction.CW);c.clipPath(p);image(c,e.cover,r);c.restore();}else text(c,"PS5",x+72,466,34,0xffb9d7ff,true);hit(r,()->app.entry(e));fit(c,e.name,x,569,210,17,Color.WHITE,true);}
            if(games.isEmpty())button(c,"Add game folder",60,385,208,true,()->app.folder());
        }
        text(c,"DEVELOPMENT ALPHA  0.1.0",60,618,13,0xff8fafdc,true);fit(c,app.gpu,60,649,760,17,0xffb1c5e2,false);
        text(c,"PS5 game execution is unavailable in this build.",60,680,16,0xffb9c7dc,false);
        button(c,"Diagnostics",854,599,166,false,()->app.diagnostics());button(c,"Firmware",1037,599,148,false,()->app.firmware());
        c.restore();
    }
    void move(int direction){selected=Math.max(0,Math.min(app.store.snapshot().size(),selected+direction));invalidate();}
    void activate(){ArrayList<GameStore.Entry> games=app.store.snapshot();if(selected==0)app.diagnostics();else if(selected<=games.size())app.entry(games.get(selected-1));}
    @Override public boolean onTouchEvent(MotionEvent e){float x=(e.getX()-ox)/scale,y=(e.getY()-oy)/scale;if(e.getAction()==MotionEvent.ACTION_DOWN){downX=x;downY=y;return true;}if(e.getAction()==MotionEvent.ACTION_UP){if(Math.abs(x-downX)>50&&downY<250){move(x<downX?1:-1);return true;}if(Math.abs(x-downX)<24&&Math.abs(y-downY)<24){for(int i=hits.size()-1;i>=0;i--)if(hits.get(i).rect.contains(x,y)){performClick();hits.get(i).action.run();return true;}}return true;}return true;}
    @Override public boolean performClick(){super.performClick();return true;}
}
