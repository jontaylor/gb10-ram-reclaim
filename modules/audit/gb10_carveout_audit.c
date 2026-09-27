// SPDX-License-Identifier: GPL-2.0
/* Read-only audit of the range returned by the validated RM metadata query.
 * Does not map memory, dereference carveout pages, patch code, or free pages.
 * Explicit acknowledgement is required even for this diagnostic module.
 */
#include <linux/module.h>
#include <linux/mm.h>
#include <linux/utsname.h>
#include <linux/string.h>
#include <linux/page_ref.h>
#include <asm/memory.h>

static bool acknowledge_read_only;
module_param(acknowledge_read_only, bool, 0400);
MODULE_PARM_DESC(acknowledge_read_only, "Required explicit opt-in to read-only inspection");

static int __init gb10_audit_init(void)
{
    const unsigned long first = 0x280200000ULL >> PAGE_SHIFT;
    const unsigned long end = 0x300000000ULL >> PAGE_SHIFT;
    unsigned long pfn, valid = 0, invalid = 0, reserved = 0, mapped = 0;
    unsigned long refzero = 0, refone = 0, other = 0, normal = 0;

    if (!acknowledge_read_only)
        return -EPERM;
    if (strcmp(init_utsname()->release, "6.17.0-1032-nvidia"))
        return -EINVAL;
    if (PAGE_SHIFT != 12)
        return -EINVAL;

    /* pfn_valid consults arm64 memblock classification; it does not touch
     * the physical range. Yield regularly during the bounded scan.
     */
    for (pfn = first; pfn < end; ++pfn) {
        if (pfn_valid(pfn)) {
            struct page *page = pfn_to_page(pfn);
            ++valid;
            reserved += PageReserved(page);
            mapped += pfn_is_map_memory(pfn);
            refzero += page_ref_count(page) == 0;
            refone += page_ref_count(page) == 1;
            other += page_ref_count(page) != 0 && page_ref_count(page) != 1;
            normal += page_zonenum(page) == ZONE_NORMAL;
        } else
            ++invalid;
        if (!(pfn & 0xfff))
            cond_resched();
    }
    pr_info("gb10_carveout_audit: read-only range=[0x280200000,0x300000000) valid_pfns=%lu invalid_pfns=%lu total=%lu; no ownership changes\n",
            valid, invalid, end - first);
    pr_info("gb10_carveout_audit: reserved=%lu mapped=%lu ref0=%lu ref1=%lu other_refs=%lu zone_normal=%lu\n",
            reserved, mapped, refzero, refone, other, normal);
    return 0;
}

static void __exit gb10_audit_exit(void)
{
    pr_info("gb10_carveout_audit: unloaded; no memory changes to undo\n");
}

module_init(gb10_audit_init);
module_exit(gb10_audit_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Explicitly invoked read-only GB10 display carveout diagnostic");
