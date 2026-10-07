# Regional reference data packs (`ref_packs`)

- **Group:** Commercial
- **Phase:** P4

What it is
Regional reference data packs are tenant-selectable reference content for a region: standards codes, cost references, currencies, tax rates and jurisdiction defaults. They are treated as data, not code. The Asia-Pacific material (AIQS/Rawlinsons, NATSPEC, Singapore BCA) is folded into this module as enableable packs rather than a separate asia_pac_pack code module. Commercial module, suggested phase P4.

What it does
A tenant enables the packs it needs, and the content then appears as pick-lists and references in other modules. Packs are versioned, and projects pin a version so existing records keep pointing at the standard revision that was in force when the work was done. Rawlinsons and NATSPEC are licensed content, so the product ships only the structures; customers load their own licensed data. For the first customer (Kaefer on Rio Tinto remediation work) the priorities are AUD, Australian standards (AS/NZS, AS 2885 and CUI-related references) and WA jurisdiction defaults. Other regions are added later.

Features
- Standards and code lists per region
- Standards reference pack linking codes (AS/NZS, AS 2885, ISO, API, ASTM NDT and coating standards) to ITP checklist items and acceptance criteria, so inspectors can cite the governing clause on forms and reports
- Currencies and tax rates
- Exchange rate source and effective date captured on each priced record, for auditable conversion
- Import and enable per tenant
- Customer-loaded licensed content import with a licence flag and no cross-tenant sharing
- Pack versioning with versions pinned per project and an upgrade preview
- Regional vocabulary and jurisdiction pack bundling terminology, tax, public holidays and date/number formats, enabling a market in one step

Interactions
- Terminology dictionary and localisation: supplies regional vocabulary; the vocabulary and jurisdiction pack feeds renamable terminology per market.
- Cost items and schedule of rates (thin): supplies rate references.
- Read by procurement and supplier_catalogs (rates and currency), requirements and compliance_docs (standards references), and variations and changeorders (pricing basis).
- payment_clock uses jurisdiction settings from this module.
- ITP and inspection templates: standards-to-checklist mapping links clauses to checklist items and acceptance criteria.
- It has no dependencies of its own.

Data
- ReferenceLibrary: source, version, licence
- ReferenceItem: code, description, unit, rate, region
- Currency and ExchangeRate: with rate date and source
- StandardsMap: standard code to checklist item or requirement
- Per-tenant pack enablement, per-project pinned pack version, licence flag on loaded content, tenant ownership so licensed content is never shared across tenants
- Jurisdiction settings: tax, public holidays, date and number formats, terminology

Pages
- Library manager (enable, import, version, licence)
- Currency and rate settings
- Picker component used inside other modules
- Upgrade preview for a new pack version

Decisions and notes
- Model as tenant-enabled content, not logic.
- Ship structures only for licensed content (Rawlinsons, NATSPEC); customers load their own data.
- Owner accepted all five scout suggestions: standards linking, version pinning with upgrade preview, regional vocabulary and jurisdiction pack, exchange rate source and date on priced records, and customer-loaded licensed import.
- Deletion rather than disabling applies to dropped modules; webhook_leads is dropped and asia_pac_pack is folded in here.
- Effort estimates from the scout: M for standards linking, versioning and the vocabulary pack; S for exchange rate capture and licensed import.

Open questions
- Priority conflict: the Competitor researcher rates bundled cost databases as low value for an inspection-focused product and advises prioritising multi-currency, AU/NZ locale and configurable terminology, deferring content licensing. The designer's scope includes AIQS/Rawlinsons, NATSPEC and BCA structures. The owner has not decided how much of the cost-reference side to build in P4.
- Third-party licensing terms for Rawlinsons and NATSPEC data are unconfirmed.
- Whether pack update change notifications (seen in the market) are wanted is undecided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
