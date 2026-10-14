#!/usr/bin/env python3
"""Checks a Nova PS5 native Android APK before it is handed out.

- signed with the CI test key (installs over earlier test builds)
- package/version, arm64-v8a only, the game activity in its own process
- every native library is AArch64, 16 KB aligned, and every DT_NEEDED is either inside the APK
  or an Android system library (no glibc, no Linux runtime)
- the entry points SDL's Java side and Nova's controller call exist
  verify_native_apk.py APK --sdk SDK [--ndk NDK]
"""
import argparse, os, pathlib, re, subprocess, sys, tempfile, zipfile

p = argparse.ArgumentParser()
p.add_argument('apk')
p.add_argument('--sdk', required=True)
p.add_argument('--ndk', default=os.environ.get('ANDROID_NDK_LATEST_HOME') or os.environ.get('ANDROID_NDK_HOME'))
p.add_argument('--version-name', default='0.7.6-android')
p.add_argument('--version-code', default='34')
a = p.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]
sdk = pathlib.Path(a.sdk)
bt = sorted((x for x in (sdk / 'build-tools').glob('3*') if re.fullmatch(r'[0-9.]+', x.name)),
            key=lambda x: [int(n) for n in x.name.split('.')])[-1]
readelf = pathlib.Path(a.ndk) / 'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf'
failures = []


def check(name, ok, detail=''):
    print(f"{'PASS' if ok else 'FAIL'} {name}{(': ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def out(*args):
    return subprocess.run([str(x) for x in args], capture_output=True, text=True, check=True).stdout


# Signature: the same certificate as the CI keystore.
certs = out(bt / 'apksigner', 'verify', '--print-certs', a.apk)
key = out('keytool', '-list', '-v', '-keystore', root / 'tools/ci/novaps5-ci-test.keystore', '-storepass', 'android', '-alias', 'novaps5dev')
apk_sha = re.search(r'certificate SHA-256 digest: ([0-9a-f]+)', certs)
key_sha = re.search(r'SHA256: ([0-9A-F:]+)', key)
check('signed with the Nova test key', apk_sha is not None and key_sha is not None and
      apk_sha.group(1) == key_sha.group(1).replace(':', '').lower(), certs[:200])

badging = out(bt / 'aapt', 'dump', 'badging', a.apk)
check('package', "package: name='com.kaminofilms.novaps5'" in badging)
check('version', f"versionCode='{a.version_code}'" in badging and f"versionName='{a.version_name}'" in badging)
check('arm64-v8a only', "native-code: 'arm64-v8a'" in badging)
tree = out(bt / 'aapt', 'dump', 'xmltree', a.apk, 'AndroidManifest.xml')
check('game activity in its own process', 'GameActivity' in tree and ':game' in tree)

SYSTEM = {'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libandroid.so', 'libvulkan.so', 'libOpenSLES.so',
          'libaaudio.so', 'libGLESv1_CM.so', 'libGLESv2.so', 'libGLESv3.so', 'libEGL.so', 'libnativewindow.so', 'libz.so', 'libjnigraphics.so',
          'libmediandk.so', 'libamidi.so'}
with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(a.apk) as z:
    libs = [n for n in z.namelist() if n.startswith('lib/')]
    check('no non-arm64 libraries', all(n.startswith('lib/arm64-v8a/') for n in libs), str(libs))
    names = {n.rsplit('/', 1)[1] for n in libs}
    for need in ['libSDL3.so', 'libmain.so', 'libnovafex.so']:
        check(f'{need} present', need in names)
    dex = b''.join(z.read(n) for n in z.namelist() if n.endswith('.dex'))
    for cls in [b'Lcom/kaminofilms/novaps5/GameActivity;', b'Lcom/kaminofilms/novaps5/MainActivity;',
                b'Lcom/kaminofilms/novaps5/NovaPad;', b'Lorg/libsdl/app/SDLActivity;']:
        check(f'class {cls.decode()}', cls in dex)
    exports = {}
    for n in libs:
        path = pathlib.Path(tmp) / n.rsplit('/', 1)[1]
        path.write_bytes(z.read(n))
        raw = path.read_bytes()
        check(f'{path.name} is AArch64 ELF', raw[:4] == b'\x7fELF' and raw[18:20] == b'\xb7\x00')
        dynamic = out(readelf, '-d', path)
        needed = re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', dynamic)
        missing = [x for x in needed if x not in names and x not in SYSTEM]
        check(f'{path.name} dependencies resolvable on Android', not missing, ', '.join(missing))
        symbols = out(readelf, '--dyn-syms', '-W', path)
        check(f'{path.name} has no glibc symbol versions', 'GLIBC_' not in symbols)
        exports[path.name] = {line.split()[-1].split('@')[0] for line in symbols.splitlines()
                              if ' UND ' not in line and len(line.split()) >= 8}
        segments = out(readelf, '-lW', path)
        aligns = [int(m, 16) for m in re.findall(r'^\s+LOAD\s+.*\s(0x[0-9a-f]+)$', segments, re.M)]
        check(f'{path.name} 16 KB page aligned', bool(aligns) and min(aligns) >= 0x4000, str(aligns))
    check('libmain exports the FPS counter entry',
          'Java_com_kaminofilms_novaps5_NovaPad_nativeFrames' in exports.get('libmain.so', set()))
    check('libmain exports SDL_main', 'SDL_main' in exports.get('libmain.so', set()))
    check('libmain exports the touch controller entry',
          'Java_com_kaminofilms_novaps5_NovaPad_nativeState' in exports.get('libmain.so', set()))
    # SDL registers its natives from JNI_OnLoad (RegisterNatives).
    check('libSDL3 exports JNI_OnLoad', 'JNI_OnLoad' in exports.get('libSDL3.so', set()))
    check('libnovafex exports only its API', all(s.startswith('_ZN7NovaFex') or s in ('', 'Name')
                                                  for s in exports.get('libnovafex.so', set()) if not s.startswith('Java_')),
          ', '.join(sorted(s for s in exports.get('libnovafex.so', set()) if not s.startswith('_ZN7NovaFex'))[:10]))
print('NOVA_NATIVE_APK:', 'ALL PASS' if not failures else f'{len(failures)} FAILED: ' + ', '.join(failures))
sys.exit(1 if failures else 0)
