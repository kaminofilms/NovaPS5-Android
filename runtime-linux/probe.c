#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <unistd.h>
#include <sys/mman.h>
#include <dlfcn.h>

typedef struct {uint32_t type; const void *next; const char *app; uint32_t av; const char *engine; uint32_t ev, api;} AppInfo;
typedef struct {uint32_t type; const void *next; uint32_t flags; const AppInfo *app; uint32_t layers; const char *const *layer; uint32_t extensions; const char *const *extension;} InstanceInfo;
int main(int argc, char **argv) {
  printf("NOVA_PROBE: x86-64 Linux process; page_size=%ld pid=%d\n", sysconf(_SC_PAGESIZE), getpid());
  if (argc>1 && !strcmp(argv[1],"--vulkan")) {
    void *library=dlopen("libvulkan.so.1",RTLD_NOW);
    if(!library){fprintf(stderr,"NOVA_ERROR: Vulkan guest loader: %s\n",dlerror());return 71;}
    int32_t (*create)(const InstanceInfo*,const void*,void**)=dlsym(library,"vkCreateInstance");
    int32_t (*enumerate)(void*,uint32_t*,void**)=dlsym(library,"vkEnumeratePhysicalDevices");
    void (*destroy)(void*,const void*)=dlsym(library,"vkDestroyInstance");
    if(!create||!enumerate||!destroy){fputs("NOVA_ERROR: Vulkan entrypoints missing\n",stderr);return 72;}
    AppInfo app={0,0,"Nova FEX preflight",1,"Nova",1,1u<<22};
    InstanceInfo info={1,0,0,&app,0,0,0,0};void *instance=0;int32_t result=create(&info,0,&instance);
    if(result){fprintf(stderr,"NOVA_ERROR: vkCreateInstance=%d\n",result);return 73;}
    uint32_t count=0;result=enumerate(instance,&count,0);destroy(instance,0);
    printf("NOVA_VULKAN: vkEnumeratePhysicalDevices=%d devices=%u; frame presentation UNVERIFIED\n",result,count);
    return result||!count?74:0;
  }
  if(argc>1 && !strcmp(argv[1],"--memory")) {
    const uintptr_t base=0x1000000000ULL;const size_t size=0xec00000000ULL;
    errno=0;void *p=mmap((void*)base,size,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_NORESERVE|MAP_FIXED_NOREPLACE,-1,0);int e=errno;
    printf("NOVA_MEMORY: address=0x%016lx size=0x%016lx result=%p errno=%d (%s); diagnostic only\n",(unsigned long)base,(unsigned long)size,p,e,strerror(e));
    if(p!=MAP_FAILED)munmap(p,size);
  }
  return 0;
}
