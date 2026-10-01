---
name: 🔀 Pull Request Template
description: Standard PR template for BXP Protocol contributions
title: "[PR] "
labels: []
assignees: []
body:
  - type: markdown
    attributes:
      value: |
        Thanks for contributing to BXP Protocol! Please fill out the sections below.

  - type: checkboxes
    id: type
    attributes:
      label: Type of Change
      options:
        - label: 🐛 Bug fix (non-breaking change fixing an issue)
        - label: ✨ New feature (non-breaking change adding functionality)
        - label: 💥 Breaking change (fix or feature causing existing functionality to change)
        - label: 📝 Documentation update
        - label: 🧪 Test addition/improvement
        - label: ♻️ Refactoring (no functional changes)
        - label: ⚡ Performance improvement
        - label: 🔧 CI/CD / Infrastructure
        - label: 📦 Packaging / Release

  - type: input
    id: related
    attributes:
      label: Related Issue/PR
      description: Link related issues or PRs (e.g., "Fixes #123", "Relates to #456")
      placeholder: "Fixes #123"

  - type: textarea
    id: description
    attributes:
      label: Description
      description: Clear description of what this PR does and why
      placeholder: |
        This PR adds a PurpleAir importer that fetches real-time data from api.purpleair.com
        and converts it to valid BXP records with source: "imported" and proper sensor classification.
      render: markdown
    validations:
      required: true

  - type: textarea
    id: changes
    attributes:
      label: Key Changes
      description: List the main files changed and what they do
      placeholder: |
        - `integrations/purpleair_import.py` - New importer module
        - `integrations/__init__.py` - Export new module
        - `tests/test_purpleair_import.py` - Unit tests
        - `README.md` - Updated integrations section
      render: markdown
    validations:
      required: true

  - type: dropdown
    id: testing
    attributes:
      label: Testing Done
      options:
        - All existing tests pass (`pytest`, `npm test`, conformance)
        - New unit tests added and passing
        - Integration tests added and passing
        - Conformance vectors updated and passing (if spec change)
        - Manual testing performed (describe below)
        - No tests needed (documentation only)
    validations:
      required: true

  - type: textarea
    id: manual_testing
    attributes:
      label: Manual Testing Details
      description: If you did manual testing, describe what you tested
      placeholder: |
        Ran `python integrations/purpleair_import.py --fixture fixtures/purpleair_sample.json --out-dir ./test_output`
        Verified output files are valid BXP JSON with correct source classification.
        Validated against conformance suite: 17/17 pass.

  - type: checkboxes
    id: conformance
    attributes:
      label: Conformance Impact
      options:
        - label: This PR does NOT affect wire format or API contracts
        - label: This PR ADDS new conformance test vectors (spec change)
        - label: This PR MODIFIES existing conformance behavior (breaking)
        - label: This PR requires RFC (specification change)

  - type: checkboxes
    id: checklist
    attributes:
      label: Pre-submission Checklist
      options:
        - label: Code follows project style (ruff for Python, prettier for TS)
          required: true
        - label: All tests pass locally (`pytest`, `npm test`)
          required: true
        - label: Conformance tests pass (`python conformance/verify_python.py`, `node conformance/verify_typescript.mjs`)
          required: true
        - label: Documentation updated (README, docstrings, CHANGELOG.md if user-facing)
          required: true
        - label: No new security vulnerabilities introduced
          required: true
        - label: No secrets, keys, or credentials committed
          required: true
        - label: Commit messages follow conventional commits (feat:, fix:, docs:, etc.)
          required: true

  - type: textarea
    id: screenshots
    attributes:
      label: Screenshots / Demo (if UI/CLI changes)
      description: Drag and drop screenshots or describe CLI output changes
      placeholder: "CLI output now shows: `Generated reading.bxp.json with source=imported, 3 agents`"

  - type: markdown
    attributes:
      value: |
        ---
        **Reviewer Notes:** Tag `@bxpprotocol/maintainers` for review. Specification changes require RFC approval per CONTRIBUTING.md.