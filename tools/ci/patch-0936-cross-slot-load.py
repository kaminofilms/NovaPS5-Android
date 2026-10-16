#!/usr/bin/env python3
"""Pinned FEX: keep guest EA for boundary-aware 128-bit vector loads."""
from pathlib import Path
import json
import sys

root = Path(sys.argv[1]) / 'FEXCore/Source/Interface'
p = root / 'IR/IR.json'
s = p.read_text()
anchor = '      "GPR = NovaXlat GPR:$Addr": {'
assert s.count(anchor) == 1
assert 'NovaLoad128' not in s
s = s.replace(anchor, '''      "FPR = NovaLoad128 GPR:$Addr, u8:$TSO": {
        "Desc": ["Nova: 128-bit load across separately backed guest slots."],
        "DestSize": "OpSize::i128Bit",
        "HasSideEffects": true
      },
''' + anchor)
json.loads(s)
p.write_text(s)

p = root / 'IR/Passes/NovaAddressTranslationPass.cpp'
s = p.read_text()
anchor = '    Rewrite(Node, T::Addr_Index, EA);'
assert s.count(anchor) == 1
s = s.replace(anchor, '''    if constexpr (std::is_same_v<T, IROp_LoadMem> || std::is_same_v<T, IROp_LoadMemTSO>) {
      if (Op->Class == RegClass::FPR && IROp->Size == OpSize::i128Bit) {
        Ref Value = Emit->_NovaLoad128(EA, std::is_same_v<T, IROp_LoadMemTSO>);
        Emit->ReplaceUsesWithAfter(Node, Value, Node);
        Emit->Remove(Node);
        return;
      }
    }
''' + anchor)
s = '#include <type_traits>\n' + s
p.write_text(s)

p = root / 'Core/JIT/MemoryOps.cpp'
s = p.read_text()
assert 'DEF_OP(NovaLoad128)' not in s
end = '\n} // namespace FEXCore::CPU'
assert s.count(end) == 1
hook = r'''

DEF_OP(NovaLoad128) {
  const auto Op = IROp->C<IR::IROp_NovaLoad128>();
  const auto Guest = GetReg(Op->Addr);
  const auto Dst = GetVReg(Node);
  static_assert(TMP_ABIARGS, "Nova cross-slot loads require the Android ABI");
  ARMEmitter::ForwardLabel Direct, Split, Done;

  // No arithmetic flags, calls, spills, guest register writes or speculative reads.
  // Guest remains live and unchanged. x0..x3/v0..v1 are FEX reserved temporaries.
  auto Translate = [&] {
    ARMEmitter::ForwardLabel Identity;
    ubfx(ARMEmitter::Size::i64Bit, TMP2, TMP1, 39, 25);
    (void)cbz(ARMEmitter::Size::i64Bit, TMP2, &Identity);
    ubfx(ARMEmitter::Size::i64Bit, TMP2, TMP1, FEXCore::Nova::kGuestVASlotShift, 17);
    LoadConstant(ARMEmitter::Size::i64Bit, TMP3, reinterpret_cast<uint64_t>(&FEXCore::Nova::GuestVATable[0]));
    add(ARMEmitter::Size::i64Bit, TMP3, TMP3, TMP2, ARMEmitter::ShiftType::LSL, 3);
    ldar(TMP2, TMP3);
    add(ARMEmitter::Size::i64Bit, TMP1, TMP1, TMP2);
    (void)Bind(&Identity);
  };

  // Low addresses use identity mappings; only the last 15 bytes of a translated
  // slot need the slow path. Translating the first byte alone is insufficient.
  ubfx(ARMEmitter::Size::i64Bit, TMP1, Guest, 39, 25);
  (void)cbz(ARMEmitter::Size::i64Bit, TMP1, &Direct);
  ubfx(ARMEmitter::Size::i64Bit, TMP1, Guest, 0, FEXCore::Nova::kGuestVASlotShift);
  add(ARMEmitter::Size::i64Bit, TMP1, TMP1, 15);
  (void)tbnz(TMP1, FEXCore::Nova::kGuestVASlotShift, &Split);
  (void)Bind(&Direct);
  mov(TMP1, Guest);
  Translate();
  ldr(Dst.Q(), TMP1, 0);
  (void)b(&Done);

  (void)Bind(&Split);
  movi(ARMEmitter::SubRegSize::i64Bit, VTMP1.Q(), 0);
  for (unsigned i = 0; i != 16; ++i) {
    add(ARMEmitter::Size::i64Bit, TMP1, Guest, i);
    Translate();
    ldrb(VTMP2, TMP1, 0);
    ins(ARMEmitter::SubRegSize::i8Bit, VTMP1.Q(), i, VTMP2.Q(), 0);
  }
  // A failing byte load faults normally, at the original guest instruction RIP.
  // The allocated destination vector is committed only after all reads succeed.
  mov(Dst.Q(), VTMP1.Q());
  (void)Bind(&Done);
  if (Op->TSO && CTX->IsVectorAtomicTSOEnabled()) {
    dmb(ARMEmitter::BarrierScope::ISHLD);
  }
}
'''
s = s.replace(end, hook + end)
p.write_text(s)
