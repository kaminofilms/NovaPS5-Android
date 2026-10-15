#!/usr/bin/env python3
"""Apply bounded native aliases at measured Kyty guest-memory hot paths.

Run AFTER the 0.9.23 Android Kyty patch series and BEFORE CMake configuration.
Anchors are strict, so upstream changes fail safely rather than silently producing
a partial runtime. Host pointer aliases are never written back into guest ABI state.
"""
from __future__ import annotations

import pathlib
import sys

root = pathlib.Path(sys.argv[1])
shader_path = root / "src/graphics/shader/shader.cpp"
ajm_path = root / "src/libs/ajm.cpp"
shader = shader_path.read_text()
ajm = ajm_path.read_text()

def once(s: str, old: str, new: str, tag: str) -> str:
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"NOVA_HOTPATH: {tag} changed ({n} anchors), refusing partial patch")
    return s.replace(old, new, 1)

shader = once(
    shader,
    "\t(*g_shader_map)[addr] = {data, hash};",
    """\t// ShaderMappedData contains guest-owned semantic metadata. Translate the
\t// whole fixed-size view once on registration, rather than taking a SIGSEGV
\t// for every semantic field in PrepareProgram(PS). Do not rewrite the
\t// original guest pointers or flatten a view crossing a 1 GiB slot.
\tShaderMappedData native_data = data;
#if defined(KYTY_NOVA_FEX)
\tif (data.input_semantics != nullptr && data.num_input_semantics > 0 &&
\t    data.num_input_semantics <= 32u) {
\t\tnative_data.input_semantics = GuestMemory::Ptr<ShaderSemantic>(
\t\t    data.input_semantics, static_cast<uint64_t>(data.num_input_semantics) * sizeof(ShaderSemantic));
\t}
#endif
\t(*g_shader_map)[addr] = {native_data, hash};""",
    "shader semantic native view",
)

