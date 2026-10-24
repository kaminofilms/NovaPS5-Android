// Exact guest instructions used by clock_probe.cpp; compiled by the byte-regression test.
.text
.globl nova_clock_probe
nova_clock_probe:
 push %rbx
 lfence
 rdtsc
 shl $32,%rdx
 or %rdx,%rax
 mov %rax,0(%rdi)
 rdtscp
 shl $32,%rdx
 or %rdx,%rax
 mov %rax,8(%rdi)
 mov $0x15,%eax
 xor %ecx,%ecx
 cpuid
 mov %eax,16(%rdi)
 mov %ebx,20(%rdi)
 mov %ecx,24(%rdi)
 mov %edx,28(%rdi)
 pop %rbx
 ret
