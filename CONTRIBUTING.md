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
