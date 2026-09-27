# SPDX-License-Identifier: GPL-2.0-only
"""Optional root test: generates disposable keys in /tmp; never enrolls anything."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.geteuid() == 0, 'run explicitly as root to test key creation')
class KeyWorkflowTests(unittest.TestCase):
    def test_module_only_key_permissions_and_no_overwrite(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='gb10-key-test-') as tmp:
            keydir = Path(tmp)/'keys'
            command = ['bash', str(repo/'scripts/create-key.sh'), str(keydir)]
            subprocess.run(command, check=True, capture_output=True)
            key = keydir/'module.key'
            digest = hashlib.sha256(key.read_bytes()).digest()
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(keydir.stat().st_mode), 0o700)
            self.assertEqual(key.stat().st_uid, 0)
            cert = subprocess.check_output(['openssl','x509','-inform','DER','-in',str(keydir/'module.der'),'-noout','-text'], text=True)
            self.assertIn('1.3.6.1.4.1.2312.16.1.2', cert)
            self.assertIn('CA:FALSE', cert)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(hashlib.sha256(key.read_bytes()).digest(), digest)
            refused = subprocess.run(['bash',str(repo/'scripts/create-key.sh'),str(repo/'build/forbidden-test-key')], capture_output=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse((repo/'build/forbidden-test-key').exists())


if __name__ == '__main__':
    unittest.main()
