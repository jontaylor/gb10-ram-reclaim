// SPDX-License-Identifier: GPL-2.0-only
/* Allocate and immediately release one 64 KiB scanout allocation. No mapping.
 * Run against stock and guarded driver to verify that the guard rejects both
 * explicit carveout and ISO allocation routes. */
#include <stdio.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <string.h>
#include "nvtypes.h"
#include "nvmisc.h"
#include "nvos.h"
#include "class/cl0080.h"

static int alloc_obj(int fd, NVOS21_PARAMETERS *a) {
    int rc = ioctl(fd, _IOWR('F', 0x2b, NVOS21_PARAMETERS), a);
    if (rc) { perror("RM ioctl"); return -1; }
    return 0;
}
int main(int argc, char **argv) {
    int fd = open("/dev/nvidiactl", O_RDWR), gpu = open("/dev/nvidia0", O_RDWR);
    int iso = argc > 1 && !strcmp(argv[1], "iso");
    if (fd < 0 || gpu < 0) return 2;
    if (ioctl(gpu, _IOWR('F', 201, int), &fd)) { perror("register"); return 2; }
    NVOS21_PARAMETERS a = {.hClass = NV01_ROOT_CLIENT};
    if (alloc_obj(fd, &a) || a.status) return 3;
    NvHandle root = a.hObjectNew;
    NV0080_ALLOC_PARAMETERS d = {0};
    a = (NVOS21_PARAMETERS){.hRoot=root, .hObjectParent=root, .hObjectNew=0x80000001,
        .hClass=NV01_DEVICE_0, .pAllocParms=(NvP64)(uintptr_t)&d, .paramsSize=sizeof(d)};
    if (alloc_obj(fd, &a) || a.status) return 4;
    NV_MEMORY_ALLOCATION_PARAMS m = {.owner=0xcafe, .size=65536, .alignment=65535};
    m.attr = DRF_DEF(OS32, _ATTR, _LOCATION, _PCI) |
             DRF_DEF(OS32, _ATTR, _COHERENCY, _WRITE_COMBINE);
    m.attr2 = iso ? DRF_DEF(OS32, _ATTR2, _ISO, _YES) :
                   DRF_DEF(OS32, _ATTR2, _USE_SCANOUT_CARVEOUT, _TRUE);
    a = (NVOS21_PARAMETERS){.hRoot=root, .hObjectParent=0x80000001, .hObjectNew=0x80000003,
        .hClass=0x3e, .pAllocParms=(NvP64)(uintptr_t)&m, .paramsSize=sizeof(m)};
    if (alloc_obj(fd, &a)) return 5;
    printf("route=%s status=0x%x offset=0x%llx size=%llu\n", iso?"ISO":"explicit",
           a.status, (unsigned long long)m.offset, (unsigned long long)m.size);
    close(gpu); close(fd);
    return 0;
}
