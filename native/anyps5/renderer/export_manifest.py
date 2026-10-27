import base64
import hashlib
import pathlib
import re
import subprocess
import sys

# Follows AnyPS5's NidResolver (core/libs/nid/src/NidResolver.cpp):
#   name_nid_no_patch / name_nid_no_patch_cut  -> host-only, never a guest export
#   name_nid_postfix (optionally _nid_disambigN) -> guest export under the NID of the stripped name
#   plain name that also has a name_nid_postfix twin -> host-only (the postfix symbol is exported)
POSTFIX = '_nid_postfix'

def stripped(symbol):
    name = symbol[:-len(POSTFIX)] if symbol.endswith(POSTFIX) else symbol
    return re.sub(r'_nid_disambig\d+$', '', name)

def guest_exports(symbols):
    names = set(symbols)
    result = []
    for symbol in sorted(names):
        if symbol.endswith('_nid_no_patch') or symbol.endswith('_nid_no_patch_cut'):
            continue
        name = stripped(symbol)
        if name == symbol and symbol + POSTFIX in names:
            continue
        if '_nid_' in name:
            raise SystemExit(f'Unrecognised NID suffix in exported symbol {symbol}')
        if name.startswith('sceAgcDriver'):
            library = 'Graphics5Driver'
        elif name.startswith('sceAgc'):
            library = 'Graphics5'
        elif name.startswith('sceVideoOut'):
            library = 'VideoOut'
        else:
            continue
        result.append((symbol, name, library))
    return result

def nid(name):
    digest = hashlib.sha1(name.encode() + bytes.fromhex('518d64a635ded8c1e6b039b1c3e55230')).digest()[:8][::-1]
    return base64.b64encode(digest).decode().rstrip('=').replace('/', '-')

if __name__ == '__main__':
    symbols = subprocess.check_output([sys.argv[1], '--dynamic', '--defined-only', '--just-symbol-name', sys.argv[2]], text=True).splitlines()
    exports = guest_exports(symbols)
    if not exports:
        raise SystemExit('No actual AnyPS5 exports in the linked module')
    seen = {}
    for symbol, name, _ in exports:
        if nid(name) in seen:
            raise SystemExit(f'Duplicate guest NID for {symbol} and {seen[nid(name)]}')
        seen[nid(name)] = symbol
    pathlib.Path(sys.argv[3]).write_text(''.join(f'{{"{symbol}", "{nid(name)}", "{library}"}},\n' for symbol, name, library in exports))
    print(f'Generated {len(exports)} actual AnyPS5 native export bindings')
