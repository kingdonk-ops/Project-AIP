# Page specs for `voice_phone`

#### Voice notes register `/voice` (Voice notes & phone log)

Track notes, drafts and outcomes.

- **layout**: DataTable with filters and a draft-review drawer.
- **sections**:
  - Filters (status, proposed type, author, project, date, transcription)
  - Notes table (recorded at, author, input, duration, proposed type, status, result, audio retention date)
  - Pending-drafts banner
- **actions**:
  - New note
  - Review draft
  - Confirm
  - Discard
  - Play audio
  - View transcript
  - Open created record
  - Delete audio early
  - Reassign project
- **access**: Authors see their own. Project leads see all with voice.view. Early deletion needs voice.manage.

#### Capture note `/voice/new` (Voice notes & phone log)

Record or type a note with consent.

- **layout**: Focused single-column capture screen.
- **sections**:
  - Project and input mode
  - Recorder or long text
  - Consent notice and checkbox
  - Context asset picker
  - Transcription opt-in status
- **actions**:
  - Record
  - Pause
  - Type instead
  - Submit for drafting
  - Cancel
- **access**: voice.create. Recording is disabled if the tenant has not opted in.

#### Draft review `/voice/:id` (Voice notes & phone log)

Edit and confirm the AI draft. Nothing saves until confirmed.

- **layout**: Split view with audio and transcript on the left and editable draft form on the right.
- **sections**:
  - Capture summary
  - Audio player and retention
  - Transcript with provider, region and model
  - Proposed record and editable fields
  - Suggested asset (user confirms)
  - Consent record
  - Created record link
  - Data-flow log
- **actions**:
  - Change draft type
  - Edit fields
  - Confirm
  - Discard
  - Re-run drafting
  - Retranscribe
- **access**: The author, or a delegate with voice.review.

#### Phone call log `/voice/calls` (Voice notes & phone log)

Register of calls and verbal instructions.

- **layout**: DataTable with a detail drawer.
- **sections**:
  - Filters (direction, party, verbal instruction, date)
  - Calls table (time, parties, direction, duration, summary, instruction, change link)
  - Flagged instructions tab
- **actions**:
  - Log call
  - Flag verbal instruction
  - Start change record
  - Link to diary day
  - Export
- **access**: voice.view; flagging and change start need voice.instruct.

#### Log call `/voice/calls/new` (Voice notes & phone log)

Capture call details quickly.

- **layout**: Form, mobile-friendly.
- **sections**:
  - Parties and companies
  - Direction, time, duration
  - Summary
  - Instruction given and flag
  - Recording consent and jurisdiction rule
  - Context asset or project
- **actions**:
  - Save
  - Save and start change
  - Cancel
- **access**: voice.create.

#### Voice settings `/voice/settings` (Voice notes & phone log)

Control opt-in, provider, consent and retention.

- **layout**: Tabbed settings.
- **sections**:
  - Tenant opt-in
  - Provider and region
  - Consent text and jurisdiction rules
  - Audio retention
  - Allowed draft types
  - Draft expiry
  - Verbal instruction recipients
  - Max recording length
  - Terminology keys
- **actions**:
  - Save
  - Test consent text
  - View AI register entry
- **access**: Tenant admin with voice.configure and ai_gov permission.

#### Mobile voice capture `/m/voice` (Voice notes & phone log)

One-handed recording on site.

- **layout**: Full-screen recorder with a large record button and a queue list.
- **sections**:
  - Record button and timer
  - Consent prompt
  - Offline queue
  - My drafts
- **actions**:
  - Record
  - Stop and send
  - Type note
  - Confirm draft
  - Discard
- **access**: Full users with voice.create. Audio is held offline and uploaded through the quarantine pipeline.
