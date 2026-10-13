#!/usr/bin/env python3
"""Check the packaged Android ABI, including access flags missed by descriptor checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zipfile

CORE_SHA = 'd7cc6f357216fdb02f7f3a6fc50c450ffbe7a64c53a55130bebd9888eb0898dc'
RELEASE = 'Lcom/droiddeck/launcher/runtime/LinuxRuntimeInstaller$Release;'
CTOR = '<init>(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;J)V'
ACTIVITY_INHERITED = {'dispatchTouchEvent(Landroid/view/MotionEvent;)Z'}


class Dex:
    def __init__(self, data):
        self.data = data
        assert data[:4] == b'dex\n'
        count, offset = struct.unpack_from('<II', data, 0x38)
        self.strings = []
        for index in range(count):
            address = struct.unpack_from('<I', data, offset + 4 * index)[0]
            _, address = self.uleb(address)
            self.strings.append(data[address:data.index(0, address)].decode('utf-8', 'replace'))
        count, offset = struct.unpack_from('<II', data, 0x40)
        self.types = [self.strings[struct.unpack_from('<I', data, offset + 4 * index)[0]] for index in range(count)]
        count, offset = struct.unpack_from('<II', data, 0x48)
        prototypes = []
        for index in range(count):
            _, result, params = struct.unpack_from('<III', data, offset + 12 * index)
            arguments = []
            if params:
                size = struct.unpack_from('<I', data, params)[0]
                arguments = [self.types[struct.unpack_from('<H', data, params + 4 + 2 * i)[0]] for i in range(size)]
            prototypes.append('(' + ''.join(arguments) + ')' + self.types[result])
        count, offset = struct.unpack_from('<II', data, 0x58)
        self.references = []
        for index in range(count):
            owner, prototype, name = struct.unpack_from('<HHI', data, offset + 8 * index)
            self.references.append((self.types[owner], self.strings[name] + prototypes[prototype]))
        count, offset = struct.unpack_from('<II', data, 0x60)
        self.classes = {}
        self.definitions = {}
        for index in range(count):
            values = struct.unpack_from('<8I', data, offset + 32 * index)
            self.classes[self.types[values[0]]] = values[1]
            address = values[6]
            if not address:
                continue
            sizes = []
            for _ in range(4):
                value, address = self.uleb(address)
                sizes.append(value)
            for _ in range(sizes[0] + sizes[1]):
                _, address = self.uleb(address)
                _, address = self.uleb(address)
            for size in sizes[2:]:
                method = 0
                for _ in range(size):
                    delta, address = self.uleb(address)
                    flags, address = self.uleb(address)
                    _, address = self.uleb(address)
                    method += delta
                    self.definitions[self.references[method]] = flags

    def uleb(self, offset):
        value = shift = 0
        while True:
            byte = self.data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, offset
            shift += 7


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--json-output', type=Path)
    parser.add_argument('--linux-core', action='store_true')
    parser.add_argument('--core-exe-sha', help='Expected SHA-256 of rebuilt Kyty executable')
    parser.add_argument('--expect-inaccessible', action='store_true')
    args = parser.parse_args()
    data = args.apk.read_bytes()
    with zipfile.ZipFile(args.apk) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), 'Duplicate ZIP entries'
        assert archive.testzip() is None, 'Corrupt ZIP member'
        dexes = [Dex(archive.read(name)) for name in names if re.fullmatch(r'classes\d*\.dex', name)]
        classes, definitions = {}, {}
        for dex in dexes:
            assert not set(classes).intersection(dex.classes), 'Duplicate DEX classes'
            classes.update(dex.classes)
            definitions.update(dex.definitions)
        flags = definitions[(RELEASE, CTOR)]
        if args.expect_inaccessible:
            assert not flags & 1, 'The old constructor unexpectedly became public'
            print('CONFIRMED 0.2.0 regression: installer constructor is package-private, flags=' + hex(flags))
            return
        assert classes[RELEASE] & 1 and flags & 1, 'Installer Release constructor is inaccessible across packages'
        nova = Dex(archive.read('classes3.dex'))
        assert all(name.startswith('Lcom/kaminofilms/novaps5/') for name in nova.classes), 'Compile-only backend stubs were packaged'
        for owner, signature in nova.references:
            if owner.startswith('Lcom/droiddeck/'):
                # Public android.app.Activity methods that SessionActivity inherits without overriding
                # resolve to the framework at runtime (super calls from NovaSessionActivity).
                if owner == 'Lcom/droiddeck/launcher/SessionActivity;' and (owner, signature) not in definitions and signature in ACTIVITY_INHERITED:
                    continue
                assert (owner, signature) in definitions, 'Unresolved platform method: ' + owner + signature
                # NovaSessionActivity is a subclass, so protected lifecycle calls
                # are legal; all other external platform calls must be public.
                lifecycle = owner == 'Lcom/droiddeck/launcher/SessionActivity;' and signature in ['onCreate(Landroid/os/Bundle;)V', 'onDestroy()V']
                access = definitions[(owner, signature)]
                assert classes[owner] & 1 and (access & 1 or lifecycle and access & 4), 'Inaccessible platform method: ' + owner + signature
        session = 'Lcom/droiddeck/launcher/SessionActivity;'
        assert not classes[session] & 16, 'Nova cannot subclass a final platform session class'
        assert 'Lcom/kaminofilms/novaps5/NovaSessionActivity;' in nova.classes
        assert 'Kyty is loading' in set().union(*(set(dex.strings) for dex in dexes))
        assert 'Steam is loading' not in set().union(*(set(dex.strings) for dex in dexes))
        guard = archive.read('assets/engine/session-guard.sh')
        subprocess.run(['bash', '-n'], input=guard, check=True)
        session_script = archive.read('assets/linuxfs/usr/local/bin/bannerlator-session')
        assert b'source /opt/novaps5/session-guard.sh "$mode" "${1:-}" || exit $?' in session_script
        subprocess.run(['bash', '-n'], input=session_script, check=True)
        with tempfile.TemporaryDirectory(prefix='nova-route-check-') as directory:
            guard_path = Path(directory) / 'guard.sh'
            guard_path.write_bytes(guard)
            staged_script = session_script.replace(b'/opt/novaps5/session-guard.sh', str(guard_path).encode())
            for mode, target in [('steam', '/opt/novaps5/launch.sh'), ('run', '/usr/bin/steam')]:
                rejected = subprocess.run(['bash', '-s', '--', mode, target], input=staged_script, capture_output=True, timeout=5)
                assert rejected.returncode == 64 and b'NOVA_ERROR: Refusing non-Kyty session' in rejected.stderr
        if args.linux_core:
            import io,tarfile
            core=archive.read('assets/engine/kyty_emulator')
            assert core[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',core,18)[0]==62
            core_sha=hashlib.sha256(core).hexdigest()
            # RuntimeEngine re-verifies the installed core against this exact string.
            assert any(core_sha.encode() in archive.read(name) for name in names if re.fullmatch(r'classes\d*\.dex',name)),'core SHA-256 not compiled into RuntimeEngine'
            assert not any(b'@NOVA_LINUX_CORE_SHA256@' in archive.read(name) for name in names if name.endswith('.dex'))
            assert b'/lib64/ld-linux-x86-64.so.2' in core
            assert 'assets/engine/memory-compat.zip' not in names
            manifest=json.loads(archive.read('assets/engine/linux-runtime.tar.json'))
            payload=archive.read('assets/engine/linux-runtime.tar.gz')
            assert hashlib.sha256(payload).hexdigest()==manifest['archive_sha256']
            with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as runtime:
                for path,expected in manifest['files'].items():
                    assert hashlib.sha256(runtime.extractfile(path).read()).hexdigest()==expected,path
                for path,machine in [('host/usr/bin/FEX',183),('host/usr/bin/FEXServer',183),('guest/nova-probe',62),('guest/usr/lib/nova/libfakeinput.so',62),('host/usr/lib/aarch64-linux-gnu/fex-emu/HostThunks/libvulkan-host.so',183),('host/usr/share/fex-emu/GuestThunks/libvulkan-guest.so',62)]:
                    raw=runtime.extractfile(path).read();assert raw[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',raw,18)[0]==machine
                    if path.endswith(('FEX','FEXServer','nova-probe')):assert runtime.getmember(path).mode&0o111
            linux_launcher=archive.read('assets/engine/launch.sh')
            assert linux_launcher==archive.read('assets/engine/launch-linux.sh')
            assert b'nova "$core" --game "$game"' in linux_launcher
            assert b'"$wine"' not in linux_launcher and b'Z:' not in linux_launcher and b'.exe' not in linux_launcher
            helper=archive.read('assets/engine/fex-linux.sh')
            subprocess.run(['bash','-n'],input=helper,check=True)
            assert b'FEX_THUNKHOSTLIBS' in helper and b'FEX_ROOTFS' in helper
            # FEX concatenates file names onto FEX_APP_CONFIG_LOCATION; without the slash
            # the Vulkan thunk overlays are never loaded (vkCreateInstance=-9 on device).
            assert b'FEX_APP_CONFIG_LOCATION=${config%/}/' in helper
            assert b'NOVA_KYTY_REQ' in linux_launcher and b'NOVA_STAGE: $1 $2' in linux_launcher
            assert b'--inhibit-cache --library-path "$nova_guest_libs"' in helper
            with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as runtime:
                assert runtime.extractfile('guest/etc/ld.so.preload').read()==b''
                # The guest Vulkan loader is the FEX thunk itself (proot cannot redirect openat2()).
                assert runtime.extractfile('guest/usr/lib/x86_64-linux-gnu/libvulkan.so.1').read()==runtime.extractfile('host/usr/share/fex-emu/GuestThunks/libvulkan-guest.so').read()
                assert runtime.extractfile('guest/usr/lib/x86_64-linux-gnu/libasound.so.2').read()==runtime.extractfile('host/usr/share/fex-emu/GuestThunks/libasound-guest.so').read()
                # 0.4: native AArch64 Kyty with embedded FEXCore and its bundled loader.
                native=runtime.extractfile('native/kyty_emulator').read()
                assert native[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',native,18)[0]==183
                assert b'/opt/novaps5/linux-runtime/native/ld-linux-aarch64.so.1' in native
                assert runtime.getmember('native/kyty_emulator').mode&0o111
                for name in ['libnovafex.so','ld-linux-aarch64.so.1','libc.so.6','libstdc++.so.6']:
                    assert 'native/'+name in manifest['files'],name
            assert b'"$native/kyty_emulator" --game "$game"' in linux_launcher

        else:
            engine_bytes = archive.read('assets/engine/kyty-windows-df5b9b9.zip')
            if args.core_exe_sha:
                import io
                with zipfile.ZipFile(io.BytesIO(engine_bytes)) as engine:
                    assert hashlib.sha256(engine.read('kyty_emulator.exe')).hexdigest() == args.core_exe_sha.lower(), 'Rebuilt Kyty executable checksum mismatch'
            else:
                assert hashlib.sha256(engine_bytes).hexdigest() == CORE_SHA
            compatibility=json.loads(archive.read('assets/engine/memory-compat.json'))
            compatibility_bytes=archive.read('assets/engine/memory-compat.zip')
            assert hashlib.sha256(compatibility_bytes).hexdigest()==compatibility['archive_sha256']
            import io
            with zipfile.ZipFile(io.BytesIO(compatibility_bytes)) as overlay:
                assert set(overlay.namelist())=={'kyty_emulator-nova.exe','novamemory.dll','host-va-limit'}
                for name,expected in compatibility['files'].items():
                    assert hashlib.sha256(overlay.read(name)).hexdigest()==expected
                exe=overlay.read('kyty_emulator-nova.exe')
                assert b'novamemory.dll\0' in exe and b'NovaVirtualQuery\0' in exe and b'NovaVirtualAlloc2\0' in exe
                probe=overlay.read('host-va-limit')
                assert probe[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',probe,18)[0]==183
                for member in ['kyty_emulator-nova.exe','novamemory.dll']:
                    pe=overlay.read(member); at=struct.unpack_from('<I',pe,60)[0]
                    assert pe[at:at+4]==b'PE\0\0' and struct.unpack_from('<H',pe,at+4)[0]==0x8664
        launcher = archive.read('assets/engine/launch.sh')
        subprocess.run(['bash', '-n'], input=launcher, check=True)
        libraries = []
        four_k = []
        for name in names:
            if name.startswith('lib/') and name.endswith('.so'):
                raw = archive.read(name)
                assert name.startswith('lib/arm64-v8a/') and raw[:6] == b'\x7fELF\x02\x01'
                assert struct.unpack_from('<H', raw, 18)[0] == 183
                offset = struct.unpack_from('<Q', raw, 32)[0]
                size, count = struct.unpack_from('<HH', raw, 54)
                if any(struct.unpack_from('<Q', raw, offset + size * i + 48)[0] == 4096 for i in range(count) if struct.unpack_from('<I', raw, offset + size * i)[0] == 1):
                    four_k.append(name)
                libraries.append(name)
    report = {'filename': args.apk.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
        'installerConstructorFlags': hex(flags), 'platformMethodAccess': 'passed', 'zipIntegrity': 'passed',
        'arm64Libraries': len(libraries), 'inherited4KiBLibraries': four_k, 'ps5GameBootVerified': False, 'executionPath': 'linux-fex' if args.linux_core else 'windows-wine-fex'}
    if args.linux_core:report['linuxCoreSha256']=hashlib.sha256(core).hexdigest();report['linuxRuntimeSha256']=manifest['archive_sha256']
    if args.sdk:
        bt = args.sdk / 'build-tools/36.0.0'
        signature = subprocess.check_output([str(bt / 'apksigner'), 'verify', '--verbose', '--print-certs', str(args.apk)], text=True)
        assert 'Verified using v3 scheme (APK Signature Scheme v3): true' in signature
        report['signingCertificateSha256'] = re.search(r'certificate SHA-256 digest: ([0-9a-f]+)', signature).group(1)
        badging = subprocess.check_output([str(bt / 'aapt'), 'dump', 'badging', str(args.apk)], text=True)
        for line in badging.splitlines():
            if line.startswith('package:'):
                report['packageMetadata'] = line
        assert "name='com.kaminofilms.novaps5'" in badging
        if args.linux_core:
            assert "versionName='0.4.2-native'" in badging and "versionCode='17'" in badging and "native-code: 'arm64-v8a'" in badging
        subprocess.run([str(bt / 'zipalign'), '-c', '-P', '16', '4', str(args.apk)], check=True)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()


