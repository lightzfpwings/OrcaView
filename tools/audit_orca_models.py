"""Cross-check specific ORCA 6.1.1 keyword tables against PDF pages and OrcaView.

Run with PYTHONPATH=src, lxml, the root of the manual HTML mirror, and the
output of pdftotext -layout on the official PDF. Page ranges are physical.
"""

import argparse
from pathlib import Path
import re

from lxml import html

from orcaview.core._state_catalog import DOUBLE_HYBRID_RESPONSE
from orcaview.core.methods import canonical_method, dispersion_options


def rows(file, number):
    document = html.parse(str(file))
    captions = document.xpath("//caption")
    table = next(cap.getparent() for cap in captions if
                 re.search(rf"Table 3\.{number}\b", cap.text_content()))
    return table.xpath("./tbody/tr")


def compact(string):
    return "".join(string.casefold().split()).replace("−", "-")


def pdf_contains(pages, term):
    target = compact(term)
    if target in compact(" ".join(pages)):
        return True
    # pdftotext -layout may wrap a keyword inside its table column. Join
    # consecutive lines in that column, without joining adjacent cells.
    for page in pages:
        lines = page.splitlines()
        for index, line in enumerate(lines):
            for word in re.finditer(r"\S+", line):
                first = compact(word[0])
                if not target.startswith(first):
                    continue
                chunks = []
                for after in lines[index:index + 4]:
                    cell = re.split(r"\s{2,}", after[word.start():].strip(), maxsplit=1)[0]
                    chunks.append(compact(cell))
                    if "".join(chunks) == target:
                        return True
    return False


def exported(term, group):
    if group == "LibXC":
        return canonical_method(f"LibXC({term})")
    if term.startswith(("SCS", "SOS")) and term in DOUBLE_HYBRID_RESPONSE.values():
        return canonical_method("TDA-" + term)
    if term.endswith(" D3BJ"):
        parent = term.split()[0]
        try:
            return canonical_method(term)
        except ValueError:
            return "D3BJ" in dispersion_options(canonical_method(parent))
    return canonical_method(term)


def inventory(root, pdf_text):
    chapters = root / "contents" / "modelchemistries"
    layout = pdf_text.read_text().split("\f")
    if "6.1.1" not in "".join(layout[:3]):
        raise ValueError("Expected the ORCA 6.1.1 PDF")
    definitions = [
        ("DensityFunctionalTheory", n, "DFT", 1, start, end)
        for n, start, end in ((1, 225, 225), (2, 225, 226), (4, 229, 230),
                              (6, 233, 234), (8, 236, 237), (9, 237, 238))
    ] + [("DensityFunctionalTheory", 12, "LibXC", 0, 242, 244),
         ("semiempirical", 22, "NDO", 0, 261, 261),
         ("casdft", 47, "CASDFT", 0, 498, 498),
         ("casdft", 48, "CASDFT", 0, 499, 499),
         ("casdft", 49, "CASDFT", 0, 501, 502)]
    issues = []
    for chapter, number, group, column, start, end in definitions:
        names = []
        for row in rows(chapters / (chapter + ".html"), number):
            cols = row.xpath("./td")
            if len(cols) <= column:
                continue
            cell = cols[column]
            terms = [code.text_content() for code in cell.xpath(".//code")]
            if group in ("CASDFT", "NDO"):
                terms = [cell.text_content().strip()]
            names.extend(term for term in terms if term)
        if not names:
            raise ValueError(f"No keyword rows found in HTML table 3.{number}")
        for term in names:
            if not pdf_contains(layout[start - 1:end], term):
                issues.append(f"HTML 3.{number}, PDF {start}-{end}: {term}")
            if term == "WB97M(2)":
                continue  # Separate two-step example in examples/native_methods/water-wb97m2.inp.
            try:
                if not exported(term, group):
                    issues.append("Missing combination: " + term)
            except ValueError:
                issues.append("Missing from OrcaView: " + term)
        print(f"HTML 3.{number:2}  PDF {start}-{end}  {len(names):3} keyword entries")
    return issues


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("html_root", type=Path)
    cli.add_argument("pdf_layout_text", type=Path)
    args = cli.parse_args()
    differences = inventory(args.html_root, args.pdf_layout_text)
    for difference in differences:
        print(difference)
    raise SystemExit(bool(differences))
