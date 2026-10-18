import base64
import hashlib
import pathlib
import subprocess
import sys
symbols = subprocess.check_output([sys.argv[1], '--dynamic', '--defined-only', '--just-symbol-name', sys.argv[2]], text=True).splitlines()
entries = []
for symbol in sorted(set(symbols)):
    if symbol.startswith('sceAgcDriver'):
        library = 'Graphics5Driver'
    elif symbol.startswith('sceAgc'):
        library = 'Graphics5'
    elif symbol.startswith('sceVideoOut'):
        library = 'VideoOut'
    else:
        continue
    if '_nid_' in symbol:
        continue
    digest = hashlib.sha1(symbol.encode() + bytes.fromhex('518d64a635ded8c1e6b039b1c3e55230')).digest()[:8][::-1]
    nid = base64.b64encode(digest).decode().rstrip('=').replace('/', '-')
    entries.append(f'{{"{symbol}", "{nid}", "{library}"}},\n')
if not entries:
    raise SystemExit('No actual AnyPS5 exports in the linked module')
pathlib.Path(sys.argv[3]).write_text(''.join(entries))
print(f'Generated {len(entries)} actual AnyPS5 native export bindings')
