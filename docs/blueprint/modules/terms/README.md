# Terminology dictionary & localisation (`terms`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The terminology dictionary and localisation layer lets each tenant rename the product's terms so it fits their market, client and language. Every label, status name and record-type name is a key with a platform default and layered overrides. The domain model stays neutral underneath (record, inspection plan, deviation) and workflow logic uses stable internal codes, so renaming never changes behaviour. Neutral internal names are never shown raw to users. This is a platform requirement, not an optional feature, and is part of Foundations & architecture, suggested phase P0.

What it does
It resolves every user-facing string through a key-based dictionary with a fallback chain. Examples of renaming: Variation vs Change Order vs Client Instruction, Work Pack vs Campaign, Defect vs Punch vs Deficiency. It also covers languages, date and number formats, and units, and applies them consistently across the UI, emails, PDF reports and exports. A new market is set up quickly by importing a terminology pack. For the first customer, Kaefer working on Rio Tinto remediation, client-specific wording (for example Rio's term for a hold point) can apply without changing Kaefer's own vocabulary elsewhere. Renaming or adding a market is a pack import with no deployment; adding a key is one entry in the default JSON.

Features
- Key-based dictionary (i18next with ICU message format) with tenant overrides and per-client overrides
- Override precedence chain: platform default, market pack, tenant, client, project; cached, with invalidation when a pack is activated
- Admin screen to search keys, preview and override labels
- Plural and gender-safe messages
- Units (metric/imperial) and date formats per tenant
- Applies to UI, emails, PDF reports and exports; the same dictionary feeds server-side PDF templates and emails (Python i18n or ICU via a shared JSON pack)
- Neutral internal names (record, inspection plan, deviation) never shown raw
- Import/export of a terminology pack so a new market can be set up quickly (built-in packs planned for AU mining, NZ, UK, Asia)
- Terminology pack versioning with diff, dry-run preview (which keys change and where they appear) and rollback
- Dictionary coverage linter in CI, plus an admin 'untranslated or hard-coded string' report, to stop raw labels such as 'ITP' or 'NCR' leaking from the AIP code base into renamed markets, especially in emails and PDFs
- Tenant-scoped glossary of standards and abbreviations (CUI, ITP, MDR, WPS, hold/witness/review) with definitions shown as tooltips; each market can map equivalent concepts (for example hold point vs inspection stop)
- Term alias mapping in search and import: searching 'punch' finds 'defect' records, and spreadsheet imports with market-specific column headers map automatically to neutral fields
- Unit conversion layer for measurement fields (mm/in, bar/psi, °C/°F) storing canonical SI, with display units set per project; relevant to NDT thickness, temperature and pressure readings

Interactions
- Design system & app shell: the UI reads every label from the dictionary
- Report engine & published records: report templates use the same keys
- Content types, item types & attributes: their names are tenant data (already renamable in AIP, for example Inspectivity calls them item categories) and stay in entity_types; terms holds only UI keys
- Tenancy, organisations & data residency: dictionary overrides are stored per tenant; new tenants are seeded with a default market pack and client creation enables the client override level
- Workflow engine: statuses display tenant names while logic uses stable internal codes; internal codes are never stored as display text
- Search and import: alias mapping feeds both
- Projects: new projects inherit locale settings

Data
- Dictionary key with module, default locale, default text and ICU message, and translator description
- Override rows keyed by level (market pack, tenant, client, project), key and locale
- Terminology pack with version, contents (key to locale to text), hash and change history for diff and rollback
- Glossary entry: term, abbreviation, definition, tenant
- Alias mapping: alias term to neutral term or field
- Tenant and project settings for locale, date and number formats, and display units
- Measurements stored in canonical SI

Pages
- Admin dictionary screen: search keys, preview, override
- Terminology pack import/export with diff and dry-run preview, plus version history and rollback
- Untranslated or hard-coded string report
- Glossary management
- Tenant and project locale and units settings

Decisions and notes
- Owner accepted: override precedence chain, coverage linter and report, glossary with tooltips, pack versioning with diff, dry-run and rollback, term alias mapping, and the unit conversion layer.
- Never hard-code labels such as 'Variation' or 'ITP' in the UI or API names; keep the domain model neutral.
- The dictionary is part of the locked foundations (with tenancy, authorisation, asset tree, workflow engine and audit) built before vertical modules. Asset tree plus terminology is sized M.
- Beware the naming clash between RFI and the hold-point inspection kind in AIP.
- Brief: 'easily customisable, change terms and names to suit different markets'.

Open questions
- None currently; no advisor conflicts remain unresolved.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
