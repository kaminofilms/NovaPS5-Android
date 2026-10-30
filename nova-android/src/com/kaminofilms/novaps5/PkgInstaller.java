package com.kaminofilms.novaps5;

import android.content.Context;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.os.StatFs;
import java.io.File;
import java.io.IOException;
import java.util.UUID;

final class PkgInstaller {
    private static native String extract(int descriptor, String destination) throws IOException;

    static File install(Context context, Uri uri) throws IOException {
        try { System.loadLibrary("novapkg"); }
        catch (UnsatisfiedLinkError error) { throw new IOException("This build does not include the native PKG installer", error); }
        File storage = context.getExternalFilesDir("games");
        if (storage == null || (!storage.isDirectory() && !storage.mkdirs()))
            throw new IOException("Game installation storage is unavailable");
        GameStore.hideMedia(context, storage);
        String id = UUID.randomUUID().toString();
        File staging = new File(storage, ".install-" + id);
        File installed = new File(storage, "pkg-" + id);
        if (!staging.mkdir()) throw new IOException("Cannot create installation staging directory");
        boolean published = false;
        try (ParcelFileDescriptor descriptor = context.getContentResolver().openFileDescriptor(uri, "r")) {
            if (descriptor == null) throw new IOException("Cannot open the selected package");
            long size = descriptor.getStatSize();
            long available = new StatFs(storage.getPath()).getAvailableBytes();
            if (size < 512) throw new IOException("Choose a complete, seekable PKG file on device storage");
            if (size > (available - Math.min(available, 256L * 1024 * 1024)) / 2)
                throw new IOException("Insufficient installation space; allow at least twice the package size plus 256 MiB");
            String result = extract(descriptor.getFd(), staging.getCanonicalPath());
            if (result == null || !new File(result).getCanonicalFile().equals(new File(staging, "pfs_files").getCanonicalFile()))
                throw new IOException("Invalid package extraction result");
            if (!staging.renameTo(installed)) throw new IOException("Cannot publish the installed game");
            published = true;
            return new File(installed, "pfs_files");
        } finally {
            if (!published) remove(staging);
        }
    }

    private static void remove(File file) {
        if (file.isDirectory() && !java.nio.file.Files.isSymbolicLink(file.toPath())) {
            File[] children = file.listFiles();
            if (children != null) for (File child : children) remove(child);
        }
        file.delete();
    }
}
