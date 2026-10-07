#!/usr/bin/env python3
"""Check CycloneDX SBOMs against the licence policy (STACK-04, ADR 0009, ADR 0011). Stdlib only.

Usage: python3 tools/ci/check_licences.py [--policy PATH] [--today YYYY-MM-DD] SBOM [SBOM ...]

Every component's licences are classified as allow, review or deny:
- a licence id is matched against the policy's `deny`, `review` and `allow` lists (SPDX ids,
  case-insensitive, shell globs); anything unmatched, and a component with no licence, is denied;
- an SPDX expression passes an `OR` if any branch passes and an `AND` only if every branch does;
  `WITH <exception>` is judged by the licence it modifies;
- several licence entries on one component must all pass (conservative AND);
- `review` licences (LGPL) pass only in SBOMs whose file name matches `review_allowed_sboms`
  (the sandbox images);
- OS packages and binaries in container image SBOMs (`system_packages.sboms`) use the narrower
  `system_packages` rule; in other SBOMs they get the full policy;
- `system_packages.deny_names` (Ghostscript, MuPDF, ...) is denied everywhere;
- `first_party` components (our own packages) are skipped.

A denied component passes only with an unexpired exception; one expiring within 30 days passes with
a `::warning`. For each violation it prints `component@version licence sbom`, a
`security.sbom.policy_violation` JSON line and a GitHub `::error` annotation, then exits 1.
Exit 0 means every component passed; exit 2 means bad arguments, policy or SBOM.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Verdict = Literal["allow", "review", "deny"]
Policy = dict[str, Any]

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config" / "licence-policy.json"
WARN_DAYS = 30
RANK: dict[Verdict, int] = {"allow": 0, "review": 1, "deny": 2}
EXCEPTION_FIELDS = ("component", "licence", "reason", "approver", "expires")
LIST_FIELDS = ("allow", "review", "review_allowed_sboms", "deny", "first_party")
SKIPPED_TYPES = {"file", "operating-system"}
LANGUAGE_TYPES = {"library", "framework"}
TOKEN = re.compile(r"\(|\)|[^\s()]+")


class PolicyError(ValueError):
    """The policy file is malformed."""


class SbomError(ValueError):
    """An SBOM file cannot be read."""


@dataclass
class Violation:
    component: str
    licence: str
    sbom: str
    note: str


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list[Violation])
    warnings: list[str] = field(default_factory=list[str])


# --- policy -------------------------------------------------------------------------------------


def load_policy(path: Path) -> Policy:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyError(f"{path}: top level must be an object")
    policy: Policy = dict(raw)  # pyright: ignore[reportUnknownArgumentType]
    for key in LIST_FIELDS:
        value = policy.setdefault(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):  # pyright: ignore[reportUnknownVariableType]
            raise PolicyError(f"{path}: `{key}` must be a list of strings")
    if not isinstance(policy.setdefault("aliases", {}), dict):
        raise PolicyError(f"{path}: `aliases` must be an object")
    system = policy.setdefault("system_packages", {})
    if not isinstance(system, dict):
        raise PolicyError(f"{path}: `system_packages` must be an object")
    system.setdefault("sboms", ["image-*.cdx.json"])
    for key in ("sboms", "purl_types", "deny", "deny_names"):
        if not isinstance(system.setdefault(key, []), list):
            raise PolicyError(f"{path}: `system_packages.{key}` must be a list")
    exceptions = policy.setdefault("exceptions", [])
    if not isinstance(exceptions, list):
        raise PolicyError(f"{path}: `exceptions` must be a list")
    for index, exc in enumerate(exceptions):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        if not isinstance(exc, dict):
            raise PolicyError(f"{path}: exceptions[{index}] must be an object")
        missing = [k for k in EXCEPTION_FIELDS if not isinstance(exc.get(k), str) or not exc.get(k)]  # pyright: ignore[reportUnknownMemberType]
        if missing:
            raise PolicyError(f"{path}: exceptions[{index}] is missing {', '.join(missing)}")
        try:
            dt.date.fromisoformat(str(exc["expires"]))  # pyright: ignore[reportUnknownArgumentType]
        except ValueError as err:
            raise PolicyError(
                f"{path}: exceptions[{index}].expires must be YYYY-MM-DD, got {exc['expires']!r}"
            ) from err
    return policy


def _matches(value: str, patterns: list[str]) -> bool:
    folded = value.casefold()
    return any(fnmatch.fnmatchcase(folded, p.casefold()) for p in patterns)


def _resolve_alias(text: str, policy: Policy) -> str:
    aliases: dict[str, str] = policy["aliases"]
    stripped = text.strip()
    for key, value in aliases.items():
        if key.casefold() == stripped.casefold():
            return value
    return stripped


# --- classification -----------------------------------------------------------------------------


def _classify_id(licence: str, policy: Policy) -> Verdict:
    licence = _resolve_alias(licence, policy).removesuffix("+")
    if _matches(licence, policy["deny"]):
        return "deny"
    if _matches(licence, policy["review"]):
        return "review"
    if _matches(licence, policy["allow"]):
        return "allow"
    return "deny"  # unknown


def _classify_system_id(licence: str, policy: Policy) -> Verdict:
    licence = _resolve_alias(licence, policy).removesuffix("+")
    return "deny" if _matches(licence, policy["system_packages"]["deny"]) else "allow"


class _Parser:
    """Recursive-descent SPDX expression parser: OR binds loosest, then AND, then WITH."""

    def __init__(self, tokens: list[str], judge: Any) -> None:
        self.tokens = tokens
        self.pos = 0
        self.judge = judge

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise ValueError("unexpected end of expression")
        self.pos += 1
        return token

    def parse(self) -> Verdict:
        verdict = self.or_expr()
        if self.peek() is not None:
            raise ValueError(f"unexpected token {self.peek()!r}")
        return verdict

    def or_expr(self) -> Verdict:
        verdict = self.and_expr()
        while (self.peek() or "").upper() == "OR":
            self.take()
            other = self.and_expr()
            verdict = min(verdict, other, key=RANK.__getitem__)
        return verdict

    def and_expr(self) -> Verdict:
        verdict = self.term()
        while (self.peek() or "").upper() == "AND":
            self.take()
            other = self.term()
            verdict = max(verdict, other, key=RANK.__getitem__)
        return verdict

    def term(self) -> Verdict:
        token = self.take()
        if token == "(":
            verdict = self.or_expr()
            if self.take() != ")":
                raise ValueError("missing )")
            return verdict
        if token == ")" or token.upper() in {"AND", "OR", "WITH"}:
            raise ValueError(f"unexpected token {token!r}")
        if (self.peek() or "").upper() == "WITH":
            self.take()
            self.take()  # the exception id; judged by the licence it modifies
        return self.judge(token)


def _evaluate(text: str, policy: Policy, system: bool) -> Verdict:
    judge = _classify_system_id if system else _classify_id
    resolved = _resolve_alias(text, policy)
    if not resolved:
        return "allow" if system else "deny"
    if system and any(_matches(t, policy["system_packages"]["deny"]) for t in (text, resolved)):
        # Loose patterns (*AGPL*, *Affero*, ...) catch non-SPDX and malformed spellings, and
        # an OR branch cannot rescue an AGPL/SSPL system package.
        return "deny"
    try:
        return _Parser(TOKEN.findall(resolved), lambda lic: judge(lic, policy)).parse()  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    except ValueError:
        return judge(resolved, policy)  # not an expression: judge the whole text as one name


def classify(expression: str, policy: Policy) -> Verdict:
    """Classify one SPDX id, expression or alias name under the full policy."""
    return _evaluate(expression, policy, system=False)


def _licence_terms(entry: dict[str, Any], policy: Policy) -> list[str]:
    terms: list[str] = []
    for item in entry.get("licenses") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("expression")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        lic = item.get("license")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if not text and isinstance(lic, dict):
            text = lic.get("id") or lic.get("name")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(text, str) and text.strip():
            term = _resolve_alias(text, policy)
            if term not in terms:
                terms.append(term)
    return terms


def component_licence(entry: dict[str, Any], policy: Policy) -> str:
    """The component's licences as one display string (entries joined with AND)."""
    terms = _licence_terms(entry, policy)
    if len(terms) == 1:
        return terms[0]
    return " AND ".join(f"({t})" if " OR " in t.upper() else t for t in terms)


