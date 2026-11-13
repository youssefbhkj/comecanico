"""Knowledge base: load and validate fault sheets, exact DTC lookup, catalog, keyword search.

Validate all sheets from the command line:  python -m mecapilot.knowledge [sheets_dir]
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from mecapilot.models import FaultSheet, make_citation

STOPWORDS = {
    "le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "et", "ou", "a", "au", "aux",
    "en", "dans", "sur", "pour", "par", "avec", "sans", "est", "sont", "ce", "cette", "ces",
    "qui", "que", "qu", "ne", "pas", "plus", "se", "sa", "son", "ses", "il", "elle", "on",
}


class SheetLoadError(Exception):
    """A fault sheet is invalid; nothing is loaded."""


class UnknownSheetError(KeyError):
    """No sheet with this id."""


class Passage(BaseModel):
    id: str                    # citation id, e.g. "SYN-001#causes"
    sheet: str
    section: str
    score: int                 # number of distinct query terms found
    matched_terms: list[str]
    text: str
    safety_critical: bool
    validated: bool


def tokenize(text: str) -> list[str]:
    """Lowercase, strip accents, split into words, drop French stopwords."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9]+", ascii_text) if t not in STOPWORDS]


def covers(sheet: FaultSheet, codes: list[str]) -> bool:
    """True if the sheet explicitly lists at least one of the codes (exact match only)."""
    return bool(set(sheet.codes) & set(codes))


class KnowledgeBase:
    def __init__(self, sheets: list[FaultSheet]):
        self._sheets: dict[str, FaultSheet] = {}
        for sheet in sheets:
            if sheet.id in self._sheets:
                raise SheetLoadError(f"duplicate sheet id {sheet.id!r}")
            self._sheets[sheet.id] = sheet
        self._by_code: dict[str, list[str]] = {}
        for sheet in self._sheets.values():
            for code in sheet.codes:
                self._by_code.setdefault(code, []).append(sheet.id)

    @classmethod
    def load(cls, sheets_dir: str | Path) -> KnowledgeBase:
        sheets = []
        for path in sorted(Path(sheets_dir).glob("*.yaml")):
            try:
                with open(path, encoding="utf-8") as f:
                    sheets.append(FaultSheet.model_validate(yaml.safe_load(f)))
            except (yaml.YAMLError, ValidationError) as exc:
                raise SheetLoadError(f"{path.name}: {exc}") from exc
        return cls(sheets)

    def __len__(self) -> int:
        return len(self._sheets)

    def lookup(self, code: str) -> list[str]:
        """Sheets that explicitly list this code. Never uses code similarity."""
        return list(self._by_code.get(code, []))

    def get(self, sheet_id: str) -> FaultSheet:
        try:
            return self._sheets[sheet_id]
        except KeyError:
            raise UnknownSheetError(sheet_id) from None

    def list_sheets(self) -> list[dict]:
        """Catalog without section text (cheap for the LLM context)."""
        return [
            {"id": s.id, "title": s.title, "codes": s.codes, "safety_critical": s.safety_critical,
             "synthetic": s.synthetic, "validated": s.validated_by is not None, "sections": list(s.sections)}
            for s in self._sheets.values()
        ]

    def search(self, query: str, codes: list[str] | None = None,
               sheet_ids: list[str] | None = None, limit: int = 5) -> list[Passage]:
        """Keyword search over sections. Score = distinct query terms present (title and codes count)."""
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms:
            return []
        candidates = [
            s for s in self._sheets.values()
            if (codes is None or covers(s, codes)) and (sheet_ids is None or s.id in sheet_ids)
        ]
        results = []
        for sheet in candidates:
            sheet_tokens = set(tokenize(sheet.title)) | set(tokenize(" ".join(sheet.codes)))
            for order, (section, text) in enumerate(sheet.sections.items()):
                tokens = sheet_tokens | set(tokenize(text)) | set(tokenize(section))
                matched = [t for t in terms if t in tokens]
                if matched:
                    results.append((order, Passage(
                        id=make_citation(sheet.id, section), sheet=sheet.id, section=section,
                        score=len(matched), matched_terms=matched, text=text,
                        safety_critical=sheet.safety_critical, validated=sheet.validated_by is not None,
                    )))
        results.sort(key=lambda r: (-r[1].score, r[1].sheet, r[0]))
        return [p for _, p in results[:limit]]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    sheets_dir = args[0] if args else "data/sheets"
    try:
        kb = KnowledgeBase.load(sheets_dir)
    except SheetLoadError as exc:
        print(f"INVALID: {exc}")
        return 1
    print(f"OK: {len(kb)} sheet(s) valid in {sheets_dir}")
    for entry in kb.list_sheets():
        flags = [f for f, on in (("synthetic", entry["synthetic"]), ("SAFETY", entry["safety_critical"]),
                                 ("NOT VALIDATED", not entry["validated"])) if on]
        print(f"  {entry['id']}  {', '.join(entry['codes'])}  [{', '.join(flags)}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
