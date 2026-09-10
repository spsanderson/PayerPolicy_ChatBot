"""Behavior tests for document fingerprints."""
import unittest

from payer_policy import provenance


class FingerprintTests(unittest.TestCase):
    """Check stable content identity independently of document metadata."""

    def test_rejects_non_bytes(self) -> None:
        """Reject mutable buffers and implicit string encoding."""
        for value in ("abc", bytearray(b"abc"), None, 123):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    provenance.fingerprint_document(value)


    def test_known_sha256_digest(self):
        """Return the standard SHA-256 digest for a known byte sequence."""
        function = getattr(provenance, "fingerprint_document", None)
        self.assertTrue(callable(function), "fingerprint function missing")
        self.assertEqual(
            function(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223"
            "b00361a396177a9cb410ff61f20015ad",
        )
