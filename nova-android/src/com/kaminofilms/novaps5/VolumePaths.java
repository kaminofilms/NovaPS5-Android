package com.kaminofilms.novaps5;

import java.io.File;
import java.io.IOException;
import java.util.Map;

/** Filesystem identities shared by USB launch, SAF imports and library rescanning. */
final class VolumePaths {
    private VolumePaths() {}

    static boolean contains(File root, File file) {
        return file.equals(root) || file.getPath().startsWith(root.getPath() + File.separator);
    }

    static File resolve(Map<String, File> volumes, String documentId) throws IOException {
        int colon = documentId == null ? -1 : documentId.indexOf(':');
        if (colon < 1) throw new IOException("Invalid storage document ID");
        String id = documentId.substring(0, colon);
        File volume = null;
        for (Map.Entry<String, File> item : volumes.entrySet()) {
            if (item.getKey().equalsIgnoreCase(id)) { volume = item.getValue(); break; }
        }
        if (volume == null) throw new IOException("Storage volume " + id + " is unavailable. Reconnect the USB drive or SD card.");
        String relative = documentId.substring(colon + 1);
        if (relative.startsWith("/") || relative.indexOf('\0') >= 0)
            throw new IOException("Invalid game folder path");
        for (String part : relative.split("/")) {
            if (part.equals("..")) throw new IOException("Invalid game folder path");
        }
        File root = volume.getCanonicalFile();
        File target = new File(root, relative).getCanonicalFile();
        if (!contains(root, target)) throw new IOException("Game folder escapes the selected volume");
        return target;
    }

    static String documentId(Map<String, File> volumes, File directory) throws IOException {
        File target = directory.getCanonicalFile();
        File best = null;
        String id = null;
        for (Map.Entry<String, File> item : volumes.entrySet()) {
            File root = item.getValue().getCanonicalFile();
            if (contains(root, target) && (best == null || root.getPath().length() > best.getPath().length())) {
                best = root;
                id = item.getKey();
            }
        }
        if (best == null) throw new IOException("Game folder is not on an available storage volume");
        String relative = target.equals(best) ? "" : target.getPath().substring(best.getPath().length() + 1);
        return id + ":" + relative;
    }
}
