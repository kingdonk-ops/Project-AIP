"""Report template packages: load, validate and hash (REPORTS-01).

A package is a definition (``template.json``, the ``report-template.schema.json`` contract), a
Jinja2 body, a stylesheet, sample data and inlined assets. ``load_package`` reads one from a folder
(``config/report-templates/<key>/<variant>/v<version>/``); ``parse_package`` reads the same parts
from an API upload (``{definition, body, css, sampleData, assets: {name: base64}}``). Both run the
same checks, in order, and stop at the first failure with a ``TemplatePackageError(code, path,
detail)``:

1. ``SCHEMA_INVALID``: the definition against the JSON Schema; ``fontLicences`` is required once a
   ``font/woff2`` asset is declared; declared and supplied assets must match; body and stylesheet
   size limits (256 KB and 128 KB);
2. ``ASSET_TOO_LARGE``: an asset over 1 MB, or all assets over 4 MB;
3. ``ASSET_TYPE_MISMATCH``: an asset whose magic bytes do not match its declared type;
4. ``TEMPLATE_SYNTAX``: the body does not parse as Jinja;
5. ``HTML_POLICY``: ``html_policy.check_template`` on the body;
6. ``CSS_POLICY``: ``html_policy.check_css`` on the stylesheet;
7. ``TEMPLATE_SYNTAX``: the body does not compile in the render sandbox (an unknown filter).

``content_sha256`` is the sha256 (hex) of the RFC 8785 canonical JSON of ``{definition, body, css,
sampleData, assets: {name: sha256}}``, so the same package always hashes the same, whichever way
it arrived.

The contract is loaded from a byte-identical copy at ``data/report-template.schema.json`` (the
runtime image ships the package, not ``packages/contracts``); ``tests/test_template_package`` keeps
the two in step. Loading is lazy and cached.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Final

import rfc8785
from jinja2 import TemplateSyntaxError
from jsonschema import Draft202012Validator

from aip.modules.report_engine.html_policy import HtmlViolation, check_css, check_template
from aip.modules.report_engine.render import compile_body

__all__ = [
    "ASSETS_MAX_BYTES",
    "ASSET_MAX_BYTES",
    "BODY_MAX_BYTES",
    "CONTRACT_PATH",
    "CSS_MAX_BYTES",
    "PACKAGE_ERROR_CODES",
    "TemplateAsset",
    "TemplatePackage",
    "TemplatePackageError",
    "content_sha256",
    "load_package",
    "parse_package",
]

CONTRACT_PATH = Path(__file__).resolve().parent / "data" / "report-template.schema.json"

BODY_MAX_BYTES: Final = 256 * 1024
CSS_MAX_BYTES: Final = 128 * 1024
ASSET_MAX_BYTES: Final = 1024 * 1024
ASSETS_MAX_BYTES: Final = 4 * 1024 * 1024

PACKAGE_ERROR_CODES: Final = (
    "SCHEMA_INVALID",
    "ASSET_TOO_LARGE",
    "ASSET_TYPE_MISMATCH",
    "HTML_POLICY",
    "CSS_POLICY",
    "TEMPLATE_SYNTAX",
)

_FILES: Final = ("template.json", "body.html.j2", "style.css", "sample-data.json")


def _is_webp(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


_MAGIC: Final = {
    "image/png": lambda data: data[:4] == b"\x89PNG",
    "image/jpeg": lambda data: data[:3] == b"\xff\xd8\xff",
    "image/webp": _is_webp,
    "font/woff2": lambda data: data[:4] == b"wOF2",
}


class TemplatePackageError(ValueError):
    """A package failed a check: a stable ``code``, the ``path`` it concerns and a ``detail``."""

    def __init__(
        self,
        code: str,
        path: str,
        detail: str,
        violations: list[HtmlViolation] | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        self.violations = violations or []
        super().__init__(f"{code} at {path or '<root>'}: {detail}")

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "path": self.path, "detail": self.detail}
        if self.violations:
            body["violations"] = [v.as_dict() for v in self.violations]
        return body


@dataclass(frozen=True, slots=True)
class TemplateAsset:
    name: str
    content_type: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True, slots=True)
class TemplatePackage:
    """A validated package. ``definition`` is ``template.json`` as parsed."""

    definition: Mapping[str, Any]
    body: str
    css: str
    sample_data: Mapping[str, Any]
    assets: Mapping[str, TemplateAsset]
    content_sha256: str = field(default="")

    @property
    def key(self) -> str:
        return str(self.definition["key"])

    @property
    def variant(self) -> str:
        return str(self.definition["variant"])

    @property
    def version(self) -> int:
        return int(self.definition["version"])

    @property
    def record_type(self) -> str:
        return str(self.definition["recordType"])

    @property
    def term_keys(self) -> frozenset[str]:
        return frozenset(self.definition["termKeys"])

    def asset_files(self) -> dict[str, tuple[str, bytes]]:
        """``{name: (contentType, bytes)}`` for the render contract."""
        return {name: (a.content_type, a.data) for name, a in self.assets.items()}


@cache
def _validator() -> Draft202012Validator:
    schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _schema_error(definition: Any) -> TemplatePackageError | None:
    errors = sorted(_validator().iter_errors(definition), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    error = errors[0]
    path = [str(part) for part in error.absolute_path]
    if error.validator == "additionalProperties" and isinstance(error.instance, dict):
        allowed = set(error.schema.get("properties", {}))  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownArgumentType]
        extra = sorted(str(k) for k in error.instance if k not in allowed)  # pyright: ignore[reportUnknownVariableType]
        if extra:
            path.append(extra[0])
    return TemplatePackageError("SCHEMA_INVALID", ".".join(path), error.message[:200])


def content_sha256(
    definition: Mapping[str, Any],
    body: str,
    css: str,
    sample_data: Mapping[str, Any],
    assets: Mapping[str, TemplateAsset],
) -> str:
    """The package's content hash (RFC 8785 canonical JSON, sha256 hex)."""
    canonical = rfc8785.dumps(
        {
            "definition": dict(definition),
            "body": body,
            "css": css,
            "sampleData": dict(sample_data),
            "assets": {name: asset.sha256 for name, asset in sorted(assets.items())},
        }
    )
    return hashlib.sha256(canonical).hexdigest()


