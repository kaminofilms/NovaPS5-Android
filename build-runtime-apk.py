#!/usr/bin/env python3
"""Build the Nova runtime preview using a verified, pinned DroidDeck platform APK.

The Nova Java and C++ code is compiled from source. The upstream session platform
is reused from its official 0.1.7 binary; matching source is in vendor/droiddeck-0.1.7.
The compile-only ABI declarations below NEVER enter the packaged DEX.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'droid-runtime/app/src/main'
PINS = {
    'platform.apk': (
        'https://github.com/The412Banner/DroidDeck/releases/download/0.1.7/DroidDeck-0.1.7.apk',
        'd7a578e09521f546f13ab6fb445dee3adc38fd12fd181ed44609796f9414eb55'),
    'apktool.jar': (
        'https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar',
        'dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423'),
    'commons-compress.jar': (
        'https://repo.maven.apache.org/maven2/org/apache/commons/commons-compress/1.27.1/commons-compress-1.27.1.jar',
        '293d80f54b536b74095dcd7ea3cf0a29bbfc3402519281332495f4420d370d16'),
}
CORE_SHA = 'd7cc6f357216fdb02f7f3a6fc50c450ffbe7a64c53a55130bebd9888eb0898dc'
CORE_URL = 'https://raw.githubusercontent.com/kaminofilms/NovaPS5-Android/ps5-boot-api/droid-runtime/app/src/main/assets/engine/kyty-windows-df5b9b9.zip'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            digest.update(data)
    return digest.hexdigest()


def fetch(path, url, expected, provided=None):
    if provided:
        if sha(provided) != expected:
            raise RuntimeError('Unexpected checksum for ' + str(provided))
        if provided != path:
            shutil.copyfile(provided, path)
    if not path.exists():
        temporary = path.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=60) as source, temporary.open('wb') as output:
            shutil.copyfileobj(source, output, 1048576)
        if sha(temporary) != expected:
            temporary.unlink()
            raise RuntimeError('Download checksum mismatch: ' + url)
        temporary.replace(path)
    if sha(path) != expected:
        raise RuntimeError('Unexpected checksum for ' + str(path))


def jar(classes, target):
    with zipfile.ZipFile(target, 'w') as archive:
        for path in sorted(classes.rglob('*.class')):
            archive.write(path, path.relative_to(classes).as_posix())


def prepare_platform(base, core=None):
    android = '{http://schemas.android.com/apk/res/android}'
    path = base / 'AndroidManifest.xml'
    tree = ET.parse(path)
    manifest = tree.getroot()
    manifest.set('package', 'com.kaminofilms.novaps5')
    app = manifest.find('application')
    app.set(android + 'label', 'NovaPs5')
    app.set(android + 'icon', '@drawable/novaps5_icon')
    for element in manifest.iter():
        for key, value in list(element.attrib.items()):
            if key == android + 'name' and value.startswith('.'):
                element.set(key, 'com.droiddeck.launcher' + value)
            if key in [android + 'authorities', android + 'taskAffinity'] or element.tag in ['permission', 'uses-permission']:
                if value.startswith('com.droiddeck.launcher'):
                    element.set(key, value.replace('com.droiddeck.launcher', 'com.kaminofilms.novaps5', 1))
    for activity in app.findall('activity'):
        if activity.get(android + 'name') == 'com.droiddeck.launcher.MainActivity':
            activity.set(android + 'name', 'com.kaminofilms.novaps5.MainActivity')
        if activity.get(android + 'name') == 'com.droiddeck.launcher.SessionActivity':
            attributes = dict(activity.attrib)
            attributes[android + 'name'] = 'com.kaminofilms.novaps5.NovaSessionActivity'
    ET.SubElement(app, 'activity', attributes)
    ET.register_namespace('android', 'http://schemas.android.com/apk/res/android')
    tree.write(path, encoding='utf-8', xml_declaration=True)
    path = base / 'apktool.yml'
    value = path.read_text()
    # Apktool 3 writes the manifest package from resourcesInfo while linking.
    # Pin it too, so the repack remains an upgrade of Nova rather than DroidDeck.
    if 'resourcesInfo:\n' not in value:
        raise RuntimeError('Pinned Apktool resource metadata changed')
    value = value.replace('resourcesInfo:\n', 'resourcesInfo:\n  packageName: com.kaminofilms.novaps5\n', 1)
    for key, setting in [('versionCode', '6'), ('versionName', '0.2.4-bootapi'), ('minSdkVersion', '28'), ('targetSdkVersion', '28')]:
        value = re.sub(r'(?m)^(  ' + key + r':).*$', r'\1 ' + setting, value)
    path.write_text(value)
    shutil.copyfile(ROOT / 'android/res/drawable/app_icon.xml', base / 'res/drawable/novaps5_icon.xml')
    shutil.copytree(APP / 'assets/engine', base / 'assets/engine', dirs_exist_ok=True)
    # SessionFiles refreshes this script from APK assets on every launch.
    # Protect that copy too, or it would overwrite RuntimeEngine's root guard.
    path = base / 'assets/linuxfs/usr/local/bin/bannerlator-session'
    value = path.read_text()
    anchor = 'shift || true\n'
    if anchor not in value:
        raise RuntimeError('Pinned compositor session entry changed')
    path.write_text(value.replace(anchor, anchor + '# NOVA_DIRECT_KYTY_ONLY\nsource /opt/novaps5/session-guard.sh "$mode" "${1:-}" || exit $?\n', 1))
    if core is not None:
        shutil.copyfile(core, base / 'assets/engine/kyty-windows-df5b9b9.zip')
    # Change app-ID/action constants only. Preserve class names, Kotlin metadata
    # and native JNI namespaces from the upstream platform.
    for directory in [base / 'smali', base / 'smali_classes2']:
        for path in directory.rglob('*.smali'):
            value = path.read_text()
            changed = re.sub(r'"com\.droiddeck\.launcher(?P<tail>\.[A-Z_]+)?"',
                lambda match: '"com.kaminofilms.novaps5' + (match.group('tail') or '') + '"', value)
            if changed != value:
                path.write_text(changed)
    path = base / 'smali_classes2/com/droiddeck/launcher/input/OnScreenControls.smali'
    value = path.read_text()
    for old, new in [('A', '×'), ('B', '○'), ('X', '□'), ('Y', '△')]:
        value = re.sub(r'(const-string\s+v\d+,\s*)"' + old + '"', r'\1"' + new + '"', value)
    path.write_text(value)
    path = base / 'smali_classes2/com/droiddeck/launcher/session/SessionService.smali'
    path.write_text(path.read_text().replace('"BL_FPS=0"', '"BL_FPS=60"'))
    path = base / 'smali_classes2/com/droiddeck/launcher/runtime/LinuxRuntime.smali'
    path.write_text(path.read_text().replace('"DroidDeck"', '"NovaPs5"'))
    path = base / 'smali_classes2/com/droiddeck/launcher/runtime/LinuxRuntimeInstaller$Release.smali'
    value = path.read_text()
    constructor = '.method constructor <init>(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;J)V'
    if constructor not in value:
        raise RuntimeError('Pinned installer constructor access changed; inspect the new platform')
    # Nova is in another package. The original package-private constructor throws
    # IllegalAccessError even though its descriptor matches the compile-time ABI.
    path.write_text(value.replace(constructor, constructor.replace('.method constructor', '.method public constructor'), 1))
    # The Nova subclass owns route validation and persistent guest boot feedback.
    path = base / 'smali_classes2/com/droiddeck/launcher/SessionActivity.smali'
    value = path.read_text()
    declaration = '.class public final Lcom/droiddeck/launcher/SessionActivity;'
    if declaration not in value:
        raise RuntimeError('Pinned session class declaration changed')
    path.write_text(value.replace(declaration, declaration.replace(' final ', ' '), 1))
    path = base / 'smali_classes2/com/droiddeck/launcher/ui/SessionOverlayKt.smali'
    value = path.read_text()
    if '"Steam is loading"' not in value:
        raise RuntimeError('Pinned loading overlay changed')
    path.write_text(value.replace('"Steam is loading"', '"Kyty is loading"'))
    path = base / 'res/values/arrays.xml'
    tree = ET.parse(path)
    hints = tree.getroot().find("string-array[@name='loading_hints']")
    hints.clear()
    hints.set('name', 'loading_hints')
    for hint in ['Nova starts the selected game directly through Kyty and ARM64 Wine/FEX.',
                 'Tap the boot status at the top to read the Kyty session log.',
                 '720p and 60 Hz are configuration targets; game compatibility is experimental.']:
        ET.SubElement(hints, 'item').text = hint
    tree.write(path, encoding='utf-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--jdk', type=Path, default=Path(os.environ.get('JAVA_HOME', '/usr')))
    parser.add_argument('--keystore', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-apk', type=Path)
    parser.add_argument('--apktool', type=Path)
    parser.add_argument('--compress-jar', type=Path)
    parser.add_argument('--windows-sdk', type=Path, default=Path('/usr/x86_64-w64-mingw32'),
                        help='MinGW Windows headers and import libraries used by the Wine memory bridge')
    parser.add_argument('--build-dir', type=Path, default=ROOT / 'build/runtime')
    parser.add_argument('--verify-dependencies-only', action='store_true')
    args = parser.parse_args()
    sdk, ndk, jdk, output = [x.resolve() for x in [args.sdk, args.ndk, args.jdk, args.output]]
    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    for name, provided in [('platform.apk', args.base_apk), ('apktool.jar', args.apktool), ('commons-compress.jar', args.compress_jar)]:
        fetch(build / name, *PINS[name], provided.resolve() if provided else None)
    core = APP / 'assets/engine/kyty-windows-df5b9b9.zip'
    if core.is_file():
        if sha(core) != CORE_SHA:
            raise RuntimeError('Incorrect pinned Kyty engine archive')
    else:
        core = build / 'kyty-windows-df5b9b9.zip'
        fetch(core, CORE_URL, CORE_SHA)
    if args.verify_dependencies_only:
        print('All four build dependencies verified by SHA-256')
        return
    sys.path.insert(0, str(ROOT / 'runtime-compat'))
    from build_compat import build as build_compat
    build_compat(ndk, args.windows_sdk.resolve(), core, APP / 'assets/engine', build / 'memory-compat')
    environment = dict(os.environ, JAVA_HOME=str(jdk))
    def run(*command):
        subprocess.run([str(item) for item in command], check=True, env=environment)
    java, javac = jdk / 'bin/java', jdk / 'bin/javac'
    bt = sdk / 'build-tools/36.0.0'
    platform = sdk / 'platforms/android-36/android.jar'
    llvm = ndk / 'toolchains/llvm/prebuilt/linux-x86_64'
    base = build / 'base'
    shutil.rmtree(base, ignore_errors=True)
    run(java, '-jar', build / 'apktool.jar', 'd', '-f', build / 'platform.apk', '-o', base)
    prepare_platform(base, core)
    # Apktool changes the tool mode; use a writable copy on hosted SDK installations.
    aapt = build / 'aapt2'
    shutil.copyfile(bt / 'aapt2', aapt)
    aapt.chmod(0o755)
    run(java, '-jar', build / 'apktool.jar', 'b', base, '--aapt', aapt, '-o', build / 'platform-rebuilt.apk')
    for name in ['stubs', 'stub-classes', 'nova-classes', 'dex']:
        shutil.rmtree(build / name, ignore_errors=True)
        (build / name).mkdir()
    # Method/constructor descriptors verified against the pinned platform DEX.
    declarations = {
        'com/droiddeck/launcher/SessionActivity.java': 'package com.droiddeck.launcher; public class SessionActivity extends android.app.Activity {}',
        'com/droiddeck/launcher/session/SessionState.java': 'package com.droiddeck.launcher.session; public final class SessionState {public static final SessionState INSTANCE=null; public boolean getRunning(){return false;} public String getMode(){return null;} public String getProgram(){return null;} public java.util.List<String> getProgramArgs(){return null;} public void setMode(String mode){} public java.io.File getLogFile(){return null;}}',
        'com/droiddeck/launcher/runtime/LinuxRuntime.java': 'package com.droiddeck.launcher.runtime; public final class LinuxRuntime {public static java.io.File rootDir(android.content.Context c){return null;} public static boolean isInstalled(android.content.Context c){return false;} public static java.io.File debugLogDir(){return null;}}',
        'com/droiddeck/launcher/runtime/LinuxRuntimeInstaller.java': 'package com.droiddeck.launcher.runtime; public final class LinuxRuntimeInstaller {public interface ProgressListener {void onProgress(String s,int n);} public static final class Release {public Release(String version,String url,String hash,long size){}} public static boolean install(android.content.Context c,Release r,ProgressListener l){return false;}}',
        'com/droiddeck/launcher/session/SessionService.java': 'package com.droiddeck.launcher.session; public final class SessionService {public static final String EXTRA_MODE="mode",MODE_RUN="run",EXTRA_PROGRAM="program",EXTRA_PROGRAM_ARGS="programArgs";}',
    }
    for name, declaration in declarations.items():
        path = build / 'stubs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(declaration)
    run(javac, '-source', '8', '-target', '8', '-classpath', platform, '-d', build / 'stub-classes', *sorted((build / 'stubs').rglob('*.java')))
    jar(build / 'stub-classes', build / 'stubs.jar')
    classpath = os.pathsep.join(str(x) for x in [platform, build / 'stubs.jar', build / 'commons-compress.jar'])
    run(javac, '-source', '8', '-target', '8', '-classpath', classpath, '-d', build / 'nova-classes', *sorted((APP / 'java/com/kaminofilms/novaps5').glob('*.java')))
    jar(build / 'nova-classes', build / 'nova.jar')
    run(bt / 'd8', '--release', '--min-api', '28', '--lib', platform, '--classpath', build / 'stubs.jar', '--classpath', build / 'commons-compress.jar', '--output', build / 'dex', build / 'nova.jar')
    native = APP / 'cpp/novadiag'
    run(llvm / 'bin/clang++', '--target=aarch64-linux-android28', '--sysroot=' + str(llvm / 'sysroot'),
        '-std=c++17', '-O2', '-g0', '-fPIC', '-shared', '-static-libstdc++', '-fvisibility=hidden',
        '-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384', '-Wl,--no-undefined',
        '-Wl,-soname,libnovaps5.so', '-I' + str(native),
        *[native / name for name in ['cpu_block.cpp', 'probe.cpp', 'renderer.cpp', 'jni.cpp']],
        '-lvulkan', '-landroid', '-llog', '-o', build / 'libnovaps5.so')
    run(llvm / 'bin/llvm-strip', '--strip-unneeded', build / 'libnovaps5.so')
    with zipfile.ZipFile(build / 'platform-rebuilt.apk') as source, zipfile.ZipFile(build / 'unsigned.apk', 'w') as target:
        for entry in source.infolist():
            if re.match(r'^META-INF/(MANIFEST\.MF|[^/]+\.(SF|RSA|DSA|EC))$', entry.filename, re.I):
                continue
            target.writestr(entry, source.read(entry.filename))
        target.write(build / 'dex/classes.dex', 'classes3.dex', compress_type=zipfile.ZIP_DEFLATED)
        target.write(build / 'libnovaps5.so', 'lib/arm64-v8a/libnovaps5.so', compress_type=zipfile.ZIP_DEFLATED)
    run(bt / 'zipalign', '-P', '16', '-f', '4', build / 'unsigned.apk', build / 'aligned.apk')
    if not args.keystore.is_file():
        raise RuntimeError('Preserve and supply your existing NovaPs5 development signing key')
    output.parent.mkdir(parents=True, exist_ok=True)
    run(bt / 'apksigner', 'sign', '--ks', args.keystore.resolve(), '--ks-key-alias', 'novaps5dev', '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', output, build / 'aligned.apk')
    run(bt / 'apksigner', 'verify', '--verbose', '--print-certs', output)
    run(bt / 'zipalign', '-c', '-P', '16', '4', output)
    run(bt / 'aapt', 'dump', 'badging', output)
    print('APK:', output)
    print('SHA256:', sha(output))


if __name__ == '__main__':
    main()
