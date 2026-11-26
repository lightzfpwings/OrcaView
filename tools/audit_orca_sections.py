"""Emit the offline section/keyword lookup from the ORCA 6.1.1 HTML and PDF.

Usage: python tools/audit_orca_sections.py HTML_ROOT orca.pdf manual-layout.txt
Requires lxml and pypdfium2. The application does not require either dependency.
"""
import argparse
from difflib import SequenceMatcher
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import urldefrag

from lxml import html
import pypdfium2 as pdfium


def scope(section):
    chapter, part = map(int, section.split(".")[:2])
    if chapter == 2 and part != 16:
        return True
    if chapter == 3 or chapter in (6, 7):
        return True
    if chapter == 4:
        return part != 7
    if chapter == 8:
        return part in (2, 3, 4)
    return chapter == 5 and part in (*range(4, 14), 15, 24, 26, 27, 34, 37, 39)


def pdf_sections(document):
    chapter = 0
    numbers = []
    result = {}
    for mark in document.get_toc(max_depth=12):
        if mark.level == 0:
            if mark.get_title() == "Quickstart Guide":
                chapter = 1
            elif chapter:
                chapter += 1
            numbers = [chapter]
        elif chapter:
            level = mark.level
            numbers = numbers[:level] + [numbers[level] + 1 if len(numbers) > level else 1]
        if 2 <= chapter <= 8:
            result[".".join(map(str, numbers))] = (mark.get_title(), mark.get_dest().get_index() + 1)
    return result


def simplify(title):
    return "".join(c for c in title.lower() if c.isalnum())


def check_heading(section, web_title, pdf_title):
    # These math commands disappear from the three corresponding PDF bookmarks.
    plain = re.sub(r"\\(?:omega|Delta|rm)\b", "", web_title)
    if SequenceMatcher(None, simplify(plain), simplify(pdf_title)).ratio() < 0.82:
        raise ValueError(f"Review {section}: {web_title!r}, {pdf_title!r}")


def candidates(node):
    # Index literal identifiers in manual markup and input examples. These names
    # are search terms. They do not enable a keyword in the structured writer.
    identifier = r"[%!]?[A-Za-z][A-Za-z0-9_+./()\[\],*-]{1,64}"
    for element in node.xpath(".//code | .//pre"):
        parent = next(element.iterancestors("section"), None)
        if parent is not node:
            continue
        value = element.text_content()
        if element.tag == "code":
            if re.fullmatch(identifier, value):
                yield value
            continue
        if not re.search(r"^\s*(?:[%!]|\* xyz)", value, re.MULTILINE):
            continue
        for line in value.splitlines():
            body = line.partition("#")[0].strip()
            if not body:
                continue
            tokens = body.lstrip("!").split() if body.startswith("!") else body.split()[:1]
            for token in tokens:
                if re.fullmatch(identifier, token) and token.lower() not in ("end", "true", "false"):
                    yield token


def audit(web, pdf, layout):
    if sha256(pdf.read_bytes()).hexdigest() != "4df05dcc1126d7816b1770367e29388bb69d079b5ee7b907b939cc7c46830c92":
        raise ValueError("PDF differs from the audited 2025-12-02 Release 6.1.1; check the edition")
    pages = layout.read_text().split("\f")
    bookmarks = pdf_sections(pdfium.PdfDocument(pdf))
    pdf_order = list(bookmarks)
    page_span = {}
    for i, section in enumerate(pdf_order):
        depth = section.count(".")
        next_section = next((s for s in pdf_order[i+1:] if s.count(".") <= depth), None)
        page_span[section] = bookmarks[next_section][1] if next_section else len(pages)

    @lru_cache(maxsize=None)
    def page(path):
        return html.parse(str(web / path))

    rows = []
    for anchor in page("index.html").xpath("//article//a"):
        href = anchor.get("href", "")
        title = " ".join(anchor.text_content().split())
        match = re.fullmatch(r"([2-8](?:\.\d+)+)\. (.+)", title)
        if not match or not href.startswith("contents/") or "/appendix/" in href:
            continue
        section, title = match.groups()
        pdf_title, first = bookmarks[section]
        check_heading(section, title, pdf_title)
        if not scope(section):
            continue
        path, fragment = urldefrag(href)
        doc = page(path)
        nodes = doc.xpath('//*[@id=$target]', target=fragment) if fragment else doc.xpath("//article/section[1]")
        if len(nodes) != 1:
            raise ValueError(f"Missing or ambiguous HTML destination for {section}: {href}")
        node = nodes[0]
        if node.tag != "section":
            node = next(node.iterancestors("section"))
        pdf_text = "\n".join(pages[first-1:page_span[section]]).casefold()
        terms = sorted({t.casefold() for t in candidates(node) if t.casefold() in pdf_text})
        # Bookmarks lose some mathematical symbols. Restore the names from the web heading.
        if "B97" in pdf_title and r"\omega" in title:
            pdf_title = pdf_title.replace("B97", "ωB97", 1)
        rows.append((section, pdf_title, href, str(first), " ".join(terms)))
    listed = {s for s, *_ in rows}
    missing = [s for s in bookmarks if "." in s and scope(s) and s not in listed]
    if missing:
        raise ValueError(f"Missing HTML sections: {missing}")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("html", "pdf", "layout"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    records = audit(args.html, args.pdf, args.layout)
    print('"""ORCA 6.1.1 calculation section reference. Generated by tools/audit_orca_sections.py."""\n')
    print("SECTION_ROWS = (")
    for row in records:
        print("    " + repr(row) + ",")
    print(")")
