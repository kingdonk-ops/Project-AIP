# Markup, viewer & plan room (`markup`)

- **Group:** Documents & records
- **Phase:** P2

What it is
A shared annotation layer and plan room for PDFs, drawings and site photos. Users view and mark up files, and see pins for defects, photos and inspections positioned on a drawing page. Markups are stored as data against file versions, so the original file stays immutable. The owner requires markup and annotations on both photos and PDFs. The product is asset-centric: markups and pins can link to a node in the asset hierarchy, and terminology must be renamable per market (first customer Kaefer on Rio Tinto remediation work).

What it does
A three-pane viewer gives a file list, a canvas with markup tools, and a side panel for comments, versions and approval. Photos open straight into markup. The plan room overlays defect, photo and inspection pins on a drawing page with layer toggles. Selecting an asset on a drawing opens its inspection history. Markups are saved as annotation data and are only flattened into a sealed copy on approval, publication or transmittal.

Features
- PDF and image viewer with markup tools: cloud, arrow, text, dimension, freehand and stamp
- Stamp templates and a stamp library (approved, rejected, custom), managed by an admin screen
- Stamps show who, when and document hash
- Scale calibration for on-drawing measurements
- Photo markup (pinning, arrows, text); GPS metadata stripped by default
- Photo markup with before-and-after pairing against the same asset (accepted)
- Markup threads with status (open, resolved) and a comment-thread panel on each markup
- Plan room pins for defects, photos, inspections and notes, with layer toggles for pins, markups and photos; pin detail popover; area filter by date and status
- Asset pin placement linking a drawing location to a node in the asset tree (accepted)
- Inspection finding pins with severity colouring on drawings, for CUI and coating condition maps (accepted)
- Revision overlay comparison between drawing revisions; pins carry forward or are flagged as needing review (accepted)
- Offline drawing sets cached per scope, with annotations syncing later through the existing protocol (accepted)
- Hash-stamped flattened export on approval, producing a sealed marked-up copy while the source stays unchanged (accepted)
- Markups saved as data (annotations JSONB), not burned in until approval

Interactions
- Document library and control: source files and file versions
- Punch list and defects liability: defect pins
- Inspections, ITPs and hold points: photo answers with markup; NDT and CUI photos feed inspection records
- NCRs and daily diary photos also open in the viewer
- Comments, mentions and notifications: comment pins on pages; open and resolved events notify
- Asset hierarchy: pins reference asset_id, not only a drawing page
- Permissions: enforced per source module so hidden layers never leak

Data
- Annotation: type, geometry, page, author, colour, status, linked to a file version
- Markup layer per document version
- Stamp template
- ScaleCalibration
- DrawingSheet: document version, page, scale, calibration, asset or area link
- OverlayItem: type, source module and id, x/y or geometry, layer
- PhotoNotePin
- Pins stored in drawing coordinates and referencing asset_id
- Existing in AIP: PRD media table has annotations JSONB and an annotated_image type; the v2 blade has an 'ISO markup' evidence tile placeholder
- The plan room writes only positioned pins; it reads documents, file versions, comments and defect, punchlist, inspection and NCR pins

Pages
- Viewer: file list, canvas with top toolbar, side panel for comments, versions and approval; stamp library in a side drawer
- Stamp library admin
- Assets > Plan Room: full-screen drawing with a layer panel; clicking a pin opens the record in a side drawer

Decisions and notes
- Owner: markup and annotations are needed on photos and PDFs
- Annotations are non-destructive vector overlays stored separately and versioned; flatten only on approval or publication
- Advisors recommend one annotation service merging file comments and plan room
- Build approach favoured by most advisors: PDF.js with Konva or Fabric, JSON (or XFDF) storage; render large drawings as tiles
- Suggested as Phase 1, scoped to photos and PDFs first
- Differentiator: markup on CUI and NDT photos tied to asset ID, defect or inspection record, with signed stamps
- Competitors: Bluebeam, ACC, Procore, Dalux, Fieldwire, Trimble Connect

Open questions
- Build on PDF.js with Konva or Fabric, or license a commercial SDK (Nutrient/Apryse) to save months at licence cost? The owner has not decided
- Phase scoping: the delivery manager suggests Phase 1 for photos and PDFs only; the accepted drawing features (revision overlay, offline sets) need phase placement
- Annotation storage format: JSONB or XFDF

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
