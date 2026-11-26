"""Read the structure of one editable inline ORCA deck, independently of Qt."""

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
import re

from ..core._block_catalog import SIMPLE_INPUT_CONTROLS
from ..core.block_options import parse_option_value
from ..core.models import Atom
from ..io._quantum_geometry import atom
from .input import GENERATED_COMMENT, inline_coordinate


@dataclass
class Deck:
    words: tuple
    fields: dict
    atoms: tuple
    charge: int
    multiplicity: int
    comments: tuple


_TOKENS = re.compile(r'"[^"]*"|#[^#]*(?:#|$)|[^\s="#;]+|[=;]|"')
_COORDINATE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[ed][+-]?[0-9]+)?")
_NESTED = {"scf": {"trah"}, "casscf": {"ci", "ptsettings", "aughess", "dmrg"}}
_CONTROL_FIELDS = {(option.block, option.key.casefold()): option for option in SIMPLE_INPUT_CONTROLS}
CONTROL_WORDS = frozenset(word.casefold() for names in SIMPLE_INPUT_CONTROLS.values() for word in names.values())


def _control_keywords(words, fields):
    if any(a == "mini" and b == "print" for a, b in zip(words, words[1:])):
        raise ValueError("Write MiniPrint as one word in the ! line. MINI is an orbital basis set.")
    counts = Counter(words)
    for option, spellings in SIMPLE_INPUT_CONTROLS.items():
        selected = None
        for value, keyword in spellings.items():
            count = counts[keyword.casefold()]
            if count > 1:
                raise ValueError(f"Duplicate ! keyword: {keyword}")
            if count:
                selected = str(value).casefold()
        if selected is not None:
            # ORCA processes explicit block assignments after every simple keyword.
            fields.setdefault((option.block, option.key.casefold()), selected)
    return tuple(word for word in words if word not in CONTROL_WORDS)


def _tokens(line, comments):
    result = []
    for token in _TOKENS.findall(line):
        if token.startswith("#"):
            note = token.strip("#").strip().replace("\t", " ")
            if note and note != GENERATED_COMMENT:
                comments.append(note)
        elif token == '"':
            raise ValueError("Unclosed quote in the input preview")
        elif token not in ("=", ";"):
            result.append(token.strip('"').casefold())
    return result


def _block(fields, name, tokens):
    """Read scalar assignments and the nested sections used by the template writer."""
    path = [name]
    cursor = 0
    if tokens == ["end"]:
        raise ValueError(f"Empty input block: %{name}")

    def take():
        nonlocal cursor
        if cursor == len(tokens):
            raise ValueError(f"Incomplete %{name} block (missing value or end)")
        token = tokens[cursor]
        cursor += 1
        return token

    while path:
        key = take()
        parent = ".".join(path)
        if key == "end":
            path.pop()
            continue
        if key in _NESTED.get(parent, ()):
            path.append(key)
            continue
        value = take()
        if value == "end":
            raise ValueError(f"Missing value for %{parent} {key}")
        if (parent, key) == ("mrci", "newblock"):
            if take() != "*":
                raise ValueError("Expected * in the MRCI newblock header")
            path.append("newblock")
        elif (parent, key) == ("mrci.newblock", "refs"):
            if take() != "end":
                raise ValueError("Expected end after the MRCI reference")
        elif key in ("scspar", "dftcis_c"):
            while value.endswith(","):
                value += take()
        if (parent, key) in _CONTROL_FIELDS:
            # Check each assignment, including those superseded later in the file.
            parse_option_value(_CONTROL_FIELDS[parent, key], value)
        elif (parent, key) in fields:
            raise ValueError(f"Duplicate input setting: %{parent} {key}")
        fields[parent, key] = value
    if cursor != len(tokens):
        raise ValueError(f"Unexpected text after %{name} end: {tokens[cursor]}")


def block_fields(lines):
    fields = {}
    name = None
    body = []
    for tokens in lines:
        if tokens[0].startswith("%"):
            if name is not None:
                _block(fields, name, body)
            name, body = tokens[0][1:], tokens[1:]
        else:
            if name is None:
                raise ValueError(f"Unexpected input line: {' '.join(tokens)}")
            body.extend(tokens)
    if name is not None:
        _block(fields, name, body)
    return fields


def template_fields(lines):
    return block_fields([_tokens(line, []) for line in lines])


