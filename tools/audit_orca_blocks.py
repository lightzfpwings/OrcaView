"""Check the two structured block catalogs against the cited ORCA 6.1.1 manual sections."""

import argparse
from dataclasses import replace
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
import re
import sys

from orcaview.core._block_catalog import catalog_options
from orcaview.core._solver_block_catalog import solver_options
from orcaview.core.integrals import integral_options
from orcaview.core.methods import METHODS, dispersion_options, reference_options
from orcaview.core.models import CalculationSpec
from orcaview.core.reaction_path import options as reaction_options
from orcaview.core.solvation import solvation_block_options, solvation_options


LEDGER = Path(__file__).resolve().parents[1] / "docs/research/ORCA611_BLOCK_AUDIT.md"
CHAPTER_LINK = re.compile(
    r"\[(\d+)–(\d+)\]\(https://orca-manual\.mpi-muelheim\.mpg\.de/(contents/[\w/-]+\.html)\)"
)


class ManualChapter(HTMLParser):
    """Only index the article body, omitting navigation, comments and the global index."""

    def __init__(self):
        super().__init__()
        self.in_article = False
        self.in_title = False
        self.body = []
        self.title = []

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self.in_article = True
        elif tag == "title":
            self.in_title = True
        elif self.in_article and tag in ("tr", "td", "th", "p", "li", "pre", "br", "section"):
            self.body.append("\n")

    def handle_endtag(self, tag):
        if tag == "article":
            self.in_article = False
        elif tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_article:
            self.body.append(data)
        if self.in_title:
            self.title.append(data)


@lru_cache(maxsize=None)
def article_text(path):
    doc = ManualChapter()
    doc.feed(path.read_text(encoding="utf-8"))
    doc.close()
    if "ORCA 6.1.1 Manual" not in "".join(doc.title) or not doc.body:
        raise ValueError(f"Expected an ORCA 6.1.1 manual chapter in {path}")
    return "".join(doc.body)


def catalog_fields():
    common = set()
    solvers = set()
    solvent_path = set()
    for method, preset in METHODS.items():
        for job in preset.job_types:
            for model in solvation_options(method, job):
                spec = CalculationSpec(method=method, job_type=job, solvation_model=model)
                solvent_path.update((o.block, o.key) for o in (*solvation_block_options(spec), *reaction_options(spec)))
            for approximation in integral_options(method, job):
                for reference in reference_options(method, job):
                    spec = CalculationSpec(method=method, job_type=job, wavefunction=reference,
                                           integral_approximation=approximation)
                    solvers.update((opt.block, opt.key) for opt in solver_options(spec))
                    for dispersion in dispersion_options(method):
                        common.update((opt.block, opt.key) for opt in
                                      catalog_options(replace(spec, dispersion=dispersion)))
    return common, solvers, solvent_path


def source_ledger():
    sources = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `%"):
            continue
        heading, fields, references = line.strip("|").split("|")
        block = re.match(r"\s*`%([\w.]+)`", heading).group(1)
        chapters = [(int(first), int(last), path) for first, last, path in CHAPTER_LINK.findall(references)]
        keys = re.findall(r"`(\w+)`", fields)
        if not chapters or not keys:
            raise ValueError(f"Missing fields or references in {line}")
        for key in keys:
            if (block, key) in sources:
                raise ValueError(f"Duplicate ledger entry %{block}.{key}")
            sources[block, key] = chapters
    if not sources:
        raise ValueError(f"No field rows in {LEDGER}")
    return sources


def physical_page(html_root, pages, key, chapters):
    token = re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)", re.IGNORECASE)
    for first, last, path in chapters:
        if not 1 <= first <= last <= len(pages):
            raise ValueError(f"Invalid physical PDF page interval {first}–{last}")
        if token.search(article_text(html_root / path)):
            for page in range(first, last + 1):
                if token.search(pages[page - 1]):
                    return path, page
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_root", type=Path, help="ORCA manual HTML mirror containing contents/")
    parser.add_argument("pdf_layout_text", type=Path, help="pdftotext -layout output with form feeds")
    parser.add_argument("--show-fields", action="store_true", help="print matched chapter and physical page per field")
    args = parser.parse_args()
    pages = args.pdf_layout_text.read_text(encoding="utf-8").rstrip("\f\n").split("\f")
    if len(pages) != 1601 or not re.search(r"Release\s+6\.1\.1\b", pages[0]):
        parser.error("Expected the 1601-page ORCA 6.1.1 PDF with original page breaks")

    common, solvers, solvent_path = catalog_fields()
    sources = source_ledger()
    fields = common | solvers | solvent_path
    errors = [f"catalog field without evidence row %{b}.{k}" for b, k in sorted(fields - sources.keys())]
    errors.extend(f"evidence row absent from catalog %{b}.{k}" for b, k in sorted(sources.keys() - fields))
    matched = 0
    for block, key in sorted(fields & sources.keys()):
        evidence = physical_page(args.html_root, pages, key, sources[block, key])
        if evidence is None:
            errors.append(f"no HTML/PDF match in the cited chapter for %{block}.{key}")
        else:
            matched += 1
            if args.show_fields:
                chapter, page = evidence
                print(f"%{block}.{key}\t{chapter}\tPDF {page}")
    print(f"Common {len(common)}, solver {len(solvers)}, solvent/path {len(solvent_path)}, distinct {len(fields)}, matched in both sources {matched}")
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
