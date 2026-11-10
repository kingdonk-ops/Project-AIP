/**
 * In-memory renderer adapters for previews (FORMS-03 fixture, FORMS-11 designer preview): picking a
 * photo or signature returns a synthetic file id, and asset and user references search a small fixed
 * list. Nothing is uploaded and no request is made. The names are sample data, not product labels.
 */
import type { MediaAdapter, ReferenceAdapter, RendererAdapters } from "@aip/form-renderer";

// Synthetic ids (valid UUIDs, so the evaluator accepts the stored answers).
const ASSETS = [
  { id: "00000000-0000-4000-8000-00000000a001", label: "PV-101 Pressure vessel" },
  { id: "00000000-0000-4000-8000-00000000a002", label: "TK-201 Storage tank" },
];
const USERS = [
  { id: "00000000-0000-4000-8000-00000000b001", label: "Alice Inspector" },
  { id: "00000000-0000-4000-8000-00000000b002", label: "Bob Painter" },
];

// A grey square, so photo thumbnails render without any network request.
const THUMBNAIL =
  "data:image/svg+xml;utf8," +
  encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#a3a3a3"/></svg>');

export function previewAdapters(): RendererAdapters {
  let counter = 0;
  const media: MediaAdapter = {
    async pick(_fieldKey, kind) {
      counter += 1;
      const suffix = String(counter).padStart(12, "0");
      return {
        fileId: `00000000-0000-4000-8000-${suffix}`,
        name: kind === "photo" ? `photo-${counter}.jpg` : `signature-${counter}.png`,
      };
    },
    thumbnailUrl: () => THUMBNAIL,
  };
  const references: ReferenceAdapter = {
    async search(kind, query) {
      const q = query.trim().toLowerCase();
      return (kind === "asset" ? ASSETS : USERS).filter((item) => item.label.toLowerCase().includes(q));
    },
    async label(kind, id) {
      return (kind === "asset" ? ASSETS : USERS).find((item) => item.id === id)?.label ?? null;
    },
  };
  return { media, references };
}