def read_deck(text):
    words, comments, blocks, rows = [], [], [], []
    state = None
    in_xyz = False
    maxcore = None
    for line_no, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        tokens = _tokens(line, comments)
        if not tokens:
            continue
        first, *rest = tokens
        if in_xyz:
            if tokens == ["*"]:
                in_xyz = False
            elif len(tokens) == 4:
                rows.append((line_no, tokens))
            else:
                raise ValueError(f"Line {line_no}: expected an element and three coordinates, or a closing *")
        elif first.startswith("!"):
            words.extend(word for word in (first[1:], *rest) if word)
        elif first.startswith("*"):
            header = ([first[1:]] if first != "*" else []) + rest
            if state is not None or len(header) != 3 or header[0] != "xyz":
                raise ValueError("The preview requires one inline * xyz charge multiplicity section")
            if any(not re.fullmatch(r"[+-]?[0-9]+", value) for value in header[1:]):
                raise ValueError("Charge and multiplicity must be integers")
            state = tuple(int(value) for value in header[1:])
            if not -2**31 <= state[0] < 2**31 or not 1 <= state[1] < 2**31:
                raise ValueError("Charge and multiplicity exceed the supported range")
            in_xyz = True
        elif first == "%maxcore":
            if maxcore is not None or len(rest) != 1:
                raise ValueError("Expected one %maxcore value in MB per process")
            maxcore = rest[0]
        else:
            blocks.append(tokens)
    if in_xyz or state is None:
        raise ValueError("The inline * xyz coordinate section is missing or unfinished")
    if not rows:
        raise ValueError("A molecule requires at least one atom")
    fields = block_fields(blocks)
    words = _control_keywords(words, fields)
    if maxcore is not None:
        fields["", "maxcore"] = maxcore
    if "bohrs" in words and "angs" in words:
        raise ValueError("Conflicting coordinate units in the input preview")
    unit = "bohr" if "bohrs" in words else "angstrom"
    words = tuple(word for word in words if word not in ("bohrs", "angs"))
    atoms = []
    for line_no, (symbol, *xyz) in rows:
        try:
            if not all(_COORDINATE.fullmatch(value) for value in xyz):
                raise ValueError("Expected three finite decimal coordinates")
            item = atom(symbol, xyz, unit)
            item.validate()
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Line {line_no}: {exc}") from None
        atoms.append(item)
    return Deck(words, fields, tuple(atoms), *state, tuple(comments))


def edited_geometry(molecule, deck):
    # The display has eight decimal places. Match displayed rows before mapping
    # edited rows, and retain full source precision on every untouched axis.
    displayed = [Atom(a.element, *(float(inline_coordinate(v)) for v in (a.x, a.y, a.z))) for a in molecule.atoms]
    mapping = [i if i < len(displayed) and row == displayed[i] else None for i, row in enumerate(deck.atoms)]
    used = set(mapping) - {None}
    identical = defaultdict(deque)
    for i, row in enumerate(displayed):
        if i not in used:
            identical[row].append(i)
    for i, row in enumerate(deck.atoms):
        if mapping[i] is None and identical[row]:
            mapping[i] = identical[row].popleft()
            used.add(mapping[i])
    if len(deck.atoms) == len(displayed):
        for i, previous in enumerate(mapping):
            if previous is None and i not in used:
                mapping[i] = i
                used.add(i)
    # Pair remaining moved atoms by element only where every row can be accounted for.
    old, new = defaultdict(list), defaultdict(list)
    for i, row in enumerate(displayed):
        if i not in used:
            old[row.element].append(i)
    for i, row in enumerate(deck.atoms):
        if mapping[i] is None:
            new[row.element].append(i)
    for element, indices in new.items():
        if len(indices) == len(old[element]):
            for i, source in zip(indices, old[element]):
                mapping[i] = source

    atoms = []
    for row, index in zip(deck.atoms, mapping):
        if index is not None:
            original, shown = molecule.atoms[index], displayed[index]
            row = Atom(row.element, *(getattr(original, key) if getattr(row, key) == getattr(shown, key)
                                      else getattr(row, key) for key in ("x", "y", "z")))
        atoms.append(row)
    surviving = {source: i for i, source in enumerate(mapping) if source is not None}
    bonds = tuple(replace(b, a=surviving[b.a], b=surviving[b.b]) for b in molecule.bonds
                  if b.a in surviving and b.b in surviving)
    return replace(molecule, atoms=tuple(atoms), bonds=bonds, charge=deck.charge,
                   multiplicity=deck.multiplicity), tuple(mapping)
