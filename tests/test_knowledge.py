import pytest
import yaml

from mecapilot.knowledge import KnowledgeBase, SheetLoadError, UnknownSheetError, covers, main, tokenize

SHEETS_DIR = "data/sheets"


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(SHEETS_DIR)


def write_sheet(path, **overrides):
    sheet = {
        "id": "SYN-T", "synthetic": True, "title": "t", "codes": ["P0001"], "safety_critical": False,
        "source": "Synthetic test data", "causes": {"C1": "Synthetic cause"},
        "tests": {}, "sections": {"causes": "texte fictif"},
    }
    sheet.update(overrides)
    path.write_text(yaml.safe_dump(sheet, allow_unicode=True), encoding="utf-8")


def test_demo_sheets_load_and_are_synthetic(kb):
    assert len(kb) == 3
    assert all(entry["synthetic"] for entry in kb.list_sheets())


def test_empty_directory_is_valid(tmp_path):
    kb = KnowledgeBase.load(tmp_path)
    assert len(kb) == 0
    assert kb.lookup("P0171") == []
    assert kb.search("alpha") == []


def test_invalid_sheet_blocks_loading(tmp_path):
    write_sheet(tmp_path / "a.yaml")
    write_sheet(tmp_path / "b.yaml", id="SYN-U", codes=["P171"])
    with pytest.raises(SheetLoadError, match="b.yaml"):
        KnowledgeBase.load(tmp_path)


def test_duplicate_id_rejected(tmp_path):
    write_sheet(tmp_path / "a.yaml")
    write_sheet(tmp_path / "b.yaml")
    with pytest.raises(SheetLoadError, match="duplicate"):
        KnowledgeBase.load(tmp_path)


def test_lookup_is_exact(kb):
    assert kb.lookup("P0171") == ["SYN-001"]
    assert kb.lookup("P0172") == []          # similar code never matches
    assert kb.lookup("P9999") == []


def test_covers(kb):
    sheet = kb.get("SYN-001")
    assert covers(sheet, ["P0171", "P2A00"])
    assert not covers(sheet, ["P0172"])


def test_tokenize_ignores_case_accents_and_stopwords():
    assert tokenize("Le Symptôme BÊTA de l'outil") == ["symptome", "beta", "outil"]


def test_search_finds_right_sheet_regardless_of_accents(kb):
    results = kb.search("symptome fictif beta")
    assert results[0].id == "SYN-001#symptoms"
    assert results[0].matched_terms == ["symptome", "fictif", "beta"]
    assert kb.search("EPSILON")[0].sheet == "SYN-003"


def test_search_ranks_by_distinct_terms(kb):
    results = kb.search("delta epsilon")
    assert results[0].id == "SYN-003#symptoms" and results[0].score == 2


def test_search_respects_filters(kb):
    assert {p.sheet for p in kb.search("fictif", codes=["P2A00"])} == {"SYN-003"}
    assert {p.sheet for p in kb.search("fictif", sheet_ids=["SYN-002"])} == {"SYN-002"}
    assert kb.search("fictif", codes=["P0172"]) == []


def test_search_without_common_term_is_empty(kb):
    assert kb.search("zzz inexistant") == []
    assert kb.search("le de et") == []


def test_search_flags_safety_and_validation(kb):
    passage = kb.search("gamma")[0]
    assert passage.sheet == "SYN-002" and passage.safety_critical and not passage.validated


def test_search_limit(kb):
    assert len(kb.search("fictif", limit=2)) == 2


def test_catalog_has_no_section_text(kb):
    entry = next(e for e in kb.list_sheets() if e["id"] == "SYN-001")
    assert entry["sections"] == ["symptoms", "causes", "tests"]
    assert "alpha" not in str(entry)


def test_get_unknown_sheet(kb):
    with pytest.raises(UnknownSheetError):
        kb.get("SYN-999")


def test_validation_command(tmp_path, capsys):
    assert main([SHEETS_DIR]) == 0
    assert "OK: 3 sheet(s)" in capsys.readouterr().out
    write_sheet(tmp_path / "bad.yaml", causes={})
    assert main([str(tmp_path)]) == 1
    assert "INVALID" in capsys.readouterr().out
