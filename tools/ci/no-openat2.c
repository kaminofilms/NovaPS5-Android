// Run a command with openat2() failing with ENOSYS, as it does for FEX under DroidDeck's proot.
// Usage: no-openat2 <program> [args...]
#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#ifndef __NR_openat2
#define __NR_openat2 437
#endif
int main(int argc, char** argv) {
	if (argc < 2) { fprintf(stderr, "usage: %s program [args]\n", argv[0]); return 2; }
	struct sock_filter filter[] = {
		BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
		BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_openat2, 0, 1),
		BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (ENOSYS & SECCOMP_RET_DATA)),
		BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
	};
	struct sock_fprog prog = {sizeof(filter) / sizeof(filter[0]), filter};
	if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog)) { perror("seccomp"); return 3; }
	execvp(argv[1], argv + 1);
	perror("execvp");
	return 4;
}
