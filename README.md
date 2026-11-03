# ARMNAB scraper

Scrapes ARMNAB's register of accredited management-system certification bodies
(https://armnab.am/management-systems) and converts it into a CertiFind dataset.

Put this folder at `CertiFind/database/armenia`, next to `greece`.

## Setup and run

```
pip install -r requirements.txt
python armnab_scraper.py --download-docs
python prepare_certifind.py
python -m pytest
```

Nothing is imported into the database.

## armnab_scraper.py

Writes `output/bodies.csv`, `output/accreditations.csv`, `output/bodies.json` and `output/run_report.json`.

- The list page only serves its first 15 rows without a SignalR connection, so the scraper walks detail IDs from `MS00000001` and checks the total against the list page.
- Unknown IDs return HTTP 200 with "Չի գտնվել", which is treated as not found.
- Waits 0.3 s between requests, retries twice, and lists failures in `run_report.json`.
- `--download-docs` saves each detail page to `output/scope_documents/`, plus any linked PDF, Word or Excel file. Files already there are skipped. In November 2026 the site linked no certificate or annex files.

## prepare_certifind.py

Writes `bodies.csv`, `accreditations.csv` and `scopes.csv` to `../../certifind/data/armnab-armenia/`, and `output/REVIEW.md`.

Options: `--input`, `--dataset`, `--greece`, `--active-only`.

The mapping tables are loaded from `../greece/prepare_certifind.py`, so that file must define `NACE_TO_EA`, `NACE_SPANS`, `FOOD_CATEGORIES`, `ENERGY_AREAS`, `MEDICAL_AREAS` and `EXCLUDED_SCHEMES`.

### Scope rules

- Scopes come from the page text: the scope block, plus the extension block.
- Codes named in a reduction note or the reduction block are removed, per scheme.
- Food, energy and medical schemes use their category tables. Other schemes use listed EA codes, or NACE sections mapped through the Greek tables.
- A scheme with no sector rows gets `ALL`, as does one listing every NACE section with no reduction.
- Other standards named in a scope (ISO 31000, HACCP, and so on) are listed in `REVIEW.md`, not written.
- Terminated records are kept with status `withdrawn`. Use `--active-only` to leave them out.
- Lines the parser can't read go to `REVIEW.md`.

## Tests

`tests/` runs against a local mock site. `tests/build_fixtures.py` regenerates the fixtures, which use markup and text copied from armnab.am with long scope lists shortened.
