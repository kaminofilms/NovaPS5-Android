#!/usr/bin/env python3
"""Nova PS5 native Android APK (no DroidDeck): Java front end + SDL3 Java glue + native libraries.

Gradle-free: aapt2, javac, d8, zipalign, apksigner from the Android SDK.
  build-native-apk.py --sdk SDK --libs DIR --sdl-java DIR --keystore KS --output APK
                      --version-name 0.7.0-android --version-code 28
DIR holds the arm64-v8a .so files (libSDL3.so, libmain.so, libnovafex.so, ...).
"""
import argparse, hashlib, os, pathlib, re, shutil, subprocess, zipfile

p = argparse.ArgumentParser()
p.add_argument('--sdk', required=True)
p.add_argument('--libs', required=True)
p.add_argument('--sdl-java', required=True, help='SDL3 android-project/app/src/main/java')
p.add_argument('--keystore', required=True)
p.add_argument('--output', required=True)
p.add_argument('--version-name', required=True)
p.add_argument('--version-code', required=True)
a = p.parse_args()

root = pathlib.Path(__file__).resolve().parent
app = root / 'nova-android'
sdk = pathlib.Path(a.sdk).resolve()
out = pathlib.Path(a.output).resolve()
build = root / 'build' / 'nova-android'
shutil.rmtree(build, ignore_errors=True)
for d in ['classes', 'dex', 'src', 'res']:
    (build / d).mkdir(parents=True)


def newest(directory, pattern):
    found = sorted(directory.glob(pattern), key=lambda x: [int(n) if n.isdigit() else n for n in re.split(r'(\d+)', x.name)])
    if not found:
        raise SystemExit(f'missing {pattern} in {directory}')
    return found[-1]


bt = newest(sdk / 'build-tools', '3*')
platform = newest(sdk / 'platforms', 'android-3*') / 'android.jar'


def run(*args):
    subprocess.run([str(x) for x in args], check=True)


# Sources: Nova's, plus SDL's Java glue from the same SDL checkout the native library was built from.
shutil.copytree(app / 'src', build / 'src', dirs_exist_ok=True)
sdl_dst = build / 'src/org/libsdl/app'
shutil.copytree(pathlib.Path(a.sdl_java) / 'org/libsdl/app', sdl_dst)
activity = sdl_dst / 'SDLActivity.java'
text = activity.read_text()
# Kyty's main thread runs deep shader compilation; give it a real stack.
patched = text.replace('new Thread(new SDLMain(), "SDLThread")', 'new Thread(null, new SDLMain(), "SDLThread", 64L * 1024 * 1024)')
if patched == text:
    raise SystemExit('SDLActivity: SDLThread creation not found')
activity.write_text(patched)
for java in (build / 'src').rglob('*.java'):
    java.write_text(java.read_text().replace('@NOVA_VERSION_NAME@', a.version_name))

manifest = build / 'AndroidManifest.xml'
manifest.write_text((app / 'AndroidManifest.xml').read_text()
                    .replace('@NOVA_VERSION_CODE@', a.version_code).replace('@NOVA_VERSION_NAME@', a.version_name))

run(bt / 'aapt2', 'compile', '--dir', app / 'res', '-o', build / 'resources.zip')
run(bt / 'aapt2', 'link', '-o', build / 'unsigned.apk', '-I', platform, '--manifest', manifest, build / 'resources.zip',
    '--min-sdk-version', '33', '--target-sdk-version', '33', '--version-code', a.version_code, '--version-name', a.version_name)
sources = sorted(str(x) for x in (build / 'src').rglob('*.java'))
run('javac', '-nowarn', '-encoding', 'UTF-8', '-source', '8', '-target', '8', '-bootclasspath', platform,
    '-d', build / 'classes', *sources)
with zipfile.ZipFile(build / 'classes.jar', 'w') as jar:
    for f in sorted((build / 'classes').rglob('*.class')):
        jar.write(f, str(f.relative_to(build / 'classes')))
run(bt / 'd8', '--release', '--lib', platform, '--min-api', '33', '--output', build / 'dex', build / 'classes.jar')

libs = sorted(pathlib.Path(a.libs).glob('*.so'))
names = {x.name for x in libs}
for required in ['libSDL3.so', 'libmain.so', 'libnovafex.so']:
    if required not in names:
        raise SystemExit(f'missing native library {required}')
with zipfile.ZipFile(build / 'unsigned.apk', 'a', compression=zipfile.ZIP_DEFLATED) as apk:
    for dex in sorted((build / 'dex').glob('*.dex')):
        apk.write(dex, dex.name)
    for lib in libs:
        apk.write(lib, 'lib/arm64-v8a/' + lib.name)
run(bt / 'zipalign', '-P', '16', '-f', '4', build / 'unsigned.apk', build / 'aligned.apk')
key = pathlib.Path(a.keystore).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
run(bt / 'apksigner', 'sign', '--ks', key, '--ks-key-alias', 'novaps5dev', '--ks-pass', 'pass:android',
    '--key-pass', 'pass:android', '--out', out, build / 'aligned.apk')
run(bt / 'apksigner', 'verify', '--print-certs', out)
print('APK', out)
print('SHA256', hashlib.sha256(out.read_bytes()).hexdigest())
