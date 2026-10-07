# Page specs for `search`

#### Global Search `/search` (Search, retrieval & saved views)

Permission-filtered search with facets and preview

- **layout**: Results list, facet rail, preview pane
- **sections**:
  - Query bar
  - Facets (type, subtree, project, NDT method)
  - Results
  - Recent searches
  - Preview
- **actions**:
  - Search
  - Filter
  - Save as view
  - Open record
- **access**: Authenticated, results filtered by permission

#### Command Bar `(global) Cmd+K` (Search, retrieval & saved views)

Keyboard navigation and actions

- **layout**: Modal palette
- **sections**:
  - Input
  - Results and commands
  - Recents
- **actions**:
  - Navigate
  - Run action
- **access**: Authenticated

#### Structured Finder `/retrieval` (Search, retrieval & saved views)

Deterministic party, date, reference retrieval

- **layout**: Filter form with grouped results and timeline toggle
- **sections**:
  - Filters
  - Grouped results
  - Timeline
- **actions**:
  - Run
  - Add to bundle
  - Pin to case
- **access**: retrieval.use; party restrictions apply

#### Evidence Bundle Builder `/retrieval/bundles/:id` (Search, retrieval & saved views)

Build exports with index, hashes and chain of custody

- **layout**: Selection list with manifest preview
- **sections**:
  - Selected records
  - Index
  - Hash manifest
  - Legal hold marker
- **actions**:
  - Export
  - Apply hold marker
- **access**: Commercial access roles

#### Saved Views Manager `/views` (Search, retrieval & saved views)

Manage and share saved views

- **layout**: List with editor drawer
- **sections**:
  - My/Team/Project views
  - Parameters
  - Display mode
- **actions**:
  - Create/edit
  - Share
  - Use as tile
- **access**: Own; team/project sharing needs views.share

#### Search Settings `/admin/search/synonyms` (Search, retrieval & saved views)

Terminology synonyms and indexing status

- **layout**: Settings page
- **sections**:
  - Synonyms
  - Index status
  - Semantic toggle
- **actions**:
  - Edit
  - Reindex
- **access**: Tenant admin

#### Mobile Search and Scan `/m/search` (Search, retrieval & saved views)

Find assets by tag or scan

- **layout**: Search field with results list
- **sections**:
  - Query
  - Recent assets
  - Results
- **actions**:
  - Search
  - Open asset
- **access**: Authenticated
