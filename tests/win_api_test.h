/* Test-only Windows ABI declarations. Never compiled into shipped artifacts. */
#include <stddef.h>
#include <stdint.h>
#define WINAPI
#define __declspec(x)
typedef void *PVOID,*LPVOID,*HINSTANCE,*HMODULE,*HANDLE;
typedef const void *LPCVOID;
typedef size_t SIZE_T;
typedef uint32_t DWORD,ULONG;
typedef int32_t LONG;
typedef int BOOL;
typedef struct {PVOID BaseAddress,AllocationBase;DWORD AllocationProtect;
    SIZE_T RegionSize;DWORD State,Protect,Type;} MEMORY_BASIC_INFORMATION,*PMEMORY_BASIC_INFORMATION;
#define TRUE 1
#define PAGE_NOACCESS 1
#define MEM_COMMIT 0x1000
#define MEM_RESERVE 0x2000
#define MEM_FREE 0x10000
#define MEM_RELEASE 0x8000
#define ERROR_PROC_NOT_FOUND 127
#define STD_OUTPUT_HANDLE ((DWORD)-11)
HMODULE GetModuleHandleA(const char*);
HMODULE LoadLibraryA(const char*);
void *GetProcAddress(HMODULE,const char*);
DWORD GetEnvironmentVariableA(const char*,char*,DWORD);
BOOL WriteFile(HANDLE,const void*,DWORD,DWORD*,void*);
HANDLE GetStdHandle(DWORD);
HANDLE GetCurrentProcess(void);
LONG InterlockedCompareExchange(volatile LONG*,LONG,LONG);
LONG InterlockedExchange(volatile LONG*,LONG);
void Sleep(DWORD);
BOOL VirtualFree(PVOID,SIZE_T,DWORD);
void SetLastError(DWORD);
