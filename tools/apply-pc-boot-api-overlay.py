#!/usr/bin/env python3
"""Apply the reviewed PC boot API files to a complete pinned upstream checkout."""
import argparse
import json
import hashlib
import subprocess
from pathlib import Path

PIN = "df5b9b92be7dfd463b47756b707d6d356a9f0550"
FILES = [
    "CMakeLists.txt",
    "src/graphics/host_gpu/hostMemory.cpp",
    "src/graphics/host_gpu/hostMemory.h",
    "src/kernel/fileSystem.cpp",
    "src/kernel/fileSystem.h",
    "src/kernel/guestPipe.h",
    "src/kernel/memory.cpp",
    "src/libs/guestStdio.h",
    "src/libs/libC.cpp",
    "src/libs/libKernel.cpp",
    "src/loader/runtimeLinker.cpp",
    "src/loader/runtimeLinker.h",
    "tests/GuestPipeTests.cpp",
    "tests/HomebrewBootApiTests.cpp",
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    actual = subprocess.check_output(["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True).strip()
    if actual != PIN:
        raise SystemExit(f"Expected pinned Kyty {PIN}; found {actual}")
    patch = root / "patches" / "pc-boot-api.patch"
    subprocess.run(["git", "-C", str(args.checkout), "apply", "--check", str(patch)], check=True)
    subprocess.run(["git", "-C", str(args.checkout), "apply", str(patch)], check=True)
    print(json.dumps({"upstream_sha": actual, "overlay_files": FILES,
                      "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest()}, indent=2))

if __name__ == "__main__":
    main()
