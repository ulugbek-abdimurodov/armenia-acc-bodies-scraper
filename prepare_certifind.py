#!/usr/bin/env python3
"""Convert armnab_scraper.py output into a CertiFind importer dataset.

Writes bodies.csv, accreditations.csv and scopes.csv to
../../certifind/data/armnab-armenia/ and output/REVIEW.md. Nothing is imported.

NACE_TO_EA, NACE_SPANS, FOOD_CATEGORIES, ENERGY_AREAS, MEDICAL_AREAS and
EXCLUDED_SCHEMES are loaded from ../greece/prepare_certifind.py, not copied.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
AB_CODE = "ARMNAB"
ACCREDITATION_STANDARD = "ISO/IEC 17021-1"
EA_SEPARATOR = ";"
ALL_CODES = "ALL"
TABLE_NAMES = ("NACE_TO_EA", "NACE_SPANS", "FOOD_CATEGORIES", "ENERGY_AREAS",
               "MEDICAL_AREAS", "EXCLUDED_SCHEMES")

STATUS_MAP = {"Գործող": "active", "Կասեցված": "suspended", "Դադարեցված": "withdrawn"}
SCOPE_BLOCK = "Հավատարմագրման ոլորտը"
EXTENSION_BLOCK = "Ոլորտի ընդլայնում"
REDUCTION_BLOCK = "Ոլորտի կրճատում"
CHANGES_LABEL = "Փոփոխությունները"

# Certifiable schemes this register uses. Anything else is logged, never written.
STANDARDS = {"9001": "ISO 9001", "14001": "ISO 14001", "22000": "ISO 22000",
             "27001": "ISO/IEC 27001", "45001": "ISO 45001", "18001": "OHSAS 18001",
             "50001": "ISO 50001", "22301": "ISO 22301", "28000": "ISO 28000",
             "13485": "ISO 13485", "7101": "ISO 7101", "20000": "ISO/IEC 20000-1", "20121": "ISO 20121",
             "21001": "ISO 21001", "30301": "ISO 30301", "30401": "ISO 30401", "37001": "ISO 37001",
             "37101": "ISO 37101", "37301": "ISO 37301", "41001": "ISO 41001", "55001": "ISO 55001",
             "56001": "ISO 56001"}
FSSC = "FSSC 22000"
FOOD_STANDARDS = {"ISO 22000", FSSC}
HEADING_KEYWORDS = [
    ("FSSC", FSSC), ("Որակի", "ISO 9001"), ("Շրջակա միջավայրի", "ISO 14001"),
    ("Էկոլոգիական", "ISO 14001"), ("Սննդամթերքի անվտանգության", "ISO 22000"),
    ("Տեղեկատվական անվտանգության", "ISO/IEC 27001"), ("Էներգետիկայի", "ISO 50001"),
    ("Բիզնեսի շարունակականության", "ISO 22301"), ("Մատակարարման շղթայի", "ISO 28000"),
    ("Բժշկական սարքեր", "ISO 13485"), ("առողջության և աշխատանքի", "ISO 45001"),
    ("Աշխատանքի անվտանգության", "ISO 45001"),
]
# Letter in legacy certificate numbers such as 003/E-004.
CERT_LETTERS = {"Q": ["ISO 9001"], "E": ["ISO 14001"], "F": ["ISO 22000", FSSC],
                "L": ["ISO/IEC 27001"], "H": ["OHSAS 18001"]}

EA_ORDER = [str(n) for n in range(1, 17)] + ["17", "17.1", "17.2"]
EA_ORDER += [str(n) for n in range(18, 29)] + ["29", "29/1", "29/2", "30", "31", "31/1", "31/2",
                                                "32", "32/1", "32/2", "33", "34", "34/1", "34/2",
                                                "35", "36", "37", "38", "38/1", "38/2", "38/3", "39"]
ALL_SECTIONS = set("ABCDEFGHIJKLMNOPQRSTU")
SECTION_DIVISIONS = {"A": (1, 3), "B": (5, 9), "C": (10, 33), "D": (35, 35), "E": (36, 39),
                     "F": (41, 43), "G": (45, 47), "H": (49, 53), "I": (55, 56), "J": (58, 63),
                     "K": (64, 66), "L": (68, 68), "M": (69, 75), "N": (77, 82), "O": (84, 84),
                     "P": (85, 85), "Q": (86, 88), "R": (90, 93), "S": (94, 96), "T": (97, 98),
                     "U": (99, 99)}

# Older records number the NACE sections by name, with no letter or EA code.
SECTION_NAMES = [("գյուղատնտեսություն", "A"), ("հանքագործական", "B"), ("մշակող արդյունաբերություն", "C"),
                 ("էլեկտրականության", "D"), ("ջրամատակարարում", "E"), ("շինարարություն", "F"),
                 ("մեծածախ", "G"), ("փոխադրումներ", "H"), ("կացության", "I"), ("տեղեկատվություն", "J"),
                 ("ֆինանսական", "K"), ("անշարժ գույք", "L"), ("մասնագիտական", "M"), ("վարչարարական", "N"),
                 ("պետական կառավարում", "O"), ("կրթություն", "P"), ("առողջապահություն", "Q"),
                 ("մշակույթ", "R"), ("սպասարկման այլ", "S"), ("տնային տնտեսությունների", "T"),
                 ("օտարերկրյա", "U")]
NUMBERED_ROW = re.compile(r"^\d+[.․]?\s+(.+)$")

SKIP_LINE = re.compile(r"^(որպես|Որպես|լրացուցիչ|Ծանոթություն|\(?հավատարմագրման վկայագրի|Հ/հ|ոլորտը դասակարգչի|"
                       r"Օբյեկտի անվանումը|Կատեգորիաների նկարագրությունը|IAF/EA|-+$)")
HEADING_RE = re.compile(r"կառավա\w*\s+համակարգ|Բժշկական սարքեր\.")
REDUCTION_RE = re.compile(r"կրճատվել է.*?՝\s*(.+)$")
LINE_CERT_RE = re.compile(r"\d{3}/[A-Z]-\d{3}")
TRAILING_STANDARD = re.compile(r"\s+Հ?\s?ՍՏ\s.*$|\s+(?:ԳՕՍՏ|ГОСТ)\s.*$")
EA_ROW = re.compile(r"\S\s+(\d{1,2}(?:[./]\d{1,2})?)\.?\s*(?:Բաժին\s*)?"
                    r"(?:[A-U](?:\s*,\s*[A-U])*)?\s*(?:\d{2}\.\d{1,2}(?:\.\d+)?)?\s*$")
SECTION_ROW = re.compile(r"(?:\s-+\s*|\s|,\s*)(?:Բաժին\s*)?([A-U])\s*(\d{2}\.\d+)?\s*$")
FOOD_WITH_SECTION = re.compile(r"\s([A-M])\s+Բաժին\s*[A-U](?:\s*,\s*[A-U])*\s*$")
ONLY_SECTION = re.compile(r"Բաժին\s*[A-U]\s*$")
FOOD_ROW = re.compile(r"\s([A-M])(?:\s+[A-U]|\s*-+)?\s*$")
ENERGY_ROW = re.compile(r"\s([A-H])\s*$")
MEDICAL_ROW = re.compile(r"Աղյուսակ\s*Ա?\.?\s*1\.(\d)")


def to_latin(text: str) -> str:
    text = text.replace("․", ".")
    for armenian, latin in (("ԻՍՕ", "ISO"), ("ԻՍO", "ISO"), ("ԻԷԿ", "IEC"), ("ՕՀՍԱՍ", "OHSAS"),
                            ("ԳՕՍՏ", "GOST"), ("ГОСТ", "GOST"), ("ИСО", "ISO"), ("ՀՍՏ", "AST"), ("ՏՍ", "TS")):
        text = text.replace(armenian, latin)
    return text


def standard_numbers(text: str) -> list[str]:
    return re.findall(r"(?:ISO(?:/IEC)?(?:/TS)?|OHSAS)\s*(\d{4,5})", to_latin(text))


def resolve_heading(line: str) -> tuple[str | None, list[str]]:
    """Return (standard, other standards named on the same line)."""
    if "FSSC" in line:
        return FSSC, []
    numbers = standard_numbers(line)
    for position, number in enumerate(numbers):
        if number in STANDARDS:
            others = numbers[:position] + numbers[position + 1:]
            return STANDARDS[number], [n for n in others if not n.startswith(("170", "2200"))]
    for keyword, standard in HEADING_KEYWORDS:
        if keyword in line:
            return standard, []
    return None, numbers


def expand_reduction(text: str) -> tuple[set[str], list[str]]:
    """Parse "6, 8-ից մինչև 11, 15-17.2, 29/1-30" into codes, plus tokens it can't read."""
    codes: set[str] = set()
    unread: list[str] = []
    text = re.sub(r"\s*-?ից\s+մինչև\s+", "-", text.rstrip(" ։."))
    for token in re.split(r"\s*,\s*", text):
        token = token.strip()
        match = re.fullmatch(r"([\d./]+)\s*-\s*([\d./]+)", token)
        if match and match[1] in EA_ORDER and match[2] in EA_ORDER:
            start, end = EA_ORDER.index(match[1]), EA_ORDER.index(match[2])
            selected = EA_ORDER[start:end + 1]
            codes.update(selected)
            # A range ending on a parent code covers its sub-codes.
            codes.update(code for code in EA_ORDER if re.split(r"[./]", code)[0] == match[2])
        elif token in EA_ORDER:
            codes.add(token)
            codes.update(code for code in EA_ORDER if re.split(r"[./]", code)[0] == token)
        elif token:
            unread.append(token)
    return codes, unread


