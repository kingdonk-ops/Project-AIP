# UPLOADS-06 — Upload tray + scan status chip

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-03, UPLOADS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`apps/web/src/features/uploads/`, orval client, `packages/ui`)
4. Only for the layout: [`routes.md`](../../docs/blueprint/modules/uploads/routes.md) ("Upload tray" and "Attachment scan chip")

## Spec

Give the web app one upload tray. It shows per-file progress with pause, resume, retry and cancel, and a recovery prompt after the connection drops. A reusable scan-status chip shows Scanning, Clean or Blocked from server state (tag: extend). The offline Dexie queue belongs to the R1+ field app and is out of scope.

- **files**:
  - apps/web/src/features/uploads/useUpload.ts
  - apps/web/src/features/uploads/upload-store.ts
  - apps/web/src/features/uploads/transports/single-post.ts
  - apps/web/src/features/uploads/components/UploadTray.tsx
  - apps/web/src/features/uploads/components/ScanChip.tsx
  - apps/web/src/features/uploads/components/RecoveryPrompt.tsx
  - apps/web/src/features/uploads/tests/upload-store.test.ts
  - apps/web/src/features/uploads/tests/ScanChip.test.tsx
  - apps/web/src/features/uploads/tests/UploadTray.test.tsx
  - e2e/web/uploads-tray.spec.ts
- **steps**:
  - 1. `upload-store.ts` (a Zustand store or a reducer in context, whichever DESIGN-02 established):
    - per-file state `queued|uploading|paused|confirming|scanning|clean|blocked|failed|cancelled`, with `progress`, `attempts` and `sessionId`
    - pure transitions, with a maximum of 3 automatic retries and exponential backoff (1 s, 2 s, 4 s)
  - 2. `useUpload(projectId)` makes the calls in this order: `POST /uploads/sessions` (generated `packages/api-client`), then the transport, then `POST /confirm`, then polling `GET /sessions/:id/status` every 2 s (backoff to 10 s) until `released` or `rejected`.
    - Transport `single-post.ts` uses `XMLHttpRequest` for upload progress events. Pause aborts the XHR, and resume re-requests a session with the same `clientRequestId` and restarts.
    - If UPLOADS-03 is `done` when you start, also add `transports/multipart.ts`. It resumes from `GET /sessions/:id` `uploadedParts` for files over 100 MiB, and is listed in the PR. Otherwise write a one-line stub follow-up task for it.
  - 3. `UploadTray.tsx` is docked in the DESIGN-02 shell slot on desktop and is a full-screen sheet at widths below 640 px.
    - Each row shows the name, size, progress bar, state text, `ScanChip`, and the actions Pause, Resume, Retry and Cancel.
    - The header has an "Upload files" button that uses the current project from the scope bar, and is disabled with an explanation when no project is selected.
    - Rows persist only in memory.
  - 4. `RecoveryPrompt.tsx`: on `window` `offline`, uploading rows become `paused` with reason `offline`. On `online`, a prompt reads "N uploads were interrupted", with "Resume all" and "Dismiss".
  - 5. `ScanChip.tsx` (props `{status, scannedAt?, reasonKey?}`) maps the server statuses:
    - `requested|uploading|uploaded|scanning|validating` → Scanning
    - `released` → Clean
    - `rejected` → Blocked, with the reason from `uploads.reject.<reason>`
    - `expired|aborted` → Not uploaded

    It shows an icon and text, not colour alone, with `role="status"` and `aria-live="polite"`. Export it from the feature for host modules' attachment lists.
  - 6. All strings use `t('uploads.tray.*')` and `t('uploads.chip.*')` keys. Run axe in the tests.
- **acceptance**:
  - A user can upload several files and watch each one reach Clean or Blocked.
  - Pause, resume, retry and cancel work.
  - Going offline mid-upload pauses the row, and reconnecting offers to resume.
  - The chip never shows Clean unless the server status is `released`.
  - No axe violations at desktop or mobile widths.
- **tests**:
  - **unit**:
    - Store: `uploading` + `error` with `attempts 2` → `uploading` again with `attempts 3`. With `attempts 3` → `failed`.
    - Store: the `offline` event with two `uploading` rows → both `paused`, `reason:'offline'`.
    - `ScanChip status='scanning'` → the text "Scanning" with `role="status"`. `status='rejected', reasonKey='clamav'` → "Blocked" plus the en-AU text for `uploads.reject.clamav`.
    - `ScanChip status='uploaded'` never renders "Clean".
  - **integration**:
    - Component tests with MSW:
      - Session 201 → presigned POST 204 → confirm 200 → status `uploaded`, `scanning`, `released` → the row ends `clean` with the chip showing Clean.
      - Presigned POST 500 twice, then 204 → succeeds with `attempts 2`.
      - Status `rejected` with `reason 'magic_bytes'` → the row shows Blocked.
      - No project selected → the "Upload files" button is disabled.
  - **e2e**:
    - Playwright `web` project on the compose stack, signed in as the `kaefer-demo` user with project P1 selected:
      - Upload `e2e/fixtures/photo.jpg` through the tray → the chip reaches Clean within 60 s.
      - Upload a runtime-generated EICAR `eicar.txt` → Blocked.
      - Start a 20 MiB upload, call `context.setOffline(true)` → the row is Paused. Call `setOffline(false)` → the recovery prompt appears. Click Resume all → the upload reaches Clean.
      - Mobile viewport 390×844 → the tray opens as a full-screen sheet.
      - The axe scan → 0 violations.
