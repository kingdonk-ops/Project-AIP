# Page specs for `procurement`

#### Catalogue Browser `/procurement/catalogue` (Supplier catalogue, requisitions & POs)

Browse supplier items and add them to the requisition basket.

- **layout**: Faceted search with filters on the left, results grid or list, and a basket drawer on the right.
- **sections**:
  - Search and filters (supplier, category, price validity)
  - Favourites and recently ordered tabs
  - Item cards or rows
  - Basket drawer
  - Add or edit item dialog
- **actions**:
  - Search
  - Favourite
  - Add to basket
  - Add new item
  - Edit item
  - Submit requisition
- **access**: Users with procurement.view. Price fields are hidden from subcontractor roles.

#### Requisition List `/procurement/requisitions` (Supplier catalogue, requisitions & POs)

List requisitions with status.

- **layout**: DataTable with status filters and saved views.
- **sections**:
  - Filters
  - Requisition table
  - Status chips
- **actions**:
  - Open
  - Filter
  - Export
- **access**: Requesters see their own. Accounts and procurement see all.

#### Requisition View `/procurement/requisitions/:id` (Supplier catalogue, requisitions & POs)

Accounts review, comment, print, reply, approve or reject, and upload the issued PO.

- **layout**: Two columns: lines and totals on the left, comment thread and approvals on the right, with a WorkflowBar at the top.
- **sections**:
  - Header (project, optional asset, required date)
  - Lines table
  - Comment thread with mentions
  - Approval trail
  - Linked PO and uploaded PO file
- **actions**:
  - Print
  - Reply
  - Comment
  - Approve
  - Reject
  - Raise PO
  - Upload signed or issued PO
- **access**: Requester, accounts and approvers. Approve or reject needs procurement.approve.

#### PO List `/procurement/orders` (Supplier catalogue, requisitions & POs)

List purchase orders with an outstanding filter.

- **layout**: DataTable with status tabs (draft, issued, part-received, received, closed).
- **sections**:
  - Status tabs
  - Outstanding toggle
  - PO table
  - Totals bar
- **actions**:
  - Open
  - Filter
  - Export
  - Accounting export (Xero, MYOB, CSV)
- **access**: procurement.view. Export requires procurement.export.

#### PO Detail with Three-Way Match `/procurement/orders/:id` (Supplier catalogue, requisitions & POs)

Single record showing PO, delivery docket and invoice together with the match result.

- **layout**: Header with a WorkflowBar, then tabs: Overview, Lines, Receipts, Documents, Match, Audit.
- **sections**:
  - PO header (number, supplier, delivery address, required date, project, asset)
  - Lines with links to cost code/WBS text, scope tasks and asset nodes
  - Eligibility gate banner (expired vendor insurance or accreditation)
  - Three-panel match view (PO, docket, invoice) with tolerance results
  - Exception queue
  - Documents
- **actions**:
  - Issue PO (blocked if the eligibility gate fails)
  - Send to supplier by email
  - Upload signed PO
  - Receive goods
  - Upload invoice
  - Resolve match exception
  - Close PO
- **access**: Procurement and accounts roles. Subcontractors have no access.

#### Goods Receipt Entry `/procurement/orders/:id/receive` (Supplier catalogue, requisitions & POs)

Record deliveries against a PO, including partials, batch/serial and material certificates.

- **layout**: Form with a lines grid. The mobile version is optimised for the loading dock.
- **sections**:
  - Delivery docket upload
  - Lines receipted vs ordered
  - Batch and serial capture
  - Material cert (MTR) attach
  - Stock destination
- **actions**:
  - Save receipt
  - Capture batch or serial
  - Attach MTR
  - Flag discrepancy
- **access**: Storepersons and site users with procurement.receive

#### Price-List Import and Review Queue `/procurement/imports` (Supplier catalogue, requisitions & POs)

Import supplier price files and approve diffs before publishing.

- **layout**: Wizard for upload and mapping, then a review table of per-line diffs.
- **sections**:
  - Upload or email-ingested files list
  - Column mapping
  - Per-line diff with % change flags and effective-from date
  - Scheduled re-import settings
  - Import job history
- **actions**:
  - Upload file
  - Map columns
  - Approve line
  - Reject line
  - Publish
  - Roll back
  - Schedule re-import
- **access**: Procurement admins with procurement.catalogue_admin. Publishing is separate from import.

#### Vendor Master List `/procurement/vendors` (Supplier catalogue, requisitions & POs)

Directory of suppliers with compliance status.

- **layout**: DataTable with compliance status chips.
- **sections**:
  - Search and filters
  - Vendor table (ABN, terms, insurance status)
- **actions**:
  - Create vendor
  - Open
  - Export
- **access**: procurement.view

#### Vendor Detail `/procurement/vendors/:id` (Supplier catalogue, requisitions & POs)

Vendor details, certificates, bank details and change control.

- **layout**: Tabs: Profile, Contacts, Certificates, Bank details, Price lists, Orders.
- **sections**:
  - Profile (ABN, terms)
  - Insurance and accreditation certificates with expiry
  - Bank-detail change log with dual approval and call-back verification
  - Linked price lists
- **actions**:
  - Edit
  - Upload certificate
  - Request bank change
  - Approve bank change (second approver)
  - Log call-back
- **access**: Procurement and accounts. Bank change approval requires two distinct users with procurement.bank_approve.
