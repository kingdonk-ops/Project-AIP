import { Button, Icon } from "@aip/ui";
import { useState } from "react";
import type { MediaAdapter } from "../adapters";
import type { Json } from "../logic/types";
import { GroupFrame, NotAnswered, ReadOnlyFrame, type FieldProps } from "./FieldFrame";

function fileIdOf(item: Json | undefined): string | null {
  if (item && typeof item === "object" && !Array.isArray(item) && typeof item["fileId"] === "string") return item["fileId"];
  return null;
}

function photoIds(value: Json | undefined): string[] {
  return Array.isArray(value) ? value.map(fileIdOf).filter((id): id is string => id !== null) : [];
}

/** File names the picker returned this session (answers store only `{fileId}`). */
function useNames(): [Record<string, string>, (fileId: string, name: string) => void] {
  const [names, setNames] = useState<Record<string, string>>({});
  return [names, (fileId, name) => setNames((prev) => ({ ...prev, [fileId]: name }))];
}

function Thumbnail({ media, fileId, alt }: { media: MediaAdapter | undefined; fileId: string; alt: string }) {
  const url = media?.thumbnailUrl(fileId) ?? null;
  return url ? <img className="aip-form-renderer__thumb" src={url} alt={alt} /> : <span>{alt}</span>;
}

function AdapterMissing({ t, frame }: Pick<FieldProps, "t" | "frame">) {
  return (
    <ReadOnlyFrame frame={frame}>
      <span className="aip-form-renderer__empty">{t("forms.renderer.adapter_missing")}</span>
    </ReadOnlyFrame>
  );
}

/**
 * `photo` → an "Add photo" button calling `media.pick(fieldKey, "photo")`, then a list of thumbnails
 * (alt = file name) with a remove button each. The value is `[{fileId}, ...]`.
 */
export function PhotoField({ field, value, onChange, t, adapters, readOnly, frame }: FieldProps) {
  const [names, remember] = useNames();
  const media = adapters.media;
  const ids = photoIds(value);
  const altFor = (fileId: string) => names[fileId] ?? frame.label;

  if (readOnly) {
    return (
      <ReadOnlyFrame frame={frame}>
        {ids.length ? (
          <ul className="aip-form-renderer__thumbs">
            {ids.map((fileId) => (
              <li key={fileId}>
                <Thumbnail media={media} fileId={fileId} alt={altFor(fileId)} />
              </li>
            ))}
          </ul>
        ) : (
          <NotAnswered t={t} />
        )}
      </ReadOnlyFrame>
    );
  }
  if (!media) return <AdapterMissing t={t} frame={frame} />;

  const add = async () => {
    const picked = await media.pick(field.key, "photo");
    if (!picked) return;
    remember(picked.fileId, picked.name);
    onChange([...ids.map((fileId) => ({ fileId })), { fileId: picked.fileId }]);
  };
  const remove = (fileId: string) => {
    const rest = ids.filter((id) => id !== fileId).map((id) => ({ fileId: id }));
    onChange(rest.length ? rest : undefined);
  };

  return (
    <GroupFrame frame={frame}>
      {ids.length ? (
        <ul className="aip-form-renderer__thumbs">
          {ids.map((fileId) => (
            <li key={fileId} className="aip-form-renderer__thumb-item">
              <Thumbnail media={media} fileId={fileId} alt={altFor(fileId)} />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={t("forms.renderer.remove_photo", { name: altFor(fileId) })}
                onClick={() => remove(fileId)}
              >
                <Icon name="close" />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <Button type="button" variant="secondary" onClick={() => void add()}>
        {t("forms.renderer.add_photo")}
      </Button>
    </GroupFrame>
  );
}

/**
 * `signature` → a "Sign" button calling `media.pick(fieldKey, "signature")`, then the signed file's
 * name and a "Clear" button. The value is `{fileId}`.
 */
export function SignatureField({ field, value, onChange, t, adapters, readOnly, frame }: FieldProps) {
  const [names, remember] = useNames();
  const media = adapters.media;
  const fileId = fileIdOf(value);
  const name = fileId ? (names[fileId] ?? frame.label) : null;

  if (readOnly) {
    return (
      <ReadOnlyFrame frame={frame}>
        {fileId && name ? <Thumbnail media={media} fileId={fileId} alt={name} /> : <NotAnswered t={t} />}
      </ReadOnlyFrame>
    );
  }
  if (!media) return <AdapterMissing t={t} frame={frame} />;

  const sign = async () => {
    const picked = await media.pick(field.key, "signature");
    if (!picked) return;
    remember(picked.fileId, picked.name);
    onChange({ fileId: picked.fileId });
  };

  return (
    <GroupFrame frame={frame}>
      {fileId && name ? (
        <div className="aip-form-renderer__signed">
          <span>{name}</span>
          <Button type="button" variant="secondary" onClick={() => onChange(undefined)}>
            {t("forms.renderer.clear_signature")}
          </Button>
        </div>
      ) : (
        <Button type="button" variant="secondary" onClick={() => void sign()}>
          {t("forms.renderer.sign")}
        </Button>
      )}
    </GroupFrame>
  );
}
