# Search, retrieval & saved views (`search`)

- **Group:** Reporting, search & AI
- **Phase:** P2

What it is
Search, retrieval and saved views is the module that lets users find anything in the platform, retrieve dated and referenced evidence for commercial and legal work, and save any filter for reuse as a list, count or dashboard tile. It sits in the Reporting, search and AI group, suggested phase P2. Search is asset-centric: tags, asset subtrees and NDT-method filters are the practical advantage over generic document search.

What it does
It provides global search across assets, inspections, issues, documents, reports, correspondence and other records, combining Postgres full-text search with pgvector semantic search and rank fusion. Every query is filtered by the caller's permissions and tenant inside the SQL query itself, never post-filtered, so results and aggregates cannot leak. Retrieval adds deterministic filters by party, date window, reference and record type for commercial teams, with fuzzy search used only for fuzzy matches so exact filters stay defensible. Saved views store a filter against any record type, can be personal, team or project, accept parameters, and are reused as a list, count or tile. Search follows the tenant's terminology, so renamed terms still find records.

Features
- Header search: assets by tag, documents, issues, reports; deep links (built: direct asset matches plus deep link, TASKS section 26)
- Command bar (keyboard) for navigation and actions
- Postgres full-text search with pgvector semantic search and rank fusion; semantic search enabled once AI is enabled
- Tag-aware asset search with fuzzy and pattern matching, handling partial tags, line numbers, spool marks, wildcard asset codes and typos
- Terminology-aware synonyms driven by the tenant dictionary, so labels differ per market and renamed terms still match
- Search inside document OCR text and drawing title blocks, linked back to assets, with hit highlighting, to find an isometric or datasheet by line number
- Type facets, asset subtree and project filters, tag and NDT-method filters, recent items and recent searches, result preview
- Retrieval filters: party, date window, reference, record type, asset
- Evidence retrieval pack builder from search results: dated, referenced sets of records with an index, document hashes (hash manifest) and chain of custody; pin to a case; legal hold marker
- Saved views: personal, team, project; as list, count or tile
- Saved views with parameters such as 'my area' or 'this shutdown', so one view serves many users and projects
- Embedding lifecycle tied to permissions, deletion and legal hold: embeddings are tenant-scoped, deleted when source records are deleted, on offboarding or crypto-shredding, and handled under legal hold release rules
- Permission filtering at query time, never post-filtered, including embeddings
- Party-level restrictions so one party's privileged or without-prejudice material is not exposed to another
- Masked health fields are not indexed
- Every query and export is logged

Interactions
- Roles, permissions and teams: the permission filter and party restrictions
- Document library and control: OCR text and title blocks
- Dashboards and KPI reporting: tiles from saved views
- AI assistant and agents: retrieval as a tool for AI
- Correspondence, change orders, RFIs, variations and timeline events: read for claim-grade retrieval; exports logged to the timeline
- Contacts: party resolution
- Tenant terminology dictionary: synonyms and labels
- Indexed via domain events and background jobs: assets, documents (OCR), tasks, RFIs, submittals, NCRs, inspections, comments and meeting transcripts

Data
- Search index entry: tenant, record type, record id, asset, project, text, embedding, ACL tags
- Indexing job
- Query log (every query and export)
- Retrieval query: party, date window, reference, record types
- Result set snapshot
- Export bundle: index, hashes, chain of custody
- Saved view: filter against any record type, owner, scope (personal, team, project), parameters, display mode (list, count, tile)

Pages
- Global search with type facets, asset subtree and project filters, recent searches and result preview
- Command bar
- Structured finder for party, date, reference and asset filters, with results grouped by record type and a timeline view
- Export and bundle builder, limited to roles with commercial access
- Saved views manager and sharing

Decisions and notes
- Use Postgres full-text search plus pgvector; avoid OpenSearch or Meilisearch until a measured need, since it adds tenant-isolation work (spec E9-S2; the PRD decision on a later move stays open).
- Drop BOQ and BIM collections in v1.
- Exports respect legal hold and records retention, include document hashes, and are logged to the timeline.
- Results never include material the user cannot normally view.
- Cross-collection vector search is not a buyer differentiator unless accurate on technical documents; the differentiators are asset-tree and tag facets, and party, date and reference retrieval with hash-manifest bundles.
- Claim-grade retrieval depends on correspondence and change orders, so it is a later phase.
- The embedding provider counts as another data processor.

Open questions
- None recorded where advisors conflict; the owner's accepted suggestions cover the scope above. Still to confirm: the embedding provider and its data-processor terms, and the phase for claim-grade retrieval relative to P2.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
