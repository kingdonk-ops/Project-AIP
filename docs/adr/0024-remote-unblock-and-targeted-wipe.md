# ADR 0024: Remote un-block and targeted wipe of one inspection on a field device

- **Status:** accepted (owner specification, 2026-10-10); points 1 to 7 adjust that specification and need the owner's confirmation
- **Date:** 2026-10-10
- **Affects:** offline module (after R1), access (ACCESS-01), identity (device revoke), audit; builds on ADR 0010, 0020, 0021

## Context

An inspection checked out to a tablet can get stuck: a sync deadlock, a corrupted photo, a broken schema migration or a
double check-out. The owner specified a way for an authorised admin to break the lock on the server and delete just that
inspection's local copy, without a factory reset and without touching other inspections. The idea is sound. Reviewing the
specification against earlier decisions found places where it could destroy evidence or be misused.

## Decision

1. **Permission** `inspections.checkout.unblock` (named per ADR 0020). Default holders: the tenant admin and QA/QC manager
   roles, tenant-wide or per project; a project owner can be granted it for their project through a project override,
   never beyond what they hold themselves. Platform operators do not hold it, except inside a customer-approved support
   grant (ADR 0017). The specification listed Super Admin as a default holder.
2. **The lock is released by check-out token, not by a queue entry.** Each check-out carries a token with an epoch. An
   un-block raises the epoch, clears the assigned device and returns the inspection to ready for inspection (or its last
   confirmed revision). Any upload with an older token is refused with 410 `INSPECTION_UNBLOCKED_BY_ADMIN` for good, even
   after the purge command has expired or been delivered, so a late tablet cannot bring a stale copy back.
3. **Refused uploads are quarantined, not dropped.** The rejected payload is stored encrypted, never applied to the
   records, and readable by QA managers and auditors. It is kept 90 days, or for the sign-off retention period (ADR 0021)
   if it contains any signed record or hold-point or witness-point release. The specification discarded it.
4. **Signed work needs a second person.** If the inspection holds provisional sign-offs or hold-point and witness-point
   releases (ADR 0010), the un-block needs a second approver who also holds the permission; the person unblocking cannot
   approve a wipe of their own records. The inspector, the QA manager and any client reviewer of a witness point are
   notified, and the affected hold points are marked voided with re-inspection required, because work may have proceeded
   under a release that is now gone.
5. **Device side.** Only the target inspection's rows and cached media are deleted; other inspections, drawings, the
   session and credentials stay. Before deleting, the app writes an encrypted recovery snapshot under the user's unlock,
   kept 30 days and exportable only by an authorised admin with the tablet in hand. The device acknowledges success or failure.
6. **Delivery.** The primary channel is the pre-sync check: before the server accepts any upload from a device, it returns
   that device's pending commands. A push message may wake the app but carries no inspection content. The specification's
   native pieces (Firebase push, Android file paths, SQLite and Expo file calls) belong to a native app; this is a web app
   (ADR 0004), so the app deletes from browser storage (IndexedDB, Cache Storage, origin storage).
7. **A lost or broken tablet needs more than an un-block.** Un-blocking frees one inspection but leaves the rest of the
   tablet's data readable. The form offers "revoke device" (ADR 0010 adjustment 2: sessions revoked, cache wiped on next
   contact) when the reason is device lost or broken.
8. **Records.** Table `device_remote_command` (tenant table template, FORCE RLS; the specification's table had no tenant
   protection) with a foreign key to the device register, statuses pending, delivered, acknowledged, failed and expired.
   Every un-block writes an immutable audit entry: time, admin, approver, device, inspection, reason code, the number of
   discarded revisions and the hash of the quarantined payload.
9. **Reason required:** sync deadlock, corrupted media, device lost or broken, reassignment, with optional notes. The
   confirmation shows the device and when it last reported ("not reported for 18 hours").

## Consequences

Backlog for the offline module (after R1, ADR 0007): the check-out token and epoch, the command list on the pre-sync
check, the quarantine store, the client purge and recovery snapshot, the admin page, and the device revoke action. ACCESS-01
adds the permission to the catalogue when the offline module declares it.
