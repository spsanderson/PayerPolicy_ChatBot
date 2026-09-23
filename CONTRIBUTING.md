# Development workflow

Build one phase, one module, and one behavior at a time. Group functions only
when they form a small coherent behavior that can be tested together.

1. Describe the function contract and acceptance criteria.
2. Write one failing behavioral test and run it (RED).
3. Implement the smallest solution and run the tests (GREEN).
4. Refactor without adding behavior and rerun all tests.
5. Update README status, the delivery plan, and architecture when boundaries or
   implementation status change. Distinguish proposed from working features.
6. Report actual verification and remaining limitations; never invent metrics.

Use standard-library unittest initially. No network calls in unit tests.
Live-source tests must be separate and preserve URL, access time, and outcomes.
Never commit credentials, user libraries, patient data, or downloaded policies
without explicit rights and scope review.

Keep modules independent of the UI and provider SDKs where possible. Use typed,
small functions with PEP 257 docstrings; follow .github/python.instructions.
Documentation is part of each increment, not a final cleanup task.

## Simplicity and explanation

- Build the smallest working slice that meets the accepted contract. Prefer the
  standard library and existing modules over new dependencies, layers, abstract
  interfaces, or speculative features. Add an abstraction only when a real
  second use or tested boundary makes it worthwhile. Preserve safety checks
  where the risk is real; simplicity is not permission to skip them.
- Give **every function** a concise docstring that says what it does in plain
  English, what it returns, and what failure matters. Explain non-obvious
  inputs and side effects; avoid repeating types that annotations already show.
- When a function depends on another project function or an important library
  function, link to its definition or official documentation and paraphrase the
  relevant behavior in your own words. Explain why that behavior matters here.
  Keep the link near the function (docstring or adjacent short comment); group
  shared references once in module documentation to avoid repeating URLs.
  Do not paste long documentation excerpts or add links for routine syntax.
- Write user-facing docs and change reports in **ELI5** language: define jargon
  on first use, use a concrete example where helpful, and keep technical
  constraints, security caveats, and actual verification intact.
- Make each new function easy to find and test. A few cohesive functions are
  better than a pile of one-line wrappers or a large do-everything function.

Example (illustrative, not a project feature):

```python
def fingerprint_document(content: bytes) -> str:
    """Return a stable fingerprint of the exact file bytes.

    SHA-256 (Python hashlib: https://docs.python.org/3/library/hashlib.html)
    turns bytes into a repeatable digest; matching digests help spot identical
    downloads but do not prove a policy is genuine or applicable.
    Reject non-bytes instead of silently converting their meaning.
    """
    ...
```

This example describes the documentation standard; do not replace an existing
working function with the ellipsis.