ajm = once(ajm, '#include "common/assert.h"', '#include "common/assert.h"\n#include "common/guestMemory.h"', "AJM guest memory include")
ajm = once(
    ajm,
    """static uint8_t* AjmReserveJob(AjmBatchInfo* info, size_t job_size) {
\tEXIT_NOT_IMPLEMENTED(info == nullptr);

\tif (info->offset + job_size > info->size) {""",
    """static uint8_t* AjmReserveJob(AjmBatchInfo* info, size_t job_size) {
\tEXIT_NOT_IMPLEMENTED(info == nullptr);
#if defined(KYTY_NOVA_FEX)
\t// The job cursor and capacity live in guest memory. Keep the fields
\t// (including the saved guest job address) unchanged; alias only the
\t// native HLE receiver for this call.
\tinfo = GuestMemory::Ptr<AjmBatchInfo>(info, sizeof(*info));
#endif

\tif (info->offset + job_size > info->size) {""",
    "AJM job receiver",
)
ajm = once(
    ajm,
    """\tstd::memset(result, 0, size);

\tif (size >= AJM_SIDEBAND_RESULT_SIZE) {""",
    """#if defined(KYTY_NOVA_FEX)
\tresult = GuestMemory::Ptr<void>(result, size);
#endif
\tstd::memset(result, 0, size);

\tif (size >= AJM_SIDEBAND_RESULT_SIZE) {""",
    "AJM result view",
)
ajm = once(
    ajm,
    """static void AjmWriteStreamResult(void* result, size_t result_size,
                                 const AjmDecodeResult& decode_result, bool multiple_frames) {
\tif (result == nullptr) {
\t\treturn;
\t}

\tAjmWriteResult(result, result_size, decode_result);""",
    """static void AjmWriteStreamResult(void* result, size_t result_size,
                                 const AjmDecodeResult& decode_result, bool multiple_frames) {
\tif (result == nullptr) {
\t\treturn;
\t}
#if defined(KYTY_NOVA_FEX)
\tresult = GuestMemory::Ptr<void>(result, result_size);
#endif

\tAjmWriteResult(result, result_size, decode_result);""",
    "AJM stream result",
)
ajm = once(
    ajm,
    """\tAjmWriteResult(result, result_size, decode_result);

\tauto* format_output = reinterpret_cast<AjmSidebandFormat*>(static_cast<uint8_t*>(result) +""",
    """#if defined(KYTY_NOVA_FEX)
\tresult = GuestMemory::Ptr<void>(result, result_size);
#endif
\tAjmWriteResult(result, result_size, decode_result);

\tauto* format_output = reinterpret_cast<AjmSidebandFormat*>(static_cast<uint8_t*>(result) +""",
    "AJM format result",
)
ajm = once(
    ajm,
    """\tdecoder->WriteCodecInfo(static_cast<uint8_t*>(result) + AJM_SIDEBAND_RESULT_SIZE,
\t                        result_size - AJM_SIDEBAND_RESULT_SIZE, decode_result);""",
    """#if defined(KYTY_NOVA_FEX)
\tresult = GuestMemory::Ptr<void>(result, result_size);
#endif
\tdecoder->WriteCodecInfo(static_cast<uint8_t*>(result) + AJM_SIDEBAND_RESULT_SIZE,
\t                        result_size - AJM_SIDEBAND_RESULT_SIZE, decode_result);""",
    "AJM codec info result",
)
ajm = once(
    ajm,
    """static void AjmWriteSideband(uint64_t flags, void* sideband_output, size_t sideband_output_size,
                             AjmDecoder* decoder, const AjmGaplessState* gapless,
                             const AjmDecodeResult& decode_result) {
\tif (sideband_output == nullptr || sideband_output_size == 0) {
\t\treturn;
\t}

\tAjmWriteResult(sideband_output, sideband_output_size, decode_result);""",
    """static void AjmWriteSideband(uint64_t flags, void* sideband_output, size_t sideband_output_size,
                             AjmDecoder* decoder, const AjmGaplessState* gapless,
                             const AjmDecodeResult& decode_result) {
\tif (sideband_output == nullptr || sideband_output_size == 0) {
\t\treturn;
\t}
#if defined(KYTY_NOVA_FEX)
\tsideband_output = GuestMemory::Ptr<void>(sideband_output, sideband_output_size);
#endif

\tAjmWriteResult(sideband_output, sideband_output_size, decode_result);""",
    "AJM sideband result",
)
ajm = once(
    ajm,
    """\treturn state->decoder->Decode(input, input_size, output, output_size, multiple_frames,
\t                              &state->gapless);
}""",
    """\t// Opus/FFmpeg parse packet bytes one at a time. Using an untranslated
\t// guest pointer here caused thousands of kernel signals per frame. Use a
\t// native alias when fully contained in one mapped guest slot. For buffers
\t// crossing a slot, stage a contiguous snapshot and copy only produced PCM
\t// back, preserving the decoder's returned byte counts and error codes.
\tconst void* native_input = input;
\tvoid* native_output = output;
#if defined(KYTY_NOVA_FEX)
\tstd::vector<uint8_t> staged_input;
\tstd::vector<uint8_t> staged_output;
\tif (NovaFex::GuestVAEnabled() && input != nullptr && input_size != 0 &&
\t    NovaGuest::IsHigh(input, input_size)) {
\t\tauto* view = GuestMemory::Ptr<const uint8_t>(static_cast<const uint8_t*>(input), input_size);
\t\tif (view != input) {
\t\t\tnative_input = view;
\t\t} else {
\t\t\tstaged_input.resize(input_size);
\t\t\tNovaGuest::Copy(staged_input.data(), input, input_size);
\t\t\tnative_input = staged_input.data();
\t\t}
\t}
\tif (NovaFex::GuestVAEnabled() && output != nullptr && output_size != 0 &&
\t    NovaGuest::IsHigh(output, output_size)) {
\t\tauto* view = GuestMemory::Ptr<uint8_t>(static_cast<uint8_t*>(output), output_size);
\t\tif (view != output) {
\t\t\tnative_output = view;
\t\t} else {
\t\t\tstaged_output.resize(output_size);
\t\t\tnative_output = staged_output.data();
\t\t}
\t}
#endif
\tauto result = state->decoder->Decode(native_input, input_size, native_output, output_size,
\t                                     multiple_frames, &state->gapless);
#if defined(KYTY_NOVA_FEX)
\tif (!staged_output.empty() && result.output_written != 0) {
\t\tNovaGuest::Copy(output, staged_output.data(), std::min(output_size, result.output_written));
\t}
#endif
\treturn result;
}""",
    "AJM decoder native views",
)
ajm = once(
    ajm,
    """\tAjmWriteResult(result, AJM_SIDEBAND_RESULT_SIZE + AJM_SIDEBAND_RESAMPLE_INFO_SIZE,
\t               decode_result);
\tif (result != nullptr) {
\t\tauto* resample""",
    """\tAjmWriteResult(result, AJM_SIDEBAND_RESULT_SIZE + AJM_SIDEBAND_RESAMPLE_INFO_SIZE,
\t               decode_result);
#if defined(KYTY_NOVA_FEX)
\tif (result != nullptr) {
\t\tresult = GuestMemory::Ptr<void>(result, AJM_SIDEBAND_RESULT_SIZE + AJM_SIDEBAND_RESAMPLE_INFO_SIZE);
\t}
#endif
\tif (result != nullptr) {
\t\tauto* resample""",
    "AJM resample result",
)

# Both files are written only once ALL expected anchors have been validated.
shader_path.write_text(shader)
ajm_path.write_text(ajm)
print("NOVA_HOTPATH: shader semantic table + AJM native views, decoding and sidebands applied")
