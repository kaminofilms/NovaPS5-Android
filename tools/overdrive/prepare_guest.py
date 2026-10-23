#!/usr/bin/env python3
"""Apply a narrow Nova guest profile to Overdrive v1.0.9 source. No APK UI changes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

REVISION = "ce407214eee01df732d859434085ebea1399ef70"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Overdrive source anchor changed: {old[:100]!r}")
    return text.replace(old, new, 1)


def prepare(root, certificates):
    root = Path(root)
    framework = root / "ps5-react"
    build = framework / "tools/build_ps5.py"
    network = framework / "native/ps5/network_platform.cpp"
    update = root / "app/state/update.js"
    # Calculate every source edit before writing any of them.
    build_text = replace_once(build.read_text(),
        'access_client = dependency("filesystemHelperClient") if config.get("filesystemAccess") == "console" else None',
        'access_client = None  # Nova maps the title sandbox; no Lapy/elevation helper.')
    build_text = replace_once(build_text,
        'sources.extend(access_client / "examples/pacbrew-curl" / name for name in ("netdb.c",))',
        'sources.extend(compatibility_client / "examples/pacbrew-curl" / name for name in ("netdb.c",))')
    build_text = replace_once(build_text,
        'ROOT / "native/ps5/elevation_transport.cpp",', '')
    network_text = network.read_text()
    if network_text.count('/system/common/cert/CA_LIST.cer') != 2:
        raise ValueError("Expected exactly two certificate path anchors")
    network_text = network_text.replace('/system/common/cert/CA_LIST.cer', '/app0/nova/ca-bundle.pem')
    network_text = replace_once(network_text,
        'native networking requires successful console filesystem elevation',
        'Nova title sandbox is not ready')
    network_text = replace_once(network_text,
        'native networking cannot read the system certificate store',
        'Nova guest CA bundle is missing')
    update_text = update.read_text()
    start = update_text.index('  function useAvailableUpdate() {')
    end = update_text.index('  async function installUpdate(', start)
    update_text = update_text[:start] + '''  function useAvailableUpdate() {
    // Preserve the guest-specific executable; update the whole game folder through Nova.
    return null;
  }
''' + update_text[end:]
    pem = Path(certificates).read_bytes()
    if b"-----BEGIN CERTIFICATE-----" not in pem or len(pem) > 4 * 1024 * 1024:
        raise ValueError("--ca-bundle must be a public PEM certificate bundle")
    # resources are copied by the existing pinned builder.
    config_file = root / "app/app.json"
    config = json.loads(config_file.read_text())
    if "nova" in config.get("resources", []):
        raise ValueError("Nova guest profile already applied")
    config.setdefault("resources", []).append("nova")
    (root / "app/nova").mkdir()
    (root / "app/nova/ca-bundle.pem").write_bytes(pem)
    (root / "app/nova/guest-profile.json").write_text(json.dumps({
        "profile": "nova-overdrive-guest-experimental-1", "upstream": REVISION,
        "ca_sha256": hashlib.sha256(pem).hexdigest(),
        "runtime_tested": False,
        "notes": "PS5 guest; no Android replacement UI. Graphics/HLE boot remains unverified."
    }, indent=2) + "\n")
    build.write_text(build_text)
    network.write_text(network_text)
    update.write_text(update_text)
    config_file.write_text(json.dumps(config, indent=2) + "\n")
    shutil.copyfile(Path(__file__).with_name("filesystem_access.cpp"),
                    framework / "native/ps5/filesystem_access.cpp")
    shutil.copyfile(Path(__file__).with_name("payload_loader.cpp"),
                    framework / "native/ps5/payload_loader.cpp")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--ca-bundle", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.ca_bundle)
