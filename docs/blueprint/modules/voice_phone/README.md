# Voice notes & phone log (`voice_phone`)

- **Group:** Field operations
- **Phase:** P4

What it is
A module that turns spoken notes and phone calls into structured, dispute-ready records. Not built in AIP (suggested phase P4); advisors deferred voice/AI until the AI transcription and AU-region data-flow controls exist. It shares one speech-to-text pipeline with meetings transcription.

What it does
A worker records or types a note and AI drafts a diary entry, defect or task for them to confirm; nothing is saved without confirmation. Phone calls and verbal instructions are logged with parties, direction, duration, summary and the instruction given, locked after saving and corrected only by superseding records. Recording requires a consent notice, and transcription runs through the AI governance controls.

Features
- Voice note to structured draft (diary note, defect, task) with editable fields and a confirm or discard step; drafting only, no tool actions
- Phone call log: parties (via contacts), direction, duration, summary, instruction given, related asset or package, follow-up confirmation
- Verbal instruction flag feeding change and claims, with notification to the commercial lead
- Recording consent prompt with jurisdiction rules, consent stored per record
- Transcription via an AU-region model with tenant opt-in
- Custom vocabulary for NDT, CUI and coating terms plus asset tags
- Asset and scope suggestion from spoken tag numbers, user-confirmed
- Verbal instruction confirmation email or task requesting written confirmation
- Side-by-side transcript and audio with edit history
- Per-tenant switch to disable audio retention after transcription
- Offline voice capture queue with deferred transcription

Interactions
- AI governance & data controls: transcription data controls, opt-in, data-flow log
- Site diary & field reports: creates diary entries
- Change orders, variations & MOC: verbal instructions start a change record
- Claims evidence pack: evidence chronology
- Correspondence: confirmation emails; contacts for parties; tasks for follow-ups
- Events consumed: ai.transcription_completed and failed, uploads.file_released, retention.audio_due, ai_gov.tenant_optin_changed
- Events emitted: voice.note_captured, voice.transcription_requested, voice.draft_ready, voice.draft_confirmed, voice.draft_discarded, voice.call_logged, voice.verbal_instruction_flagged
- Notifications: draft awaiting confirmation, transcription failed, instruction flagged, change started, audio scheduled for deletion, consent missing on a recorded call

Data
- VoiceNote: audio reference, transcript, provider, region and model, proposed type, extracted fields, confirmation status, result record link
- PhoneCall/PhoneEntry: date and time, direction, duration, parties, summary, instruction, instruction flag, asset or package, follow-up
- ConsentRecord: notice text, jurisdiction rule applied, acceptance
- Raw audio in S3 under a retention schedule; transcripts treated as untrusted input
- Entries attributable and immutable after confirmation
- Configuration: consent text and rules, tenant opt-in and provider region, audio retention, draft target types and mappings, prompt versions, verbal instruction keywords

Pages
- Voice notes register (/voice) with draft-review drawer and pending-drafts banner
- Capture note (/voice/new): recording disabled without tenant opt-in
- Draft review (/voice/:id): audio and transcript left, editable draft right
- Phone call log (/voice/calls) with flagged instructions tab
- Permissions: voice.view, voice.create, voice.review, voice.manage (early audio deletion), voice.instruct
- Settings: opt-in, region (AU only by default), consent rules, retention, allowed draft types, draft expiry, recipients, maximum recording length, terminology keys

Decisions and notes
- All six advisor suggestions were accepted by the owner
- A human always confirms before an AI draft becomes a record
- Avoid call recording unless the consent model is settled

Open questions
- Phase conflict: the architecture advisor suggested phase 3, while the delivery manager and the plan say phase 4. The owner has not decided.
- Is call recording in scope at all, or only logging and voice notes?
- Raw audio retention default period?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