def new_scheme(standard: str) -> dict:
    return {"standard": standard, "codes": [], "sections": [], "nace": [], "food": [], "energy": [],
            "medical": [], "certs": [], "removed": set(), "extras": [], "reduction_notes": 0, "wrapped_lines": 0}


def parse_scope(lines: list[str], review_lines: list[str] | None = None) -> dict[str, dict]:
    """Split register text into schemes and their sector rows. Unread lines are collected."""
    schemes: dict[str, dict] = {}
    current: dict | None = None
    unparsed = review_lines if review_lines is not None else []
    index = 0
    pending: list[str] = []  # lines with no code yet; a coded next line means they were wrapped

    def flush_pending() -> None:
        unparsed.extend(pending)
        pending.clear()

    def start(standard: str) -> dict:
        return schemes.setdefault(standard, new_scheme(standard))

    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue

        certs = LINE_CERT_RE.findall(line)
        if certs and current is not None and "գրանցահամար" in line:
            current["certs"].extend(certs)
            continue

        reduction = REDUCTION_RE.search(line)
        if "կրճատվել է" in line and "՝" in line:
            while "։" not in line and index < len(lines) and index < 400:
                line += " " + lines[index].strip()
                index += 1
            reduction = REDUCTION_RE.search(line)
            if reduction and current is not None:
                removed, unread = expand_reduction(reduction[1])
                current["removed"] |= removed
                current["reduction_notes"] += 1
                unparsed.extend(f"reduction token not read: {token}" for token in unread)
            else:
                unparsed.append(line)
            continue
        if line.startswith("Համաձայն") or "ընդլայնվել է" in line or SKIP_LINE.match(line):
            continue

        latin = to_latin(line)
        if HEADING_RE.search(line) and not EA_ROW.search(TRAILING_STANDARD.sub("", line)):
            flush_pending()
            standard, others = resolve_heading(line)
            if standard is None:
                # Some headings only name the scheme; its standard is on the next line.
                following = standard_numbers(lines[index]) if index < len(lines) else []
                if not (following and following[0] in STANDARDS):
                    unparsed.append(f"scheme not recognised: {line}")
                current = None
                continue
            current = start(standard)
            current["certs"].extend(LINE_CERT_RE.findall(line))
            current["extras"].extend(others)
            continue

        row = TRAILING_STANDARD.sub("", line)
        bare = standard_numbers(row)  # a standard after the code is a table column, not a heading
        is_bare_standard = bool(bare) and not EA_ROW.search(row)
        if is_bare_standard or re.search(r"HACCP|CAC/", latin):
            number = next(iter(bare), "")
            known = STANDARDS.get(number)
            if known and (current is None or (current["standard"] != known and has_rows(current))):
                current = start(known)
            elif current is not None and (not known or current["standard"] != known):
                current["extras"].append(line)
            elif current is None:
                unparsed.append(f"standard outside any scheme: {line}")
            continue

        if current is None:
            unparsed.append(f"row outside any scheme: {line}")
            continue
        if read_row(current, row):
            current["wrapped_lines"] += len(pending)
            pending.clear()
        else:
            pending.append(f"{current['standard']}: {line}")
    flush_pending()
    return schemes


