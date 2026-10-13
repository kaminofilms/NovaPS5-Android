package com.kaminofilms.novaps5;

import android.content.Context;
import android.graphics.*;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.MotionEvent;
import android.view.View;
import java.util.HashMap;
import java.util.Map;

/**
 * The on-screen PS5 controller. Its state goes to Kyty as an SDL virtual gamepad (libmain's
 * NovaPad.nativeState), so the game sees an ordinary controller. A swipe in from the left edge,
 * or the PS button, opens the game menu.
 */
final class NovaPad extends View {
    // SDL_GamepadButton numbering.
    static final int CROSS = 1, CIRCLE = 1 << 1, SQUARE = 1 << 2, TRIANGLE = 1 << 3, TOUCHPAD = 1 << 4, PS = 1 << 5,
            OPTIONS = 1 << 6, L3 = 1 << 7, R3 = 1 << 8, L1 = 1 << 9, R1 = 1 << 10, UP = 1 << 11, DOWN = 1 << 12,
            LEFT = 1 << 13, RIGHT = 1 << 14, CREATE = 1 << 15;
    // Internal only: the triggers are analog axes for SDL.
    static final int L2 = 1 << 20, R2 = 1 << 21;

    static native void nativeState(int buttons, float lx, float ly, float rx, float ry, float l2, float r2);

    interface Listener { void openMenu(); }

    private final Listener listener;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final HashMap<Integer, PointF> points = new HashMap<>();
    private final Vibrator vibrator;
    private float sx = 1, sy = 1, lx, ly, rx, ry;
    private int buttons, lastSent = -1, leftPointer = -1, rightPointer = -1, edgePointer = -1;
    private float edgeStartX;
    private float lastLx, lastLy, lastRx, lastRy;
    boolean visible = true;
    float opacity = 0.7f;

    NovaPad(Context context, Listener listener) {
        super(context);
        this.listener = listener;
        vibrator = context.getSystemService(Vibrator.class);
        setContentDescription("PS5 touch controller");
    }

    static void send(int buttons, float lx, float ly, float rx, float ry) {
        try {
            nativeState(buttons & 0xffff, lx, ly, rx, ry, (buttons & L2) != 0 ? 1f : 0f, (buttons & R2) != 0 ? 1f : 0f);
        } catch (UnsatisfiedLinkError ignored) {
            // The emulator library is not loaded yet.
        }
    }

    private void text(Canvas c, String value, float x, float y, float size, int color) {
        paint.setStyle(Paint.Style.FILL);
        paint.setTextSize(size);
        paint.setColor(color);
        paint.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        c.drawText(value, x - paint.measureText(value) / 2, y + size * 0.35f, paint);
    }