def _check_assets(definition: Mapping[str, Any], supplied: Mapping[str, bytes]) -> None:
    declared = {str(a["name"]): str(a["contentType"]) for a in definition["assets"]}
    if len(declared) != len(definition["assets"]):
        raise TemplatePackageError("SCHEMA_INVALID", "assets", "an asset name is declared twice")
    for name in sorted(declared.keys() - supplied.keys()):
        raise TemplatePackageError("SCHEMA_INVALID", f"assets.{name}", "declared but not supplied")
    for name in sorted(supplied.keys() - declared.keys()):
        raise TemplatePackageError("SCHEMA_INVALID", f"assets.{name}", "supplied but not declared")
    if "font/woff2" in declared.values() and not definition.get("fontLicences"):
        raise TemplatePackageError(
            "SCHEMA_INVALID", "fontLicences", "a font/woff2 asset needs fontLicences (OFL-1.1)"
        )
    total = 0
    for name, data in sorted(supplied.items()):
        total += len(data)
        if len(data) > ASSET_MAX_BYTES:
            raise TemplatePackageError(
                "ASSET_TOO_LARGE", f"assets.{name}", f"{len(data)} bytes; the limit is 1 MB"
            )
    if total > ASSETS_MAX_BYTES:
        raise TemplatePackageError("ASSET_TOO_LARGE", "assets", "all assets exceed 4 MB")
    for name, data in sorted(supplied.items()):
        if not _MAGIC[declared[name]](data):
            raise TemplatePackageError(
                "ASSET_TYPE_MISMATCH", f"assets.{name}", f"the bytes are not {declared[name]}"
            )


def _first(violations: list[HtmlViolation]) -> str:
    first = violations[0]
    where = f" <{first.element}>" if first.element else ""
    attr = f" {first.attribute}" if first.attribute else ""
    return f"{first.rule}{where}{attr} at line {first.line}"


