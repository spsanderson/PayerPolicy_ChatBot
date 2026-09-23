# PayerPolicy ChatBot

A Windows-first, local policy-research application being built for Anthem's
administration of the NYSHIP Empire Plan Hospital Program.

> Early development. There is no installer, chat interface, indexed policy
> collection, or automatic policy downloader yet. A bounded HTTPS GET building
> block is available for approved hosts; it does not collect policies. The
> previous README described planned features as completed; those claims are
> not verified. Its history remains in Git.

## Working today

- `payer_policy.provenance.fingerprint_document(content: bytes) -> str`:
  SHA-256 fingerprint of exact document bytes, with explicit input validation.
- `payer_policy.source_registry.validate_source_definition(source) -> list[str]`:
  checks required metadata, identifiers, URLs, and applicability status without
  changing inputs or accessing the network. See the [source contract](docs/source-definition.md).
- URL checks reject DEL and C1 control characters in both source and evidence
  URLs; regression tests cover the entire U+007F–U+009F range.
- `parse_source_registry(text)` and `load_source_registry(path)` validate whole
  JSON registries, reject duplicate keys/IDs, and preserve source values.
- [Initial registry](sources/registry.json): one reviewed Anthem reference source,
  not a policy collection. [Review evidence](docs/source-reviews/anthem-empire-plan-overview.md).
- `payer_policy.network_safety`: pure URL allowlist, complete resolved-address,
  and redirect/history checks. Rejects private/special-use addresses and unsafe
  redirects without DNS or HTTP. See the [contract and offline example](docs/network-safety.md).
  These helpers are not a downloader or a complete SSRF defense.
- `payer_policy.https_transport.fetch_https`: a bounded HTTPS GET building
  block. It checks DNS answers, connects only to a checked numeric address,
  keeps normal hostname-based TLS certificate checks, and rechecks redirects.
  See the [transport contract and limits](docs/https-transport.md). It is not
  an automatic downloader or permission to crawl an approved host.
- Standard-library unit tests: 48 test methods pass on Python 3.11.16; a
  separate local-loopback TLS integration test also passes. No third-party
  runtime dependency was added. The integration test needs OpenSSL to generate
  a temporary certificate.

A fingerprint identifies content, not authenticity or plan applicability.
Empty bytes can be fingerprinted; a later download validator must reject empty
or invalid documents before ingestion.

## Run the tests (development)

Requires Python 3.11 or newer. From the repository root:

```console
python -m unittest discover -s tests -v
python -m unittest discover -s tests/integration -v
```

The second command tests a real local TLS connection; it needs the OpenSSL
command-line tool and skips if unavailable. No public policy site is contacted.

Example in Python, launched from the repository root:

```python
from payer_policy.provenance import fingerprint_document
print(fingerprint_document(b"abc"))
```

Load the checked-in registry from the repository root (no network calls):

```python
from pathlib import Path
from payer_policy.source_registry import load_source_registry

sources = load_source_registry(Path("sources/registry.json"))
assert list(sources) == ["anthem-empire-plan-overview"]
assert sources["anthem-empire-plan-overview"]["applicability_status"] == "reference"
print(list(sources))
```

The eventual installer will bundle the application runtime. Python is currently
a development requirement, not the intended end-user installation experience.

## Architecture and delivery

- [Architecture diagram](docs/architecture.md): Markdown with a Mermaid diagram
  and component table, distinguishing implemented and planned states.
  The original HTML remains available as an offline snapshot.
- [Incremental delivery plan](docs/implementation-plan.md): phases, modules,
  function contracts, acceptance gates, and next increment.
- [Development conventions](CONTRIBUTING.md): small test-first changes and living
  documentation.

## Intended product (not implemented)

Official-source discovery -> immutable originals and version metadata ->
PDF/HTML extraction and OCR -> reviewable chunks -> hybrid retrieval ->
model-independent answers with precise citations.

Sources must establish applicability to the selected Empire Plan benefit,
member group, and date. General Anthem policies are not automatically governing
Empire Plan policies. All applicable categories are in scope; incomplete or
restricted source coverage must remain visible.

Ollama, OpenAI API keys, and Anthropic API keys are planned. Codex integration
requires validation. Claude subscription login is not promised without
Anthropic approval. Answering models and embeddings remain independent.

No patient-record workflow or coverage guarantee is in scope. Cloud requests
will require explicit consent; local storage alone does not make an app HIPAA
compliant.

## Repository layout

```text
payer_policy/provenance.py      Content fingerprint function
payer_policy/source_registry.py Source validation, parsing, and local loading
payer_policy/network_safety.py  Pure destination, address, and redirect checks
payer_policy/https_transport.py  Checked-address HTTPS GET building block
sources/registry.json            Reviewed starting-source registry
tests/                          Offline unit tests
tests/integration/              Explicit local-loopback TLS test
docs/architecture.md            Maintained Markdown system diagram
docs/architecture.html          Original offline HTML snapshot
docs/implementation-plan.md     Living delivery plan
docs/source-definition.md       Validator contract and example
docs/network-safety.md          Offline safety contract and executable example
docs/https-transport.md          HTTPS transport contract and limitations
```

`GETTING_STARTED.md`, `IMPLEMENTATION_GUIDE.md`, `SPARC_Documents/`, and
`plan/feature-rag-application-1.md` are historical design material, not verified
implementation instructions or current constraints. Use this README and docs/
for the rebuild. No legacy performance or production-readiness claim applies.
