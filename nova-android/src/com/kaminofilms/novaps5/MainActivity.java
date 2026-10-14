package com.kaminofilms.novaps5;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.provider.DocumentsContract;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Nova PS5 front end: game library, launching, settings and logs. Games run in GameActivity. */
public final class MainActivity extends Activity {
    static final String VERSION = "@NOVA_VERSION_NAME@";
    static final int FOLDER = 10, EXPORT = 12, DRIVER = 13;
    final ExecutorService io = Executors.newSingleThreadExecutor();
    GameStore store;
    HomeView home;
    volatile String gpu = "";
    String exportText = "";

    void ui(Runnable r) { runOnUiThread(() -> { if (!isFinishing() && !isDestroyed()) r.run(); }); }

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
        BootLog.install(this);
        BootLog.write(this, "NovaPs5 " + VERSION + " started; Android " + Build.VERSION.SDK_INT + " " + Build.MANUFACTURER + " " + Build.MODEL);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        gpu = Build.MANUFACTURER + " " + Build.MODEL + " · " + Build.SOC_MODEL + " · Android " + Build.VERSION.RELEASE;
        store = new GameStore(this);
        home = new HomeView(this);
        setContentView(home);
        immersive();
        io.execute(() -> { Drivers.ensureBundled(this); store.loadImages(); ui(() -> home.invalidate()); });
        if (!Environment.isExternalStorageManager()) askFileAccess();
    }

    void immersive() {
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
    }

    @Override protected void onResume() { super.onResume(); immersive(); if (home != null) home.invalidate(); refreshLibrary(); }

    private long lastRefresh;

    /** Downloads SteamGridDB backgrounds for games that do not have one yet. */
    void fetchArt(boolean report) {
        if (Art.key(this).isEmpty()) return;
        try {
            boolean any = store.fetchArt();
            if (any) ui(() -> home.invalidate());
            if (report) ui(() -> Toast.makeText(this, any ? "Game backgrounds updated" : "Backgrounds are up to date", Toast.LENGTH_SHORT).show());
        } catch (Exception x) {
            BootLog.write(this, "SteamGridDB: " + x.getMessage());
            if (report) ui(() -> Toast.makeText(this, "SteamGridDB: " + x.getMessage(), Toast.LENGTH_LONG).show());
        }
    }
    /** Rescans the game folders so newly copied games show up without re-importing. */
    void refreshLibrary() {
        long now = android.os.SystemClock.elapsedRealtime();
        if (store == null || now - lastRefresh < 3000) return;
        lastRefresh = now;
        io.execute(() -> {
            try {
                if (store.refresh()) { BootLog.write(this, "Library refreshed: " + store.snapshot().size() + " game(s)"); ui(() -> home.invalidate()); }
            } catch (Exception x) { BootLog.write(this, "Library refresh failed: " + x); }
            fetchArt(false);
        });
    }
    @Override protected void onDestroy() { io.shutdownNow(); super.onDestroy(); }

    void askFileAccess() {
        new AlertDialog.Builder(this).setTitle("Allow access to your games")
                .setMessage("Nova reads your extracted PS5 game folders directly from storage. Turn on \"Allow access to manage all files\" for NovaPs5 on the next screen.")
                .setPositiveButton("Open setting", (d, w) -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:" + getPackageName())));
                    } catch (ActivityNotFoundException x) {
                        startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION));
                    }
                })
                .setNegativeButton("Later", null).show();
    }

    void info(String title, String message) {
        TextView t = new TextView(this);
        t.setText(message);
        t.setTextSize(14);
        t.setTextColor(Color.WHITE);
        t.setPadding(28, 24, 28, 20);
        t.setTextIsSelectable(true);
        ScrollView s = new ScrollView(this);
        s.addView(t);
        new AlertDialog.Builder(this).setTitle(title).setView(s).setPositiveButton("Close", null).show();
    }

    interface Work { String run() throws Exception; }

    void busy(String title, Work work, java.util.function.Consumer<String> done) {
        ProgressDialog p = new ProgressDialog(this);
        p.setTitle(title);
        p.setMessage("Working…");
        p.setIndeterminate(true);
        p.setCancelable(false);
        p.show();
        io.execute(() -> {
            try {
                String value = work.run();
                ui(() -> { p.dismiss(); done.accept(value); });
            } catch (Exception e) {
                ui(() -> { p.dismiss(); info(title, "Could not complete this operation.\n\n" + e.getMessage()); });
            }
        });
    }

    void folder() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(i, FOLDER);
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (result != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (request == FOLDER) {
            try {
                getContentResolver().takePersistableUriPermission(uri, data.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } catch (SecurityException e) {
                info("Folder access", "This provider cannot retain access. Choose a folder on internal storage.");
                return;
            }
            busy("Importing game folder", () -> {
                List<GameStore.Entry> found = store.scan(uri);
                store.addAll(found);
                store.addRoot(GameStore.pathOf(uri.toString()));
                store.loadImages();
                return found.size() + " game folder(s) found.";
            }, value -> { home.invalidate(); info("Library updated", value); });
        } else if (request == DRIVER) {
            String name = "Turnip.zip";
            try (android.database.Cursor c = getContentResolver().query(uri, new String[] {android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                if (c != null && c.moveToFirst() && c.getString(0) != null) name = c.getString(0);
            } catch (Exception ignored) {}
            final String file = name;
            busy("Importing GPU driver", () -> "Installed and selected: " + Drivers.importZip(this, uri, file), value -> info("GPU driver", value));
        } else if (request == EXPORT) {
            final String content = exportText;
            busy("Exporting log", () -> {
                try (OutputStream out = getContentResolver().openOutputStream(uri, "wt")) {
                    if (out == null) throw new IOException("No writable document returned");
                    out.write(content.getBytes(StandardCharsets.UTF_8));
                }
                return "Log saved.";
            }, value -> Toast.makeText(this, value, Toast.LENGTH_SHORT).show());
        }
    }

    /** A game folder picked through Android Files, as a path on internal storage. */
    String resolveGame(GameStore.Entry e) throws Exception {
        Uri uri = Uri.parse(e.uri);
        String doc = DocumentsContract.getDocumentId(uri);
        if (!doc.startsWith("primary:")) throw new IOException("Nova launches games from internal shared storage. Select the extracted game folder on internal storage.");
        File base = Environment.getExternalStorageDirectory().getCanonicalFile();
        File game = new File(base, doc.substring(8)).getCanonicalFile();
        if (!game.getPath().startsWith(base.getPath() + File.separator)) throw new IOException("Invalid game folder path");
        if (!new File(game, "eboot.bin").canRead()) {
            if (!Environment.isExternalStorageManager()) {
                ui(this::askFileAccess);
                throw new IOException("Nova needs \"Allow access to manage all files\" to read the game.");
            }
            throw new IOException("eboot.bin is not readable in " + game);
        }
        return game.getAbsolutePath();
    }

    /** Ends a game that is still running (its own process) so the next launch starts clean. */
    void endRunningGame() {
        ActivityManager am = getSystemService(ActivityManager.class);
        // Earlier games' tasks (one per launch otherwise piles up in Recents).
        if (am != null) {
            for (ActivityManager.AppTask task : am.getAppTasks()) {
                try {
                    ActivityManager.RecentTaskInfo info = task.getTaskInfo();
                    if (info.baseActivity != null && info.baseActivity.getClassName().endsWith(".GameActivity")) task.finishAndRemoveTask();
                } catch (Exception ignored) {}
            }
        }
        List<ActivityManager.RunningAppProcessInfo> list = am == null ? null : am.getRunningAppProcesses();
        if (list == null) return;
        for (ActivityManager.RunningAppProcessInfo p : list) {
            if (p.processName != null && p.processName.endsWith(":game") && p.pid != android.os.Process.myPid()) {
                BootLog.write(this, "Ending the previous game (pid " + p.pid + ")");
                android.os.Process.killProcess(p.pid);
            }
        }
    }

    void launchGame(GameStore.Entry e) {
        final String path;
        try {
            path = resolveGame(e);
        } catch (Exception x) {
            info("Game access", x.getMessage());
            return;
        }
        endRunningGame();
        BootLog.write(this, "Launching " + e.name + " (" + e.id + ") from " + path);
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            Intent intent = new Intent(this, GameActivity.class)
                    .putExtra(GameActivity.EXTRA_GAME, path).putExtra(GameActivity.EXTRA_NAME, e.name)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
            startActivity(intent);
        }, 400);
    }

    void entry(GameStore.Entry e) {
        new AlertDialog.Builder(this).setTitle(e.name)
                .setMessage(e.id + (e.version.isEmpty() ? "" : " · " + e.version))
                .setPositiveButton("Play", (d, w) -> launchGame(e))
                .setNeutralButton("Remove from library", (d, w) -> { try { store.remove(e); } catch (Exception ignored) {} home.invalidate(); })
                .setNegativeButton("Close", null).show();
    }

    /** The diagnostic lines of a game log, so they survive even when the log is cut. */
    static String keyLines(File file) {
        if (!file.isFile()) return "(none)";
        StringBuilder out = new StringBuilder();
        int count = 0, errorLines = 0, waits = 0;
        try (java.io.BufferedReader in = new java.io.BufferedReader(new java.io.InputStreamReader(new java.io.FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = in.readLine()) != null && count < 600) {
                boolean keep = errorLines > 0;
                if (keep) errorLines--;
                if (line.startsWith("Title ID") || line.startsWith("NOVA_WAIT") || line.startsWith("NOVA_GPU") || line.startsWith("NOVA_AUDIO")
                        || line.startsWith("NOVA_AAUDIO") || line.startsWith("NOVA_FAULT") || line.startsWith("NOVA_ABORT") || line.startsWith("NOVA_MEMTRACE") || line.startsWith("NOVA_FREEZE: no frame")
                        || line.startsWith("Unresolved import") || line.contains("AAudio") || line.contains("AAUDIO")
                        || (line.startsWith("NOVA_MEMORY") && (line.contains("fail") || line.contains("BEYOND") || line.contains("fit")))
                        || (line.startsWith("NOVA_ANDROID") && !line.contains("touch"))) keep = true;
                if (line.startsWith("--- Error ---")) { keep = true; errorLines = 2; }
                if (keep && line.startsWith("NOVA_WAIT") && ++waits > 30) keep = false;
                if (keep) { out.append(line).append('\n'); count++; }
            }
        } catch (Exception x) {
            return "(unreadable: " + x + ")";
        }
        return out.length() == 0 ? "(none)" : out.toString();
    }

    static String tail(File file, int limit) {
        if (!file.isFile()) return "(none)";
        try (RandomAccessFile in = new RandomAccessFile(file, "r")) {
            long size = in.length();
            byte[] bytes = new byte[(int) Math.min(size, limit)];
            in.seek(size - bytes.length);
            in.readFully(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (Exception x) {
            return "(unreadable: " + x + ")";
        }
    }

    String fullReport() {
        File logs = new File(getFilesDir(), "logs");
        return "NovaPs5 " + VERSION + " (native Android)\n" + gpu + "\nABIs: " + Arrays.toString(Build.SUPPORTED_ABIS)
                + "\nAll files access: " + Environment.isExternalStorageManager()
                + "\nGPU driver: " + Drivers.label(this)
                + "\n\nKey lines (latest game):\n" + keyLines(new File(logs, "kyty-session.log"))
                + "\n\nLatest game log:\n" + tail(new File(logs, "kyty-session.log"), 400000)
                + "\n\nPrevious game log (end):\n" + tail(new File(logs, "kyty-session.previous.log"), 60000)
                + "\n\nApp log:\n" + BootLog.read(this)
                + "\n\nAndroid audio/SDL log:\n" + logcat();
    }

    /** Recent SDL / AAudio lines from Android's log (this app's own entries). */
    static String logcat() {
        try {
            java.lang.Process p = new ProcessBuilder("logcat", "-d", "-t", "400", "-v", "time", "-s",
                    "SDL:V", "SDL/APP:V", "SDL/AUDIO:V", "AAudio:V", "AudioStream:V", "AudioStreamLegacy:V", "AudioTrack:W", "libOpenSLES:W")
                    .redirectErrorStream(true).start();
            byte[] out = readAll(p.getInputStream(), 200000);
            p.waitFor();
            return out.length == 0 ? "(empty)" : new String(out, StandardCharsets.UTF_8);
        } catch (Exception x) {
            return "(unavailable: " + x + ")";
        }
    }

    static byte[] readAll(java.io.InputStream in, int limit) throws IOException {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int n;
        while ((n = in.read(buffer)) > 0) { if (out.size() < limit) out.write(buffer, 0, Math.min(n, limit - out.size())); }
        return out.toByteArray();
    }

    void diagnostics() {
        File logs = new File(getFilesDir(), "logs");
        String value = "NovaPs5 " + VERSION + " (native Android)\n" + gpu
                + "\nGPU driver: " + Drivers.label(this)
                + "\n\nKey lines (latest game):\n" + keyLines(new File(logs, "kyty-session.log"))
                + "\n\nLatest game log (end):\n" + tail(new File(logs, "kyty-session.log"), 30000);
        TextView text = new TextView(this);
        text.setText(value.length() > 60000 ? value.substring(0, 60000) + "\n\n(… use Export for the full log)" : value);
        text.setTextSize(12);
        text.setTextIsSelectable(true);
        text.setPadding(28, 20, 28, 20);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(text);
        
        new AlertDialog.Builder(this).setTitle("Session log").setView(scroll)
                .setNeutralButton("Export", (d, w) -> {
                    exportText = fullReport();
                    Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    i.setType("text/plain");
                    i.addCategory(Intent.CATEGORY_OPENABLE);
                    i.putExtra(Intent.EXTRA_TITLE, "NovaPs5-log.txt");
                    startActivityForResult(i, EXPORT);
                })
                .setPositiveButton("Close", null).show();
    }

    void settings() {
        SharedPreferences prefs = getSharedPreferences("nova", 0);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(40, 20, 40, 12);
        // Driver selection must remain visible on short landscape screens.
        Button driver = new Button(this);
        driver.setAllCaps(false);
        driver.setText("GPU driver: " + Drivers.label(this));
        driver.setOnClickListener(v -> gpuDriver());
        box.addView(driver);
        TextView opacityLabel = new TextView(this);
        opacityLabel.setText("Touch controller opacity");
        box.addView(opacityLabel);
        SeekBar opacity = new SeekBar(this);
        opacity.setMax(85);
        opacity.setProgress(prefs.getInt("opacity", 70) - 15);
        box.addView(opacity);
        CheckBox touch = new CheckBox(this);
        touch.setText("Show the touch controller in games (hidden automatically with a gamepad)");
        touch.setChecked(prefs.getBoolean("touch_controls", true));
        box.addView(touch);
        CheckBox showFps = new CheckBox(this);
        showFps.setText("Show the FPS counter in games");
        showFps.setChecked(prefs.getBoolean("show_fps", true));
        box.addView(showFps);
        TextView artLabel = new TextView(this);
        artLabel.setText("SteamGridDB API key (full-screen game backgrounds)");
        artLabel.setPadding(0, 16, 0, 0);
        box.addView(artLabel);
        LinearLayout artRow = new LinearLayout(this);
        artRow.setOrientation(LinearLayout.HORIZONTAL);
        EditText artKey = new EditText(this);
        artKey.setSingleLine(true);
        artKey.setHint("Paste your API key");
        artKey.setText(prefs.getString("sgdb_key", ""));
        artRow.addView(artKey, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button paste = new Button(this);
        paste.setAllCaps(false);
        paste.setText("Paste");
        paste.setOnClickListener(v -> {
            ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            if (cm != null && cm.hasPrimaryClip() && cm.getPrimaryClip().getItemCount() > 0) {
                CharSequence t = cm.getPrimaryClip().getItemAt(0).coerceToText(this);
                if (t != null) artKey.setText(t.toString().trim());
            }
        });
        artRow.addView(paste);
        box.addView(artRow);
        Button getKey = new Button(this);
        getKey.setAllCaps(false);
        getKey.setText("Get a free key at steamgriddb.com");
        getKey.setOnClickListener(v -> {
            try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Art.KEY_PAGE))); }
            catch (Exception x) { Toast.makeText(this, Art.KEY_PAGE, Toast.LENGTH_LONG).show(); }
        });
        box.addView(getKey);
        File old = new File(getFilesDir(), "linuxfs");
        if (old.exists()) {
            Button clean = new Button(this);
            clean.setAllCaps(false);
            clean.setText("Remove the old Linux runtime (no longer used)");
            clean.setOnClickListener(v -> new AlertDialog.Builder(this).setTitle("Remove old runtime")
                    .setMessage("Versions 0.3–0.6 ran games inside a downloaded Linux system. This version does not use it. Your saves and shader cache have already been carried over the first time you started a game; start a game once before removing it if you have not yet.")
                    .setPositiveButton("Remove", (d, w) -> busy("Removing old runtime", () -> {
                        deleteTree(old);
                        deleteTree(new File(getFilesDir(), "linux_vulkan_drivers"));
                        return "Removed.";
                    }, value -> { clean.setEnabled(false); Toast.makeText(this, value, Toast.LENGTH_SHORT).show(); }))
                    .setNegativeButton("Cancel", null).show());
            box.addView(clean);
        }
        TextView about = new TextView(this);
        about.setText("NovaPs5 " + VERSION + "\nKyty and the x86-64 translator (FEXCore) run natively inside the app. In a game, swipe in from the left edge or press PS for the game menu.");
        about.setPadding(0, 18, 0, 0);
        box.addView(about);
        ScrollView settingsScroll = new ScrollView(this);
        settingsScroll.setFillViewport(true);
        settingsScroll.addView(box, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        new AlertDialog.Builder(this).setTitle("Settings").setView(settingsScroll)
                .setPositiveButton("Save", (d, w) -> {
                    String newKey = artKey.getText().toString().trim();
                    boolean keyChanged = !newKey.equals(prefs.getString("sgdb_key", ""));
                    prefs.edit().putInt("opacity", opacity.getProgress() + 15).putBoolean("touch_controls", touch.isChecked()).putBoolean("show_fps", showFps.isChecked()).putString("sgdb_key", newKey).apply();
                    if (keyChanged && !newKey.isEmpty()) io.execute(() -> fetchArt(true));
                })
                .setNegativeButton("Close", null).show();
    }

    void gpuDriver() {
        List<Drivers.Driver> drivers = Drivers.list(this);
        String current = Drivers.selected(this);
        String[] labels = new String[drivers.size() + 1];
        String[] ids = new String[drivers.size() + 1];
        labels[0] = "System Vulkan driver (Qualcomm)";
        ids[0] = Drivers.SYSTEM;
        int selected = 0;
        for (int i = 0; i < drivers.size(); i++) {
            labels[i + 1] = drivers.get(i).label;
            ids[i + 1] = drivers.get(i).id;
            if (ids[i + 1].equals(current)) selected = i + 1;
        }
        new AlertDialog.Builder(this).setTitle("GPU driver")
                .setSingleChoiceItems(labels, selected, (d, w) -> {
                    Drivers.select(this, ids[w]);
                    BootLog.write(this, "GPU driver selected: " + labels[w]);
                    d.dismiss();
                    Toast.makeText(this, "Games will use: " + labels[w], Toast.LENGTH_SHORT).show();
                })
                .setPositiveButton("Import Turnip zip", (d, w) -> {
                    Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                    i.addCategory(Intent.CATEGORY_OPENABLE);
                    i.setType("*/*");
                    startActivityForResult(i, DRIVER);
                })
                .setNegativeButton("Close", null).show();
    }

    static void deleteTree(File file) {
        // Symbolic links are removed, never followed.
        if (file.isDirectory() && !java.nio.file.Files.isSymbolicLink(file.toPath())) {
            file.setWritable(true, true);
            file.setExecutable(true, true);
            File[] children = file.listFiles();
            if (children != null) for (File child : children) deleteTree(child);
        }
        file.delete();
    }

    @Override public boolean dispatchKeyEvent(KeyEvent e) {
        int key = e.getKeyCode();
        if ((e.getSource() & (InputDevice.SOURCE_GAMEPAD | InputDevice.SOURCE_DPAD)) != 0 && e.getAction() == KeyEvent.ACTION_DOWN && e.getRepeatCount() == 0) {
            if (key == KeyEvent.KEYCODE_DPAD_LEFT) { home.move(-1); return true; }
            if (key == KeyEvent.KEYCODE_DPAD_RIGHT) { home.move(1); return true; }
            if (key == KeyEvent.KEYCODE_BUTTON_A || key == KeyEvent.KEYCODE_DPAD_CENTER) { home.activate(); return true; }
            if (key == KeyEvent.KEYCODE_BUTTON_START) { settings(); return true; }
        }
        return super.dispatchKeyEvent(e);
    }
}

