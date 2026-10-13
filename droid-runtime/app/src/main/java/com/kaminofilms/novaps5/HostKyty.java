package com.kaminofilms.novaps5;

import android.content.Context;
import android.os.FileObserver;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/**
 * Runs Kyty outside proot.
 *
 * Under proot every signal a traced program receives stops it until proot resumes it. Kyty takes a
 * page-fault signal for each CPU write to memory the GPU caches watch, so in game it spent most of
 * its time in the kernel and threads could stay stopped. The session's launcher (launch.sh, inside
 * proot under gamescope) writes a ready-to-run script into {@link #dir} and renames it to
 * "request"; this watcher, in the app process, runs it with Android's shell. The script loads
 * Kyty with the runtime's own glibc loader, so it is the same program, just not traced. It talks
 * to gamescope's Xwayland, PulseAudio and the controller rings through paths that are the same on
 * both sides. "pid" (written by the script) and "exit" (written here) tell the launcher how it went.
 */
final class HostKyty {
    private static FileObserver observer;
    private static Process current;

    private HostKyty() {}

    static File dir(Context context) {return new File(context.getFilesDir(), "nova-host");}

    /** Starts the watcher once per app process; the launcher falls back to proot if it is absent. */
    static synchronized void watch(Context context) {
        if (observer != null) return;
        final Context app = context.getApplicationContext();
        final File dir = dir(app);
        if (!dir.isDirectory() && !dir.mkdirs()) {BootLog.write(app, "Host launch directory unavailable"); return;}
        @SuppressWarnings("deprecation")
        FileObserver created = new FileObserver(dir.getPath(), FileObserver.MOVED_TO | FileObserver.CLOSE_WRITE) {
            @Override public void onEvent(int event, String path) {
                if ("request".equals(path)) launch(app, dir);
            }
        };
        created.startWatching();
        observer = created;
        BootLog.write(app, "Host launch watcher ready: " + dir);
    }

    private static synchronized void launch(Context context, File dir) {
        File request = new File(dir, "request");
        File script = new File(dir, "run.sh");
        if (!request.isFile()) return;
        if (current != null && current.isAlive()) {
            BootLog.write(context, "Host launch: ending the previous Kyty");
            current.destroyForcibly();
        }
        if (!request.renameTo(script)) {BootLog.write(context, "Host launch: cannot take the request"); return;}
        try {
            ProcessBuilder builder = new ProcessBuilder("/system/bin/sh", script.getPath()).directory(dir);
            builder.environment().clear();
            builder.environment().put("PATH", "/system/bin");
            builder.redirectErrorStream(true);
            builder.redirectOutput(ProcessBuilder.Redirect.appendTo(new File(dir, "host.log")));
            final Process process = builder.start();
            current = process;
            BootLog.write(context, "Host launch: Kyty started outside proot");
            Thread waiter = new Thread(() -> {
                int status = -1;
                try {status = process.waitFor();} catch (InterruptedException ignored) {}
                write(new File(dir, "exit"), Integer.toString(status));
                BootLog.write(context, "Host launch: Kyty ended with status " + status);
            }, "nova-host-kyty");
            waiter.setDaemon(true);
            waiter.start();
        } catch (Exception x) {
            BootLog.write(context, "Host launch failed: " + x);
            write(new File(dir, "exit"), "127");
        }
    }

    private static void write(File file, String text) {
        File temp = new File(file.getPath() + ".tmp");
        try (FileOutputStream out = new FileOutputStream(temp)) {
            out.write((text + "\n").getBytes(StandardCharsets.UTF_8));
        } catch (Exception ignored) {
            return;
        }
        if (!temp.renameTo(file)) temp.delete();
    }

    /** The end of the host launch log, for the diagnostics report. */
    static String report(Context context) {
        File log = new File(dir(context), "host.log");
        if (!log.isFile()) return "(none)";
        try (java.io.RandomAccessFile in = new java.io.RandomAccessFile(log, "r")) {
            long size = in.length();
            byte[] bytes = new byte[(int) Math.min(size, 4096)];
            in.seek(size - bytes.length);
            in.readFully(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (Exception x) {
            return "(unreadable: " + x + ")";
        }
    }

    /** Tells the launcher where the runtime's files are on the Android side. */
    static void writeHostEnvironment(Context context, File engine, File root) throws Exception {
        String text = "NOVA_HOST_ROOT=" + root.getPath() + "\nNOVA_HOST_DIR=" + dir(context).getPath() + "\n";
        Files.write(new File(engine, "host-env").toPath(), text.getBytes(StandardCharsets.UTF_8));
    }
}
