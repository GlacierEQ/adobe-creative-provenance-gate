from __future__ import annotations

import unittest

from src.promotion_authority import PromotionAuthority


class PromotionAuthTests(unittest.TestCase):
    def test_issue_verify(self):
        authority = PromotionAuthority(b"test-secret", ttl_s=60)
        grant = authority.issue("GlacierEQ/x", "abc", "def", now=1000.0)
        ok, reason = authority.verify(grant, now=1001.0)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_expired(self):
        authority = PromotionAuthority(b"test-secret", ttl_s=10)
        grant = authority.issue("GlacierEQ/x", "abc", "def", now=1000.0)
        ok, reason = authority.verify(grant, now=2000.0)
        self.assertFalse(ok)
        self.assertEqual(reason, "GRANT_EXPIRED")

    def test_mac_tamper_fails(self):
        authority = PromotionAuthority(b"test-secret", ttl_s=60)
        grant = authority.issue("GlacierEQ/x", "abc", "def", now=1000.0)
        tampered = type(grant)(
            repository=grant.repository,
            source_sha="different",
            proof_receipt_digest=grant.proof_receipt_digest,
            not_after=grant.not_after,
            mac=grant.mac,
        )
        ok, reason = authority.verify(tampered, now=1001.0)
        self.assertFalse(ok)
        self.assertEqual(reason, "BAD_MAC")


if __name__ == "__main__":
    unittest.main()
