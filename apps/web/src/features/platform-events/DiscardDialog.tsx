/**
 * Discard a dead letter with a reason (ARCH-09 step 3). The reason is required: submit stays
 * disabled until the trimmed text is 1–1000 characters, matching the API's 422 rule (ADR 0030).
 */
import { Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, Label } from "@aip/ui";
import { useEffect, useId, useState } from "react";
import { t } from "../shell/t";

export const MAX_REASON = 1000;

export interface DiscardDialogProps {
  open: boolean;
  eventId: string;
  onOpenChange: (open: boolean) => void;
  /** Called with the trimmed reason. */
  onSubmit: (reason: string) => void;
  busy?: boolean;
}

export function DiscardDialog({ open, eventId, onOpenChange, onSubmit, busy = false }: DiscardDialogProps) {
  const [reason, setReason] = useState("");
  const reasonId = useId();
  const hintId = useId();
  useEffect(() => {
    if (open) setReason("");
  }, [open, eventId]);
  const trimmed = reason.trim();
  const valid = trimmed.length >= 1 && trimmed.length <= MAX_REASON;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t("arch.events.dead_letter.discard_title")}</DialogTitle>
        <DialogDescription>{t("arch.events.dead_letter.discard_body", { id: eventId })}</DialogDescription>
        <form
          className="platform-events__discard"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid && !busy) onSubmit(trimmed);
          }}
        >
          <Label htmlFor={reasonId}>{t("arch.events.dead_letter.discard_reason")}</Label>
          <textarea
            id={reasonId}
            className="platform-events__reason"
            value={reason}
            required
            maxLength={MAX_REASON}
            rows={4}
            aria-describedby={hintId}
            onChange={(event) => setReason(event.target.value)}
          />
          <p id={hintId} className="platform-events__hint">
            {t("arch.events.dead_letter.discard_hint")}
          </p>
          <div className="platform-events__dialog-actions">
            <DialogClose asChild>
              <Button variant="secondary">{t("ui.confirm.cancel")}</Button>
            </DialogClose>
            <Button type="submit" variant="danger" disabled={!valid || busy}>
              {t("arch.events.dead_letter.discard_confirm")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
