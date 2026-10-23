#!/usr/bin/env python3
"""Exercise the production guest filesystem and pinned-source profile edits."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prepare_guest", HERE / "prepare_guest.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def main(source):
    with tempfile.TemporaryDirectory(prefix="nova-overdrive-tests-") as temp:
        temp = Path(temp)
        source_copy = temp / "source"
        for name in ("ps5-react/tools/build_ps5.py", "ps5-react/tools/verify.py", "ps5-react/native/ps5/network_platform.cpp",
                     "ps5-react/native/ps5/filesystem_access.hpp", "ps5-react/native/ps5/payload_loader.hpp",
                     "app/state/update.js", "app/app.json"):
            dest = source_copy / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, dest)
        pem = temp / "cert.pem"
        pem.write_text("-----BEGIN CERTIFICATE-----\ntest fixture\n-----END CERTIFICATE-----\n")
        profile.prepare(source_copy, pem)
        native = source_copy / "ps5-react/native/ps5"
        b = (source_copy / "ps5-react/tools/build_ps5.py").read_text()
        compile(b, "build_ps5.py", "exec")
        verifier = (source_copy / "ps5-react/tools/verify.py").read_text()
        compile(verifier, "verify.py", "exec")
        assert 'guest["ca_sha256"] == digest(app / "nova/ca-bundle.pem")' in verifier
        assert 'helper["elf_sha256"] == digest(app / "lapy.elf")' in verifier
        check = next(node for node in ast.parse(verifier).body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        branch = next(node for node in check.body if isinstance(node, ast.If) and 'filesystemAccess' in ast.unparse(node.test))
        executable_check = compile(ast.Module(body=[branch], type_ignores=[]), 'verify-guest-block', 'exec')
        context = {'receipt': {'config': {'filesystemAccess': 'console'}},
                   'app': source_copy / 'app', 'param': {'downloadDataSize': '1048576'},
                   'TITLE': 'PPSA99058', 'json': json,
                   'digest': lambda path: hashlib.sha256(path.read_bytes()).hexdigest()}
        exec(executable_check, context)
        ca = source_copy / 'app/nova/ca-bundle.pem'
        ca.write_bytes(ca.read_bytes() + b'tampered')
        try:
            exec(executable_check, context)
            raise RuntimeError('Verifier accepted a different CA bundle')
        except AssertionError:
            pass
        assert 'access_client = None' in b
        assert 'sources.extend(compatibility_client /' in b
        assert 'ROOT / "native/ps5/elevation_transport.cpp"' not in b
        assert '/system/common/cert/CA_LIST.cer' not in (native / 'network_platform.cpp').read_text()
        assert json.loads((source_copy / 'app/nova/guest-profile.json').read_text())['runtime_tested'] is False
        update = (source_copy / 'app/state/update.js').read_text()
        probe = update.split('function useAvailableUpdate() {', 1)[1].split('async function installUpdate', 1)[0]
        assert 'setTimeout' not in probe and 'return null;' in probe
        try:
            profile.prepare(source_copy, pem)
            raise AssertionError('Applying the profile twice must fail')
        except ValueError:
            pass
        for name in ('app0', 'download0', 'temp0'):
            (temp / name).mkdir()
        test = temp / 'test.cpp'
        test.write_text(r'''
#include "filesystem_access.hpp"
#include "payload_loader.hpp"
#include <cassert>
#include <cstring>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
int main() {
  assert(!console_filesystem_accessible());
  assert(rmdir(NOVA_GUEST_TEMP_ROOT) == 0);
  initialize_filesystem_access();
  assert(!console_filesystem_accessible());
  assert(mkdir(NOVA_GUEST_TEMP_ROOT, 0700) == 0);
  initialize_filesystem_access();
  assert(console_filesystem_accessible());
  char out[2048];
  assert(resolve_filesystem_path("/data/homebrew/a", out, sizeof out));
  assert(std::string(out) == NOVA_GUEST_DATA_ROOT "/homebrew/a");
  assert(resolve_filesystem_path("/cache0/images", out, sizeof out));
  assert(std::string(out) == NOVA_GUEST_DATA_ROOT "/.cache/images");
  assert(resolve_filesystem_path("/app0/nova/ca-bundle.pem", out, sizeof out));
  assert(std::string(out) == NOVA_GUEST_APP_ROOT "/nova/ca-bundle.pem");
  assert(resolve_filesystem_path("/download0", out, sizeof out));
  assert(std::string(out) == NOVA_GUEST_DATA_ROOT);
  assert(resolve_filesystem_path("/temp0/job", out, sizeof out));
  assert(std::string(out) == NOVA_GUEST_TEMP_ROOT "/job");
  for (const char* bad : {"/data/../app0", "/download0/..", "/data//../x",
                         "/data2/file", "/system/file", "/mnt/usb0/a", "relative", ""})
    assert(!resolve_filesystem_path(bad, out, sizeof out));
  assert(!resolve_filesystem_path(nullptr, out, sizeof out));
  assert(!resolve_filesystem_path("/app0", nullptr, sizeof out));
  assert(!resolve_filesystem_path("/app0", out, 1));
  std::string error;
  assert(payload_loader::send("x", "", 0, "install", error) == -1);
  assert(error.find("unavailable") != std::string::npos);
  assert(payload_loader::receive(1, out, sizeof out) == -1);
  assert(!payload_loader::write(1, "x", 1));
}
''')
        command = ['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-I', str(native)]
        for macro, name in (('APP', 'app0'), ('DATA', 'download0'), ('TEMP', 'temp0')):
            command.append(f'-DNOVA_GUEST_{macro}_ROOT="{temp / name}"')
        command += [str(test), str(native / 'filesystem_access.cpp'), str(native / 'payload_loader.cpp'), '-o', str(temp / 'test')]
        subprocess.run(command, check=True)
        subprocess.run([str(temp / 'test')], check=True)
        assert not list(temp.rglob('.nova-overdrive-probe-*'))
    print('PASS: sandbox I/O proof, path mapping, traversal/bounds rejection, no console payload launch, source edits')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    main(parser.parse_args().source)