def classify_component(entry: dict[str, Any], policy: Policy, system: bool = False) -> Verdict:
    terms = _licence_terms(entry, policy)
    if not terms:
        return "allow" if system else "deny"
    verdicts: list[Verdict] = [_evaluate(t, policy, system) for t in terms]
    return max(verdicts, key=RANK.__getitem__)


# --- SBOM walking -------------------------------------------------------------------------------


def _display_name(entry: dict[str, Any]) -> str:
    name = str(entry.get("name", "?"))
    group = entry.get("group")
    return f"{group}/{name}" if group else name


def _purl_type(entry: dict[str, Any]) -> str | None:
    purl = entry.get("purl")
    if not isinstance(purl, str) or not purl.startswith("pkg:"):
        return None
    return purl[4:].split("/", 1)[0].casefold()


def _walk(components: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(components, list):
        return found
    for entry in components:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(entry, dict):
            found.append(entry)  # pyright: ignore[reportUnknownArgumentType]
            found.extend(_walk(entry.get("components")))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return found


def _exception_for(name: str, version: str, licence: str, policy: Policy) -> dict[str, str] | None:
    candidates = {name.casefold(), f"{name}@{version}".casefold()}
    for exc in policy["exceptions"]:
        if (
            exc["component"].casefold() in candidates
            and exc["licence"].casefold() == licence.casefold()
        ):
            return exc
    return None


def _check_component(
    entry: dict[str, Any], sbom_name: str, policy: Policy, today: dt.date, report: Report
) -> None:
    if entry.get("type") in SKIPPED_TYPES:
        return
    name = _display_name(entry)
    if _matches(name, policy["first_party"]):
        return
    version = str(entry.get("version") or "")
    label = f"{name}@{version}" if version else name
    licence = component_licence(entry, policy)
    purl_type = _purl_type(entry)
    # The loose system rule applies only inside container image SBOMs (ADR 0011).
    system = _matches(sbom_name, policy["system_packages"]["sboms"]) and (
        purl_type in policy["system_packages"]["purl_types"]
        or (purl_type is None and entry.get("type") not in LANGUAGE_TYPES)
    )

    if _matches(str(entry.get("name", "")), policy["system_packages"]["deny_names"]):
        note = "denied package (system_packages.deny_names)"
    else:
        verdict = classify_component(entry, policy, system=system)
        if verdict == "allow":
            return
        if verdict == "review":
            if _matches(sbom_name, policy["review_allowed_sboms"]):
                return
            note = "review licence (LGPL) is allowed only in sandbox image SBOMs"
        else:
            note = "unknown or missing licence" if not licence else "denied licence"

    exc = _exception_for(name, version, licence, policy)
    if exc is not None:
        expires = dt.date.fromisoformat(exc["expires"])
        if expires >= today:
            if (expires - today).days <= WARN_DAYS:
                report.warnings.append(
                    f"licence exception for {exc['component']} ({exc['licence']}) expires "
                    f"{exc['expires']}; approver {exc['approver']}; reason: {exc['reason']}"
                )
            return
        note += f" (exception expired {exc['expires']})"
    report.violations.append(Violation(label, licence, sbom_name, note))


def check_documents(
    documents: list[tuple[str, dict[str, Any]]], policy: Policy, today: dt.date
) -> Report:
    """Check parsed SBOMs, each given as (file name, CycloneDX JSON)."""
    report = Report()
    for sbom_path, doc in documents:
        sbom_name = Path(sbom_path).name
        for entry in _walk(doc.get("components")):
            _check_component(entry, sbom_name, policy, today, report)
    return report


def load_sbom(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SbomError(f"{path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("bomFormat") != "CycloneDX":  # pyright: ignore[reportUnknownMemberType]
        raise SbomError(f"{path}: not a CycloneDX JSON document")
    return doc  # pyright: ignore[reportUnknownVariableType]


# --- CLI ----------------------------------------------------------------------------------------


def _annotation(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("sboms", nargs="+", type=Path, metavar="SBOM")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument(
        "--today", type=dt.date.fromisoformat, default=None, help="override today (tests)"
    )
    args = parser.parse_args(argv)
    today: dt.date = args.today or dt.datetime.now(dt.UTC).date()
    try:
        policy = load_policy(args.policy)
        documents = [(str(p), load_sbom(p)) for p in args.sboms]
    except (PolicyError, SbomError) as exc:
        print(f"check_licences: {exc}", file=sys.stderr)
        return 2

    report = check_documents(documents, policy, today)
    for warning in report.warnings:
        print(f"::warning title=Licence exception expiring::{_annotation(warning)}")
    for v in report.violations:
        print(f"{v.component} {v.licence or '(none)'} {v.sbom}")
        event = {
            "event": "security.sbom.policy_violation",
            "component": v.component,
            "licence": v.licence,
            "sbom": v.sbom,
        }
        print(json.dumps(event, sort_keys=False))
        print(
            "::error title=Licence policy violation::"
            + _annotation(f"{v.component} {v.licence or '(none)'} in {v.sbom}: {v.note}")
        )
    return 1 if report.violations else 0


if __name__ == "__main__":
    sys.exit(main())
