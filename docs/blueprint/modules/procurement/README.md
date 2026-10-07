# Supplier catalogue, requisitions & POs (`procurement`)

- **Group:** Commercial
- **Phase:** P3

What it is
A basic procurement module for the Commercial area that combines a supplier catalogue (what can be bought from approved suppliers, with prices kept current) with the full chain: requisition, approval, purchase order, delivery, invoice. It is treated as one Procurement context, covering both the supplier catalogue and vendor management and the PO core. The owner has decided it stays basic, and accounting is not built here. Suggested phase P3. Not yet built in AIP; the owner's comment on supplier catalogs defines the flow.

What it does
Users browse a catalogue of supplier items, add them to a requisition cart and send it to accounts. Accounts are notified in-app (their own user account) and by email, and can view, print, reply and comment. Accounts approve or reject, raise a PO, send it to the supplier by email and upload the signed or issued PO. When the delivery arrives, the PO, delivery docket and invoice are all visible together on one record, with a three-way match. Received items flow into stock. Catalogue updates are as automated as possible, with a review step so silent price errors cannot publish.

Features
- Supplier catalogue: items, codes, SKU, spec, units of measure, prices, supplier, lead time; users can add new items and edit existing ones
- Price lists with validity dates and tiers
- Import and update from supplier price files (CSV/Excel), with scheduled re-imports and email-ingested files
- Price-list import review queue: per-line diffs, % change flags and effective-from dates, approved before publish
- Search and filter the catalogue; favourites; recently ordered
- Requisition cart, submitted to accounts with in-app notification and email
- Accounts view: print, reply, comment, approve/reject via the approvals engine
- Raise PO (number, supplier, lines, delivery address, required date, project, optional asset, status, totals); send to supplier by email; upload the signed/issued PO
- PO status: draft, issued, part-received, received, closed; PO list with outstanding filter
- Goods receipt against PO with delivery docket upload; partial deliveries; batch/serial capture
- Capture material certs (MTRs, batch numbers) on goods receipt
- Link PO lines to cost items, scope tasks and asset nodes, so received coatings, insulation and consumables trace to the work they were used on
- Supplier invoice upload and three-way match (PO / docket / invoice) with tolerance rules and an exception queue, all on one record
- Vendor master: contacts, ABN, terms, insurance certs
- Supplier eligibility gate: block PO issue when vendor insurance or accreditation certificate is expired (reuses AIP's certificate hard-block pattern)
- Vendor bank-detail change control: dual approval and call-back verification log
- Accounting export (Xero, MYOB, CSV) of approved POs and matched invoices
- Pricing hidden from subcontractor roles

Interactions
- Workflow & approvals engine: requisition and PO approval
- Comments, mentions & notifications: replies, in-app and email notifications
- Stock, consumables & materials: receipts flow into stock; goods.received event
- Site logistics & mobilisation: delivery bookings
- Contacts & companies: supplier records
- Document library & control: PO, docket and invoice files
- Emits requisition.submitted and goods.received

Data
- Vendor, CatalogItem, PriceList, Requisition, RequisitionLine (optional asset_id), PurchaseOrder, POLine, GoodsReceipt, Invoice, document links (PO, docket, invoice), import jobs with diff lines, bank-detail change log
- Reads contacts, projects, users; writes PO drafts and notifications
- Supplier price lists are commercially sensitive: no visibility across tenants or to other suppliers or subcontractors
- Inbound PO and other uploads are treated as untrusted files

Pages
- Catalogue browser with search, filters and basket
- Price-list import and review queue
- Requisition view with comment thread, print, reply and PO upload
- PO list and PO detail with three-way match panel (PO, docket, invoice)
- Receipt entry
- Vendor master

Decisions and notes
- Owner: procurement is a basic system; flow as described in the owner's comment
- Do not build accounting; export instead
- Accepted: import review queue, three-way match with tolerances, bank-detail change control, PO line links and material certs, accounting export, supplier eligibility gate
- Automation of catalogue updates may follow the core flow (lead programmer and delivery manager advice), but scheduled and email-ingested import is accepted in scope

Open questions
- Is this needed in Kaefer's v1 or Phase 2 (tech stack advisor)?
- Should optional punch-out via cXML or API be included? It was suggested only by the tech stack advisor and the scout and has not been accepted.
- Which email service sends POs (Amazon SES was suggested)?
- Should PDF price lists be supported for import (suggested by the designer)?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