    private void circle(Canvas c, float x, float y, float r, int bit, String label, int tint) {
        boolean down = (buttons & bit) != 0;
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(down ? 0x99a8d4ff : 0x44202a44);
        c.drawCircle(x, y, r, paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(3);
        paint.setColor(down ? 0xffd6ebff : 0xaac4d9ee);
        c.drawCircle(x, y, r, paint);
        text(c, label, x, y, r * 0.95f, tint);
    }

    private void rect(Canvas c, RectF r, int bit, String label) {
        boolean down = (buttons & bit) != 0;
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(down ? 0x99a8d4ff : 0x44202a44);
        c.drawRoundRect(r, 20, 20, paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(3);
        paint.setColor(down ? 0xffd6ebff : 0x99c4d9ee);
        c.drawRoundRect(r, 20, 20, paint);
        text(c, label, r.centerX(), r.centerY(), 22, 0xffe2ecf9);
    }

    private void stick(Canvas c, float x, float y, float ax, float ay, boolean active) {
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(0x33202a44);
        c.drawCircle(x, y, 78, paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(3);
        paint.setColor(0x9994b9df);
        c.drawCircle(x, y, 78, paint);
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(active ? 0xcc9fcaff : 0x886f92c2);
        c.drawCircle(x + ax * 50, y + ay * 50, 34, paint);
    }

    // Layout in a 1280x720 space, scaled to the screen.
    private static final RectF R_L2 = new RectF(40, 30, 180, 90), R_L1 = new RectF(40, 104, 180, 164),
            R_R1 = new RectF(1100, 104, 1240, 164), R_R2 = new RectF(1100, 30, 1240, 90),
            R_PAD = new RectF(520, 20, 760, 92), R_CREATE = new RectF(420, 32, 500, 80),
            R_OPTIONS = new RectF(780, 32, 860, 80), R_L3 = new RectF(196, 640, 276, 690),
            R_R3 = new RectF(1004, 640, 1084, 690);
    private static final float LSX = 236, LSY = 548, RSX = 1044, RSY = 548;
    private static final float[][] FACE = {
            {150, 300, UP}, {214, 364, RIGHT}, {150, 428, DOWN}, {86, 364, LEFT},
            {1130, 300, TRIANGLE}, {1194, 364, CIRCLE}, {1130, 428, CROSS}, {1066, 364, SQUARE}};

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (!visible) return;
        sx = getWidth() / 1280f;
        sy = getHeight() / 720f;
        canvas.save();
        canvas.scale(sx, sy);
        canvas.saveLayerAlpha(0, 0, 1280, 720, (int) (opacity * 255));
        rect(canvas, R_L2, L2, "L2");
        rect(canvas, R_L1, L1, "L1");
        rect(canvas, R_R2, R2, "R2");
        rect(canvas, R_R1, R1, "R1");
        rect(canvas, R_PAD, TOUCHPAD, "TOUCHPAD");
        rect(canvas, R_CREATE, CREATE, "⧉");
        rect(canvas, R_OPTIONS, OPTIONS, "≡");
        rect(canvas, R_L3, L3, "L3");
        rect(canvas, R_R3, R3, "R3");
        String[] labels = {"▲", "▶", "▼", "◀", "△", "○", "✕", "□"};
        int[] tints = {0xffe2ecf9, 0xffe2ecf9, 0xffe2ecf9, 0xffe2ecf9, 0xff7fe0c8, 0xffff8a9a, 0xff8fb8ff, 0xffe6a2e6};
        for (int i = 0; i < FACE.length; i++) circle(canvas, FACE[i][0], FACE[i][1], 40, (int) FACE[i][2], labels[i], tints[i]);
        stick(canvas, LSX, LSY, lx, ly, leftPointer >= 0);
        stick(canvas, RSX, RSY, rx, ry, rightPointer >= 0);
        circle(canvas, 640, 660, 30, PS, "PS", 0xffe2ecf9);
        canvas.restore();
        canvas.restore();
    }

    private static boolean near(PointF p, float x, float y, float r) { return Math.hypot(p.x - x, p.y - y) <= r; }

    private int hit(PointF p) {
        if (R_L2.contains(p.x, p.y)) return L2;
        if (R_L1.contains(p.x, p.y)) return L1;
        if (R_R2.contains(p.x, p.y)) return R2;
        if (R_R1.contains(p.x, p.y)) return R1;
        if (R_PAD.contains(p.x, p.y)) return TOUCHPAD;
        if (R_CREATE.contains(p.x, p.y)) return CREATE;
        if (R_OPTIONS.contains(p.x, p.y)) return OPTIONS;
        if (R_L3.contains(p.x, p.y)) return L3;
        if (R_R3.contains(p.x, p.y)) return R3;
        if (near(p, 640, 660, 40)) return PS;
        int bits = 0;
        // D-pad diagonals: a press between two arrows holds both.
        for (float[] f : FACE) if (near(p, f[0], f[1], 50)) bits |= (int) f[2];
        if (bits == 0 && near(p, 150, 364, 120)) {
            float dx = p.x - 150, dy = p.y - 364;
            if (Math.abs(dx) > 22) bits |= dx < 0 ? LEFT : RIGHT;
            if (Math.abs(dy) > 22) bits |= dy < 0 ? UP : DOWN;
        }
        return bits;
    }

    private void update() {
        int b = 0;
        lx = ly = rx = ry = 0;
        for (Map.Entry<Integer, PointF> e : points.entrySet()) {
            PointF p = e.getValue();
            int id = e.getKey();
            if (id == leftPointer || id == rightPointer) {
                float cx = id == leftPointer ? LSX : RSX, cy = id == leftPointer ? LSY : RSY;
                float dx = (p.x - cx) / 62, dy = (p.y - cy) / 62, len = (float) Math.hypot(dx, dy);
                if (len > 1) { dx /= len; dy /= len; }
                if (id == leftPointer) { lx = dx; ly = dy; } else { rx = dx; ry = dy; }
            } else if (id != edgePointer) {
                b |= hit(p);
            }
        }
        if ((b & PS) != 0 && (buttons & PS) == 0) {
            release();
            listener.openMenu();
            return;
        }
        int pressed = b & ~buttons;
        buttons = b;
        if (pressed != 0 && vibrator != null) {
            try { vibrator.vibrate(VibrationEffect.createOneShot(12, 60)); } catch (Exception ignored) {}
        }
        if (buttons != lastSent || lx != lastLx || ly != lastLy || rx != lastRx || ry != lastRy) {
            send(buttons, lx, ly, rx, ry);
            lastSent = buttons; lastLx = lx; lastLy = ly; lastRx = rx; lastRy = ry;
        }
        invalidate();
    }

    void release() {
        points.clear();
        leftPointer = rightPointer = edgePointer = -1;
        buttons = 0;
        lx = ly = rx = ry = 0;
        send(0, 0, 0, 0, 0);
        lastSent = 0; lastLx = lastLy = lastRx = lastRy = 0;
        invalidate();
    }

    @Override public boolean onTouchEvent(MotionEvent e) {
        int action = e.getActionMasked(), index = e.getActionIndex(), id = e.getPointerId(index);
        switch (action) {
            case MotionEvent.ACTION_DOWN:
            case MotionEvent.ACTION_POINTER_DOWN: {
                PointF p = new PointF(e.getX(index) / sx, e.getY(index) / sy);
                if (e.getX(index) < getWidth() * 0.025f && edgePointer < 0) {
                    edgePointer = id;
                    edgeStartX = e.getX(index);
                }
                if (!visible) {
                    points.put(id, p);
                    return true;
                }
                points.put(id, p);
                if (leftPointer < 0 && near(p, LSX, LSY, 130)) leftPointer = id;
                else if (rightPointer < 0 && near(p, RSX, RSY, 130)) rightPointer = id;
                break;
            }
            case MotionEvent.ACTION_MOVE:
                for (int i = 0; i < e.getPointerCount(); i++) {
                    int pointer = e.getPointerId(i);
                    if (pointer == edgePointer && e.getX(i) - edgeStartX > getWidth() * 0.12f) {
                        release();
                        listener.openMenu();
                        return true;
                    }
                    if (points.containsKey(pointer)) points.put(pointer, new PointF(e.getX(i) / sx, e.getY(i) / sy));
                }
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_POINTER_UP:
                points.remove(id);
                if (id == leftPointer) leftPointer = -1;
                if (id == rightPointer) rightPointer = -1;
                if (id == edgePointer) edgePointer = -1;
                if (action == MotionEvent.ACTION_UP) performClick();
                break;
            case MotionEvent.ACTION_CANCEL:
                release();
                return true;
            default:
                return true;
        }
        if (visible) update();
        return true;
    }

    @Override public boolean performClick() { super.performClick(); return true; }
}
