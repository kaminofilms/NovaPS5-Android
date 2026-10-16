#!/usr/bin/env python3
"""Configure a signature-checked Luna profile before the main ELF can execute."""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/loader/runtimeLinker.cpp'
s = p.read_text()
anchor = '\t\tCreateSymbolDatabase(program);'
if s.count(anchor) != 1 or 'NOVA_LUNA_CONSTRUCTOR_PROFILE' in s:
    raise SystemExit('NOVA_LUNA_CONSTRUCTOR_PROFILE: unexpected loader source')
hook = r'''
#if defined(KYTY_NOVA_FEX)
        // NOVA_LUNA_CONSTRUCTOR_PROFILE: loaded mapped ranges, before any guest
        // initializer or main code. Unknown builds reject without arming.
        const char* nova_title = std::getenv("NOVA_CACHE_TITLE_ID");
        if (!program->elf->IsShared() && nova_title && std::strcmp(nova_title, "PPSA36257") == 0) {
            (void)NovaFex::ConfigureLunaWatchpointProfile(program->base_vaddr, program->base_size);
        }
#endif
'''
p.write_text(s.replace(anchor, anchor + '\n' + hook, 1))
print('NOVA_LUNA_CONSTRUCTOR_PROFILE: signature-checked main-module setup applied')
