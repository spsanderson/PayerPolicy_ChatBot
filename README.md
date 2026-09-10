# PayerPolicy ChatBot

A Windows-first, local policy-research application being built for Anthem's
administration of the NYSHIP Empire Plan Hospital Program.

> Early development. There is no installer, chat interface, downloader, or
> indexed policy collection yet. The previous README described planned features
> as completed; those claims are not verified. Its history remains in Git.

## Working today

- `payer_policy.provenance.fingerprint_document(content: bytes) -> str`:
  SHA-256 fingerprint of exact document bytes, with explicit input validation.
- Standard-library unit tests. No third-party dependencies for this increment.

A fingerprint identifies content, not authenticity or plan applicability.
Empty bytes can be fingerprinted; a later download validator must reject empty
or invalid documents before ingestion.

## Run the tests (development)

Requires Python 3.11 or newer. From the repository root:

```console
python -m unittest discover -s tests -v
```

Example in Python, launched from the repository root:

```python
from payer_policy.provenance import fingerprint_document
print(fingerprint_document(b"abc"))
```

The eventual installer will bundle the application runtime. Python is currently
a development requirement, not the intended end-user installation experience.

## Architecture and delivery

- [Architecture diagram](docs/architecture.html): download/open in any modern
  browser; entirely offline, with implemented and planned states distinguished.
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
payer_policy/provenance.py    Implemented content fingerprint function
 tests/test_provenance.py     Unit tests (under tests/)
 docs/architecture.html      Offline system diagram
 docs/implementation-plan.md Living delivery plan
```

`GETTING_STARTED.md`, `IMPLEMENTATION_GUIDE.md`, `SPARC_Documents/`, and
`plan/feature-rag-application-1.md` are historical design material, not verified
implementation instructions or current constraints. Use this README and docs/
for the rebuild. No legacy performance or production-readiness claim applies.
