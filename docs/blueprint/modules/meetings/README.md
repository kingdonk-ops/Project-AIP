# Meetings & AI minutes (`meetings`)

- **Group:** Collaboration & coordination
- **Phase:** P4

What it is
Meetings & AI minutes (Collaboration & coordination, suggested phase P4) covers meeting agendas, minutes, decisions and action items, with voice capture and AI transcription. It is used to run toolbox, progress, HSE and client meetings. The owner's requirement: use voice input and/or recording, and use AI to transcribe meeting minutes, from phone, tablet, computer or website. A person always confirms the AI draft before anything is published. Status in AIP: not built; planned.

What it does
A user plans a meeting with an agenda and attendees, records audio (or dictates, or uploads a recording), and the platform transcribes it and drafts minutes, decisions and actions. The chair reviews the draft with the transcript beside it, confirms or corrects it, and publishes signed minutes. Actions become tasks with an owner and due date. Decisions and discussion can be tagged to assets, packages, NCRs and RFIs so meetings become part of asset history. Recording is an optional, per-tenant opt-in feature and requires consent. Transcripts are treated as untrusted input to the AI model.

Features
- Meeting planner: agenda (with agenda templates and recurring meeting series), attendees (contact or user, with attendance and apologies), minutes, decisions and actions recorded per item
- Record audio from phone, tablet, desktop or browser; upload a recording; resumable uploads; offline recording
- AI transcription and draft minutes with action extraction; human confirmation before publishing
- Consent capture workflow: recording notice shown to all attendees, per-attendee consent state recorded, recording blocked or paused if someone declines
- Transcript-to-minutes review editor with source highlights: click an AI-suggested action to hear and see the originating segment
- Asset and package tagging inside minutes, with suggested links to assets, NCRs and RFIs named in the discussion
- Domain vocabulary hints for transcription (NDT, CUI, weld, ITP terms and project asset tags)
- Audio retention policy: automatic deletion after minutes are approved (transcript kept, audio optional), with legal-hold override; recordings stored under legal-hold-aware retention
- Toolbox-talk mode: short templated meeting with quick attendee sign-on by PIN or QR and a single signed attendance record, offline-capable
- Actions flow into tasks with owner and due date; open actions carry forward into the next meeting
- Signed minutes publishing, distributed to attendees with acknowledgement
- Attendees' contributions can be corrected

Interactions
- AI governance & data controls: transcription controls, tenant opt-in, provider and region settings
- Tasks, deadlines & my work: actions become tasks and deadline entries
- Report engine & published records: published minutes
- Voice notes & phone log: shared audio pipeline (browser MediaRecorder upload, Transcribe, then LLM draft that a human confirms)
- Reads contacts, users, projects and open items from RFIs, submittals, interface management and NCRs to build the agenda
- Sends distribution via notifications, correspondence and transmittals; logs to the timeline

Data
- Meeting: series, type, asset/package links
- Agenda item
- Attendee: contact or user, attendance, apologies, consent state
- Recording: audio, resumable upload, retention, legal hold
- Transcript
- Minutes: draft, approved, signed
- Decision
- Action: owner, due date, linked asset
- Vocabulary hints per project

Pages
- Meeting list and planner (Projects and Planning area)
- Meeting detail page: agenda, record or upload audio, AI-drafted minutes for review, actions that become tasks
- Live capture screen with recording and quick notes
- Minutes review editor: transcript beside AI-suggested decisions and actions, with source highlights
- Toolbox-talk sign-on screen (PIN or QR)

Decisions and notes
- Owner decision: voice input and/or recording, AI transcription, on phone, tablet, computer and website.
- Owner accepted: consent capture, review editor with source highlights, asset and package tagging, retention policy with legal-hold override, vocabulary hints, toolbox-talk mode.
- AI drafts are never published or signed without human confirmation.
- Use an AU-region transcription service (for example Amazon Transcribe ap-southeast-2, or Whisper in a worker) with tenant opt-in, then an LLM summary. Check data residency and consent before sending audio or text to any external AI service (IRAP and Privacy Act concerns).
- Keep audio in tenant storage; show consent notices to all attendees.
- Transcripts are untrusted input to the model.
- Differentiator: voice capture on phone or tablet, with AI minutes whose actions link to assets, tasks and the deadline register.

Open questions
- None conflicting. Still to confirm: the transcription provider choice (Amazon Transcribe versus Whisper in a worker), the default retention period, and whether PIN or QR sign-on needs a separate identity rule for non-users.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
