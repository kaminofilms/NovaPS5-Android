#!/bin/bash
# Sourced by both the outer compositor session and its inner program session.
if [ "${1:-}" != run ] || [ "${2:-}" != /opt/novaps5/launch.sh ]; then
    echo "NOVA_ERROR: Refusing non-Kyty session: mode=${1:-missing} program=${2:-missing}" >&2
    return 64
fi
return 0
