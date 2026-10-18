#!/usr/bin/env python3
"""Execute the production backend gate for default, explicit, and invalid selections."""
from pathlib import Path
import subprocess, tempfile
source = (Path(__file__).resolve().parents[1] / "native/anyps5/kyty_bridge.cpp").read_text()
start = source.index("bool Enabled() {")
end = source.index("\n}", start) + 2
function = source[start:end]
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    (p/"test.cpp").write_text('#include <cstdlib>\n#include <cstring>\n#include <cassert>\n'+function+r"""
int main() {
    unsetenv("NOVA_GPU_BACKEND"); assert(!Enabled());
    setenv("NOVA_GPU_BACKEND","kyty",1); assert(!Enabled());
    setenv("NOVA_GPU_BACKEND","anyps5",1); assert(Enabled());
    setenv("NOVA_GPU_BACKEND","",1); assert(!Enabled());
    setenv("NOVA_GPU_BACKEND","typo",1); assert(!Enabled());
}
""")
    subprocess.run(["c++","-std=c++17","-Wall","-Wextra","-Werror",str(p/"test.cpp"),"-o",str(p/"test")],check=True)
    subprocess.run([str(p/"test")],check=True)
print("NOVA_BACKEND_TEST: default Kyty, explicit AnyPS5 and invalid selection PASS")
