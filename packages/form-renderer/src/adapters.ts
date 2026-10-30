// The only way out of @aip/form-renderer (FORMS-03). The package has no network code: the host
// (INSPECTIONS-04, the FORMS-04 preview, the dev fixture) passes these adapters, which call the
// uploads pipeline and the asset/user lookups. A missing adapter renders the field read-only with
// `forms.renderer.adapter_missing`, never a crash.

/** A file the host's picker produced (photo upload or signature capture). */
export interface PickedFile {
  fileId: string;
  name: string;
}

export type MediaKind = "photo" | "signature";

export interface MediaAdapter {
  /** Opens the host's picker; resolves `null` when the user cancels. */
  pick(fieldKey: string, kind: MediaKind): Promise<PickedFile | null>;
  /** A displayable thumbnail URL for a stored file, or `null` when there is none. */
  thumbnailUrl(fileId: string): string | null;
}

export type ReferenceKind = "asset" | "user";

export interface ReferenceItem {
  id: string;
  label: string;
}

export interface ReferenceAdapter {
  search(kind: ReferenceKind, query: string): Promise<ReferenceItem[]>;
  label(kind: ReferenceKind, id: string): Promise<string | null>;
}

export interface RendererAdapters {
  media?: MediaAdapter;
  references?: ReferenceAdapter;
}
