import csv
import json

import armnab_scraper as scraper
import prepare_certifind as prepare
from tests.conftest import FIXTURES


def record(name):
    html = (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
    return scraper.parse_detail(html, name, f"https://armnab.am/management-systems/{name}")


def dataset(tables, *names, **kwargs):
    return prepare.convert({"records": [record(name) for name in names]}, tables, "2026-11-03", **kwargs)


def scope(scopes, certificate, standard):
    return next(row for row in scopes if row["certificate_number"] == certificate
                and row["certification_standard"] == standard)


def test_reduction_ranges():
    codes, unread = prepare.expand_reduction("6, 8-ից մինչև 11, 15-17.2, 29/1-30, 34։")
    assert {"6", "8", "9", "10", "11", "15", "16", "17", "17.1", "17.2", "29/1", "29/2", "30", "34", "34/1", "34/2"} <= codes
    assert "7" not in codes and "29" not in codes and unread == []


def test_reduction_range_ending_on_parent_covers_sub_codes():
    codes, _ = prepare.expand_reduction("36-38")
    assert {"36", "37", "38", "38/1", "38/2", "38/3"} <= codes


def test_inline_reduction_removes_listed_codes(tables):
    _, _, scopes, _, _ = dataset(tables, "MS00000016")
    codes = scope(scopes, "006/M-012", "ISO 9001")["ea_codes"].split(";")
    assert "14" not in codes and "17" not in codes
    assert "1" in codes


def test_reduction_block_removes_codes_too(tables):
    _, _, scopes, review, _ = dataset(tables, "MS00000016")
    codes = scope(scopes, "006/M-012", "ISO 9001")["ea_codes"].split(";")
    assert "18" not in codes
    assert "34/2" in codes


def test_per_scheme_reductions_stay_separate(tables):
    _, _, scopes, _, _ = dataset(tables, "MS00000012")
    assert scope(scopes, "002/M-008", "ISO 9001")["ea_codes"] == "1;2;7"
    assert scope(scopes, "002/M-008", "ISO/IEC 27001")["ea_codes"] == "13;33"


def test_extension_block_adds_food_scheme(tables):
    _, _, scopes, _, _ = dataset(tables, "MS00000012")
    assert scope(scopes, "002/M-008", "ISO 22000")["ea_codes"] == "A;C"


def test_food_row_reads_category_not_section(tables):
    _, _, scopes, _, _ = dataset(tables, "MS00000003")
    assert scope(scopes, "003/F-004", "ISO 22000")["ea_codes"] == "E;H;K"


def test_certificate_named_in_scope_heading(tables):
    _, accreditations, scopes, _, _ = dataset(tables, "MS00000003")
    assert len(accreditations) == 5
    assert scope(scopes, "003/Q-004", "ISO 9001")["ea_codes"].startswith("1;3;35")
    assert scope(scopes, "002/H-002", "OHSAS 18001")["certificate_number"] == "002/H-002"


def test_certificate_without_scope_gets_all_and_is_logged(tables):
    _, _, scopes, review, _ = dataset(tables, "MS00000003")
    assert scope(scopes, "003/E-004", "ISO 14001")["ea_codes"] == "ALL"
    assert any("inferred from its letter" in item for item in review.sections["Fallbacks"])


def test_nace_sections_are_mapped_with_tables(tables):
    _, _, scopes, _, _ = dataset(tables, "MS00000003")
    assert scope(scopes, "002/H-002", "OHSAS 18001")["ea_codes"] == "1;28;37"


def test_energy_keeps_technical_areas_only(tables):
    _, _, scopes, _, _ = dataset(tables, "MS00000016")
    assert scope(scopes, "006/M-012", "ISO 50001")["ea_codes"] == "A;E"


def test_medical_areas(tables):
    _, _, scopes, _, _ = dataset(tables, "MS00000016")
    assert scope(scopes, "006/M-012", "ISO 13485")["ea_codes"] == "A.1.1;A.1.3"


def test_additional_documents_are_logged_not_written(tables):
    _, _, scopes, review, _ = dataset(tables, "MS00000016")
    assert not any("31000" in row["certification_standard"] for row in scopes)
    assert any("31000" in item for item in review.sections["Additional documents named in scopes"])


def test_excluded_scheme(tables):
    custom = {**tables, "EXCLUDED_SCHEMES": ["OHSAS"]}
    _, _, scopes, review, _ = dataset(custom, "MS00000003")
    assert not any(row["certification_standard"] == "OHSAS 18001" for row in scopes)
    assert any("OHSAS 18001" in item for item in review.sections["Exclusions"])


def test_active_only_drops_body_without_accreditation(tables):
    bodies, accreditations, _, review, _ = dataset(tables, "MS00000003", "MS00000016", active_only=True)
    assert [body["name"] for body in bodies] == ["«ՆԱՐԵԿ» ԳԻՏԱՀԵՏԱԶՈՏԱԿԱՆ ՓԲԸ"]
    assert {row["certificate_number"] for row in accreditations} == {"006/M-012"}


def test_body_fields_and_phone_format(tables):
    bodies, accreditations, _, review, _ = dataset(tables, "MS00000001", "MS00000016")
    narek = next(body for body in bodies if "ՆԱՐԵԿ" in body["name"])
    assert narek["phone"] == "+37491005757"
    assert narek["country"] == "Armenia"
    assert narek["registration_no"] == "006/M-012"
    institute = next(body for body in bodies if "ԻՆՍՏԻՏՈՒՏ" in body["name"])
    assert institute["phone"] == "+37410287020"
    assert any("Yerevan 10" in item for item in review.sections["Fallbacks"])
    assert accreditations[0]["ab_code"] == "ARMNAB"
    assert accreditations[0]["proof_url"].startswith("https://armnab.am/management-systems/")


def test_numbered_section_names_without_letters():
    schemes = prepare.parse_scope(["1. Որակի կառավարման համակարգ", "1. Գյուղատնտեսություն, անտառային տնտեսություն և ձկնորսություն", "3. Մշակող արդյունաբերություն"])
    assert schemes["ISO 9001"]["sections"] == ["A", "C"]


def test_scheme_named_on_next_line_has_no_sector_list():
    unread = []
    schemes = prepare.parse_scope(["16 Հակակոռուպցիոն կառավարման համակարգեր", "Խարդախության հսկողության կառավարման համակարգեր - -",
                                   "ԻՍՕ 37001:2025", "ԻՍՕ 37003:2025", "15 Սոցիալական կառավարման համակարգեր - -",
                                   "ԻՍՕ 26000, FSSC 24000, SA8000 SOCIAL ACCOUNTABILITY"], unread)
    assert list(schemes) == ["ISO 37001"]
    assert schemes["ISO 37001"]["extras"] == ["ԻՍՕ 37003:2025"]
    assert any("26000" in line for line in unread) and any("Սոցիալական" in line for line in unread)


def test_unread_lines_reach_review(tables):
    unread = []
    prepare.parse_scope(["1 Որակի կառավարման համակարգ՝ ՀՍՏ ԻՍՕ 9001", "Այլ կատեգորիաներ"], unread)
    assert unread == ["ISO 9001: Այլ կատեգորիաներ"]


def test_wrapped_line_is_joined_not_unread():
    unread = []
    schemes = prepare.parse_scope(["1 Որակի կառավարման համակարգ՝ ՀՍՏ ԻՍՕ 9001", "Ճարտարագիտական ծառայություններ (ճարտարապետություն- և", "ճարտարագիտական գրասենյակներ) 34/2 Բաժին M"], unread)
    assert unread == [] and schemes["ISO 9001"]["codes"] == ["34/2"]


def test_end_to_end_writes_dataset_and_review(site, tmp_path, tables, monkeypatch):
    base, _ = site
    output = tmp_path / "output"
    monkeypatch.setattr("sys.argv", ["x", "--output", str(output), "--base-url", base, "--delay", "0"])
    scraper.main()
    monkeypatch.setattr(prepare, "load_tables", lambda path: tables)
    dataset_dir = tmp_path / "data"
    monkeypatch.setattr("sys.argv", ["x", "--input", str(output), "--dataset", str(dataset_dir)])
    assert prepare.main() == 0
    with (dataset_dir / "scopes.csv").open(encoding="utf-8") as handle:
        assert csv.DictReader(handle).fieldnames == ["certificate_number", "certification_standard", "ea_codes", "status", "scope_note"]
    with (dataset_dir / "bodies.csv").open(encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 4
    review = (output / "REVIEW.md").read_text(encoding="utf-8")
    assert "## Missing annexes (4)" in review and "## Mappings" in review


def test_load_tables_reports_missing_names(tmp_path):
    fake = tmp_path / "prepare_certifind.py"
    fake.write_text("NACE_TO_EA = {}\n", encoding="utf-8")
    try:
        prepare.load_tables(fake)
    except SystemExit as exc:
        assert "NACE_SPANS" in str(exc)
    else:
        raise AssertionError("expected SystemExit")
