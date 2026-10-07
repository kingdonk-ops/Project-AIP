# DESIGN-04 — Record detail pattern, dialogs, toasts, empty/loading/error states

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) (the "Record detail", "Real dialogs" and "Empty-state, loading and error patterns" bullets)
3. ADRs: 0004 (`packages/ui`)

## Spec

Provide the shared record-detail layout and the feedback primitives every P1 detail page uses: a confirm dialog with a promise API, non-blocking toasts, and standard empty, loading and error states (including offline and sync-conflict variants). Ban `window.confirm`, `alert` and `prompt`.

- **files**:
  - packages/ui/src/patterns/RecordDetail.tsx
  - packages/ui/src/patterns/WorkflowBar.tsx
  - packages/ui/src/feedback/confirm.tsx
  - packages/ui/src/feedback/toast.tsx
  - packages/ui/src/feedback/states.tsx
  - packages/ui/src/patterns/*.test.tsx
  - packages/ui/src/feedback/*.test.tsx
  - packages/ui/src/index.ts
  - packages/ui/eslint.config.mjs
- **steps**:
  - 1. Build RecordDetail with props `{id, title, breadcrumb, status, workflow?, tabs, rightRail?, actions?}`. The header shows the ID in mono, the title, the breadcrumb slot (for the asset path later) and a StatusChip. The optional WorkflowBar shows the current step and the next allowed actions, passed in, never computed. Tabs are URL-addressable (`?tab=history`). The default tab ids are `details|linked|documents|history`; callers may omit tabs. The right rail is collapsible, with slots for comments, approvals and attachments. Superseded entries render with a "superseded" StatusChip and a link to the replacement; they are never hidden.
  - 2. In confirm.tsx, add a `<ConfirmProvider>` and `confirm({titleKey, bodyKey, confirmKey, tone:'default'|'danger', requireText?}) → Promise<boolean>`, built on the ui Dialog. Focus starts on Cancel for danger, Escape cancels, and `requireText` (type the code to confirm) disables Confirm until the text matches.
  - 3. In toast.tsx, add `<Toaster>` and `toast.success|info|error(messageKey, params?, {action?})`. Toasts are non-blocking and use an `aria-live="polite"` region (`assertive` for error). Success and info auto-dismiss after 5s, but not while hovered or focused; errors stay until dismissed. Show at most 3 at a time. Use reduced motion when `prefers-reduced-motion` is set.
  - 4. In states.tsx, add `EmptyState {icon, titleKey, bodyKey, action?}`, `LoadingState {variant:'skeleton'|'spinner', rows?}` with `aria-busy`, and `ErrorState {error, onRetry}`. ErrorState maps HTTP status to a term key: 403 is "You don't have access", 404 is "Not found", 409 is "Changed by someone else", 5xx is generic. It shows the response's correlation id (`X-Request-Id`) in mono with a copy button. Add `OfflineState` and `SyncConflictState {mine, theirs, onKeepMine, onKeepTheirs, onMerge?}` variants for the field and offline work later.
  - 5. In the ESLint config, add `no-restricted-globals` / `no-restricted-properties` for `window.confirm`, `window.alert`, `window.prompt`, `confirm`, `alert` and `prompt`, with a message pointing to `confirm()`/`toast()`. Export the rule set so apps/web can extend it.
  - 6. All text arrives as term keys or props. Add tests and axe checks for each export.
- **acceptance**:
  - A detail page built from RecordDetail has an accessible tab list (`role=tablist`), keeps the tab in the URL, and keeps the right rail state per session.
  - `confirm()` resolves true or false and never blocks the main thread. Using `window.confirm` anywhere in apps/web or packages fails lint.
  - Error toasts persist and are announced. Success toasts auto-dismiss and are announced politely.
  - ErrorState shows the correlation id for every failed request that carried one.
- **tests**:
  - **unit**:
    - `await confirm({tone:'danger', ...})` with the user pressing Escape resolves `false`. Clicking Confirm resolves `true`. With `requireText:'L592'`, Confirm is disabled until "L592" is typed.
    - `toast.success('saved')` renders inside `[aria-live=polite]` and is gone after 5s of fake timers. Hovering at 4s and leaving at 8s dismisses it at 13s.
    - Rendering 5 toasts shows 3. `toast.error` is still present after 60s of fake timers.
    - ErrorState with `{status:409, requestId:'req_123'}` shows the 409 term text and "req_123".
    - RecordDetail with `?tab=history` renders the History panel selected (`aria-selected="true"`).
    - Lint on a fixture file containing `if (confirm('x'))` exits 1 with the restricted-globals message.
    - vitest-axe on RecordDetail, the open ConfirmDialog, Toaster with 2 toasts and every state component reports 0 violations.
  - **integration**:
    - apps/web extends the ui ESLint config and `pnpm --filter web lint` runs. Expected: green on main; adding `window.alert('x')` to a page fails.
  - **e2e** (Playwright):
    - On a fixture detail page in apps/web, click a danger action. Expected: the dialog has focus on Cancel; Tab reaches Confirm; Enter confirms; a success toast is announced and disappears within 6s.
    - Force the fixture API to return 500 with `X-Request-Id: req_e2e`. Expected: ErrorState shows "req_e2e", and Retry re-requests and renders the data.
