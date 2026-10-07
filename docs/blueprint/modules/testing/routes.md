# Page specs for `testing`

#### Test run results `/settings/quality/runs` (Testing & quality engineering)

View CI pipeline runs and download evidence artefacts.

- **layout**: Register table with filter bar and detail blade.
- **sections**:
  - Runs table (Run ID, Pipeline, Commit, Suite, Status, Duration, Coverage, Started)
  - Run report blade
  - Artefact list
- **actions**:
  - Open report
  - Re-run
  - Download artefacts
  - Export
  - Archive
- **access**: Platform engineers and security/compliance roles; read-only for tenant admins if exposed.

#### Scenario coverage matrix `/settings/quality/scenarios` (Testing & quality engineering)

Show 100% gated control areas (isolation, authorisation, workflow, eligibility, audit chain) with pass status.

- **layout**: Matrix table with gate status chips and drill-down blade.
- **sections**:
  - Control area rows
  - Required vs passing scenarios
  - Gate (100%) status
  - Last verified
- **actions**:
  - View scenarios
  - Open failing test
  - Export matrix
- **access**: Platform engineers, security and compliance roles.

#### Fixtures and datasets `/settings/quality/fixtures` (Testing & quality engineering)

Catalogue of seed, CUI scenario, golden-file, malicious-file and prompt-injection fixtures.

- **layout**: Register table with create blade.
- **sections**:
  - Fixtures table (Name, Kind, Version, Last updated, Used by)
  - Create/upload form
- **actions**:
  - Add fixture
  - Update version
  - Export
  - Refresh
- **access**: Platform engineers; customer acceptance reviewers read-only for CUI scenarios.

#### Load tests and gates `/settings/quality/load` (Testing & quality engineering)

Show load profile, results and promotion gate list.

- **layout**: Summary KPI strip, charts, settings panel.
- **sections**:
  - Load profile (users, burst size)
  - Latest results
  - Required gate list
  - Coverage thresholds
  - Flaky quarantine and evidence retention settings
- **actions**:
  - Edit thresholds
  - Trigger run
  - Download results
- **access**: Platform engineers and operations.
