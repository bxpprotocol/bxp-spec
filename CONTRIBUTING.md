# Contributing to BXP

Thank you for your interest in contributing to the Breathe Exposure
Protocol. BXP is an open standard governed by the BXP Foundation.
Every contribution — no matter how small — helps build the
infrastructure that protects billions of people's health.

---

## What We Need Most Right Now

BXP v2.0 specification is complete. The most valuable contributions
at this stage are:

- **Implementations** — build BXP-compatible tools, SDKs, or servers
  in any language
- **Validation** — review the specification for technical errors,
  ambiguities, or gaps
- **Testing** — write test cases that verify BXP-compliant behavior
- **Documentation** — improve clarity, add examples, translate to
  other languages
- **Real-world testing** — implement BXP in an actual air quality
  project and report findings
- **RFC proposals** — propose improvements or extensions to the
  specification

---

## Ways to Contribute

### 1. Report an Issue

Found a technical error, ambiguity, or gap in the specification?

- Go to the [Issues tab](https://github.com/bxpprotocol/bxp-spec/issues)
- Click **New Issue**
- Use a clear title: `[SPEC] Section 5.2 — binary header offset error`
- Describe the problem and your suggested correction
- Reference the specific section number

Issue labels:
- `spec-error` — factual or technical error in specification
- `spec-ambiguity` — unclear or ambiguous language
- `spec-gap` — missing information that should be covered
- `enhancement` — suggested improvement or addition
- `question` — request for clarification

### 2. Submit an RFC

Want to propose a new feature, extension, or breaking change?

BXP uses a formal RFC (Request for Comments) process for all
specification changes — modeled on the IETF RFC process.

**RFC Template:**
```
RFC Title: [Short descriptive title]
Author: [Your name or handle]
Date: [Submission date]
Status: Draft
Category: [Core / Extension / Process]

## Summary
One paragraph describing what this RFC proposes.

## Motivation
Why is this change needed? What problem does it solve?

## Specification
Technical details of the proposed change.

## Backward Compatibility
Does this break existing BXP implementations? How?

## Alternatives Considered
What other approaches were considered and why this was chosen.

## Open Questions
Any unresolved questions the community should discuss.
```

Submit RFCs as GitHub Issues with the label `rfc`.

### 3. Build a Reference Implementation

The most impactful contribution is a working implementation.

**Priority implementations needed:**

| Implementation | Language | Status |
|----------------|----------|--------|
| bxp-server | Python 3.11+ | Needed |
| bxp-server-node | Node.js 20+ | Needed |
| bxp-sdk-python | Python 3.11+ | Needed |
| bxp-sdk-js | JavaScript/TypeScript | Needed |
| bxp-sdk-arduino | C/C++ Arduino | Needed |
| bxp-sdk-esp32 | C/C++ ESP-IDF | Needed |
| bxp-mobile | React Native | Needed |

If you are building one of these — open an issue first with label
`implementation` so we can coordinate and avoid duplication.

All reference implementations must:
- Implement the full BXP v2.0 specification
- Include a test suite with >80% coverage
- Include clear documentation and usage examples
- Be licensed under Apache 2.0
- Pass BXP conformance tests when available

### 4. Submit a Pull Request

For documentation improvements, example additions, or minor
specification clarifications:

1. Fork the repository
2. Create a branch: `git checkout -b fix/section-5-clarification`
3. Make your changes
4. Commit with a clear message: `Fix ambiguous wording in Section 5.2`
5. Push and open a Pull Request
6. Fill in the PR template completely

**Pull Request requirements:**
- Reference the related issue number
- Explain what changed and why
- For specification changes — include before and after text
- For code changes — include test results

---

## Contribution Standards

### Language & Tone
- Use clear, precise technical language
- Follow RFC 2119 keyword conventions (MUST, SHOULD, MAY)
- Write for an international audience — avoid idioms and slang
- Be specific — vague suggestions are hard to act on

### Specification Changes
- Every change must have a clear rationale
- Breaking changes require overwhelming justification
- New fields are OPTIONAL by default unless there is strong reason
- All new agents must include WHO or equivalent threshold data
- Backward compatibility is a first-class requirement

### Code Contributions
- Follow the language's standard style guide
- Include comments explaining non-obvious decisions
- Write tests for all new functionality
- Document public APIs completely

---

## Review Process

1. All contributions are reviewed by the Technical Steering Committee
2. Significant changes go through 30-day public comment period
3. TSC votes: accept, request changes, or decline with explanation
4. Accepted changes are incorporated in the next appropriate release
5. Contributors are credited in the release changelog

Review timeline:
- Bug fixes and clarifications: 7 days
- New optional features: 30 days
- Breaking changes: 90 days minimum

---

## Community Standards

BXP is built on the principle that clean air is a human right —
not a privilege of geography or wealth. This community reflects
that principle.

We expect all contributors to:
- Treat everyone with respect regardless of background or experience
- Give and receive feedback constructively
- Prioritize the public good over personal or commercial interests
- Be honest about limitations, uncertainties, and trade-offs
- Credit others for their ideas and work

Behavior that will not be tolerated:
- Harassment or discrimination of any kind
- Bad-faith contributions designed to harm the project
- Attempts to introduce proprietary dependencies or lock-in
- Misrepresentation of the specification for commercial advantage

---

## Recognition

Every contributor is recognized in the project:

- **CHANGELOG.md** — significant contributions credited by name
- **Contributors list** — all contributors listed in the repository
- **RFC authorship** — RFCs permanently attributed to their authors
- **Implementation credits** — reference implementations credited
  to their builders

The people who help build BXP are building infrastructure that
will protect lives at planetary scale. That matters.

---

## Getting Help

- **GitHub Issues** — for specific questions about the specification
- **GitHub Discussions** — for open-ended conversation and ideas
- **Email** — bxpprotocol@proton.me for partnership and 
  institutional inquiries

---

## First Time Contributing?

Not sure where to start? Look for issues labeled `good first issue`.
These are specifically chosen for new contributors — meaningful
but well-scoped tasks that don't require deep BXP expertise.

The best first contribution is always reading SPEC.md carefully
and opening an issue for anything that is unclear. Fresh eyes
catch things that experienced contributors miss.

---

*BXP is built by people who believe the air is public*
*and the data about it should be too.*

*Copyright 2026 Elvarin — Apache 2.0 License*
```
