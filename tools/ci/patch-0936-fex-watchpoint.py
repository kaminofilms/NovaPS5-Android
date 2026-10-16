#!/usr/bin/env python3
"""Instrument only pinned FEX scalar StoreMem, leaving its store encoding intact."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
p = root / 'FEXCore/Source/Interface/Core/JIT/MemoryOps.cpp'
s = p.read_text()
assert 'Nova 0.9.36: scalar intents only' not in s, 'watchpoint patch already applied'
start = s.index('DEF_OP(StoreMem) {')
end = s.index('\nDEF_OP(', start + 1)
body = s[start:end]
anchor = '  const auto MemSrc = GenerateMemOperand(OpSize, MemReg, Op->Offset, Op->OffsetType, Op->OffsetScale);'
assert body.count(anchor) == 1
hook = r'''
  // Nova 0.9.36: scalar intents only. No callback for an empty registry.
  // x0..x3 are reserved FEX temporaries on Android, never RA operands.
  if (Op->Class == IR::RegClass::GPR && IR::OpSizeToSize(OpSize) <= 8) {
    static_assert(TMP_ABIARGS, "Nova watchpoints require the native Android ABI");
    // The pinned emitter lacks an FPSR enumerator. Architectural S3_3_C4_C4_1.
    constexpr auto FPSR = static_cast<ARMEmitter::SystemRegister>(
      ARMEmitter::GenSystemReg<0b11, 0b011, 0b0100, 0b0100, 0b001>);
    ARMEmitter::ForwardLabel NoWatchpoints;
    LoadConstant(ARMEmitter::Size::i64Bit, TMP1, reinterpret_cast<uintptr_t>(&NovaFexWatchpoint::enabled));
    ldar(TMP1.W(), TMP1);
    (void)cbz(ARMEmitter::Size::i32Bit, TMP1, &NoWatchpoints);

    // These operations do not change NZCV. Save FPCR/FPSR before FEX's spill
    // disables AFP; restore their exact incoming values after FEX's fill.
    sub(ARMEmitter::Size::i64Bit, ARMEmitter::Reg::rsp, ARMEmitter::Reg::rsp, 16);
    mrs(TMP1, ARMEmitter::SystemRegister::FPCR);
    str(TMP1, ARMEmitter::Reg::rsp, 0);
    mrs(TMP1, FPSR);
    str(TMP1, ARMEmitter::Reg::rsp, 8);
    PushDynamicRegs(TMP1);
    SpillStaticRegs(TMP1);

    // Capture all live operands before assigning any ABI argument register.
    // Inline immediates are byte offsets, matching GenerateMemOperand exactly.
    auto MaterializeExactStoreAddress = [&] {
      if (Op->Offset.IsInvalid()) {
        mov(TMP2, MemReg.X());
        return;
      }
      uint64_t Constant;
      if (IsInlineConstant(Op->Offset, &Constant)) {
        LoadConstant(ARMEmitter::Size::i64Bit, TMP1, Constant);
        add(ARMEmitter::Size::i64Bit, TMP2, MemReg, TMP1);
        return;
      }
      LOGMAN_THROW_A_FMT(Op->OffsetScale == 1 || Op->OffsetScale == IR::OpSizeToSize(OpSize), "Invalid scalar offset scale");
      const auto Index = GetReg(Op->Offset);
      const auto Shift = FEXCore::ilog2(Op->OffsetScale);
      switch (Op->OffsetType) {
      case IR::MemOffsetType::SXTX:
        add(ARMEmitter::Size::i64Bit, TMP2, MemReg, Index, ARMEmitter::ExtendedType::SXTX, Shift); break;
      case IR::MemOffsetType::UXTW:
        add(ARMEmitter::Size::i64Bit, TMP2, MemReg, Index, ARMEmitter::ExtendedType::UXTW, Shift); break;
      case IR::MemOffsetType::SXTW:
        add(ARMEmitter::Size::i64Bit, TMP2, MemReg, Index, ARMEmitter::ExtendedType::SXTW, Shift); break;
      default: FEX_UNREACHABLE;
      }
    };
    MaterializeExactStoreAddress();
    sub(ARMEmitter::Size::i64Bit, ARMEmitter::Reg::rsp, ARMEmitter::Reg::rsp, 16);
    str(TMP2, ARMEmitter::Reg::rsp, 0);
    str(GetZeroableReg(Op->Value).X(), ARMEmitter::Reg::rsp, 8);
    ldr(ARMEmitter::XReg::x0, ARMEmitter::Reg::rsp, 0);
    ldr(ARMEmitter::XReg::x1, ARMEmitter::Reg::rsp, 8);
    LoadConstant(ARMEmitter::Size::i64Bit, ARMEmitter::Reg::r2, IR::OpSizeToSize(OpSize));
    // GuestOpcode is FEX's own instruction mapping. Never use host PC as RIP.
    LOGMAN_THROW_A_FMT(!DebugData->GuestOpcodes.empty(), "StoreMem lacks guest instruction metadata");
    InsertGuestRIPMove(ARMEmitter::Reg::r3, Entry + DebugData->GuestOpcodes.back().GuestEntryOffset);
    LoadConstant(ARMEmitter::Size::i64Bit, ARMEmitter::Reg::r4, reinterpret_cast<uintptr_t>(&NovaFexWatchpoint::BeforeStore));
    if (!CTX->Config.DisableVixlIndirectCalls) {
      GenerateIndirectRuntimeCall<void, uint64_t, uint64_t, uint64_t, uint64_t>(ARMEmitter::Reg::r4);
    } else {
      blr(ARMEmitter::Reg::r4);
    }
    add(ARMEmitter::Size::i64Bit, ARMEmitter::Reg::rsp, ARMEmitter::Reg::rsp, 16);
    FillStaticRegs();
    PopDynamicRegs();
    ldr(TMP1, ARMEmitter::Reg::rsp, 0);
    msr(ARMEmitter::SystemRegister::FPCR, TMP1);
    ldr(TMP1, ARMEmitter::Reg::rsp, 8);
    msr(FPSR, TMP1);
    add(ARMEmitter::Size::i64Bit, ARMEmitter::Reg::rsp, ARMEmitter::Reg::rsp, 16);
    (void)Bind(&NoWatchpoints);
  }
'''
body = body.replace(anchor, hook + '\n' + anchor)
s = s[:start] + body + s[end:]
s = s.replace('#include "FEXCore/Core/X86Enums.h"', '#include "FEXCore/Core/X86Enums.h"\n#include "Interface/Core/JIT/DebugData.h"\n#include <FEXCore/Core/NovaFexWatchpoint.safe.hpp>', 1)
p.write_text(s)
print('NOVA_WATCHPOINT: scalar StoreMem intent instrumentation applied')
