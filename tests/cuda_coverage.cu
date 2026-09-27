// SPDX-License-Identifier: GPL-2.0-only
#include <cuda_runtime.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

#define CUDA(call) do { cudaError_t e = (call); if (e != cudaSuccess) { \
    fprintf(stderr, "%s: %s\n", #call, cudaGetErrorString(e)); return 2; } } while (0)
__global__ void transform(uint64_t *p, size_t n) {
    for (size_t i = blockIdx.x * blockDim.x + threadIdx.x; i < n;
         i += size_t(blockDim.x) * gridDim.x)
        p[i] ^= 0xd1b54a32d192ed03ULL;
}
__global__ void fill(uint64_t *p, size_t n) {
    for (size_t i = blockIdx.x * blockDim.x + threadIdx.x; i < n;
         i += size_t(blockDim.x) * gridDim.x)
        p[i] = i ^ 0xa0761d6478bd642fULL;
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    const size_t mib = argc > 1 ? strtoul(argv[1], NULL, 10) : 1024;
    if (mib < 64 || mib > 16384) return 1;
    const size_t bytes = mib << 20, n = bytes / 8;
    uint64_t *host;
    if (posix_memalign((void **)&host, 2UL << 20, bytes)) return 1;
    madvise(host, bytes, MADV_HUGEPAGE);
    for (size_t i = 0; i < n; ++i) host[i] = i;
    size_t freebytes, total;
    CUDA(cudaMemGetInfo(&freebytes, &total));
    printf("cuda_memory: free=%zu total=%zu\n", freebytes, total);
    CUDA(cudaHostRegister(host, bytes, cudaHostRegisterMapped));
    int fd = open("/proc/self/pagemap", O_RDONLY);
    if (fd < 0) return 1;
    size_t in_test = 0, in_pool = 0;
    for (size_t i = 0; i < bytes; i += 4096) {
        uint64_t entry;
        if (pread(fd, &entry, 8, ((uintptr_t)host + i) / 4096 * 8) != 8) return 1;
        if (!(entry >> 63)) return 1;
        uint64_t pa = (entry & ((1ULL << 55) - 1)) * 4096;
        in_test += pa >= 0x2c0000000ULL && pa < 0x2c0200000ULL;
        in_pool += pa >= 0x280200000ULL && pa < 0x300000000ULL;
    }
    close(fd);
    printf("ordinary_malloc: bytes=%zu reclaimed_test_pages=%zu display_pool_pages=%zu\n", bytes, in_test, in_pool);
    uint64_t *gpu_host;
    CUDA(cudaHostGetDevicePointer((void **)&gpu_host, host, 0));
    transform<<<256,256>>>(gpu_host, n);
    CUDA(cudaGetLastError()); CUDA(cudaDeviceSynchronize());
    for (size_t i = 0; i < n; ++i)
        if (host[i] != (i ^ 0xd1b54a32d192ed03ULL)) {
            fprintf(stderr, "ordinary pinned-RAM CUDA mismatch at %zu\n", i); return 3;
        }
    CUDA(cudaHostUnregister(host));
    const size_t dbytes = 64UL << 20, dn = dbytes / 8;
    uint64_t *dev;
    CUDA(cudaMalloc(&dev, dbytes));
    fill<<<256,256>>>(dev, dn);
    CUDA(cudaGetLastError()); CUDA(cudaDeviceSynchronize());
    CUDA(cudaMemcpy(host, dev, dbytes, cudaMemcpyDeviceToHost));
    for (size_t i = 0; i < dn; ++i)
        if (host[i] != (i ^ 0xa0761d6478bd642fULL)) return 4;
    CUDA(cudaFree(dev));
    free(host);
    printf("PASS: ordinary pinned-RAM GPU writes/CPU reads and ordinary cudaMalloc GPU writes/copyback\n");
    if (!in_pool) { printf("NO RECLAIMED PAGE COVERAGE\n"); return 5; }
    return 0;
}
