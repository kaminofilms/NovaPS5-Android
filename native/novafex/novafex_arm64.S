// Nova PS5 - AArch64 halves of the guest<->host bridges. See novafex.h.
// SPDX-License-Identifier: GPL-2.0-or-later

	.text

// void nova_call_native(GateBlock* block)
// Calls block->target with the SysV arguments the x86 gate spilled, mapped to AAPCS64:
//   rdi..r9 -> x0..x5, SysV stack slots 0,1 -> x6,x7, slots 2..9 -> AAPCS stack slots 0..7,
//   xmm0..7 -> q0..q7. Stores x0,x1,q0,q1 back as rax,rdx,xmm0,xmm1.
// GateBlock: gpr 0x00, xmm 0x30, stack_args 0xb0, target 0xb8, ret_gpr 0xc0, ret_xmm 0xd0.
	.globl nova_call_native
	.hidden nova_call_native
	.type nova_call_native, %function
	.p2align 4
nova_call_native:
	hint #34                        // bti c
	stp x29, x30, [sp, #-32]!
	mov x29, sp
	str x19, [sp, #16]
	mov x19, x0
	sub sp, sp, #64
	ldr x9, [x19, #0xb0]
	ldp x10, x11, [x9, #16]
	stp x10, x11, [sp, #0]
	ldp x10, x11, [x9, #32]
	stp x10, x11, [sp, #16]
	ldp x10, x11, [x9, #48]
	stp x10, x11, [sp, #32]
	ldp x10, x11, [x9, #64]
	stp x10, x11, [sp, #48]
	ldp x6, x7, [x9]
	ldp x0, x1, [x19, #0x00]
	ldp x2, x3, [x19, #0x10]
	ldp x4, x5, [x19, #0x20]
	ldp q0, q1, [x19, #0x30]
	ldp q2, q3, [x19, #0x50]
	ldp q4, q5, [x19, #0x70]
	ldp q6, q7, [x19, #0x90]
	ldr x16, [x19, #0xb8]
	blr x16
	stp x0, x1, [x19, #0xc0]
	stp q0, q1, [x19, #0xd0]
	add sp, sp, #64
	ldr x19, [sp, #16]
	ldp x29, x30, [sp], #32
	ret
	.size nova_call_native, . - nova_call_native

// Entered (via the SIGSEGV handler) when host code branched into guest code: x16 holds the
// guest target, x30 the host return address, x0-x7/q0-q7 the AAPCS arguments.
	.globl nova_guest_bridge_entry
	.hidden nova_guest_bridge_entry
	.type nova_guest_bridge_entry, %function
	.p2align 4
nova_guest_bridge_entry:
	hint #34                        // bti c
	stp x29, x30, [sp, #-0xd0]!
	mov x29, sp
	stp x0, x1, [sp, #0x10]
	stp x2, x3, [sp, #0x20]
	stp x4, x5, [sp, #0x30]
	stp x6, x7, [sp, #0x40]
	stp q0, q1, [sp, #0x50]
	stp q2, q3, [sp, #0x70]
	stp q4, q5, [sp, #0x90]
	stp q6, q7, [sp, #0xb0]
	mov x0, x16
	add x1, sp, #0x10
	bl nova_bridge_call
	ldp x0, x1, [sp, #0x10]
	ldp q0, q1, [sp, #0x50]
	ldp x29, x30, [sp], #0xd0
	ret
	.size nova_guest_bridge_entry, . - nova_guest_bridge_entry

	.section .note.GNU-stack, "", %progbits
