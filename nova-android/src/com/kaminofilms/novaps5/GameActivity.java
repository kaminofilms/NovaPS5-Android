package com.kaminofilms.novaps5;

import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.system.Os;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.ViewGroup;
import android.widget.SeekBar;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import org.libsdl.app.SDLActivity;

/**
 * Runs one game: Kyty (libmain.so) with the embedded FEXCore, drawing with Vulkan straight to this
 * activity's surface. Lives in its own process (":game"); leaving the game ends the process.
 */
public final class GameActivity extends SDLActivity implements NovaPad.Listener {
    static final String EXTRA_GAME = "game", EXTRA_NAME = "name";
    // A PS5 open-SDK homebrew's libc stub; such titles need Kyty's host C library.
    static final String HOMEBREW_LIBC_SHA = "e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036";
    private String game = "";
    private NovaPad pad;
    private AlertDialog menu;
    private android.widget.TextView fps;
    private final android.os.Handler ticker = new android.os.Handler(android.os.Looper.getMainLooper());
    private long lastFrames, lastTime;
    private final Runnable fpsTick = new Runnable() {
        public void run() {
            long now = android.os.SystemClock.uptimeMillis(), frames = NovaPad.frames();
            if (lastTime != 0 && now > lastTime) {
                float rate = (frames - lastFrames) * 1000f / (now - lastTime);
                fps.setText(String.format(java.util.Locale.US, "%.0f FPS", rate));
            }
            lastFrames = frames;
            lastTime = now;
            ticker.postDelayed(this, 500);
        }
    };

