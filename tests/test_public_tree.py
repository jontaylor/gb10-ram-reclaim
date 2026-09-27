# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_public_tree import inspect


class PublicationChecks(unittest.TestCase):
    def test_rejects_sensitive_file_types_without_printing_content(self):
        for name in ('local.key', 'local.der', 'module.ko', 'driver.log', '.env'):
            self.assertTrue(inspect(name, b'placeholder'))

    def test_rejects_generated_directories(self):
        self.assertTrue(inspect('build/output.txt', b'placeholder'))

    def test_rejects_synthetic_tokens_and_certificate_headers(self):
        for data in (b'ghp_' + b'x' * 36, b'-----BEGIN ' + b'CERTIFICATE-----\n',
                     b'-----BEGIN ' + b'PRIVATE KEY-----\n'):
            errors = inspect('notes.txt', data)
            self.assertTrue(errors)
            self.assertNotIn(data.decode(), str(errors))

    def test_allows_public_code_and_documentation(self):
        self.assertEqual(inspect('README.md', b'2046 MiB; generate your own local key.'), [])


if __name__ == '__main__':
    unittest.main()
