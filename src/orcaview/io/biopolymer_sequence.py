"""Build editable idealized protein and DNA geometries from a single sequence."""

from orcaview.io.babel_structure import record_from_babel_payload, run_babel_worker


_ALPHABETS = {"protein": "ACDEFGHIKLMNPQRSTVWY", "dna": "ACGT"}


def normalize_sequence(kind, text):
    """Read a one-letter sequence or one FASTA record, preserving residue order."""
    if kind not in _ALPHABETS:
        raise ValueError("Choose protein or DNA.")
    lines = text.strip().splitlines()
    if lines and lines[0].startswith(">"):
        lines = lines[1:]
    if any(line.lstrip().startswith(">") for line in lines):
        raise ValueError("Enter a single FASTA record.")
    letters = "".join("".join(lines).split())
    if not letters:
        raise ValueError("Enter a sequence.")
    alphabet = _ALPHABETS[kind]
    if not letters.isascii() or not set(letters.upper()) <= set(alphabet):
        if kind == "dna":
            raise ValueError("DNA sequences use A, C, G and T.")
        raise ValueError("Use the one-letter codes for the 20 standard amino acids.")
    return letters.upper()


def build_sequence_record(kind, text):
    """Generate an idealized peptide or an antiparallel complementary DNA duplex."""
    sequence = normalize_sequence(kind, text)
    payload = run_babel_worker(sequence.encode("ascii"), "sequence", kind)
    record = record_from_babel_payload("Protein" if kind == "protein" else "DNA", payload)
    record.molecule.validate()
    return record


def build_sequence(kind, text):
    return build_sequence_record(kind, text).molecule
