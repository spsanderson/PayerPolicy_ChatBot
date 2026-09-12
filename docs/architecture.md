# PayerPolicy — System Architecture

**Windows-first · Empire Plan Hospital Program · Phase 1, increment 4**

Content fingerprinting, source validation, JSON parsing, and local registry
loading are implemented. Offline URL, resolved-address, and redirect/history
checks are implemented too. One reviewed reference entry is checked in.
Document storage, DNS/HTTP transport, and the rest of the pipeline remain planned.

This Markdown version uses Mermaid for diagram rendering on GitHub and in
Mermaid-enabled Markdown viewers. The component table below remains readable
in any Markdown viewer. The [original HTML diagram](architecture.html) is
retained as an offline snapshot; this Markdown document is the maintained view.

## System diagram

Solid arrows show implemented local loading/calls. Dashed arrows show proposed
pipeline connections.

```mermaid
flowchart TB
    sources["Official policy sources: Anthem + NYSHIP publications"]
    cloud["Cloud model providers: explicit opt-in only"]

    subgraph windows["User's Windows machine — proposed local boundary"]
        acquisition["Acquisition worker: registry / fetch / validation"]
        ui["Browser UI + local API: library / review / ask"]
        adapters["Answer adapters: cloud or local Ollama"]
        originals["Originals + provenance: versions / URLs / applicability"]
        extraction["Extraction + review: PDF / HTML / OCR / corrections"]
        retrieval["Retrieval + citations: scope / date / evidence"]
        chunks["Chunks + embeddings: separate from answering model"]
        stores["Local search stores: SQLite + vector index"]
        fingerprint["IMPLEMENTED: fingerprint_document() — exact bytes to SHA-256"]
        validator["IMPLEMENTED: validate_source_definition() — metadata / URLs / status"]
        registryfile["IMPLEMENTED: sources/registry.json — one reviewed reference"]
        loader["IMPLEMENTED: load_source_registry()"]
        parser["IMPLEMENTED: parse_source_registry()"]
        destination["IMPLEMENTED: validate_destination_url() — HTTPS / host allowlist"]
        addresses["IMPLEMENTED: validate_resolved_addresses() — supplied answers only"]
        redirects["IMPLEMENTED: validate_redirect() — target / history / hop limit"]
        transport["Planned: DNS + validated-address connection / verified TLS / no auto-redirects"]
        redirects --> destination
        acquisition -.-> transport
        transport -.-> destination
        transport -.-> addresses
        transport -.-> redirects
        registryfile --> loader
        loader --> parser
        parser --> validator
        support["Planned: installer / credentials / job recovery / backup / evaluation"]

        acquisition -.-> originals
        acquisition -.-> ui
        originals -.-> extraction
        extraction -.-> chunks
        extraction -.-> retrieval
        chunks -.-> stores
        ui -.-> adapters
        adapters -.-> retrieval
        retrieval -.-> stores
    end

    sources -.-> acquisition
    adapters -.->|"Consent required"| cloud

    classDef planned fill:#0f172a,stroke:#94a3b8,stroke-dasharray:6 4,color:#e2e8f0;
    classDef implemented fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#e2e8f0;
    class sources,cloud,acquisition,ui,adapters,originals,extraction,retrieval,chunks,stores,support,transport planned;
    class fingerprint,validator,registryfile,loader,parser,destination,addresses,redirects implemented;
```

**Legend:** Green nodes are implemented functions or checked-in data. Dashed nodes and arrows
represent planned components and data flow. The Windows boundary is proposed;
it does not imply that a packaged application exists.

## Component status

| Component | Responsibility | Status |
|---|---|---|
| `fingerprint_document()` | Fingerprint exact document bytes using SHA-256 | Implemented and unit-tested |
| `validate_source_definition()` | Check source metadata, URLs, and applicability status | Implemented and unit-tested |
| `parse_source_registry()` | Strict JSON parsing and whole-registry validation | Implemented and tested |
| `load_source_registry()` | Read a local UTF-8 registry | Implemented and tested |
| `sources/registry.json` | One reviewed Anthem overview; reference only | Checked in and load-tested |
| `validate_destination_url()` | Exact reviewed HTTPS host/port and raw URL checks | Implemented and offline-tested |
| `validate_resolved_addresses()` | Reject a whole supplied answer set if any address is unsafe | Implemented and offline-tested; does not resolve DNS |
| `validate_redirect()` | Recheck target, caller history, loops, and hop limit | Implemented and offline-tested; does not follow redirects |
| DNS/HTTP transport | Validated-address connections, verified TLS/SNI, proxy/rebinding controls | Planned; no complete SSRF boundary yet |
| Official policy sources | Anthem and NYSHIP publications | Integration planned |
| Acquisition worker | Source registry, fetching, and download validation | Planned |
| Browser UI + local API | Library browsing, document review, and questions | Planned |
| Originals + provenance | Original documents, versions, source URLs, and applicability | Planned |
| Extraction + review | PDF/HTML processing, OCR, and corrections | Planned |
| Chunks + embeddings | Prepare searchable content independently of the answering model | Planned |
| Local search stores | SQLite and an embedded vector index | Planned |
| Retrieval + citations | Scope/date filtering and supporting evidence | Planned |
| Answer adapters | Connect local Ollama or cloud models | Planned |
| Cloud model providers | Optional external inference with explicit consent | Planned |
| Cross-cutting services | Installer, credentials, job recovery, backup, and evaluation | Planned |

## Implemented now

Foundation components with no external dependencies:

- **Document fingerprints:** identify identical content, not authenticity.
- **Source-definition validation:** check structure without verifying source
  authority or actual policy applicability.

- **Registry parsing:** rejects invalid content and duplicates atomically.
- **Local loading:** reads UTF-8 and preserves file/encoding errors.
- **Reference entry:** Anthem overview with a dated review note.
- **Network-safety helpers:** pure checks for reviewed URL destinations, complete
  caller-supplied addresses, and redirects. No inference of live DNS or access
  permission. See the [contract and exclusions](network-safety.md).

Only the loader reads a local file. None downloads documents, accesses a
database, or calls a model.

## Next small increment

Scope and approve the DNS/HTTP transport boundary. A future downloader must
connect only to a validated address without an unchecked second DNS lookup,
retain hostname/SNI and TLS verification, disable automatic redirects and unsafe
proxy/environment fallbacks, and validate fresh answers for every target.
Rebinding, retries, redirects, and actual connection behavior require integration
tests. Pure helpers alone cannot prevent SSRF; no automatic downloader exists.

## Trust boundary

- Documents are untrusted evidence, never executable instructions.
- Cloud transmission requires consent.
- General Anthem policy is not automatically Empire Plan policy.
- Embeddings remain separate from the answering model.

## Related documentation

- [Delivery plan](implementation-plan.md)
- [Source-definition contract](source-definition.md)
- [Network-safety contract](network-safety.md)
- [Project README](../README.md)