def has_rows(scheme: dict) -> bool:
    return any(scheme[key] for key in ("codes", "sections", "nace", "food", "energy", "medical"))


def read_row(scheme: dict, row: str) -> bool:
    standard = scheme["standard"]
    if standard in FOOD_STANDARDS:
        match = FOOD_WITH_SECTION.search(row)
        if not match and not ONLY_SECTION.search(row):
            match = FOOD_ROW.search(row)
        if match:
            scheme["food"].append(match[1])
            return True
        return False
    if standard == "ISO 50001":
        if (match := ENERGY_ROW.search(row)) is None:
            return False
        letter = match[1]
        # The site lists A/B (industrial split) and then the A-H technical areas.
        if scheme["energy"] and letter <= scheme["energy"][-1]:
            scheme["energy"].clear()
        scheme["energy"].append(letter)
        return True
    if standard == "ISO 13485":
        if (match := MEDICAL_ROW.search(row)) is None:
            return False
        scheme["medical"].append(f"A.1.{match[1]}")
        return True
    match = EA_ROW.search(row)
    if match and match[1] in EA_ORDER:
        scheme["codes"].append(match[1])
        return True
    match = SECTION_ROW.search(row)
    if match:
        scheme["nace"].append(match[2]) if match[2] else scheme["sections"].append(match[1])
        return True
    match = NUMBERED_ROW.match(row)
    if match:
        text = match[1].lower()
        for name, letter in SECTION_NAMES:
            if text.startswith(name):
                scheme["sections"].append(letter)
                return True
    return False


