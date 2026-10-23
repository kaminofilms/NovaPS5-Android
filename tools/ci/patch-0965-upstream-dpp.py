#!/usr/bin/env python3
"""Port uploaded KytyPS5 9dcff95 DPP writes without replacing Nova's runtime.
Upstream: https://github.com/KytyPS5/KytyPS5/commit/9dcff95e809ec43ba66f56648164070f4b16348f
The emitter's helper refactor is included to match the upstream write predicate.
"""
from pathlib import Path
import sys
root = Path(sys.argv[1])
translate = root / 'src/graphics/shader/recompiler/frontend/translate/Translate.cpp'
emitter = root / 'src/graphics/shader/recompiler/backend/spirv/spirvEmitterFlow.cpp'
cache = root / 'src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp'
source = translate.read_text()
anchor = """			const auto old = ir.GetVectorReg(reg);
			if (operand.dpp) {"""
replacement = """			const auto old = ir.GetVectorReg(reg);
			// Upstream 9dcff95: full-mask DPP writes need no old-register dependency.
			if (operand.dpp && (operand.dpp_row_mask != 0xfu || operand.dpp_bank_mask != 0xfu ||
			                    (!operand.dpp_bound_ctrl && !operand.dpp8))) {"""
if source.count(anchor) != 1:
    raise SystemExit('DPP translator anchor changed; refusing partial port')
emit = emitter.read_text()
old_function = 'uint32_t EmitDppWriteCondition(ValueEmitContext& ctx, const IR::DppMoveFlags& flags,\n                               uint32_t exec) {\n\tauto&      state      = ctx.state;\n\tconst auto lane       = EmitSubgroupLocalInvocationId(state);\n\tconst auto bank_shift = state.builder.AllocateId();\n\tconst auto row_shift  = state.builder.AllocateId();\n\tconst auto bank       = state.builder.AllocateId();\n\tconst auto row        = state.builder.AllocateId();\n\tconst auto bank_bit   = state.builder.AllocateId();\n\tconst auto row_bit    = state.builder.AllocateId();\n\tconst auto bank_hit   = state.builder.AllocateId();\n\tconst auto row_hit    = state.builder.AllocateId();\n\tconst auto bank_ok    = state.builder.AllocateId();\n\tconst auto row_ok     = state.builder.AllocateId();\n\tconst auto masks_ok   = state.builder.AllocateId();\n\tstate.builder.AddFunction(spv::OpShiftRightLogical, TypeU32(state), bank_shift, lane,\n\t                          ConstantU32(state, 2));\n\tstate.builder.AddFunction(spv::OpShiftRightLogical, TypeU32(state), row_shift, lane,\n\t                          ConstantU32(state, 4));\n\tstate.builder.AddFunction(spv::OpBitwiseAnd, TypeU32(state), bank, bank_shift,\n\t                          ConstantU32(state, 3));\n\tstate.builder.AddFunction(spv::OpBitwiseAnd, TypeU32(state), row, row_shift,\n\t                          ConstantU32(state, 3));\n\tstate.builder.AddFunction(spv::OpShiftLeftLogical, TypeU32(state), bank_bit,\n\t                          ConstantU32(state, 1), bank);\n\tstate.builder.AddFunction(spv::OpShiftLeftLogical, TypeU32(state), row_bit,\n\t                          ConstantU32(state, 1), row);\n\tstate.builder.AddFunction(spv::OpBitwiseAnd, TypeU32(state), bank_hit,\n\t                          ConstantU32(state, flags.bank_mask), bank_bit);\n\tstate.builder.AddFunction(spv::OpBitwiseAnd, TypeU32(state), row_hit,\n\t                          ConstantU32(state, flags.row_mask), row_bit);\n\tstate.builder.AddFunction(spv::OpINotEqual, TypeBool(state), bank_ok, bank_hit,\n\t                          ConstantU32(state, 0));\n\tstate.builder.AddFunction(spv::OpINotEqual, TypeBool(state), row_ok, row_hit,\n\t                          ConstantU32(state, 0));\n\tstate.builder.AddFunction(spv::OpLogicalAnd, TypeBool(state), masks_ok, bank_ok, row_ok);\n\tuint32_t writable = masks_ok;\n\tif (!flags.bound_control) {\n\t\tconst auto target  = EmitDppTargetLane(state, flags);\n\t\tconst auto bounded = state.builder.AllocateId();\n\t\tstate.builder.AddFunction(spv::OpLogicalAnd, TypeBool(state), bounded, writable,\n\t\t                          target.valid);\n\t\twritable = bounded;\n\t}\n\tconst auto result = state.builder.AllocateId();\n\tstate.builder.AddFunction(spv::OpLogicalAnd, TypeBool(state), result, exec, writable);\n\treturn result;\n}\n'
new_function = 'uint32_t EmitDppWriteCondition(ValueEmitContext& ctx, const IR::DppMoveFlags& flags,\n                               uint32_t exec) {\n\tauto&    state    = ctx.state;\n\tuint32_t writable = exec;\n\tuint32_t lane     = 0;\n\t// Each mask bit enables writes to one bank (4 lanes) or row (16 lanes); a full mask enables all.\n\tconst auto enable = [&](uint32_t mask, uint32_t group_shift) {\n\t\tif (mask == 0xfu) return;\n\t\tlane = lane != 0 ? lane : EmitSubgroupLocalInvocationId(state);\n\t\tconst auto group = EmitNative<spv::OpBitFieldUExtract, IR::Type::U32>(\n\t\t    state, lane, ConstantU32(state, group_shift), ConstantU32(state, 2));\n\t\tconst auto bit = EmitNative<spv::OpBitFieldUExtract, IR::Type::U32>(\n\t\t    state, ConstantU32(state, mask), group, ConstantU32(state, 1));\n\t\twritable = Binary(state, spv::OpLogicalAnd, TypeBool(state), writable,\n\t\t                  Binary(state, spv::OpINotEqual, TypeBool(state), bit, ConstantU32(state, 0)));\n\t};\n\tenable(flags.bank_mask, 2u);\n\tenable(flags.row_mask, 4u);\n\t// Only row shifts (0x101-0x10f, 0x111-0x11f) can vacate a lane; other controls always read one.\n\tconst bool row_shift = flags.control > 0x100u && flags.control < 0x120u &&\n\t                       flags.control != 0x110u;\n\tif (!flags.bound_control && row_shift) {\n\t\twritable = Binary(state, spv::OpLogicalAnd, TypeBool(state), writable,\n\t\t                  EmitDppTargetLane(state, flags).valid);\n\t}\n\treturn writable;\n}\n'
if emit.count(old_function) != 1:
    raise SystemExit('DPP emitter anchor changed; refusing partial port')
cache_source = cache.read_text()
if cache_source.count('NovaPC26:') != 1:
    raise SystemExit('DPP shader cache epoch anchor changed; refusing partial port')
# Validate all files before making any edit. Cache signature also keys shader-disk directories.
translate.write_text(source.replace(anchor, replacement, 1))
emitter.write_text(emit.replace(old_function, new_function, 1))
cache.write_text(cache_source.replace('NovaPC26:', 'NovaPC65DPP:', 1))
print('NOVA_UPSTREAM_DPP: 9dcff95 write-mask and old-operand fix applied')
