"""Check ORCA 6.1.1 basis/ECP tables against PDF layout text and the application.

Run with PYTHONPATH=src, lxml, the root of the manual HTML mirror and the
output of pdftotext -layout on the official PDF. Page numbers are physical.
"""

import argparse
from pathlib import Path
import re

from lxml import html

from orcaview.core._basis_library import FITTING_COVERAGE, ORBITAL_COVERAGE
from orcaview.core.elements import ATOMIC_NUMBERS


def html_tables(web):
    document = html.parse(str(web / "contents/essentialelements/basisset.html"))
    tables = {}
    for caption in document.xpath("//article//caption"):
        number = int(re.search(r"Table 2\.(\d+)", caption.text_content())[1])
        rows = []
        for tr in caption.getparent().xpath("./tbody/tr"):
            cells = [" ".join(td.text_content().split()) for td in tr.xpath("./td")]
            if len(cells) > 1:
                rows.append(cells)
        tables[number] = rows
    return tables


def pdf_basis_rows(pages):
    rows = {}
    for page in pages[78:97]:
        lines = page.splitlines()
        for index, line in enumerate(lines):
            cells = re.split(r"\s{2,}", line.strip())
            if len(cells) < 2:
                continue
            name, first = cells[:2]
            # A continued element cell can end in a comma or a split range.
            if (name.endswith(",") or " " in name or first == "Elements"
                    or not re.fullmatch(r"[A-Z][a-z]?[–, A-Za-z-]*", first)):
                continue
            column = line.find(first, line.find(name) + len(name))
            text = first
            for continuation in lines[index+1:index+4]:
                if not text.endswith((",", "–")) or continuation[:column].strip():
                    break
                text += re.split(r"\s{2,}", continuation[column:].strip())[0]
            if name in rows:
                raise ValueError(f"Duplicate PDF row: {name}")
            rows[name] = text
    return rows


def normalize(value):
    return "".join(value.split()).replace("–", "-")


def as_numbers(text):
    symbols = set()
    for item in normalize(text).split(","):
        limits = item.split("-")
        symbols.update(range(ATOMIC_NUMBERS[limits[0]], ATOMIC_NUMBERS[limits[-1]] + 1))
    return frozenset(symbols)


def audit(web, pdf_layout):
    tables = html_tables(web)
    pages = pdf_layout.read_text().split("\f")
    printed = pdf_basis_rows(pages)
    for first, last, library in ((12, 33, ORBITAL_COVERAGE), (34, 37, FITTING_COVERAGE)):
        online = {row[0]: row[1] for number in range(first, last + 1) for row in tables[number]}
        if library.keys() != online.keys():
            raise ValueError(f"Library / HTML basis name difference: {library.keys() ^ online.keys()}")
        for name, coverage in online.items():
            if normalize(printed.pop(name)) != normalize(coverage) or as_numbers(coverage) != library[name]:
                raise ValueError(f"Element coverage mismatch: {name}")
    if printed:
        raise ValueError(f"Extra basis keywords in PDF: {sorted(printed)}")
    # Table 2.38 splits one repeated footnote into the next line.
    ecp_text = normalize("\n".join(pages[97:100])).replace("Page80,4", "4")
    for row in tables[38]:
        fields = row[:3]
        prefix = normalize("".join(fields)).replace("[", "").replace("]", "")
        if prefix not in ecp_text:
            raise ValueError(f"Missing ECP row in PDF: {fields}")
    print(f"{len(ORBITAL_COVERAGE)} orbitals, {len(FITTING_COVERAGE)} fits, {len(tables[38])} ECP rows checked")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("html_root", type=Path)
    cli.add_argument("pdf_layout", type=Path)
    args = cli.parse_args()
    audit(args.html_root, args.pdf_layout)
