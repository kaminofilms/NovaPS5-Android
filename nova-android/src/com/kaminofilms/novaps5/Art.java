package com.kaminofilms.novaps5;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/** Full-screen game backgrounds ("heroes") from SteamGridDB, with the user's own API key. */
final class Art {
    static final String KEY_PAGE = "https://www.steamgriddb.com/profile/preferences/api";
    private static final String API = "https://www.steamgriddb.com/api/v2/";

    static String key(Context c) { return c.getSharedPreferences("nova", 0).getString("sgdb_key", "").trim(); }

    static File file(Context c, GameStore.Entry e) {
        String id = (e.id != null && !e.id.isEmpty() && !e.id.startsWith("Unknown") ? e.id : e.name).replaceAll("[^A-Za-z0-9._-]", "_");
        return new File(new File(c.getFilesDir(), "art"), id + "-hero.img");
    }

    static Bitmap load(Context c, GameStore.Entry e, int maximum) {
        File f = file(c, e);
        if (!f.isFile() || f.length() == 0) return null;
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(f.getPath(), o);
        if (o.outWidth < 1 || o.outHeight < 1) return null;
        o.inSampleSize = 1;
        while (Math.max(o.outWidth, o.outHeight) / o.inSampleSize > maximum) o.inSampleSize *= 2;
        o.inJustDecodeBounds = false;
        return BitmapFactory.decodeFile(f.getPath(), o);
    }

    /** Downloads the hero for a game if it is not cached yet. True when a new image was saved. */
    static boolean fetch(Context c, GameStore.Entry e) throws Exception {
        String key = key(c);
        if (key.isEmpty() || e.name == null || e.name.isEmpty()) return false;
        File out = file(c, e);
        if (out.isFile()) return false;
        String term = e.name.replaceAll("[™®©]", "").replaceAll("\\s+", " ").trim();
        JSONArray found = get(key, API + "search/autocomplete/" + URLEncoder.encode(term, "UTF-8").replace("+", "%20")).optJSONArray("data");
        if (found == null || found.length() == 0) return false;
        long game = found.getJSONObject(0).getLong("id");
        JSONArray heroes = get(key, API + "heroes/game/" + game + "?types=static&nsfw=false").optJSONArray("data");
        if (heroes == null || heroes.length() == 0) return false;
        String url = heroes.getJSONObject(0).getString("url");
        out.getParentFile().mkdirs();
        File tmp = new File(out.getPath() + ".part");
        HttpURLConnection h = (HttpURLConnection) new URL(url).openConnection();
        h.setConnectTimeout(15000);
        h.setReadTimeout(30000);
        try (InputStream in = h.getInputStream(); OutputStream o = new FileOutputStream(tmp)) {
            byte[] b = new byte[65536];
            int n;
            long total = 0;
            while ((n = in.read(b)) > 0) {
                total += n;
                if (total > 20_000_000) throw new IOException("Image too large");
                o.write(b, 0, n);
            }
        } finally {
            h.disconnect();
        }
        return tmp.renameTo(out);
    }

    static JSONObject get(String key, String url) throws Exception {
        HttpURLConnection h = (HttpURLConnection) new URL(url).openConnection();
        h.setRequestProperty("Authorization", "Bearer " + key);
        h.setConnectTimeout(15000);
        h.setReadTimeout(20000);
        try {
            int code = h.getResponseCode();
            if (code == 401 || code == 403) throw new IOException("SteamGridDB rejected the API key");
            if (code != 200) throw new IOException("SteamGridDB HTTP " + code);
            try (InputStream in = h.getInputStream()) {
                return new JSONObject(new String(MainActivity.readAll(in, 4_000_000), "UTF-8"));
            }
        } finally {
            h.disconnect();
        }
    }

    static void clear(Context c) {
        File[] files = new File(c.getFilesDir(), "art").listFiles();
        if (files != null) for (File f : files) f.delete();
    }
}
