/* SPDX-License-Identifier: GPL-2.0-or-later
 * Executed by NovaFEX as x86-64 guest code, never as ARM64 host code.
 * Host callbacks return a uint32 status or a bit-63-tagged Context pointer.
 */
.text
.global nova_fiber_begin, nova_fiber_host, nova_fiber_complete, nova_fiber_end
nova_fiber_begin:
    sub $24, %rsp
    stmxcsr (%rsp)
    fnstcw 4(%rsp)
    .byte 0x49, 0xbb
nova_fiber_host:
    .quad 0
    call *%r11
    test %rax, %rax
    js redirect
    ldmxcsr (%rsp)
    fldcw 4(%rsp)
    add $24, %rsp
    ret
redirect:
    btr $63, %rax
    /* Move off the departing stack before publishing that fiber as idle. */
    mov 48(%rax), %rsp
    and $-16, %rsp
    sub $16, %rsp
    mov %rax, (%rsp)
    .byte 0x49, 0xbb
nova_fiber_complete:
    .quad 0
    call *%r11
    mov (%rsp), %rax
    ldmxcsr 80(%rax)
    fldcw 84(%rax)
    mov 0(%rax), %rbx
    mov 8(%rax), %rbp
    mov 16(%rax), %r12
    mov 24(%rax), %r13
    mov 32(%rax), %r14
    mov 40(%rax), %r15
    mov 48(%rax), %rsp
    mov 56(%rax), %r11
    mov 64(%rax), %rdi
    mov 72(%rax), %rsi
    mov 88(%rax), %rax
    jmp *%r11
nova_fiber_end:
.section .note.GNU-stack,"",@progbits
