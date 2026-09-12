"""Offline destination, address, and redirect policy regression tests."""
import importlib
import importlib.util
import unittest
from unittest.mock import patch


class NetworkSafetyTests(unittest.TestCase):
    """Exercise pure helpers with networking disabled for every fixture."""

    def setUp(self) -> None:
        """Fail clearly for missing implementation; prohibit network access."""
        self.assertIsNotNone(
            importlib.util.find_spec("payer_policy.network_safety"),
            "network_safety module missing",
        )
        for target in ("socket.getaddrinfo", "socket.socket",
                       "socket.gethostbyname", "socket.create_connection"):
            guard = patch(target, side_effect=AssertionError("network used"))
            guard.start()
            self.addCleanup(guard.stop)
        self.safety = importlib.import_module("payer_policy.network_safety")
        self.hosts = ["example.org", "cdn.example.org"]

    def test_bracketed_ipfuture_is_not_a_dns_hostname(self) -> None:
        """Never approve bracketed URI IP literals as ordinary DNS hosts."""
        with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                    "hostname"):
            self.safety.validate_destination_url(
                "https://[v1.example]/", ["v1.example"]
            )

    def test_unicode_host_cannot_be_folded_into_approval(self) -> None:
        """Check ASCII on raw authority before Unicode lowercase folding."""
        with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                    "hostname"):
            self.safety.validate_destination_url(
                "https://\u212aexample.org/path", ["kexample.org"]
            )

    def test_empty_redirect_query_is_preserved(self) -> None:
        """An explicit empty query clears the old query during resolution."""
        current = "https://example.org/a?old=1"
        for location in ("?", "/a?", "https://example.org/a?"):
            with self.subTest(location=location):
                self.assertEqual(self.safety.validate_redirect(
                    current, location, self.hosts, [current], 1
                ), "https://example.org/a?")

    def test_redirect_history_and_limits(self) -> None:
        """Count completed hops and reject inconsistent caller histories."""
        start = "https://example.org/start"
        current = "https://example.org/current"
        for history, limit, reason in (
            ([], 3, "history"), (None, 3, "history"),
            (current, 3, "history"), ({current}, 3, "history"),
            (iter([current]), 3, "history"), ([start], 3, "history"),
            ([start, None, current], 3, "history"),
            (["http://example.org", current], 3, "history"),
            (["https://evil.test", current], 3, "history"),
            ([start, current, start, current], 5, "history"),
            (["https://EXAMPLE.org:443/current", current], 3, "history"),
            ([current], True, "max_redirects"),
            ([current], -1, "max_redirects"),
            ([current], 1.0, "max_redirects"),
            ([current], "2", "max_redirects"),
            ([current], None, "max_redirects"),
            ([current], 0, "limit"), ([start, current], 1, "limit"),
            ([start, "https://example.org/mid", current], 1, "limit"),
        ):
            with self.subTest(history=history, limit=limit):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            reason):
                    self.safety.validate_redirect(
                        current, "/end", self.hosts, history, limit
                    )
        history = [start, current]
        self.assertEqual(self.safety.validate_redirect(
            current, "/end", self.hosts, history, 2
        ), "https://example.org/end")
        self.assertEqual(history, [start, current])

    def test_redirect_request_identity_loops(self) -> None:
        """Detect equivalent hosts/ports/root paths without decoding data."""
        for current, target in (
            ("https://example.org/", "https://EXAMPLE.org:443"),
            ("https://example.org", "/"),
            ("https://example.org/a?q=1", "https://EXAMPLE.org:443/a?q=1"),
        ):
            with self.subTest(target=target):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            "loop"):
                    self.safety.validate_redirect(
                        current, target, self.hosts, [current], 3
                    )
        start = "https://example.org/start"
        current = "https://example.org/end"
        with self.assertRaisesRegex(self.safety.NetworkSafetyError, "loop"):
            self.safety.validate_redirect(
                current, start, self.hosts, [start, current], 3
            )
        for current, target in (
            ("https://example.org/a%2fb", "https://example.org/a%2Fb"),
            ("https://example.org/a%2fb", "https://example.org/a/b"),
            ("https://example.org/a?x=1&y=2", "https://example.org/a?y=2&x=1"),
        ):
            self.assertEqual(self.safety.validate_redirect(
                current, target, self.hosts, [current], 1
            ), target)

    def test_redirect_target_policy(self) -> None:
        """Every target, even same-host, must pass destination policy."""
        current = "https://example.org/start"
        for location, reason in (
            ("http://example.org/end", "HTTPS"),
            ("//evil.test/end", "approved"),
            ("https://sub.example.org/end", "approved"),
            ("https://example.org:8080/end", "port"),
            ("//user@example.org/end", "credentials"),
            ("//127.0.0.1/end", "hostname"),
            ("//example.org./end", "hostname"),
            ("/end#fragment", "fragment"), ("#", "fragment"),
            ("/bad%xx", "percent"), ("/bad\\end", "backslash"),
            ("", "empty"), (None, "string"), (123, "string"),
            ("https:/end", "malformed"), ("https:end", "malformed"),
            ("https:///end", "malformed"), ("///end", "malformed"),
            ("//", "malformed"), ("//?q=1", "malformed"),
            (":bad", "malformed"), ("1bad:thing", "malformed"),
            ("https://[bad", "malformed"),
        ):
            with self.subTest(location=location):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            reason):
                    self.safety.validate_redirect(
                        current, location, self.hosts, [current], 3
                    )
        for current in ("http://example.org/start", "https://evil.test/start"):
            with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                        "HTTPS|approved"):
                self.safety.validate_redirect(
                    current, "https://example.org/end", self.hosts,
                    [current], 3
                )

    def test_redirect_raw_controls(self) -> None:
        """Prevent urljoin from stripping dangerous Location characters."""
        current = "https://example.org/start"
        for number in (*range(32), *range(0x7f, 0xa0), 32, 160):
            for location in (chr(number) + "/end", "/end" + chr(number)):
                with self.subTest(location=location):
                    with self.assertRaisesRegex(
                        self.safety.NetworkSafetyError, "control|whitespace"
                    ):
                        self.safety.validate_redirect(
                            current, location, self.hosts, [current], 3
                        )

    def test_relative_redirect_resolution(self) -> None:
        """Resolve valid URI references without normalizing request data."""
        function = getattr(self.safety, "validate_redirect", None)
        self.assertTrue(callable(function), "redirect validator missing")
        current = "https://example.org/dir/start?old=1"
        for location, expected in (
            ("next%2fpart?b=2&a=1",
             "https://example.org/dir/next%2fpart?b=2&a=1"),
            ("../final", "https://example.org/final"),
            ("/final", "https://example.org/final"),
            ("?new=2", "https://example.org/dir/start?new=2"),
            ("//cdn.example.org/a", "https://cdn.example.org/a"),
            ("https://EXAMPLE.org:443/a", "https://EXAMPLE.org:443/a"),
        ):
            with self.subTest(location=location):
                visited = [current]
                self.assertEqual(function(current, location, self.hosts,
                                          visited, 3), expected)
                self.assertEqual(visited, [current])

    def test_restricted_addresses_reject_entire_answer(self) -> None:
        """Reject private, special-use, multicast and tunneling fixtures."""
        restricted = (
            "0.0.0.0", "0.1.2.3", "10.0.0.1", "100.64.0.1",
            "100.127.255.255", "127.0.0.1", "169.254.169.254",
            "172.16.0.1", "172.31.255.255", "192.168.1.1",
            "192.0.0.9", "192.0.0.10", "192.0.2.1", "192.88.99.1",
            "198.18.0.1", "198.19.255.255", "198.51.100.1",
            "203.0.113.1", "224.0.0.1", "239.255.255.255",
            "240.0.0.1", "255.255.255.255", "::", "::1", "::8.8.8.8",
            "::ffff:8.8.8.8", "::ffff:127.0.0.1", "::ffff:0:808:808",
            "64:ff9b::808:808", "64:ff9b:1::1", "100::1",
            "2001::1", "2001:20::1", "2001:1::1", "2001:2::1",
            "2001:db8::1", "2002:0808:0808::1", "3fff::1",
            "3fff:fff::1", "5f00::1", "fc00::1", "fdff::1",
            "fe80::1", "fec0::1", "ff02::1",
        )
        for address in restricted:
            for answers in ([address], ["8.8.8.8", address],
                            [address, "2606:4700:4700::1111"]):
                original = answers.copy()
                with self.subTest(answers=answers):
                    with self.assertRaisesRegex(
                        self.safety.NetworkSafetyError, "public unicast"
                    ):
                        self.safety.validate_resolved_addresses(answers)
                    self.assertEqual(answers, original)

    def test_malformed_address_answers(self) -> None:
        """Reject bad containers, invalid text, and IPv6 scope identifiers."""
        for answers, reason in (
            ([], "empty"), ((), "empty"), (None, "sequence"),
            ("8.8.8.8", "sequence"), (b"8.8.8.8", "sequence"),
            ({"8.8.8.8"}, "sequence"), ({"8.8.8.8": 1}, "sequence"),
            (iter(["8.8.8.8"]), "sequence"), ([123], "string"),
            ([None], "string"), ([b"8.8.8.8"], "string"),
        ):
            with self.subTest(answers=answers):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            reason):
                    self.safety.validate_resolved_addresses(answers)
        for address in ("", " 8.8.8.8", "8.8.8.8\n", "8.8.8.8/32",
                        "008.008.008.008", "0x08080808", "134744072",
                        "example.org", "[2606:4700::1111]", "8.8.8.999",
                        "2606:4700::1%eth0", "fe80::1%1"):
            with self.subTest(address=address):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            "invalid|scope"):
                    self.safety.validate_resolved_addresses([address])

    def test_isatap_transition_addresses(self) -> None:
        """Reject ISATAP interface IDs even inside public prefixes."""
        for text in ("2001:4860::5efe:8.8.8.8",
                     "2001:4860::200:5efe:127.0.0.1"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            "public unicast"):
                    self.safety.validate_resolved_addresses([text])

    def test_public_addresses_preserved(self) -> None:
        """Return all public addresses in order without canonicalizing."""
        function = getattr(self.safety, "validate_resolved_addresses", None)
        self.assertTrue(callable(function), "address validator missing")
        addresses = ["8.8.8.8", "2606:4700:4700::1111",
                     "2001:4860:4860:0:0:0:0:8888", "8.8.8.8"]
        original = addresses.copy()
        self.assertEqual(function(addresses), tuple(original))
        self.assertEqual(addresses, original)

    def test_malformed_destinations(self) -> None:
        """Reject parser repairs and deceptive authorities before approval."""
        cases = [
            (None, "string"), (42, "string"),
            (b"https://example.org", "string"),
            ("", "empty"), ("https://user@example.org", "credentials"),
            ("https://user:pass@example.org", "credentials"),
            ("https://example.org/#", "fragment"),
            ("https://example.org/#part", "fragment"),
            ("https://example.org/\\a", "backslash"),
            ("https://example.org/%", "percent"),
            ("https://example.org/%0g", "percent"),
            ("https://[broken", "malformed"),
        ]
        for host in ("127.0.0.1", "2130706433", "127.1", "0177.0.0.1",
                     "0x7f000001", "0x7f.0.0.1", "[::1]", "example.org.",
                     "ex%61mple.org", "éxample.org", "exa_mple.org",
                     "-example.org", "example-.org", "a..org",
                     "a" * 64 + ".org", ".org", "a." * 127 + "org"):
            cases.append(("https://" + host, "hostname"))
        for value, reason in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            reason):
                    self.safety.validate_destination_url(value, self.hosts)

    def test_raw_url_controls(self) -> None:
        """Reject all C0, DEL/C1 controls and whitespace before parsing."""
        chars = [chr(n) for n in (*range(32), *range(0x7f, 0xa0))]
        chars += [" ", "\u00a0", "\u2003"]
        for char in chars:
            for url in (char + "https://example.org",
                        "https://example.org/" + char):
                with self.subTest(url=url):
                    with self.assertRaisesRegex(
                        self.safety.NetworkSafetyError, "control|whitespace"
                    ):
                        self.safety.validate_destination_url(url, self.hosts)

    def test_invalid_allowlists_fail_closed(self) -> None:
        """Invalid configuration fails even alongside an approved entry."""
        bad_entries = ["EXAMPLE.org", "*.example.org", "https://example.org",
                       "example.org/path", "example.org:443", "example.org.",
                       "éxample.org", "127.0.0.1", "2130706433", "0x7f000001",
                       "", "a..org", None, 42]
        for hosts in [None, 42, "example.org", b"example.org",
                      iter(self.hosts), {"example.org": True}] + [
                          ["example.org", bad] for bad in bad_entries]:
            with self.subTest(hosts=hosts):
                with self.assertRaisesRegex(self.safety.NetworkSafetyError,
                                            "allowlist"):
                    self.safety.validate_destination_url(
                        "https://example.org", hosts
                    )

    def test_destination_policy(self) -> None:
        """Require HTTPS, an exact reviewed host, and default TLS port."""
        for url, reason in (
            ("http://example.org", "HTTPS"),
            ("//example.org/a", "HTTPS"),
            ("https://example.org:80", "port"),
            ("https://example.org:0", "port"),
            ("https://example.org:99999", "port"),
            ("https://example.org:", "port"),
            ("https://example.org:abc", "port"),
            ("https://sub.example.org", "approved"),
            ("https://example.org.evil.test", "approved"),
            ("https://evil-example.org", "approved"),
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(
                    self.safety.NetworkSafetyError, reason
                ):
                    self.safety.validate_destination_url(url, self.hosts)
        with self.assertRaisesRegex(
            self.safety.NetworkSafetyError, "approved"
        ):
            self.safety.validate_destination_url("https://example.org", [])

    def test_approved_destination_preserved(self) -> None:
        """Approved HTTPS URLs retain their exact request spelling."""
        for url in ("https://example.org",
                    "HTTPS://EXAMPLE.org:443/a%2fb?q=2&b=1"):
            self.assertEqual(
                self.safety.validate_destination_url(url, self.hosts), url
            )
        self.assertEqual(self.hosts, ["example.org", "cdn.example.org"])
