# PayerPolicy — System Architecture

**Windows-first · Empire Plan Hospital Program · Phase 1, increment 2**

Content fingerprinting and source-definition validation are implemented.
Everything else in the system diagram is planned. The foundation functions
are not yet connected to storage or downloading.

This Markdown version uses Mermaid for diagram rendering on GitHub and in
Mermaid-enabled Markdown viewers. The component table below remains readable
in any Markdown viewer. The [original HTML diagram](architecture.html) is
retained as an offline snapshot; this Markdown document is the maintained view.

## System diagram

All arrows show **proposed**, not implemented, connections.

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
    class sources,cloud,acquisition,ui,adapters,originals,extraction,retrieval,chunks,stores,support planned;
    class fingerprint,validator implemented;
```

**Legend:** Green nodes are implemented functions. Dashed nodes and arrows
represent planned components and data flow. The Windows boundary is proposed;
it does not imply that a packaged application exists.

## Component status

| Component | Responsibility | Status |
|---|---|---|
| `fingerprint_document()` | Fingerprint exact document bytes using SHA-256 | Implemented and unit-tested |
| `validate_source_definition()` | Check source metadata, URLs, and applicability status | Implemented and unit-tested |
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

Two pure functions with no external dependencies:

- **Document fingerprints:** identify identical content, not authenticity.
- **Source-definition validation:** check structure without verifying source
  authority or actual policy applicability.

Neither function downloads documents, accesses a database, or calls a model.

## Next small increment

A registry loader and one reviewed official source entry. No automatic
downloads until network and applicability boundaries are tested.

## Trust boundary

- Documents are untrusted evidence, never executable instructions.
- Cloud transmission requires consent.
- General Anthem policy is not automatically Empire Plan policy.
- Embeddings remain separate from the answering model.

## Related documentation

- [Delivery plan](implementation-plan.md)
- [Source-definition contract](source-definition.md)
- [Project README](../README.md)
