# Checked-address HTTPS transport

`payer_policy.https_transport.fetch_https()` can fetch **one approved HTTPS
resource into memory**. It is a small transport building block, not an
automatic policy downloader, crawler, or proof that a document governs a
NYSHIP Empire Plan benefit. No live Anthem source was contacted to verify this
increment.

## What it does

```text
fetch_https(url, allowed_hosts, *, max_redirects=3,
            timeout=10, max_bytes=10_000_000) -> FetchResult
```

- `url` must pass the [existing destination check](network-safety.md): HTTPS,
  port 443, and an exact host in the caller's reviewed allowlist. For example,
  approving `example.org` does **not** approve `cdn.example.org`. An unencoded
  non-ASCII path or query fails before DNS; callers must supply valid percent-
  encoded request data rather than letting the transport rewrite it.
- DNS (the system that looks up a host's network addresses) is called once for
  each request, including after a redirect. Every address **returned by the
  operating system for that call** must pass the existing public-address check;
  a mixed public/private answer fails entirely. It does not prove that these
  are every address that a DNS server might return later.
- The transport selects the first checked address. It creates a TCP socket for
  that **numeric address**, checks the connected peer's address and port, and
  uses the original hostname for both HTTP's `Host` header and TLS Server Name
  Indication (SNI). TLS checks that a certificate trusted by Python's default
  system trust configuration belongs to that hostname. A failed connection
  does not retry another address or fall back to a proxy. No unchecked second
  lookup of the hostname is used for the connection.
- Automatic redirects are not used. Only HTTP 301, 302, 303, 307, and 308 with
  exactly one `Location` are considered. The existing redirect validator checks
  the target, history, and hop limit **before** the next DNS lookup; the next
  request must pass fresh address and TLS checks. Other non-success statuses
  fail. Connections are closed between hops.
- GET only. On success, `FetchResult` contains the final URL, status, raw
  headers, and response bytes. `max_bytes` defaults to **10,000,000 bytes**;
  reading one extra byte detects oversized bodies. Declared sizes above the
  limit, duplicate or invalid `Content-Length`, conflicting response framing,
  and truncated declared bodies fail. Response status lines and headers,
  including intermediate `100 Continue` blocks, share a 64 KiB read limit;
  Python's HTTP parser may already have buffered more at the socket layer.
  Raw body bytes are not decoded or decompressed.
- `timeout` defaults to 10 seconds for socket operations, **not** a total
  request deadline. Operating-system DNS resolution can still block longer.
  `max_redirects` defaults to three; zero forbids the first redirect. Limits
  must be valid positive values (the redirect limit may be zero).

Bad URL, destination, address, or redirect inputs raise `NetworkSafetyError`
(a `ValueError`). Bad limits raise `ValueError`. Network, TLS, HTTP-status,
framing, and body-size failures raise `TransportError` (an `OSError`). No
partial body is returned on a failure. This operation does not write files.

## How to verify locally

From the repository root with Python 3.11 or newer:

```console
python -m unittest discover -s tests -v
python -m unittest discover -s tests/integration -v
```

The first command runs offline tests with controlled DNS/socket responses. The
second runs a **loopback-only** (your own computer) TLS connection through the
private numeric-address connection class. It uses OpenSSL to create a temporary
certificate, tests a matching and a mismatched hostname, and deletes the
certificate and key after the test. If OpenSSL is absent, that integration test
skips; a skip is not a pass. Loopback is deliberately **not** approved by the
public `fetch_https()` address policy, so this is not a live public-site test.

## Not established by this increment

- An approved host is reviewed configuration, not authorization to crawl it,
  redistribute its content, or infer document applicability. Access rules,
  response media-type/content validation, immutable originals, provenance,
  storage, and source-specific connectors remain separate work.
- This has no bounded DNS-resolution deadline or whole-request deadline. It
  does not handle proxies, authenticated sites, automatic retries, or HTTP/2.
  System trust configuration controls which TLS certificates are trusted.
- The loopback test exercises real TCP/TLS/HTTP mechanics, while the public
  fetch orchestration is tested with controlled sockets. No real public DNS
  result, Anthem request, production network path, Windows installer, or
  document-ingestion pipeline has been verified here. These limits matter when
  deciding whether this is ready to collect policies automatically.

See the [architecture](architecture.md) and [delivery plan](implementation-plan.md).
