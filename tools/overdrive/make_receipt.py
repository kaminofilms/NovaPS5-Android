#!/usr/bin/env python3
"""Record the exact staged ELF folder, after replacing its upstream SELF."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
folder = root / "PPSA99058"
assert (folder / "eboot.bin").read_bytes()[:7] == b"\x7fELF\x02\x01\x01"
assert json.loads((folder / "sce_sys/param.json").read_text())["titleId"] == "PPSA99058"
files = {}
for path in sorted(folder.rglob("*")):
    if path.is_file():
        with path.open("rb") as stream:
            files[str(path.relative_to(folder))] = hashlib.file_digest(stream, "sha256").hexdigest()
(root / "receipt.json").write_text(json.dumps({
    "title_id": "PPSA99058", "profile": "nova-overdrive-guest-experimental-1",
    "upstream": "ce407214eee01df732d859434085ebea1399ef70",
    "runtime_tested": False, "files": files,
    "upstream_receipt": "upstream-receipt.json"
}, indent=2) + "\n")
