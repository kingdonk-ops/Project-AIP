/** Shared FORMS-04 test data: two revisions of a coating ITR and API response builders. */
import type { RevisionOut, RevisionSummary, TemplateDetail, TemplateListItem } from "@aip/api-client";

export const V1 = {
  schemaVersion: 1,
  sections: [
    {
      key: "prep",
      label: "Preparation",
      fields: [
        { key: "surface_prepared", type: "boolean", label: "Surface prepared" },
        { key: "dft_avg", type: "measurement", label: "Average DFT", unit: "mm" },
      ],
    },
    { key: "final", label: "Final", fields: [{ key: "remarks", type: "text", label: "Remarks" }] },
  ],
};

export const V2 = {
  schemaVersion: 1,
  sections: [
    {
      key: "prep",
      label: "Preparation",
      fields: [
        { key: "dft_avg", type: "measurement", label: "Average DFT", unit: "um", required: true },
        {
          key: "blast_standard",
          type: "dropdown",
          label: "Blast standard",
          options: [{ value: "sa2_5", label: "Sa 2.5" }],
        },
      ],
    },
    {
      key: "final",
      label: "Final",
      fields: [
        { key: "remarks", type: "text", label: "Remarks" },
        { key: "surface_prepared", type: "boolean", label: "Surface prepared" },
      ],
    },
  ],
};

export const TEMPLATE_ID = "00000000-0000-7000-8000-00000000f001";
export const REV1_ID = "00000000-0000-7000-8000-00000000f101";
export const REV2_ID = "00000000-0000-7000-8000-00000000f102";
export const REV3_ID = "00000000-0000-7000-8000-00000000f103";

export function listItem(overrides: Partial<TemplateListItem> & Pick<TemplateListItem, "code">): TemplateListItem {
  return {
    id: crypto.randomUUID(),
    name: `Template ${overrides.code}`,
    kind: "inspection",
    status: "active",
    currentRevisionNo: 1,
    updatedAt: "2026-10-30T01:00:00Z",
    ...overrides,
  };
}

export function summary(revisionNo: number, status: RevisionSummary["status"], id: string): RevisionSummary {
  const published = status !== "draft";
  return {
    id,
    revisionNo,
    status,
    schemaHash: published ? "a".repeat(64) : null,
    changeNote: `note ${revisionNo}`,
    publishedAt: published ? "2026-10-29T02:00:00Z" : null,
    createdAt: "2026-10-29T01:00:00Z",
    updatedAt: "2026-10-29T02:00:00Z",
  };
}

export function templateDetail(revisions: RevisionSummary[], overrides: Partial<TemplateDetail> = {}): TemplateDetail {
  const current = revisions.find((r) => r.status === "published");
  return {
    id: TEMPLATE_ID,
    code: "coating-itr",
    name: "Coating ITR",
    kind: "inspection",
    status: current ? "active" : "draft",
    currentRevisionId: current?.id ?? null,
    currentRevisionNo: current?.revisionNo ?? null,
    syncVersion: 4,
    createdAt: "2026-10-29T01:00:00Z",
    updatedAt: "2026-10-29T02:00:00Z",
    revisions,
    ...overrides,
  };
}

export function revision(s: RevisionSummary, schema: Record<string, unknown>): RevisionOut {
  return {
    id: s.id,
    templateId: TEMPLATE_ID,
    revisionNo: s.revisionNo,
    status: s.status,
    schema,
    schemaHash: s.schemaHash,
    evaluatorVersion: s.status === "draft" ? null : "1",
    changeNote: s.changeNote,
    publishedAt: s.publishedAt,
    createdAt: s.createdAt,
    updatedAt: s.updatedAt,
  };
}
