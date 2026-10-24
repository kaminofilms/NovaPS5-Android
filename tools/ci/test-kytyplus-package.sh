#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
flags=()
if [[ ${SANITIZE:-0} == 1 ]]; then
    flags=(-fsanitize=address,undefined -fno-omit-frame-pointer -g)
fi
"${CXX:-g++}" -std=c++20 -DKYTY_HAS_ZLIB=1 -Werror=return-local-addr -Werror=format \
    "${flags[@]}" -I "$repo/native/pkg" \
    "$repo/native/pkg/package/pkgParser.cpp" "$repo/native/pkg/package/pfsParser.cpp" \
    "$repo/native/pkg/install.cpp" "$repo/native/pkg/package/tablePfs.cpp" "$repo/native/pkg/package/Decompressor.cpp" "$repo/tests/test_kytyplus_package.cpp" \
    -lz -ldl -pthread -o "$work/pkg-tests"
TMPDIR="$work" "$work/pkg-tests"