def clean_phone(raw: str, address: str, review: "Review", where: str) -> str:
    if not raw:
        return ""
    parts = [part for part in re.split(r"[,;/]", raw) if part.strip()]
    if len(parts) > 1:
        review.add("Cleaned values", f"{where}: phone `{raw}` has several numbers, kept the first")
    digits = re.sub(r"\D", "", parts[0])
    if digits.startswith("374") and len(digits) == 11:
        result = "+" + digits
    elif digits.startswith("0") and len(digits) == 9:
        result = "+374" + digits[1:]
    elif len(digits) == 8:
        result = "+374" + digits
    elif len(digits) == 6 and "Երևան" in address:
        result = "+37410" + digits
        review.add("Fallbacks", f"{where}: phone `{raw}` has no area code; added Yerevan 10 from the address")
    else:
        review.add("Fallbacks", f"{where}: phone `{raw}` could not be converted; left blank")
        return ""
    if result != raw:
        review.add("Cleaned values", f"{where}: phone `{raw}` -> `{result}`")
    return result


def short_name(title: str, review: "Review", where: str) -> str:
    match = re.match(r"^(«[^»]+»(?:\s+[^\s-]+)*?\s*(?:ՍՊԸ|ՓԲԸ))", title)
    if match:
        name = re.sub(r"\s+", " ", match[1])
        if name != title:
            review.add("Cleaned values", f"{where}: name `{title}` -> `{name}`")
        return name
    review.add("Fallbacks", f"{where}: no legal form found, kept the full title `{title}`")
    return title


def country_of(address: str) -> str:
    regions = ("Երևան", "ՀՀ", "Կոտայք", "Արարատ", "Արմավիր", "Արագածոտն", "Գեղարքունիք",
               "Լոռի", "Շիրակ", "Սյունիք", "Տավուշ", "Վայոց Ձոր")
    return "Armenia" if any(region in address for region in regions) else ""


