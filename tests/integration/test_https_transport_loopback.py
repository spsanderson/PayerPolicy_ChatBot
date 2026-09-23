"""Explicitly run local-loopback TLS integration tests; no public network."""
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from payer_policy.https_transport import _PinnedHTTPSConnection


class LoopbackTLSTests(unittest.TestCase):
    """Prove actual TCP, TLS identity verification, and HTTP parsing cooperate."""

    def test_checked_numeric_connection_keeps_hostname_verification(self) -> None:
        """A trusted test certificate works only for its matching DNS name."""
        if not shutil.which("openssl"):
            self.skipTest("OpenSSL CLI required to generate temporary test cert")
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / "cert.pem"
            key = Path(directory) / "key.pem"
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(cert), "-days", "1",
                "-subj", "/CN=policy.test",
                "-addext", "subjectAltName=DNS:policy.test",
            ], check=True, capture_output=True, timeout=30)
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(certfile=str(cert), keyfile=str(key))
            client_context = ssl.create_default_context(cafile=str(cert))
            self.assertTrue(client_context.verify_mode == ssl.CERT_REQUIRED)
            self.assertTrue(client_context.check_hostname)
            for hostname, permitted in (("policy.test", True),
                                        ("wrong.test", False)):
                with self.subTest(hostname=hostname):
                    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    listener.bind(("127.0.0.1", 0))
                    listener.listen(1)
                    listener.settimeout(5)
                    port = listener.getsockname()[1]
                    received = []

                    def serve_once() -> None:
                        """Reply to one real TLS GET from the private transport."""
                        try:
                            accepted, _ = listener.accept()
                            with server_context.wrap_socket(
                                    accepted, server_side=True) as tls:
                                received.append(tls.recv(4096))
                                tls.sendall(
                                    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                                    b"Connection: close\r\n\r\nOK")
                        except Exception as exc:
                            received.append(exc)

                    thread = threading.Thread(target=serve_once, daemon=True)
                    thread.start()
                    connection = _PinnedHTTPSConnection(
                        hostname, ("127.0.0.1", port), socket.AF_INET,
                        timeout=3, context=client_context,
                    )
                    try:
                        if permitted:
                            connection.request("GET", "/test", headers={
                                "Host": hostname, "Connection": "close",
                            })
                            response = connection.getresponse()
                            self.assertEqual((response.status, response.read()),
                                             (200, b"OK"))
                        else:
                            with self.assertRaises(ssl.SSLCertVerificationError):
                                connection.request("GET", "/test")
                    finally:
                        connection.close()
                        thread.join(timeout=5)
                        listener.close()
                    self.assertFalse(thread.is_alive(),
                                     "local TLS server did not exit")
                    self.assertEqual(len(received), 1)
                    if permitted:
                        self.assertIsInstance(received[0], bytes)
                        self.assertIn(b"GET /test HTTP/1.1", received[0])
                    else:
                        self.assertIsInstance(received[0], ssl.SSLError)
