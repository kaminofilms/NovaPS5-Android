#!/usr/bin/env python3
"""Verify the exact Kyty sources prepared for Android retain native guest views.

The existing guest-memory and ARM64 structured-SIMD tests exercise translation
and cross-slot behavior; the full Kyty Android compile exercises the HLE calls.
"""
import pathlib
import sys

kyty = pathlib.Path(sys.argv[1])
shader = (kyty / "src/graphics/shader/shader.cpp").read_text()
audio = (kyty / "src/libs/ajm.cpp").read_text()

expected_shader = [
    "ShaderMappedData native_data = data;",
    "native_data.input_semantics = GuestMemory::Ptr<ShaderSemantic>(",
    "(*g_shader_map)[addr] = {native_data, hash};",
]
expected_audio = [
    'info = GuestMemory::Ptr<AjmBatchInfo>(info, sizeof(*info));',
    'result = GuestMemory::Ptr<void>(result, result_size);',
    'result = GuestMemory::Ptr<void>(result, size);',
    'sideband_output = GuestMemory::Ptr<void>(sideband_output, sideband_output_size);',
    'native_input = view;',
    'native_output = view;',
    'NovaGuest::Copy(staged_input.data(), input, input_size);',
    'NovaGuest::Copy(output, staged_output.data(), std::min(output_size, result.output_written));',
    'result = GuestMemory::Ptr<void>(result, AJM_SIDEBAND_RESULT_SIZE + AJM_SIDEBAND_RESAMPLE_INFO_SIZE);',
]
for needle in expected_shader:
    assert needle in shader, f"shader hot path lost: {needle}"
for needle in expected_audio:
    assert needle in audio, f"audio hot path lost: {needle}"
assert shader.count("ShaderMappedData native_data = data;") == 1
assert audio.count("std::vector<uint8_t> staged_input;") == 1
assert audio.count("std::vector<uint8_t> staged_output;") == 1
# Do not overwrite the original guest ABI pointer, which must stay guest-relative.
assert 'info->last_good_job    = job;' in audio
print("PASS: shader semantic + AJM decode/sideband guest views preserved in compiled Kyty source")
