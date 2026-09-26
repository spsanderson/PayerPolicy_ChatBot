"""Offline tests for checked-address HTTPS connections and responses."""
import io
import socket
import unittest
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import Mock, patch


@contextmanager
def controlled_reply(
    reply: bytes,
    address: str = "8.8.8.8",
) -> Iterator[tuple[Mock, Mock, Mock, Mock]]:
    """Supply one fake TCP/TLS peer to the real HTTP response parser."""
    raw = Mock()
    raw.getpeername.return_value = (address, 443)
    tls = Mock()
    tls.makefile.side_effect = lambda *args: io.BytesIO(reply)
    context = Mock()
    context.wrap_socket.return_value = tls
    with (patch("socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
             "", (address, 443))]) as dns,
          patch("socket.socket", return_value=raw) as make_socket,
          patch("ssl.create_default_context", return_value=context)):
        yield dns, make_socket, raw, tls


class HTTPSTransportTests(unittest.TestCase):
    """Exercise the real HTTP parser with controlled DNS and sockets."""

    def test_get_connects_to_checked_ip_but_uses_original_hostname(self) -> None:
        """Do not resolve again after checking the returned TCP address."""
        from payer_policy.https_transport import fetch_https

        response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
        raw = Mock()
        raw.getpeername.return_value = ("8.8.8.8", 443)
        tls = Mock()
        tls.makefile.side_effect = lambda *args: io.BytesIO(response)
        context = Mock()
        context.wrap_socket.return_value = tls
        answers = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                    "", ("8.8.8.8", 443))]
        with (patch("socket.getaddrinfo", return_value=answers) as dns,
              patch("socket.socket", return_value=raw) as make_socket,
              patch("ssl.create_default_context", return_value=context)):
            result = fetch_https("https://EXAMPLE.org:443/a%2fb?q=2&b=1",
                                 ["example.org"])

        self.assertEqual(result.body, b"OK")
        self.assertEqual(result.url, "https://EXAMPLE.org:443/a%2fb?q=2&b=1")
        self.assertEqual(result.status, 200)
        self.assertEqual(dns.call_count, 1)
        self.assertEqual(dns.call_args.args[:2], ("example.org", 443))
        make_socket.assert_called_once()
        raw.connect.assert_called_once_with(("8.8.8.8", 443))
        context.wrap_socket.assert_called_once_with(
            raw, server_hostname="example.org")
        wire = b"".join(call.args[0] for call in tls.sendall.call_args_list)
        self.assertIn(b"GET /a%2fb?q=2&b=1 HTTP/1.1\r\n", wire)
        self.assertIn(b"Host: EXAMPLE.org:443\r\n", wire)
        self.assertIn(b"Accept-Encoding: identity\r\n", wire)
        self.assertIn(b"Connection: close\r\n", wire)
        tls.close.assert_called()

    def test_redirect_resolves_again_and_rejects_private_answer(self) -> None:
        """A same-host redirect needs fresh safe DNS before another socket."""
        from payer_policy.https_transport import fetch_https
        redirect = (b"HTTP/1.1 302 Found\r\nLocation: /next\r\n"
                    b"Content-Length: 0\r\n\r\n")
        raw = Mock()
        raw.getpeername.return_value = ("8.8.8.8", 443)
        tls = Mock()
        tls.makefile.side_effect = lambda *args: io.BytesIO(redirect)
        context = Mock()
        context.wrap_socket.return_value = tls
        with (patch("socket.getaddrinfo", side_effect=[
                [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                  "", ("8.8.8.8", 443))],
                [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                  "", ("127.0.0.1", 443))],
              ]) as dns,
              patch("socket.socket", return_value=raw) as make_socket,
              patch("ssl.create_default_context", return_value=context)):
            with self.assertRaisesRegex(ValueError, "public unicast"):
                fetch_https("https://example.org/start", ["example.org"],
                            max_redirects=1)
        self.assertEqual(dns.call_count, 2)
        make_socket.assert_called_once()
        tls.close.assert_called()

    def test_excess_response_headers_are_rejected(self) -> None:
        """A small body must not hide a large unbounded header block."""
        from payer_policy.https_transport import TransportError, fetch_https
        lines = b"".join(
            f"X-Test-{i}: ".encode() + b"a" * 1000 + b"\r\n"
            for i in range(70)
        )
        response = b"HTTP/1.1 200 OK\r\n" + lines + b"\r\nOK"
        with controlled_reply(response) as (_, _, _, tls):
            with self.assertRaisesRegex(TransportError, "headers exceed"):
                fetch_https("https://example.org/a", ["example.org"])
        tls.close.assert_called()

    def test_large_interim_headers_fail_before_final_response(self) -> None:
        """Count 100 Continue headers, not only the final 200 headers."""
        from payer_policy.https_transport import TransportError, fetch_https
        interim = (b"HTTP/1.1 100 Continue\r\n"
                   + b"X-First: " + b"a" * 33_000 + b"\r\n"
                   + b"X-Second: " + b"b" * 33_000 + b"\r\n\r\n")
        final = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
        with controlled_reply(interim + final) as (_, _, _, tls):
            with self.assertRaisesRegex(TransportError, "headers exceed"):
                fetch_https("https://example.org/", ["example.org"])
        tls.close.assert_called()

    def test_interim_and_final_headers_share_the_limit(self) -> None:
        """Several small header blocks cannot evade the total cap."""
        from payer_policy.https_transport import TransportError, fetch_https
        interim = (b"HTTP/1.1 100 Continue\r\n"
                   + b"X-First: " + b"a" * 33_000 + b"\r\n\r\n")
        final = (b"HTTP/1.1 200 OK\r\n"
                 + b"X-Second: " + b"b" * 33_000
                 + b"\r\nContent-Length: 2\r\n\r\nOK")
        with controlled_reply(interim + final) as (_, _, _, tls):
            with self.assertRaisesRegex(TransportError, "headers exceed"):
                fetch_https("https://example.org/", ["example.org"])
        tls.close.assert_called()

    def test_small_interim_response_is_accepted(self) -> None:
        """Counting interim headers must not break ordinary 100 Continue."""
        from payer_policy.https_transport import fetch_https
        reply = (b"HTTP/1.1 100 Continue\r\nX-Note: ready\r\n\r\n"
                 b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        with controlled_reply(reply) as (_, _, _, tls):
            result = fetch_https("https://example.org/", ["example.org"])
        self.assertEqual(result.body, b"OK")
        self.assertEqual(result.status, 200)
        tls.close.assert_called()

    def test_chunked_trailers_share_header_byte_limit(self) -> None:
        """A tiny body cannot hide oversized fields sent after it."""
        from payer_policy.https_transport import TransportError, fetch_https
        reply = (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                 b"2\r\nOK\r\n0\r\n" + (b"X-Test: " + b"a" * 1000 + b"\r\n") * 100
                 + b"\r\n")
        with controlled_reply(reply) as (_, _, _, tls):
            with self.assertRaisesRegex(TransportError, "headers exceed"):
                fetch_https("https://example.org/", ["example.org"], max_bytes=2)
        tls.close.assert_called()

    def test_chunk_separators_count_toward_metadata_limit(self) -> None:
        """The two bytes after each body piece belong to the shared budget."""
        from payer_policy.https_transport import TransportError, fetch_https
        prefix = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nX-Pad: "
        suffix = b"\r\n\r\n1\r\na\r\n0\r\n\r\n"
        # Exactly one byte over when the body's byte is excluded.
        reply = prefix + b"p" * (65_537 - len(prefix + suffix) + 1) + suffix
        with controlled_reply(reply) as (_, _, _, tls):
            with self.assertRaisesRegex(TransportError, "headers exceed"):
                fetch_https("https://example.org/", ["example.org"], max_bytes=1)
        tls.close.assert_called()

    def test_chunked_metadata_boundaries_and_cleanup(self) -> None:
        """Keep valid bodies, reject combined overhead, and close input files."""
        from payer_policy.https_transport import TransportError, fetch_https
        header = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        small = b"\r\n1;x=y\r\nO\r\n1\r\nK\r\n0\r\nX-End: yes\r\n\r\n"
        combined = (b"X-Pad: " + b"a" * 33_000 + b"\r\n\r\n2\r\nOK\r\n0\r\n"
                    + b"X-End: " + b"b" * 33_000 + b"\r\n\r\n")
        extensions = (b"\r\n" + (b"1;x=" + b"a" * 33_000 + b"\r\na\r\n") * 2
                      + b"0\r\n\r\n")
        prefix = header + b"X-Pad: "
        suffix = b"\r\n\r\n2\r\nOK\r\n0\r\nX-End: yes\r\n\r\n"
        exact = prefix + b"a" * (65_536 - len(prefix + suffix) + 2) + suffix
        large_body = b"a" * 70_000
        large = (header + b"\r\n" + b"%x\r\n" % len(large_body)
                 + large_body + b"\r\n0\r\n\r\n")
        for reply, limit, expected in (
            (header + small, 2, b"OK"),
            (exact, 2, b"OK"),
            (large, len(large_body), large_body),
            (header + combined, 2, None),
            (header + extensions, 2, None),
            (header + small, 1, None),
            (header + b"Connection: close\r\n" + combined, 2, None),
        ):
            with self.subTest(size=len(reply), limit=limit):
                stream = io.BytesIO(reply)
                with controlled_reply(reply) as (_, _, _, tls):
                    tls.makefile.side_effect = lambda *args: stream
                    if expected is None:
                        with self.assertRaises(TransportError):
                            fetch_https("https://example.org/", ["example.org"],
                                        max_bytes=limit)
                    else:
                        self.assertEqual(fetch_https(
                            "https://example.org/", ["example.org"],
                            max_bytes=limit).body, expected)
                self.assertTrue(stream.closed)
                tls.close.assert_called()

    def test_truncated_declared_body_is_not_success(self) -> None:
        """Do not return a partial download as if it were complete."""
        from payer_policy.https_transport import TransportError, fetch_https
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nOK"
        raw = Mock()
        raw.getpeername.return_value = ("8.8.8.8", 443)
        tls = Mock()
        tls.makefile.side_effect = lambda *args: io.BytesIO(response)
        context = Mock()
        context.wrap_socket.return_value = tls
        with (patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", ("8.8.8.8", 443))]),
              patch("socket.socket", return_value=raw),
              patch("ssl.create_default_context", return_value=context)):
            with self.assertRaisesRegex(TransportError, "incomplete"):
                fetch_https("https://example.org/a", ["example.org"])
        tls.close.assert_called()

    def test_approved_redirect_rechecks_new_host_and_returns_final_url(self) -> None:
        """Accept a reviewed target only after its own fresh DNS check."""
        from payer_policy.https_transport import fetch_https
        replies = (
            b"HTTP/1.1 302 Found\r\nLocation: //cdn.example.org/final?x=1\r\n"
            b"Content-Length: 0\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nDATA",
        )
        raws = [Mock(), Mock()]
        tls_sockets = [Mock(), Mock()]
        for raw, tls, ip, reply in zip(raws, tls_sockets,
                                        ("8.8.8.8", "1.1.1.1"), replies):
            raw.getpeername.return_value = (ip, 443)
            tls.makefile.side_effect = lambda *args, reply=reply: io.BytesIO(reply)
        context = Mock()
        context.wrap_socket.side_effect = tls_sockets
        with (patch("socket.getaddrinfo", side_effect=[
                [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                  "", ("8.8.8.8", 443))],
                [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                  "", ("1.1.1.1", 443))],
              ]) as dns,
              patch("socket.socket", side_effect=raws) as make_socket,
              patch("ssl.create_default_context", return_value=context)):
            result = fetch_https("https://example.org/start",
                                 ["example.org", "cdn.example.org"],
                                 max_redirects=1)
        self.assertEqual(result.url, "https://cdn.example.org/final?x=1")
        self.assertEqual(result.body, b"DATA")
        self.assertEqual(dns.call_count, 2)
        self.assertEqual(make_socket.call_count, 2)
        self.assertEqual(context.wrap_socket.call_args_list[1].kwargs,
                         {"server_hostname": "cdn.example.org"})
        self.assertIn(b"GET /final?x=1 HTTP/1.1\r\n", b"".join(
            c.args[0] for c in tls_sockets[1].sendall.call_args_list))
        for tls in tls_sockets:
            tls.close.assert_called()

    def test_mixed_dns_answer_never_creates_a_socket(self) -> None:
        """An unsafe companion address rejects the entire DNS result."""
        from payer_policy.https_transport import fetch_https
        with (patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", ("127.0.0.1", 443)),
              ]) as dns,
              patch("socket.socket") as make_socket):
            with self.assertRaisesRegex(ValueError, "public unicast"):
                fetch_https("https://example.org/", ["example.org"])
        dns.assert_called_once()
        make_socket.assert_not_called()

    def test_changed_peer_and_tls_failure_close_socket_without_retry(self) -> None:
        """A mismatched peer or failed certificate cannot become a download."""
        import ssl
        from payer_policy.https_transport import TransportError, fetch_https
        for peer, failure in (("1.1.1.1", None),
                              ("8.8.8.8", ssl.SSLCertVerificationError(
                                  "certificate rejected"))):
            with self.subTest(peer=peer):
                raw = Mock()
                raw.getpeername.return_value = (peer, 443)
                context = Mock()
                if failure:
                    context.wrap_socket.side_effect = failure
                with (patch("socket.getaddrinfo", return_value=[
                        (socket.AF_INET, socket.SOCK_STREAM,
                         socket.IPPROTO_TCP, "", ("8.8.8.8", 443))]) as dns,
                      patch("socket.socket", return_value=raw) as make_socket,
                      patch("ssl.create_default_context", return_value=context)):
                    with self.assertRaises(TransportError):
                        fetch_https("https://example.org/", ["example.org"])
                dns.assert_called_once()
                make_socket.assert_called_once()
                raw.close.assert_called()

    def test_redirect_limit_stops_before_second_dns_lookup(self) -> None:
        """A forbidden next hop is refused before resolving it."""
        from payer_policy.https_transport import fetch_https
        reply = b"HTTP/1.1 301 Moved\r\nLocation: /next\r\n\r\n"
        raw = Mock()
        raw.getpeername.return_value = ("8.8.8.8", 443)
        tls = Mock()
        tls.makefile.side_effect = lambda *args: io.BytesIO(reply)
        context = Mock()
        context.wrap_socket.return_value = tls
        with (patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", ("8.8.8.8", 443))]) as dns,
              patch("socket.socket", return_value=raw),
              patch("ssl.create_default_context", return_value=context)):
            with self.assertRaisesRegex(ValueError, "limit"):
                fetch_https("https://example.org/start", ["example.org"],
                            max_redirects=0)
        dns.assert_called_once()
        tls.close.assert_called()

    def test_response_limit_and_invalid_inputs(self) -> None:
        """Bound in-memory bytes and reject ambiguous size settings."""
        from payer_policy.https_transport import TransportError, fetch_https
        for options in ({"max_bytes": 0}, {"max_bytes": True},
                        {"timeout": 0}, {"timeout": float("inf")},
                        {"max_redirects": True}, {"max_redirects": -1}):
            with self.subTest(options=options):
                with patch("socket.getaddrinfo") as dns:
                    with self.assertRaises(ValueError):
                        fetch_https("https://example.org/", ["example.org"],
                                    **options)
                    dns.assert_not_called()
        raw = Mock()
        raw.getpeername.return_value = ("8.8.8.8", 443)
        tls = Mock()
        tls.makefile.side_effect = lambda *args: io.BytesIO(
            b"HTTP/1.1 200 OK\r\n\r\nOVER")
        context = Mock()
        context.wrap_socket.return_value = tls
        with (patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", ("8.8.8.8", 443))]),
              patch("socket.socket", return_value=raw),
              patch("ssl.create_default_context", return_value=context)):
            with self.assertRaisesRegex(TransportError, "max_bytes"):
                fetch_https("https://example.org/", ["example.org"],
                            max_bytes=2)
        tls.close.assert_called()

    def test_non_ascii_request_target_rejects_before_dns(self) -> None:
        """Do not connect if an unencoded path cannot be sent as a URI."""
        from payer_policy.https_transport import NetworkSafetyError, fetch_https
        with patch("socket.getaddrinfo") as dns:
            with self.assertRaisesRegex(NetworkSafetyError, "ASCII"):
                fetch_https("https://example.org/☃", ["example.org"])
            dns.assert_not_called()

    def test_unsafe_redirects_and_duplicate_locations(self) -> None:
        """Untrusted Location cannot choose a new host or ambiguous target."""
        from payer_policy.https_transport import (
            NetworkSafetyError, TransportError, fetch_https,
        )
        for headers, error in (
            (b"Location: https://evil.test/\r\n", NetworkSafetyError),
            (b"Location: http://example.org/\r\n", NetworkSafetyError),
            (b"Location: /start\r\n", NetworkSafetyError),
            (b"Location: /one\r\nLocation: /two\r\n", TransportError),
            (b"", TransportError),
        ):
            with self.subTest(headers=headers):
                reply = b"HTTP/1.1 302 Found\r\n" + headers + b"\r\n"
                with controlled_reply(reply) as (dns, make_socket, _, tls):
                    with self.assertRaises(error):
                        fetch_https("https://example.org/start",
                                    ["example.org"])
                    dns.assert_called_once()
                    make_socket.assert_called_once()
                tls.close.assert_called()

    def test_unaccepted_status_and_large_or_bad_framing(self) -> None:
        """Reject status errors, response smuggling, and declared oversize."""
        from payer_policy.https_transport import TransportError, fetch_https
        for response, limit in (
            (b"HTTP/1.1 404 Not Found\r\n\r\n", 8),
            (b"HTTP/1.1 304 Not Modified\r\n\r\n", 8),
            (b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\n", 8),
            (b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
             b"Content-Length: 2\r\n\r\nOK", 8),
            (b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
             b"Transfer-Encoding: chunked\r\n\r\nOK", 8),
            (b"HTTP/1.1 200 OK\r\nContent-Length: xx\r\n\r\nOK", 8),
        ):
            with self.subTest(response=response):
                with controlled_reply(response) as (_, _, _, tls):
                    with self.assertRaises(TransportError):
                        fetch_https("https://example.org/",
                                    ["example.org"], max_bytes=limit)
                tls.close.assert_called()

    def test_proxy_environment_is_not_a_transport_fallback(self) -> None:
        """A configured HTTPS proxy must not replace the approved IP socket."""
        from payer_policy.https_transport import fetch_https
        reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
        with (patch.dict("os.environ", {
                "HTTPS_PROXY": "http://127.0.0.1:8888",
                "HTTP_PROXY": "http://127.0.0.1:8888"}),
              controlled_reply(reply) as (dns, make_socket, raw, _)):
            self.assertEqual(fetch_https("https://example.org/",
                                         ["example.org"]).body, b"OK")
            dns.assert_called_once()
            make_socket.assert_called_once()
            raw.connect.assert_called_once_with(("8.8.8.8", 443))

    def test_valid_ipv6_uses_numeric_endpoint(self) -> None:
        """A public IPv6 answer keeps its family and does not resolve again."""
        from payer_policy.https_transport import fetch_https
        address = "2606:4700:4700::1111"
        raw = Mock()
        raw.getpeername.return_value = (address, 443, 0, 0)
        tls = Mock()
        tls.makefile.side_effect = lambda *args: io.BytesIO(
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        context = Mock()
        context.wrap_socket.return_value = tls
        with (patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", (address, 443, 0, 0))]) as dns,
              patch("socket.socket", return_value=raw) as make_socket,
              patch("ssl.create_default_context", return_value=context)):
            self.assertEqual(fetch_https("https://example.org/",
                                         ["example.org"]).body, b"OK")
        dns.assert_called_once()
        make_socket.assert_called_once_with(
            socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        raw.connect.assert_called_once_with((address, 443, 0, 0))
        tls.close.assert_called()

    def test_fetch_result_passes_offline_candidate_check(self) -> None:
        """Feed real HTTP parsing into validation, without a public socket."""
        from payer_policy.document_validation import validate_pdf_candidate
        from payer_policy.https_transport import fetch_https

        # controlled_reply above supplies fake sockets, not a fake HTTP parser.
        responses = (
            b"HTTP/1.1 200 OK\r\nContent-Type: Application/PDF\r\n"
            b"Content-Encoding: identity\r\nContent-Length: 5\r\n\r\n%PDF-",
            b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n5\r\n%PDF-\r\n0\r\n\r\n",
        )
        for response in responses:
            with self.subTest(response=response):
                with controlled_reply(response):
                    result = fetch_https("https://example.org/a",
                                         ["example.org"])
                self.assertIsNone(validate_pdf_candidate(result))
                self.assertEqual(result.body, b"%PDF-")

    def test_fetch_result_rejects_html_candidate(self) -> None:
        """A successful fetch is not automatically a PDF candidate."""
        from payer_policy.document_validation import (
            DocumentValidationError, validate_pdf_candidate,
        )
        from payer_policy.https_transport import fetch_https

        for content_type in (b"text/html", b"application/pdf"):
            response = (b"HTTP/1.1 200 OK\r\nContent-Type: " + content_type +
                        b"\r\nContent-Length: 18\r\n\r\n<html>login</html>")
            with self.subTest(content_type=content_type):
                with controlled_reply(response):
                    result = fetch_https("https://example.org/a.pdf",
                                         ["example.org"])
                with self.assertRaises(DocumentValidationError):
                    validate_pdf_candidate(result)

    def test_connection_timeout_does_not_retry_or_change_address(self) -> None:
        """A failed connect ends the request rather than choosing another IP."""
        from payer_policy.https_transport import TransportError, fetch_https
        raw = Mock()
        raw.connect.side_effect = TimeoutError("connect timed out")
        with (patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                 "", ("1.1.1.1", 443)),
              ]) as dns,
              patch("socket.socket", return_value=raw) as make_socket):
            with self.assertRaises(TransportError):
                fetch_https("https://example.org/", ["example.org"])
        dns.assert_called_once()
        make_socket.assert_called_once()
        raw.close.assert_called()