def _build(
    definition: Any,
    body: str,
    css: str,
    sample_data: Any,
    supplied: Mapping[str, bytes],
) -> TemplatePackage:
    error = _schema_error(definition)
    if error is not None:
        raise error
    if not isinstance(sample_data, dict):
        raise TemplatePackageError("SCHEMA_INVALID", "sampleData", "must be a JSON object")
    if len(body.encode("utf-8")) > BODY_MAX_BYTES:
        raise TemplatePackageError("SCHEMA_INVALID", "body", "the body exceeds 256 KB")
    if len(css.encode("utf-8")) > CSS_MAX_BYTES:
        raise TemplatePackageError("SCHEMA_INVALID", "css", "the stylesheet exceeds 128 KB")
    _check_assets(definition, supplied)

    asset_names = frozenset(supplied)
    try:
        violations = check_template(body, asset_names=asset_names)
    except TemplateSyntaxError as exc:
        raise TemplatePackageError(
            "TEMPLATE_SYNTAX", "body", f"line {exc.lineno}: {exc.message}"[:200]
        ) from None
    if violations:
        raise TemplatePackageError("HTML_POLICY", "body", _first(violations), violations)
    css_violations = check_css(css, asset_names=asset_names)
    if css_violations:
        raise TemplatePackageError("CSS_POLICY", "css", _first(css_violations), css_violations)

    try:
        compile_body(body)
    except TemplateSyntaxError as exc:
        raise TemplatePackageError(
            "TEMPLATE_SYNTAX", "body", f"line {exc.lineno}: {exc.message}"[:200]
        ) from None

    content_types = {str(a["name"]): str(a["contentType"]) for a in definition["assets"]}
    assets = {
        name: TemplateAsset(name, content_types[name], data)
        for name, data in sorted(supplied.items())
    }
    return TemplatePackage(
        definition=definition,
        body=body,
        css=css,
        sample_data=sample_data,  # pyright: ignore[reportUnknownArgumentType]
        assets=assets,
        content_sha256=content_sha256(definition, body, css, sample_data, assets),  # pyright: ignore[reportUnknownArgumentType]
    )


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TemplatePackageError(
            "SCHEMA_INVALID", label, f"cannot read {path.name}: {type(exc).__name__}"
        ) from None


def _read_text(path: Path, label: str) -> str:
    """The file's text with CRLF line ends normalised, so a Windows checkout hashes the same."""
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise TemplatePackageError(
            "SCHEMA_INVALID", label, f"cannot read {path.name}: {type(exc).__name__}"
        ) from None


def load_package(path: Path | str) -> TemplatePackage:
    """Read and validate the package folder ``path``."""
    folder = Path(path)
    for name in _FILES:
        if not (folder / name).is_file():
            raise TemplatePackageError("SCHEMA_INVALID", name, f"{name} is missing")
    definition = _read_json(folder / "template.json", "")
    sample_data = _read_json(folder / "sample-data.json", "sampleData")
    body = _read_text(folder / "body.html.j2", "body")
    css = _read_text(folder / "style.css", "css")
    supplied: dict[str, bytes] = {}
    asset_dir = folder / "assets"
    if asset_dir.is_dir():
        for file in sorted(asset_dir.iterdir()):
            if file.is_file():
                supplied[file.name] = file.read_bytes()
    return _build(definition, body, css, sample_data, supplied)


def parse_package(upload: Mapping[str, Any]) -> TemplatePackage:
    """Validate an uploaded package: ``{definition, body, css, sampleData, assets}`` where
    ``assets`` maps each asset name to its base64 bytes."""
    body, css = upload.get("body"), upload.get("css")
    if not isinstance(body, str):
        raise TemplatePackageError("SCHEMA_INVALID", "body", "must be a string")
    if not isinstance(css, str):
        raise TemplatePackageError("SCHEMA_INVALID", "css", "must be a string")
    raw_assets = upload.get("assets") or {}
    if not isinstance(raw_assets, Mapping):
        raise TemplatePackageError("SCHEMA_INVALID", "assets", "must map names to base64 data")
    supplied: dict[str, bytes] = {}
    for name, encoded in raw_assets.items():  # pyright: ignore[reportUnknownVariableType]
        if len(str(encoded)) > ASSETS_MAX_BYTES * 2:  # pyright: ignore[reportUnknownArgumentType]
            raise TemplatePackageError("ASSET_TOO_LARGE", f"assets.{name}", "over 1 MB")
        try:
            supplied[str(name)] = base64.b64decode(str(encoded), validate=True)  # pyright: ignore[reportUnknownArgumentType]
        except (binascii.Error, ValueError):
            raise TemplatePackageError(
                "SCHEMA_INVALID", f"assets.{name}", "is not valid base64"
            ) from None
    return _build(upload.get("definition"), body, css, upload.get("sampleData", {}), supplied)
