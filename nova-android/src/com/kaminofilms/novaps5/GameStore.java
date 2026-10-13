package com.kaminofilms.novaps5;
import android.content.*;
import android.database.Cursor;
import android.graphics.*;
import android.net.Uri;
import android.provider.DocumentsContract;
import org.json.*;
import java.io.*;
import java.util.*;

final class GameStore {
    static final class Entry {
        String name,id,uri,eboot,icon,background,version;
        Bitmap cover,hero;
        JSONObject json()throws JSONException {JSONObject o=new JSONObject();o.put("name",name);o.put("id",id);o.put("uri",uri);o.put("eboot",eboot);o.put("icon",icon);o.put("background",background);o.put("version",version);return o;}
    }
    static final class Node {String id,name,type;Uri uri;Node(String i,String n,String t,Uri u){id=i;name=n;type=t;uri=u;}}
    final Context context;
    final ArrayList<Entry> entries=new ArrayList<>();
    GameStore(Context c){context=c;load();}
    synchronized ArrayList<Entry> snapshot(){return new ArrayList<>(entries);}
    synchronized void addAll(List<Entry> found)throws JSONException {for(Entry e:found){boolean exists=false;for(Entry old:entries)if(old.uri.equals(e.uri)){exists=true;break;}if(!exists)entries.add(e);}save();}
    synchronized void remove(Entry e)throws JSONException {entries.remove(e);save();}
    void load(){try{JSONArray a=new JSONArray(context.getSharedPreferences("nova",0).getString("games","[]"));for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);Entry e=new Entry();e.name=o.optString("name","Game");e.id=o.optString("id","Unknown title");e.uri=o.optString("uri");e.eboot=o.optString("eboot");e.icon=o.optString("icon");e.background=o.optString("background");e.version=o.optString("version");entries.add(e);}}catch(JSONException ignored){}}
    void save()throws JSONException {JSONArray a=new JSONArray();for(Entry e:entries)a.put(e.json());context.getSharedPreferences("nova",0).edit().putString("games",a.toString()).apply();}
    List<Node> children(Uri tree,String parent)throws Exception {
        ArrayList<Node> nodes=new ArrayList<>();Uri list=DocumentsContract.buildChildDocumentsUriUsingTree(tree,parent);
        try(Cursor c=context.getContentResolver().query(list,new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID,DocumentsContract.Document.COLUMN_DISPLAY_NAME,DocumentsContract.Document.COLUMN_MIME_TYPE},null,null,null)){
            if(c!=null)while(c.moveToNext()){String id=c.getString(0);nodes.add(new Node(id,c.getString(1),c.getString(2),DocumentsContract.buildDocumentUriUsingTree(tree,id)));if(nodes.size()>4096)throw new IOException("Folder contains too many files to scan in this alpha");}
        }return nodes;
    }
    List<Entry> scan(Uri tree)throws Exception {
        ArrayList<Entry> found=new ArrayList<>();ArrayDeque<String[]> queue=new ArrayDeque<>();queue.add(new String[]{DocumentsContract.getTreeDocumentId(tree),"0"});int visited=0;
        while(!queue.isEmpty()){
            if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Scan canceled");
            String[] task=queue.remove();int depth=Integer.parseInt(task[1]);if(++visited>512)throw new IOException("Scan limit reached. Select a smaller game folder.");
            List<Node> nodes=children(tree,task[0]);Node boot=null,sys=null;
            for(Node n:nodes){if("eboot.bin".equalsIgnoreCase(n.name))boot=n;if("sce_sys".equalsIgnoreCase(n.name)&&DocumentsContract.Document.MIME_TYPE_DIR.equals(n.type))sys=n;}
            if(boot!=null){
                Entry e=new Entry();e.eboot=boot.uri.toString();e.uri=DocumentsContract.buildDocumentUriUsingTree(tree,task[0]).toString();e.name=task[0].substring(task[0].lastIndexOf('/')+1);e.id="Unknown title";e.version="";e.icon="";e.background="";
                if(sys!=null){for(Node n:children(tree,sys.id)){
                    if("param.json".equalsIgnoreCase(n.name))try{
                        JSONObject p=new JSONObject(new String(readLimited(n.uri,1048576),"UTF-8"));JSONObject localized=p.optJSONObject("localizedParameters");
                        if(localized!=null){JSONObject title=localized.optJSONObject(localized.optString("defaultLanguage","en-US"));if(title==null)title=localized.optJSONObject("en-US");if(title==null){Iterator<String> keys=localized.keys();while(keys.hasNext()){JSONObject candidate=localized.optJSONObject(keys.next());if(candidate!=null&&candidate.has("titleName")){title=candidate;break;}}}if(title!=null)e.name=title.optString("titleName",e.name);}
                        if(p.has("titleName"))e.name=p.optString("titleName",e.name);if(e.name.isEmpty())e.name="Untitled game";e.id=p.optString("titleId",p.optString("contentId",e.id));e.version=p.optString("contentVersion",p.optString("applicationVersion",""));
                    }catch(Exception ignored){}
                    if("icon0.png".equalsIgnoreCase(n.name)||"icon0.jpg".equalsIgnoreCase(n.name))e.icon=n.uri.toString();
                    if("pic1.png".equalsIgnoreCase(n.name)||"pic1.jpg".equalsIgnoreCase(n.name))e.background=n.uri.toString();
                }}found.add(e);
            }else if(depth<6){for(Node n:nodes)if(DocumentsContract.Document.MIME_TYPE_DIR.equals(n.type)&&!"sce_sys".equals(n.name))queue.add(new String[]{n.id,Integer.toString(depth+1)});}
        }return found;
    }
    byte[] readLimited(Uri uri,int limit)throws Exception {try(InputStream s=context.getContentResolver().openInputStream(uri);ByteArrayOutputStream out=new ByteArrayOutputStream()){
        if(s==null)throw new IOException("Cannot open selected file");byte[] buffer=new byte[8192];int n;while((n=s.read(buffer))>0){if(out.size()+n>limit)throw new IOException("Metadata exceeds size limit");out.write(buffer,0,n);}return out.toByteArray();}}
    byte[] executableHeader(String uri)throws Exception {try(InputStream s=context.getContentResolver().openInputStream(Uri.parse(uri));ByteArrayOutputStream out=new ByteArrayOutputStream()){
        if(s==null)throw new IOException("Cannot open executable");byte[] buffer=new byte[8192];int n;while(out.size()<1048576&&(n=s.read(buffer,0,Math.min(buffer.length,1048576-out.size())))>0)out.write(buffer,0,n);return out.toByteArray();}}
    Bitmap image(String uri,int maximum){if(uri==null||uri.isEmpty())return null;try{
        BitmapFactory.Options o=new BitmapFactory.Options();o.inJustDecodeBounds=true;try(InputStream in=context.getContentResolver().openInputStream(Uri.parse(uri))){BitmapFactory.decodeStream(in,null,o);}
        if(o.outWidth<1||o.outHeight<1||o.outWidth>32768||o.outHeight>32768)return null;o.inSampleSize=1;while(Math.max(o.outWidth,o.outHeight)/o.inSampleSize>maximum)o.inSampleSize*=2;o.inJustDecodeBounds=false;
        try(InputStream in=context.getContentResolver().openInputStream(Uri.parse(uri))){return BitmapFactory.decodeStream(in,null,o);}
    }catch(Exception e){return null;}}
    void loadImages(){for(Entry e:snapshot()){if(e.cover==null)e.cover=image(e.icon,512);if(e.hero==null)e.hero=image(e.background,1280);}}
}
