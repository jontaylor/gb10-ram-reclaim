// SPDX-License-Identifier: GPL-2.0
/* Explicit, boot-local experiment. Default inspection only. gb10_commit
 * permanently releases exactly 1022 MiB for this boot after validation, cached
 * memory tests, and acquisition of the guarded NVIDIA driver reference.
 * Never install in an automatic boot-loading mechanism. */
#include <linux/module.h>
#include <linux/mm.h>
#include <linux/mutex.h>
#include <linux/timekeeping.h>
#include <linux/utsname.h>
#include <linux/page_ref.h>
#include <linux/ioport.h>
#include <linux/memblock.h>
#include <asm/mmu.h>
#include <asm/pgtable.h>

extern struct mutex fixmap_lock;
extern phys_addr_t pgd_pgtable_alloc_init_mm(enum pgtable_type);
extern int __create_pgd_mapping_locked(pgd_t *, phys_addr_t, unsigned long,
                                      phys_addr_t, pgprot_t,
                                      phys_addr_t (*)(enum pgtable_type), int);
struct vmem_altmap;
extern void unmap_hotplug_range(unsigned long, unsigned long, bool, struct vmem_altmap *);
extern void free_empty_tables(unsigned long, unsigned long, unsigned long, unsigned long);
static struct mm_struct *const kernel_mm = &init_mm;
static struct mutex *const mapping_lock = &fixmap_lock;
static typeof(&__create_pgd_mapping_locked) const create_mapping = __create_pgd_mapping_locked;
static typeof(&pgd_pgtable_alloc_init_mm) const alloc_table = pgd_pgtable_alloc_init_mm;
static typeof(&unmap_hotplug_range) const unmap_range = unmap_hotplug_range;
static typeof(&free_empty_tables) const free_tables = free_empty_tables;
#define BASE 0x2c0200000ULL
#define BYTES (1022UL * 1024 * 1024)
static bool map_test;
static bool gb10_commit;
module_param(gb10_commit, bool, 0400);
static bool (*gb10_guard_fn)(void);
static typeof(&memblock_clear_nomap) const clear_nomap = memblock_clear_nomap;
static typeof(&memblock_mark_nomap) const mark_nomap = memblock_mark_nomap;
static struct resource reclaimed = {
    .name = "System RAM (GB10 experiment)", .start = BASE, .end = BASE + BYTES - 1,
    .flags = IORESOURCE_SYSTEM_RAM | IORESOURCE_BUSY,
};
static unsigned long expires;
module_param(map_test, bool, 0400);
module_param(expires, ulong, 0400);

static bool mapped(unsigned long va)
{
    pgd_t *pgd = pgd_offset_pgd(kernel_mm->pgd, va);
    p4d_t *p4d;
    pud_t *pud;
    pmd_t *pmd;
    pte_t *pte;
    if (pgd_none(READ_ONCE(*pgd))) return false;
    if (pgd_bad(READ_ONCE(*pgd))) return true;
    p4d = p4d_offset(pgd, va);
    if (p4d_none(READ_ONCE(*p4d))) return false;
    if (p4d_bad(READ_ONCE(*p4d))) return true;
    pud = pud_offset(p4d, va);
    if (pud_none(READ_ONCE(*pud))) return false;
    if (pud_leaf(READ_ONCE(*pud)) || pud_bad(READ_ONCE(*pud))) return true;
    pmd = pmd_offset(pud, va);
    if (pmd_none(READ_ONCE(*pmd))) return false;
    if (pmd_leaf(READ_ONCE(*pmd)) || pmd_bad(READ_ONCE(*pmd))) return true;
    pte = pte_offset_kernel(pmd, va);
    return !pte_none(READ_ONCE(*pte));
}

static void clean_invalidate(unsigned long start, unsigned long end)
{
    unsigned long a;
    for (a = start; a < end; a += 16) {
        asm volatile("dc civac, %0" : : "r" (a) : "memory");
        if (!(a & ((1UL << 20) - 1))) cond_resched();
    }
    asm volatile("dsb sy" : : : "memory");
}

