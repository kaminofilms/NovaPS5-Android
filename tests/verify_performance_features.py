#!/usr/bin/env python3
"""Verify Android feature paths survived preprocessing and native linking.
String presence is not evidence of game resolution acceptance or FPS.
"""
import sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as apk:
    native=apk.read('lib/arm64-v8a/libmain.so')
for marker in [b'NOVA_RESOLUTION: Unity launch request',b'NOVA_RESOLUTION: actual render area',b'NOVA_BDA: changed-range synchronization enabled',b'queue_poll_wait',b'NOVA_RESOLUTION_RASTER:',b'NOVA_DEADCELLS:']:
    if marker not in native:raise SystemExit('Missing compiled native feature: '+marker.decode())
print('Native APK contains raster scaler, Dead Cells completion path, resolution trace, BDA optimization and queue-wait telemetry; FPS unverified')
