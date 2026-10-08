# ADR 0014: SIL OFL-1.1 allowed for self-hosted fonts

- **Status:** accepted
- **Date:** 2026-10-08
- **Affects:** DESIGN-01, STACK-04 (`config/licence-policy.json`)

## Context

DESIGN-01 requires IBM Plex Sans and Mono self-hosted from `@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-mono` (no Google Fonts request, so a strict CSP stays possible). Both packages are licensed SIL OFL-1.1, which the STACK-04 licence policy did not list, so the SBOM check denied them as unknown.

## Decision

Add `OFL-1.1` to the `allow` list. The SIL Open Font License is a free, OSI-approved, permissive licence for fonts: embedding and redistribution are allowed (including commercially), with no copyleft on the application code. The only condition is that the font files are not sold on their own and keep their licence notice.

## Consequences

Font packages under OFL-1.1 pass the licence check. No other licence policy rule changes; GPL, AGPL and SSPL stay denied.
