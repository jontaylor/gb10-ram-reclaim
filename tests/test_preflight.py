# SPDX-License-Identifier: GPL-2.0-only
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import preflight as p


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.info = dict(arch='aarch64', page_size=4096, kernel=p.KERNEL,
                         driver=p.DRIVER, product='GX10', vendor='ASUSTeK COMPUTER INC.',
                         bios='GX10DGX.0105.2026.0505.1153', config_sha256=p.CONFIG_SHA256,
                         image_sha256=p.IMAGE_SHA256, regions=[dict(p.DISPLAY), dict(p.UEFI)],
                         reclaim_loaded=False)

    def test_known_layout_and_reordered_metadata(self):
        self.assertEqual(p.validate(self.info), [])
        self.info['regions'].reverse()
        self.assertEqual(p.validate(self.info), [])

    def test_refuses_unknown_software_or_hardware(self):
        for key in ('arch', 'kernel', 'driver', 'product', 'vendor', 'bios', 'config_sha256', 'image_sha256'):
            with self.subTest(key=key):
                info = copy.deepcopy(self.info)
                info[key] = 'unreviewed'
                self.assertTrue(p.validate(info))

    def test_refuses_large_pages(self):
        self.info['page_size'] = 65536
        self.assertTrue(p.validate(self.info))

    def test_refuses_shifted_or_expanded_carveout(self):
        for key, value in [('base', p.DISPLAY['base'] + 4096), ('size', 4 << 30), ('type', 2)]:
            with self.subTest(key=key):
                info = copy.deepcopy(self.info)
                info['regions'][0][key] = value
                self.assertTrue(p.validate(info))

    def test_refuses_extra_or_missing_regions(self):
        for regions in ([], [p.DISPLAY], [p.DISPLAY, p.UEFI, p.UEFI]):
            self.info['regions'] = regions
            self.assertTrue(p.validate(self.info))

    def test_refuses_replay_and_unknown_state(self):
        for state in (True, None):
            self.info['reclaim_loaded'] = state
            self.assertTrue(p.validate(self.info))


if __name__ == '__main__':
    unittest.main()
