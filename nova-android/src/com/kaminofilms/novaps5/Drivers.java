package com.kaminofilms.novaps5;

import android.content.Context;
import android.net.Uri;
import java.io.*;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import org.json.JSONObject;

/**
 * GPU drivers: Android's own Vulkan driver, or a Turnip build in the adrenotools zip format
 * (meta.json + the driver .so) loaded by Kyty through libadrenotools. One Turnip build for
 * Adreno 8xx ships in the APK; others can be imported.
 */
final class Drivers {
    static final String SYSTEM = "system";
    static final String BUNDLED_ASSET = "drivers/turnip-a8xx.zip";
    static final String BUNDLED_ID = "turnip-a8xx-bundled";
    static final String BUNDLED_REVISION = "4893e09fef65271c434965cb8d5380a783115ca9c481cce8dfb81ae8f7395efc";

    static final class Driver {
        final String id, label, library;
        final File dir;
        Driver(String id, String label, String library, File dir) { this.id = id; this.label = label; this.library = library; this.dir = dir; }
    }

    static File root(Context c) { return new File(c.getFilesDir(), "drivers"); }

    static String selected(Context c) { return c.getSharedPreferences("nova", 0).getString("gpu_driver", BUNDLED_ID); }

    static void select(Context c, String id) { c.getSharedPreferences("nova", 0).edit().putString("gpu_driver", id).apply(); }

    /** Installed Turnip drivers (the bundled one is unpacked on first use). */
    static List<Driver> list(Context c) {
        ensureBundled(c);
        ArrayList<Driver> out = new ArrayList<>();
        File[] dirs = root(c).listFiles();
        if (dirs != null) for (File d : dirs) {
            if (d.getName().startsWith(".")) continue;
            Driver driver = read(d);
            if (driver != null) out.add(driver);
        }
        return out;
    }

    static Driver read(File dir) {
        try {
            File meta = new File(dir, "meta.json");
            if (!meta.isFile()) return null;
            JSONObject json = new JSONObject(new String(java.nio.file.Files.readAllBytes(meta.toPath()), "UTF-8"));
            String library = json.optString("libraryName", "");
            if (library.isEmpty() || !new File(dir, library).isFile()) return null;
            String label = json.optString("name", dir.getName());
            String version = json.optString("driverVersion", "");
            return new Driver(dir.getName(), label + (version.isEmpty() ? "" : " · " + version), library, dir);
        } catch (Exception x) {
            return null;
        }
    }

    static Driver current(Context c) {
        String id = selected(c);
        if (SYSTEM.equals(id)) return null;
        for (Driver d : list(c)) if (d.id.equals(id)) return d;
        return null;
    }

    static String label(Context c) {
        Driver d = current(c);
        return d == null ? "System Vulkan driver" : d.label;
    }

    static synchronized void ensureBundled(Context c) {
        File dir = new File(root(c), BUNDLED_ID);
        File marker = new File(dir, ".nova-bundle-version");
        try {
            if (read(dir) != null && marker.isFile() && BUNDLED_REVISION.equals(
                    new String(java.nio.file.Files.readAllBytes(marker.toPath()), "UTF-8"))) return;
        } catch (IOException ignored) { /* Reinstall an incomplete bundle. */ }
        // Keep the stable ID so existing selections pick up the upgraded driver.
        // Extract and validate before replacing the installed copy.
        File stage = new File(root(c), ".bundled-installing");
        File backup = new File(root(c), ".bundled-backup");
        try (InputStream in = c.getAssets().open(BUNDLED_ASSET)) {
            // Recover if the process stopped between the two directory renames.
            if (!dir.exists() && backup.exists() && !backup.renameTo(dir))
                throw new IOException("Cannot recover the previous bundled driver");
            MainActivity.deleteTree(stage);
            unzip(in, stage);
            if (read(stage) == null) throw new IOException("Invalid bundled driver");
            java.nio.file.Files.write(new File(stage, ".nova-bundle-version").toPath(),
                    BUNDLED_REVISION.getBytes("UTF-8"));
            MainActivity.deleteTree(backup);
            boolean hadPrevious = dir.exists();
            if (hadPrevious && !dir.renameTo(backup))
                throw new IOException("Cannot back up the previous bundled driver");
            if (!stage.renameTo(dir)) {
                if (hadPrevious && !backup.renameTo(dir))
                    throw new IOException("Cannot restore the previous bundled driver");
                throw new IOException("Cannot install the new bundled driver");
            }
            MainActivity.deleteTree(backup);
            BootLog.write(c, "Bundled Turnip upgraded: 20261012 A8xx (compute mesh emulation)");
        } catch (Exception x) {
            BootLog.write(c, "Bundled Turnip unavailable: " + x);
        } finally {
            MainActivity.deleteTree(stage);
        }
    }

    static String importZip(Context c, Uri uri, String name) throws Exception {
        String id = "turnip-" + name.replaceAll("(?i)\\.zip$", "").replaceAll("[^A-Za-z0-9._-]", "_");
        File dir = new File(root(c), id);
        MainActivity.deleteTree(dir);
        try (InputStream in = c.getContentResolver().openInputStream(uri)) {
            if (in == null) throw new IOException("Cannot open the driver file");
            unzip(in, dir);
        }
        Driver d = read(dir);
        if (d == null) {
            MainActivity.deleteTree(dir);
            throw new IOException("Not an Android Turnip driver zip (needs meta.json and the driver .so). Linux (\"-Linux\") builds do not work here.");
        }
        select(c, d.id);
        return d.label;
    }

    static void unzip(InputStream input, File dir) throws IOException {
        dir.mkdirs();
        String base = dir.getCanonicalPath() + File.separator;
        try (ZipInputStream zip = new ZipInputStream(new BufferedInputStream(input))) {
            ZipEntry e;
            while ((e = zip.getNextEntry()) != null) {
                File f = new File(dir, e.getName()).getCanonicalFile();
                if (!f.getPath().startsWith(base)) throw new IOException("Driver archive path escapes its folder");
                if (e.isDirectory()) { f.mkdirs(); continue; }
                f.getParentFile().mkdirs();
                try (OutputStream out = new FileOutputStream(f)) {
                    byte[] buffer = new byte[65536];
                    int n;
                    while ((n = zip.read(buffer)) > 0) out.write(buffer, 0, n);
                }
            }
        }
    }
}