    @Override protected void onCreate(Bundle state) {
        BootLog.install(this);
        game = getIntent().getStringExtra(EXTRA_GAME);
        if (game == null) game = "";
        prepareEnvironment();
        super.onCreate(state);
        setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
        pad = new NovaPad(this, this);
        pad.opacity = getSharedPreferences("nova", 0).getInt("opacity", 70) / 100f;
        pad.visible = getSharedPreferences("nova", 0).getBoolean("touch_controls", true) && !physicalGamepad();
        addContentView(pad, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        fps = new android.widget.TextView(this);
        fps.setTextColor(0xff7dff9a);
        fps.setTextSize(14);
        fps.setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD);
        fps.setShadowLayer(4, 0, 0, 0xff000000);
        fps.setPadding(24, 12, 24, 12);
        fps.setText("-- FPS");
        android.widget.FrameLayout.LayoutParams at = new android.widget.FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, android.view.Gravity.TOP | android.view.Gravity.END);
        addContentView(fps, at);
        showFps(getSharedPreferences("nova", 0).getBoolean("show_fps", true));
        BootLog.write(this, "Game started: " + game);
    }

    private void prepareEnvironment() {
        File work = new File(getFilesDir(), "kyty");
        File logs = new File(getFilesDir(), "logs");
        work.mkdirs();
        logs.mkdirs();
        File log = new File(logs, "kyty-session.log");
        if (log.isFile()) {
            File previous = new File(logs, "kyty-session.previous.log");
            previous.delete();
            log.renameTo(previous);
        }
        migrateOldData(work);
        try {
            Os.setenv("NOVA_LOG_FILE", log.getPath(), true);
            Os.setenv("NOVA_WORKDIR", work.getPath(), true);
            Os.setenv("HOME", work.getPath(), true);
            Os.setenv("TMPDIR", getCacheDir().getPath(), true);
            Os.setenv("NOVA_RELAXED_VULKAN", "1", true);
            Os.setenv("NOVA_LIBC_HLE", homebrewLibc() ? "1" : "0", true);
            // Guest addresses above the phone's 39-bit (512 GB) address space are translated in
            // FEX (libc's 512/768 GB arena). Dead Cells does not need it and keeps the direct path.
            boolean guestVa = !"PPSA15552".equals(titleId(new File(game)));
            Os.setenv("NOVA_GUEST_VA", guestVa ? "1" : "0", true);
            if (guestVa) BootLog.write(this, "Guest address translation on (addresses above 512 GB)");
            boolean unreal = unrealGame(new File(game), 0);
            // With guest address translation the game's own libc heap (512/768 GB arena) works as on
            // the console. The emulator heap is only for titles without translation: under translation
            // it broke both Unreal test games in 0.9.6 (Meat Boy: out of memory at 32 MiB, Luna: crash
            // at start), so the old setting is ignored here.
            boolean heapHle = unreal && !guestVa;
            Os.setenv("NOVA_HEAP_HLE", heapHle ? "1" : "0", true);
            if (unreal) BootLog.write(this, heapHle ? "Unreal Engine title: the emulator serves its libc heap"
                    : "Unreal Engine title: the game's own libc heap (translated addresses)");
            Drivers.Driver driver = Drivers.current(this);
            if (driver != null) {
                Os.setenv("NOVA_TURNIP_DIR", driver.dir.getPath() + "/", true);
                Os.setenv("NOVA_TURNIP_LIB", driver.library, true);
                Os.setenv("NOVA_HOOK_DIR", getApplicationInfo().nativeLibraryDir + "/", true);
            } else {
                Os.unsetenv("NOVA_TURNIP_DIR");
            }
            BootLog.write(this, "GPU driver: " + (driver == null ? "system" : driver.label));
        } catch (Exception x) {
            BootLog.write(this, "Environment setup failed: " + x);
        }
    }

    /** Saves and the shader cache from the Linux-runtime versions (0.4-0.6) of Nova. */
    private void migrateOldData(File work) {
        File old = new File(getFilesDir(), "linuxfs/opt/novaps5/linux-runtime/native");
        for (String name : new String[] {"_SaveData", "_PipelineCache"}) {
            File from = new File(old, name), to = new File(work, name);
            if (!from.isDirectory() || to.exists()) continue;
            try {
                copyTree(from, to);
                BootLog.write(this, "Carried over " + name + " from the previous version");
            } catch (Exception x) {
                BootLog.write(this, "Could not carry over " + name + ": " + x);
            }
        }
    }

    static void copyTree(File from, File to) throws Exception {
        if (from.isDirectory()) {
            to.mkdirs();
            File[] children = from.listFiles();
            if (children != null) for (File child : children) copyTree(child, new File(to, child.getName()));
        } else {
            Files.copy(from.toPath(), to.toPath(), StandardCopyOption.REPLACE_EXISTING);
        }
    }

    /** Profiles use the metadata title ID, never a folder name or display title. */
    static String titleId(File directory) {
        File metadata = new File(directory, "sce_sys/param.json");
        if (!metadata.isFile() || metadata.length() > 1048576) return "";
        try {
            org.json.JSONObject json = new org.json.JSONObject(new String(Files.readAllBytes(metadata.toPath()),
                    java.nio.charset.StandardCharsets.UTF_8));
            return json.optString("titleId", "");
        } catch (Exception ignored) {
            return "";
        }
    }

    /** Unreal Engine titles ship their data as .pak/.utoc files under <Project>/Content/Paks. */
    static boolean unrealGame(File dir, int depth) {
        File[] files = dir.listFiles();
        if (files == null || depth > 3) return false;
        for (File f : files) {
            String n = f.getName().toLowerCase(java.util.Locale.ROOT);
            // .utoc/.ucas (IoStore) or .pak inside <Project>/Content/Paks: Unreal only. A bare .pak is
            // not enough (Dead Cells ships one too).
            if (f.isFile() && (n.endsWith(".utoc") || n.endsWith(".ucas"))) return true;
            if (f.isFile() && n.endsWith(".pak") && dir.getName().equalsIgnoreCase("Paks")
                    && dir.getParentFile() != null && dir.getParentFile().getName().equalsIgnoreCase("Content")) return true;
            if (f.isDirectory() && !n.equals("sce_sys") && !n.equals("sce_module") && unrealGame(f, depth + 1)) return true;
        }
        return false;
    }

    private boolean homebrewLibc() {
        File libc = new File(game, "sce_module/libc.prx");
        if (!libc.isFile()) return false;
        try (InputStream in = new FileInputStream(libc)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            int n;
            while ((n = in.read(buffer)) > 0) digest.update(buffer, 0, n);
            StringBuilder hex = new StringBuilder();
            for (byte b : digest.digest()) hex.append(String.format("%02x", b & 255));
            return HOMEBREW_LIBC_SHA.contentEquals(hex);
        } catch (Exception x) {
            return false;
        }
    }

    private boolean physicalGamepad() {
        for (int id : InputDevice.getDeviceIds()) {
            InputDevice device = InputDevice.getDevice(id);
            if (device == null || device.isVirtual()) continue;
            int sources = device.getSources();
            if ((sources & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                    || (sources & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK) return true;
        }
        return false;
    }

    /** PS5 games are always landscape; SDL would otherwise pick from the window size. */
    @Override public void setOrientationBis(int w, int h, boolean resizable, String hint) {
        setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
    }

    @Override protected String[] getLibraries() {
        return new String[] {"SDL3", "main"};
    }

    @Override protected String[] getArguments() {
        return new String[] {"--game", game, "--screen-width", "1280", "--screen-height", "720",
                "--vblank-frequency", "60", "--present-mode", "Fifo", "--fullscreen", "--hide-cursor", "--no-splash",
                "--vulkan-validation", "false", "--network-connected", "false"};
    }

    private void showFps(boolean on) {
        fps.setVisibility(on ? android.view.View.VISIBLE : android.view.View.GONE);
        ticker.removeCallbacks(fpsTick);
        lastTime = 0;
        if (on) ticker.post(fpsTick);
    }

    @Override public void openMenu() {
        runOnUiThread(() -> {
            if (menu != null && menu.isShowing()) return;
            String controls = pad.visible ? "Hide touch controls" : "Show touch controls";
            boolean fpsOn = getSharedPreferences("nova", 0).getBoolean("show_fps", true);
            String fpsItem = fpsOn ? "Hide FPS counter" : "Show FPS counter";
            menu = new AlertDialog.Builder(this)
                    .setTitle(getIntent().getStringExtra(EXTRA_NAME) == null ? "Game" : getIntent().getStringExtra(EXTRA_NAME))
                    .setItems(new String[] {"Resume", controls, fpsItem, "Controller opacity", "Exit game"}, (d, which) -> {
                        if (which == 1) {
                            pad.visible = !pad.visible;
                            pad.release();
                            getSharedPreferences("nova", 0).edit().putBoolean("touch_controls", pad.visible).apply();
                        } else if (which == 2) {
                            getSharedPreferences("nova", 0).edit().putBoolean("show_fps", !fpsOn).apply();
                            showFps(!fpsOn);
                        } else if (which == 3) {
                            opacityDialog();
                        } else if (which == 4) {
                            exitGame();
                        }
                    })
                    .create();
            menu.show();
        });
    }

    private void opacityDialog() {
        SeekBar bar = new SeekBar(this);
        bar.setMax(85);
        bar.setProgress((int) (pad.opacity * 100) - 15);
        bar.setPadding(48, 32, 48, 32);
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar s, int value, boolean user) { pad.opacity = (value + 15) / 100f; pad.invalidate(); }
            public void onStartTrackingTouch(SeekBar s) {}
            public void onStopTrackingTouch(SeekBar s) {
                getSharedPreferences("nova", 0).edit().putInt("opacity", s.getProgress() + 15).apply();
            }
        });
        new AlertDialog.Builder(this).setTitle("Controller opacity").setView(bar).setPositiveButton("Done", null).show();
    }

    private void exitGame() {
        BootLog.write(this, "Exit game: " + game);
        Intent home = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        startActivity(home);
        finishAndRemoveTask();
        android.os.Process.killProcess(android.os.Process.myPid());
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_BACK) {
            if (event.getAction() == KeyEvent.ACTION_UP) openMenu();
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    @Override protected void onPause() {
        if (pad != null) pad.release();
        super.onPause();
    }
}

