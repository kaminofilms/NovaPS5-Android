#!/usr/bin/env python3
"""Verify Android feature paths survived preprocessing and native linking.
String presence is not evidence of game resolution acceptance or FPS.
"""
import sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as apk:
    native=apk.read('lib/arm64-v8a/libmain.so')
for marker in [b'NOVA_RESOLUTION: Unity launch request',b'NOVA_RESOLUTION: actual render area',b'NOVA_BDA: changed-range synchronization enabled',b'queue_poll_wait',b'NOVA_RESOLUTION_RASTER:',b'NOVA_DEADCELLS:',b'NOVA_SYNC: labels=fast',b'NOVA_GPU_LABELS:',b'eop_fast',b'NOVA_ASYNC_PIPELINES:',b'cleared_copies_skipped',b'NOVA_GUEST_PUTS: ',b'NOVA_FRAMEGEN: off (%s)',b'libnovalsfg.so',b'VK_ANDROID_external_memory_android_hardware_buffer',b'NOVA_GPU_TIME: scheduler=',b'NOVA_PASS_BREAK: window_ms=',b'NOVA_PASS_MERGE: barriers_elided=',b'NOVA_UE: /app0/',b'NOVA_VRS_REPORT: draws_2x2=',b'NOVA_GPU_TURBO: %s',b'NOVA_IMAGE_BARRIERS: read_to_read_elided=']:
    if marker not in native:raise SystemExit('Missing compiled native feature: '+marker.decode())
lsfg='lib/arm64-v8a/libnovalsfg.so' in zipfile.ZipFile(sys.argv[1]).namelist()
if not lsfg: raise SystemExit('Missing libnovalsfg.so (frame generation)')
print('Frame generation library: present')
print('Native APK contains raster scaler, Dead Cells completion path, resolution trace, BDA optimization and queue-wait telemetry; FPS unverified')
