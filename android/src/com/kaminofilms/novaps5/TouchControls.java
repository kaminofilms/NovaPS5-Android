package com.kaminofilms.novaps5;
import android.graphics.*;
import android.view.*;
import java.util.*;
final class TouchControls extends View {
    final MainActivity app;final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);final HashMap<Integer,PointF> points=new HashMap<>();
    float sx=1,sy=1,lx,ly,rx,ry,l2,r2,tx,ty;int buttons,touches;long update=0;String status="Starting native Vulkan…",pad="";int leftPointer=-1,rightPointer=-1,touchPointer=-1;
    TouchControls(MainActivity a){super(a);app=a;setFocusable(true);setContentDescription("PS5 layout touch controls and native Vulkan diagnostic test");}
    void text(Canvas c,String value,float x,float y,float size,int color){paint.setShader(null);paint.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));paint.setStyle(Paint.Style.FILL);paint.setTextSize(size);paint.setColor(color);c.drawText(value,x,y,paint);}
    void round(Canvas c,RectF r,int color){paint.setColor(color);paint.setShader(null);paint.setStyle(Paint.Style.FILL);c.drawRoundRect(r,18,18,paint);}
    void circle(Canvas c,float x,float y,float r,int bit,String label){boolean pressed=((buttons|app.hardwareButtons)&bit)!=0;paint.setColor(pressed?0x779fcaff:0x33222d49);paint.setStyle(Paint.Style.FILL);c.drawCircle(x,y,r,paint);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);paint.setColor(pressed?0xffb1d9ff:0xaac4d9ee);c.drawCircle(x,y,r,paint);paint.setStyle(Paint.Style.FILL);text(c,label,x-label.length()*9,y+10,27,0xffe2ecf9);}
    void shoulder(Canvas c,RectF r,String label,int bit){round(c,r,((buttons|app.hardwareButtons)&bit)!=0?0x6697c5ff:0x33222d49);paint.setTextSize(24);paint.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));text(c,label,r.centerX()-paint.measureText(label)/2,r.centerY()+9,24,0xffe2ecf9);}
    void stick(Canvas c,float x,float y,float ax,float ay,String label){paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(4);paint.setColor(0x65618fcc);c.drawCircle(x,y,70,paint);paint.setStrokeWidth(2);paint.setColor(0x7794b9df);c.drawCircle(x,y,59,paint);paint.setStyle(Paint.Style.FILL);paint.setColor(0x556f92c2);c.drawCircle(x+ax*47,y+ay*47,29,paint);text(c,label,x-26,y+105,15,0xffbdcde4);}
    @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);sx=getWidth()/1280f;sy=getHeight()/720f;Canvas c=canvas;c.save();c.scale(sx,sy);
        long now=android.os.SystemClock.uptimeMillis();if(now-update>400){if(NativeBridge.AVAILABLE){status=NativeBridge.rendererStatus();pad=NativeBridge.padStatus();}update=now;}
        round(c,new RectF(30,22,217,68),0xbb111d35);text(c,"‹  Return home",47,52,21,Color.WHITE);text(c,"VULKAN + TOUCH TEST",420,47,15,0xffb0c6e4);text(c,"Diagnostic scene • not a PS5 game",420,76,17,0xffd7e4f5);
        text(c,"⚙",1205,55,29,Color.WHITE);float alpha=app.getSharedPreferences("nova",0).getInt("opacity",75)/100f;c.saveLayerAlpha(0,90,1280,720,(int)(alpha*255));
        shoulder(c,new RectF(49,117,188,173),"L2",0x100);shoulder(c,new RectF(205,117,323,173),"L1",0x400);shoulder(c,new RectF(957,117,1075,173),"R1",0x800);shoulder(c,new RectF(1092,117,1231,173),"R2",0x200);
        circle(c,149,366,36,0x10,"↑");circle(c,213,430,36,0x20,"→");circle(c,149,494,36,0x40,"↓");circle(c,85,430,36,0x80,"←");
        circle(c,1128,366,37,0x1000,"△");circle(c,1192,430,37,0x2000,"○");circle(c,1128,494,37,0x4000,"×");circle(c,1064,430,37,0x8000,"□");
        stick(c,325,554,lx,ly,"LEFT");stick(c,955,554,rx,ry,"RIGHT");
        shoulder(c,new RectF(508,128,772,212),"TOUCHPAD",0x100000);text(c,"Create",421,165,17,0xffbdcde4);text(c,"Options",792,165,17,0xffbdcde4);circle(c,640,616,27,0,"N");
        if(app.getSharedPreferences("nova",0).getBoolean("stick_clicks",true)){shoulder(c,new RectF(419,567,494,611),"L3",2);shoulder(c,new RectF(786,567,861,611),"R3",4);}
        if(touches!=0){paint.setColor(0xff9ecaff);c.drawCircle(508+tx*264,128+ty*84,9,paint);}c.restore();
        String[] lines=(status+"\n"+pad).split("\n");float y=246;for(int i=0;i<lines.length;i++){String line=lines[i];if(line.length()>78)line=line.substring(0,77)+"…";text(c,line,411,y,14,0xffa9c1df);y+=22;}
        c.restore();if(isAttachedToWindow()&&!app.paused)postInvalidateDelayed(32);
    }
    boolean near(PointF p,float x,float y,float r){return Math.hypot(p.x-x,p.y-y)<=r;}
    int hit(PointF p){if(new RectF(49,117,188,173).contains(p.x,p.y))return 0x100;if(new RectF(205,117,323,173).contains(p.x,p.y))return 0x400;if(new RectF(957,117,1075,173).contains(p.x,p.y))return 0x800;if(new RectF(1092,117,1231,173).contains(p.x,p.y))return 0x200;
        float[][] face={{149,366,0x10},{213,430,0x20},{149,494,0x40},{85,430,0x80},{1128,366,0x1000},{1192,430,0x2000},{1128,494,0x4000},{1064,430,0x8000}};for(float[] f:face)if(near(p,f[0],f[1],48))return (int)f[2];
        if(new RectF(788,134,867,194).contains(p.x,p.y))return 8;
        if(app.getSharedPreferences("nova",0).getBoolean("stick_clicks",true)){if(new RectF(419,567,494,611).contains(p.x,p.y))return 2;if(new RectF(786,567,861,611).contains(p.x,p.y))return 4;}return 0;
    }
    void updateState(){buttons=0;lx=ly=rx=ry=l2=r2=tx=ty=0;touches=0;
        for(Map.Entry<Integer,PointF> e:points.entrySet()){PointF p=e.getValue();int id=e.getKey();if(id==leftPointer){float dx=(p.x-325)/63,dy=(p.y-554)/63,len=(float)Math.hypot(dx,dy);if(len>1){dx/=len;dy/=len;}lx=dx;ly=dy;}
            else if(id==rightPointer){float dx=(p.x-955)/63,dy=(p.y-554)/63,len=(float)Math.hypot(dx,dy);if(len>1){dx/=len;dy/=len;}rx=dx;ry=dy;}
            else if(id==touchPointer){touches=1;tx=Math.max(0,Math.min(1,(p.x-508)/264));ty=Math.max(0,Math.min(1,(p.y-128)/84));buttons|=0x100000;}
            else buttons|=hit(p);
        }l2=(buttons&0x100)!=0?1:0;r2=(buttons&0x200)!=0?1:0;send();invalidate();
    }
    void send(){app.sendInput(buttons,lx,ly,rx,ry,l2,r2,touches,tx,ty);}
    void release(){points.clear();leftPointer=rightPointer=touchPointer=-1;updateState();}
    @Override public boolean onTouchEvent(MotionEvent e){int action=e.getActionMasked(),index=e.getActionIndex(),id=e.getPointerId(index);PointF p=new PointF(e.getX(index)/sx,e.getY(index)/sy);
        if(action==MotionEvent.ACTION_DOWN||action==MotionEvent.ACTION_POINTER_DOWN){
            if(near(p,640,616,32)){release();app.settings();return true;}if(new RectF(401,134,480,194).contains(p.x,p.y)){release();app.diagnostics();return true;}if(p.y<82){if(p.x<230){release();app.showHome();return true;}if(p.x>1180){release();app.settings();return true;}}
            points.put(id,p);if(leftPointer<0&&near(p,325,554,92))leftPointer=id;else if(rightPointer<0&&near(p,955,554,92))rightPointer=id;else if(touchPointer<0&&new RectF(508,128,772,212).contains(p.x,p.y))touchPointer=id;
        }else if(action==MotionEvent.ACTION_MOVE){for(int i=0;i<e.getPointerCount();i++){int pointer=e.getPointerId(i);if(points.containsKey(pointer))points.put(pointer,new PointF(e.getX(i)/sx,e.getY(i)/sy));}}
        else if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_POINTER_UP){points.remove(id);if(id==leftPointer)leftPointer=-1;if(id==rightPointer)rightPointer=-1;if(id==touchPointer)touchPointer=-1;performClick();}
        else if(action==MotionEvent.ACTION_CANCEL){release();return true;}
        updateState();return true;
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
