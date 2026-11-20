"""Look up calculation topics in both official ORCA 6.1.1 editions."""

from ._manual_sections import SECTION_ROWS

WEB_ROOT = "https://orca-manual.mpi-muelheim.mpg.de/"
PDF_URL = WEB_ROOT + "_static/pdf/orca.pdf"


def lookup(query):
    """Prefer exact section numbers and terms in headings over keyword-only hits."""
    words = query.casefold().strip().split()
    if not words:
        return tuple(row for row in SECTION_ROWS if row[0].count(".") == 1)
    if len(words) == 1 and all(piece.isdecimal() for piece in words[0].split(".")):
        section = words[0]
        return tuple(row for row in SECTION_ROWS if row[0] == section or row[0].startswith(section + "."))
    matches = []
    for row in SECTION_ROWS:
        number, title, _, _, terms = row
        heading = number + " " + title.casefold()
        if all(word in heading or word in terms for word in words):
            rank = 0 if query.strip() == number else 1 if all(w in heading for w in words) else 2
            matches.append((rank, row))
    return tuple(row for _, row in sorted(matches, key=lambda x: x[0]))