static int __init probe_init(void)
{
    unsigned long pfn, va = (unsigned long)__va(BASE), i, pass;
    u64 *p = (void *)va, now = ktime_get_real_seconds();
    int ret = 0;
    bool resource_added = false, nomap_cleared = false;
    unsigned long total_before = totalram_pages();
    if (strcmp(init_utsname()->release, "6.17.0-1032-nvidia") || PAGE_SHIFT != 12)
        return -EINVAL;
    if (!expires || expires < now || expires - now > 120)
        return -EPERM;
    for (pfn = BASE >> PAGE_SHIFT; pfn < (BASE + BYTES) >> PAGE_SHIFT; ++pfn) {
        if (!pfn_valid(pfn) || pfn_is_map_memory(pfn) ||
            !PageReserved(pfn_to_page(pfn)) || page_ref_count(pfn_to_page(pfn)) != 1 ||
            mapped((unsigned long)__va(pfn << PAGE_SHIFT))) {
            pr_err("gb10_reclaim_right: unexpected page state\n");
            return -EINVAL;
        }
    }
    pr_info("gb10_reclaim_right: kernel page-table inspection PASS: all %lu pages reserved and absent from direct map\n", BYTES >> PAGE_SHIFT);
    if (!map_test && !gb10_commit) return 0;
    if (gb10_commit) {
        gb10_guard_fn = (void *)__symbol_get("gb10_display_carveout_disabled");
        if (!gb10_guard_fn || !gb10_guard_fn()) {
            if (gb10_guard_fn) __symbol_put("gb10_display_carveout_disabled");
            pr_err("gb10_reclaim_right: guarded NVIDIA driver required\n");
            return -EPERM;
        }
    }
    /* Userspace must unload NVIDIA and block autoload before enabling writes. */
    {
        void *nv = __symbol_get("nvidia_p2p_get_pages");
        if (nv) { __symbol_put("nvidia_p2p_get_pages"); if (!gb10_commit) return -EBUSY; }
    }
    mutex_lock(mapping_lock);
    ret = create_mapping(kernel_mm->pgd, BASE, va, BYTES, PAGE_KERNEL, alloc_table, 7);
    mutex_unlock(mapping_lock);
    if (ret) goto unmap;
    for (i = 0; i < BYTES; i += PAGE_SIZE)
        if (!mapped(va + i)) { ret = -EFAULT; goto unmap; }
    for (pass = 0; pass < 4; ++pass) {
        u64 seed = (pass + 1) * 0x9e3779b97f4a7c15ULL;
        for (i = 0; i < BYTES / 8; ++i) WRITE_ONCE(p[i], seed ^ (BASE + i * 8));
        clean_invalidate(va, va + BYTES);
        for (i = 0; i < BYTES / 8; ++i)
            if (READ_ONCE(p[i]) != (seed ^ (BASE + i * 8))) { ret = -EIO; goto unmap; }
    }
    memset(p, 0, BYTES);
    clean_invalidate(va, va + BYTES);
    if (gb10_commit) {
        ret = insert_resource(&iomem_resource, &reclaimed);
        if (ret) goto unmap;
        resource_added = true;
        ret = clear_nomap(BASE, BYTES);
        if (ret) goto unmap;
        nomap_cleared = true;
        for (pfn = BASE >> PAGE_SHIFT; pfn < (BASE + BYTES) >> PAGE_SHIFT; ++pfn)
            if (!pfn_is_map_memory(pfn) || !PageReserved(pfn_to_page(pfn)) ||
                page_ref_count(pfn_to_page(pfn)) != 1 || page_zonenum(pfn_to_page(pfn)) != ZONE_NORMAL) {
                ret = -EINVAL; goto unmap;
            }
        /* Commit point. Both this module and the guarded NVIDIA module
         * stay pinned until reboot. No unload-based rollback is claimed. */
        __module_get(THIS_MODULE);
        for (pfn = BASE >> PAGE_SHIFT; pfn < (BASE + BYTES) >> PAGE_SHIFT; ++pfn)
            free_reserved_page(pfn_to_page(pfn));
        pr_info("gb10_reclaim_right: RELEASED %lu pages; totalram delta=%ld pages; guarded driver pinned; reboot required to revert\n",
                BYTES >> PAGE_SHIFT, (long)(totalram_pages() - total_before));
        return 0;
    }
unmap:
    if (nomap_cleared) {
        int r = mark_nomap(BASE, BYTES);
        if (r) pr_err("gb10_reclaim_right: NOMAP rollback failed %d; reboot required\n", r);
    }
    if (resource_added) remove_resource(&reclaimed);
    unmap_range(va, va + BYTES, false, NULL);
    free_tables(va, va + BYTES, PAGE_OFFSET, PAGE_END);
    if (!ret)
        for (i = 0; i < BYTES; i += PAGE_SIZE)
            if (mapped(va + i)) { ret = -EFAULT; break; }
    pr_info("gb10_reclaim_right: direct-map test result=%d; pages remain reserved\n", ret);
    if (gb10_guard_fn) __symbol_put("gb10_display_carveout_disabled");
    return ret;
}
static void __exit probe_exit(void) {}
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_INFO(livepatch, "Y");
MODULE_DESCRIPTION("Bounded GB10 direct-map probe with livepatch symbol relocations");