def load_tables(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Greece converter not found at {path}. Pass --greece.")
    spec = importlib.util.spec_from_file_location("greece_prepare_certifind", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [name for name in TABLE_NAMES if not hasattr(module, name)]
    if missing:
        raise SystemExit(f"{path} does not define: {', '.join(missing)}")
    return {name: getattr(module, name) for name in TABLE_NAMES}


def as_codes(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def expand_ea_spec(spec: str) -> list[str]:
    """Turn an EA spec like "18;20-22" into ["18", "20", "21", "22"]."""
    codes: list[str] = []
    for part in str(spec).split(";"):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = (int(x) for x in part.split("-", 1))
            codes.extend(str(n) for n in range(low, high + 1))
        else:
            codes.append(str(int(part)))
    return codes


class Mapper:
    """Looks codes up in the Greek tables. Each failed lookup goes to REVIEW.md."""

    def __init__(self, tables: dict):
        self.tables = tables

    def nace(self, code: str) -> list[str]:
        table = self.tables["NACE_TO_EA"]
        parts = code.split(".")
        candidates = [code, f"{parts[0]}.{parts[1][:1]}" if len(parts) > 1 else code, parts[0],
                      parts[0].lstrip("0")]
        for candidate in candidates:
            if candidate in table:
                return as_codes(table[candidate])
        # NACE_SPANS maps a NACE code that covers several EA sectors to an EA spec
        # string such as "18;20-22" (EA 18, 20, 21, 22).
        spans = self.tables["NACE_SPANS"]
        for candidate in candidates:
            if candidate in spans:
                return expand_ea_spec(spans[candidate])
        return []

    def section(self, letter: str) -> list[str]:
        low, high = SECTION_DIVISIONS[letter]
        found: list[str] = []
        for division in range(low, high + 1):
            for code in self.nace(f"{division:02d}"):
                if code not in found:
                    found.append(code)
        return found

    def category(self, table_name: str, key: str) -> str | None:
        table = self.tables[table_name]
        if isinstance(table, dict):
            value = table.get(key)
            return None if value is None else key
        return key if key in table else None


class Review:
    def __init__(self):
        self.sections: dict[str, list[str]] = defaultdict(list)

    def add(self, section: str, message: str) -> None:
        if message not in self.sections[section]:
            self.sections[section].append(message)

    def write(self, path: Path, summary: list[str]) -> None:
        order = ["Decisions to confirm", "Mappings", "Exclusions", "Fallbacks", "Cleaned values",
                 "Unread scope lines", "Additional documents named in scopes", "Missing annexes"]
        lines = ["# ARMNAB dataset review", "", *summary, ""]
        for section in order:
            items = self.sections.get(section, [])
            lines += [f"## {section} ({len(items)})", ""]
            lines += [f"- {item}" for item in items] or ["- none"]
            lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")


def block_lines(record: dict, title: str, label: str | None = None) -> list[str]:
    lines: list[str] = []
    for block in record["blocks"]:
        if block["title"] != title:
            continue
        for entry in block["entries"]:
            if label is None or entry["label"] == label:
                lines.extend(entry["lines"])
    return lines


def record_schemes(record: dict, review: Review, where: str) -> dict[str, dict]:
    unread: list[str] = []
    main = parse_scope(block_lines(record, SCOPE_BLOCK), unread)
    extension = parse_scope(block_lines(record, EXTENSION_BLOCK), unread)
    for standard, scheme in extension.items():
        target = main.setdefault(standard, new_scheme(standard))
        for key in ("codes", "sections", "nace", "food", "energy", "medical", "certs", "extras"):
            target[key].extend(scheme[key])
        target["removed"] |= scheme["removed"]
        review.add("Mappings", f"{where}: merged extension block rows into {standard}")
    reductions = parse_scope(block_lines(record, REDUCTION_BLOCK, CHANGES_LABEL), [])
    for standard, scheme in reductions.items():
        if standard in main:
            main[standard]["removed"] |= set(scheme["codes"])
    for line in unread:
        review.add("Unread scope lines", f"{where}: {line}")
    return main


def scheme_codes(record_id: str, scheme: dict, mapper: Mapper, review: Review) -> tuple[list[str], str]:
    where = f"{record_id} {scheme['standard']}"
    standard = scheme["standard"]
    if scheme["wrapped_lines"]:
        review.add("Cleaned values", f"{where}: {scheme['wrapped_lines']} wrapped line(s) joined to the coded row after them")
    for extra in scheme["extras"]:
        review.add("Additional documents named in scopes", f"{where}: `{extra}` not written as a scope")
    note = ""
    if standard in FOOD_STANDARDS:
        keys, table = scheme["food"], "FOOD_CATEGORIES"
    elif standard == "ISO 50001":
        keys, table = scheme["energy"], "ENERGY_AREAS"
    elif standard == "ISO 13485":
        keys, table = scheme["medical"], "MEDICAL_AREAS"
    else:
        keys, table = None, None
    if table:
        codes = []
        for key in dict.fromkeys(keys):
            mapped = mapper.category(table, key)
            if mapped is None:
                review.add("Fallbacks", f"{where}: `{key}` is not in {table}; left out")
            else:
                codes.append(mapped)
                review.add("Mappings", f"{where}: `{key}` via {table}")
        if keys and scheme["reduction_notes"]:
            review.add("Fallbacks", f"{where}: reduction note on a category scheme was not applied")
    else:
        codes = list(dict.fromkeys(scheme["codes"]))
        sections = set(scheme["sections"])
        if sections >= ALL_SECTIONS - {"U"} or sections >= ALL_SECTIONS - {"T", "U"}:
            if scheme["removed"]:
                review.add("Fallbacks", f"{where}: every NACE section listed but codes were removed; "
                                        "ALL not used, mapped section by section")
            else:
                review.add("Mappings", f"{where}: all NACE sections listed -> {ALL_CODES}")
                return [ALL_CODES], "All NACE sections listed"
        for letter in sorted(sections):
            mapped = mapper.section(letter)
            if not mapped:
                review.add("Fallbacks", f"{where}: NACE section {letter} has no EA mapping; left out")
            review.add("Mappings", f"{where}: section {letter} -> {', '.join(mapped) or 'nothing'}")
            codes.extend(code for code in mapped if code not in codes)
        for nace in dict.fromkeys(scheme["nace"]):
            mapped = mapper.nace(nace)
            if not mapped:
                review.add("Fallbacks", f"{where}: NACE {nace} has no EA mapping; left out")
            review.add("Mappings", f"{where}: NACE {nace} -> {', '.join(mapped) or 'nothing'}")
            codes.extend(code for code in mapped if code not in codes)
        removed = [code for code in codes if code in scheme["removed"]]
        if removed:
            codes = [code for code in codes if code not in scheme["removed"]]
            note = "Reduced scope applied"
            review.add("Mappings", f"{where}: removed by reduction: {', '.join(removed)}")
    if not has_rows(scheme):
        review.add("Fallbacks", f"{where}: scheme listed with no sector rows -> {ALL_CODES}")
        return [ALL_CODES], "No sector list on the register"
    return codes, note


def assign_certificates(record: dict, schemes: dict[str, dict], review: Review) -> dict[str, list[str]]:
    """Return certificate number -> standards."""
    numbers = record["certificate_numbers"]
    where = record["detail_id"]
    result: dict[str, list[str]] = {number: [] for number in numbers}
    if len(numbers) == 1:
        result[numbers[0]] = list(schemes)
        return result
    for standard, scheme in schemes.items():
        named = [cert for cert in scheme["certs"] if cert in result]
        if named:
            result[named[0]].append(standard)
            continue
        by_letter = [number for number in numbers
                     if standard in CERT_LETTERS.get(number.split("/")[1][0], [])]
        if by_letter:
            result[by_letter[0]].append(standard)
            review.add("Fallbacks", f"{where}: {standard} assigned to {by_letter[0]} from its letter")
        else:
            review.add("Fallbacks", f"{where}: {standard} matches no certificate number; left out")
    for number in numbers:
        if not result[number]:
            standards = [standard for standard in CERT_LETTERS.get(number.split("/")[1][0], [])
                         if standard not in schemes][:1]
            if standards:
                schemes[standards[0]] = new_scheme(standards[0])
                result[number] = standards
                review.add("Fallbacks", f"{where}: {number} has no scope section; "
                                        f"{standards[0]} inferred from its letter")
            else:
                review.add("Fallbacks", f"{where}: {number} has unknown letter and no scope section")
    return result


def is_excluded(standard: str, excluded) -> bool:
    return any(str(item).lower() in standard.lower() for item in excluded)


def convert(data: dict, tables: dict, verified_at: str, active_only: bool = False):
    review = Review()
    mapper = Mapper(tables)
    bodies, accreditations, scopes = [], [], []
    records = sorted(data["records"], key=lambda record: record["start_date"], reverse=True)
    body_names: dict[str, str] = {}
    written_bodies: dict[str, dict] = {}
    standards_used: dict[str, int] = defaultdict(int)

    for record in records:
        where = record["detail_id"]
        status = STATUS_MAP.get(record["status"])
        if status is None:
            review.add("Fallbacks", f"{where}: unknown status `{record['status']}`; record skipped")
            continue
        if active_only and status != "active":
            review.add("Exclusions", f"{where}: {status} record left out by --active-only")
            continue
        key = re.search(r"«([^»]+)»", record["name"])
        key = (key[1] if key else record["name"]).upper()
        name = body_names.setdefault(key, short_name(record["name"], review, where))
        if status == "active" and record["end_date"] and record["end_date"] < verified_at:
            review.add("Decisions to confirm", f"{where}: marked active but ended {record['end_date']}")

        schemes = record_schemes(record, review, where)
        for number, standards in assign_certificates(record, schemes, review).items():
            accreditations.append({
                "ab_code": AB_CODE, "certificate_number": number, "body_name": name,
                "accreditation_standard": ACCREDITATION_STANDARD, "status": status,
                "issue_date": record["start_date"], "expiry_date": record["end_date"],
                "proof_url": record["source_url"]})
            for standard in standards:
                if is_excluded(standard, tables["EXCLUDED_SCHEMES"]):
                    review.add("Exclusions", f"{where}: {standard} is in EXCLUDED_SCHEMES")
                    continue
                codes, note = scheme_codes(where, schemes[standard], mapper, review)
                if not codes:
                    review.add("Fallbacks", f"{where}: {standard} ended with no codes; row left out")
                    continue
                standards_used[standard] += 1
                scopes.append({"certificate_number": number, "certification_standard": standard,
                               "ea_codes": EA_SEPARATOR.join(codes), "status": status,
                               "scope_note": note})
        if key not in written_bodies:
            address = record["legal_address"] or record["activity_address"]
            country = country_of(address)
            if not country:
                review.add("Fallbacks", f"{where}: country not recognised in `{address}`; left blank")
            review.add("Fallbacks", f"{name}: the register has no website field; left blank")
            review.add("Mappings", f"{name}: registration_no is the newest ARMNAB number "
                                   f"{record['certificate_numbers'][:1]}")
            written_bodies[key] = {
                "name": name, "country": country,
                "registration_no": next(iter(record["certificate_numbers"]), ""),
                "phone": clean_phone(record["phone"], address, review, where),
                "email": record["email"], "website": "", "address": address,
                "source_url": record["source_url"], "verified_at": verified_at}
        if not record["documents"]:
            review.add("Missing annexes", f"{where}: no annex or certificate file; scope read from the page")

    with_accreditation = {row["body_name"] for row in accreditations}
    for body in written_bodies.values():
        if body["name"] in with_accreditation:
            bodies.append(body)
        else:
            review.add("Exclusions", f"{body['name']}: no accreditation left, body not written")
    review.add("Decisions to confirm", f"accreditation_standard is {ACCREDITATION_STANDARD} on every "
               "row; records before 2015 may have been granted under ISO/IEC 17021:2011")
    return bodies, accreditations, scopes, review, dict(standards_used)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=HERE / "output")
    parser.add_argument("--dataset", type=Path, default=HERE / "../../certifind/data/armnab-armenia")
    parser.add_argument("--greece", type=Path, default=HERE / "../greece/prepare_certifind.py")
    parser.add_argument("--active-only", action="store_true", help="leave out terminated records")
    args = parser.parse_args()

    data = json.loads((args.input / "bodies.json").read_text(encoding="utf-8"))
    report_path = args.input / "run_report.json"
    verified_at = date.today().isoformat()
    if report_path.exists():
        verified_at = json.loads(report_path.read_text(encoding="utf-8"))["finished_at"][:10]

    bodies, accreditations, scopes, review, used = convert(
        data, load_tables(args.greece), verified_at, args.active_only)
    write_csv(args.dataset / "bodies.csv", ["name", "country", "registration_no", "phone", "email",
                                            "website", "address", "source_url", "verified_at"], bodies)
    write_csv(args.dataset / "accreditations.csv",
              ["ab_code", "certificate_number", "body_name", "accreditation_standard", "status",
               "issue_date", "expiry_date", "proof_url"], accreditations)
    write_csv(args.dataset / "scopes.csv", ["certificate_number", "certification_standard", "ea_codes",
                                            "status", "scope_note"], scopes)
    summary = [f"- Bodies: {len(bodies)}", f"- Accreditations: {len(accreditations)}",
               f"- Scope rows: {len(scopes)}",
               "- Standards used: " + ", ".join(f"{k} ({v})" for k, v in sorted(used.items()))]
    review.write(args.input / "REVIEW.md", summary)
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
