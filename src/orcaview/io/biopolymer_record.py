"""Import the first deposited model of a polymer from the RCSB PDB archive."""

from collections import defaultdict
import gzip
from http.client import IncompleteRead
from io import BytesIO
import math
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zlib import error as DecompressionError

from orcaview.application.update_tls import tls_context
from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.io.structure_record import StructureRecord, polymer_atom_role


_PDB_ID = re.compile(r"(?:[1-9][a-z0-9]{3}|pdb_[a-z0-9]{8})", re.I | re.ASCII)
_MAX_XML = 64 * 1024 * 1024
_ORDERS = {"sing": 1, "doub": 2, "trip": 3, "arom": 2, "delo": 2}
_CATEGORIES = {"entry", "atom_site", "entity_poly", "chem_comp", "chem_comp_bond", "struct_conn"}


def _entry_key(identifier):
    key = identifier.upper()
    return key[8:] if key.startswith("PDB_0000") else key


def _rows(xml):
    """Release completed XML rows and categories as the reader advances."""
    parents = []
    for event, node in ElementTree.iterparse(BytesIO(xml), events=("start", "end")):
        if event == "start":
            parents.append(node)
            continue
        if len(parents) == 3:
            name = node.tag.rsplit("}", 1)[-1]
            if name in _CATEGORIES:
                row = dict(node.attrib)
                row.update((child.tag.rsplit("}", 1)[-1], child.text)
                           for child in node if child.text is not None)
                yield name, row
            parents[-2].remove(node)
        parents.pop()


def _conformer(sites):
    """Keep shared atoms and one coherent residue alternative, by mean occupancy."""
    alternatives = defaultdict(list)
    for site in sites:
        if site.get("label_alt_id"):
            key = (site["label_alt_id"], site["label_comp_id"])
            alternatives[key].append(float(site.get("occupancy", 1)))
    if not alternatives:
        return sites
    choice = min(alternatives, key=lambda key: (-sum(alternatives[key]) / len(alternatives[key]), key))
    return [site for site in sites if site["label_comp_id"] == choice[1]
            and site.get("label_alt_id", choice[0]) == choice[0]]


def _bond_type(order):
    if order not in _ORDERS:
        raise ValueError("Unsupported PDB chemical bond order: " + order)
    return _ORDERS[order], "aromatic" if order in ("arom", "delo") else "plain"


def _read_record(xml, kind, identifier):
    entities, components = {}, {}
    templates, residues = defaultdict(list), defaultdict(list)
    links = []
    entry, model = None, None
    for table, row in _rows(xml):
        if table == "entry":
            entry = row["id"]
        elif table == "entity_poly":
            entities[row["entity_id"]] = row["type"].lower()
        elif table == "chem_comp":
            components[row["id"]] = row.get("type", "").lower()
        elif table == "chem_comp_bond":
            templates[row["comp_id"]].append((row["atom_id_1"], row["atom_id_2"], row["value_order"].lower()))
        elif table == "struct_conn":
            if row["conn_type_id"].startswith(("covale", "disulf", "modres")):
                links.append(row)
        else:
            atom_model = row.get("pdbx_PDB_model_num", "1")
            if model is None:
                model = atom_model
            if atom_model == model and row.get("label_seq_id") and float(row.get("occupancy", 1)) > 0:
                key = (row["label_entity_id"], row["label_asym_id"], int(row["label_seq_id"]))
                residues[key].append(row)
    if entry is None or _entry_key(entry) != _entry_key(identifier):
        raise ValueError("The coordinate file does not match the requested PDB entry.")

    atoms, bonds, addresses, chosen = [], {}, {}, {}
    roles = []
    charge = 0
    for (entity, chain, seq), sites in residues.items():
        polymer = entities.get(entity, "")
        if kind == "protein":
            if not polymer.startswith("polypeptide("):
                continue
        elif polymer != "polydeoxyribonucleotide":
            if polymer != "polydeoxyribonucleotide/polyribonucleotide hybrid":
                continue
            sites = [s for s in sites if "dna" in components.get(s["label_comp_id"], "")]
            if not sites:
                continue
        sites = _conformer(sites)
        comp = sites[0]["label_comp_id"]
        by_name = {}
        for site in sites:
            name = site["label_atom_id"]
            if name in by_name or site["label_comp_id"] != comp:
                raise ValueError("The PDB entry has ambiguous atom positions in the selected model.")
            index = len(atoms)
            addresses[chain, seq, comp, name] = (index, site.get("label_alt_id"))
            by_name[name] = index
            atoms.append(Atom(site["type_symbol"].capitalize(),
                              *(float(site["Cartn_" + axis]) for axis in "xyz")))
            roles.append(polymer_atom_role(kind, name, atoms[-1].element))
            charge += int(site.get("pdbx_formal_charge", 0))
        chosen[chain, seq] = by_name
        if len(sites) > 1 and not templates[comp]:
            raise ValueError("The PDB entry lacks a chemical bond table for " + comp + ".")
        for a, b, order in templates[comp]:
            if a in by_name and b in by_name:
                bonds[tuple(sorted((by_name[a], by_name[b])))] = _bond_type(order)
    if not atoms:
        raise ValueError(f"No {kind.upper() if kind == 'dna' else kind} coordinates in this PDB entry.")

    # The component dictionary describes each monomer. Connect adjacent
    # sequence positions only within a chain and across a plausible bond length.
    tail, head, cutoff = ("C", "N", 1.9) if kind == "protein" else ("O3'", "P", 2.2)
    for (chain, seq), residue in chosen.items():
        a, b = residue.get(tail), chosen.get((chain, seq + 1), {}).get(head)
        if a is not None and b is not None:
            one, two = atoms[a], atoms[b]
            if .5 < math.dist((one.x, one.y, one.z), (two.x, two.y, two.z)) <= cutoff:
                bonds[tuple(sorted((a, b)))] = (1, "plain")
    for link in links:
        pair = []
        for p in ("ptnr1", "ptnr2"):
            if link.get(p + "_symmetry", "1_555") != "1_555" or not link.get(p + "_label_seq_id"):
                break
            key = (link[p + "_label_asym_id"], int(link[p + "_label_seq_id"]),
                   link[p + "_label_comp_id"], link[p + "_label_atom_id"])
            target = addresses.get(key)
            alt = link.get("pdbx_" + p + "_label_alt_id")
            if target is None or (alt and alt != target[1]):
                break
            pair.append(target[0])
        if len(pair) == 2 and pair[0] != pair[1]:
            order = link.get("pdbx_value_order", "sing").lower()
            bonds[tuple(sorted(pair))] = _bond_type(order)

    # PDB coordinates usually omit hydrogen atoms and do not specify spin.
    # Supply an editable multiplicity consistent with the atoms actually present.
    electrons = sum(ATOMIC_NUMBERS.get(atom.element, 0) for atom in atoms) - charge
    molecule = Molecule(f"PDB {entry} ({'DNA' if kind == 'dna' else 'protein'})", tuple(atoms),
                        tuple(Bond(a, b, order, style) for (a, b), (order, style) in bonds.items()),
                        charge=charge, multiplicity=1 + electrons % 2, bonds_explicit=True)
    molecule.validate()
    return StructureRecord(molecule, polymer_roles="".join(roles))


def load_pdb_record(kind, identifier):
    """Fetch a finite protein or DNA model, retaining deposited Cartesian coordinates."""
    if kind not in ("protein", "dna"):
        raise ValueError("Choose protein or DNA.")
    identifier = identifier.strip()
    if not _PDB_ID.fullmatch(identifier):
        raise ValueError("Enter a four-character PDB ID or an extended pdb_ identifier.")
    request = Request(f"https://files.rcsb.org/download/{identifier.lower()}.xml.gz",
                      headers={"User-Agent": "OrcaView"})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=20, context=tls_context()) as response, gzip.GzipFile(fileobj=response) as archive:
                xml = archive.read(_MAX_XML + 1)
            break
        except HTTPError as exc:
            if exc.code == 404:
                raise ValueError("PDB entry not found: " + identifier) from exc
            raise ValueError(f"RCSB PDB returned HTTP {exc.code}.") from exc
        except (gzip.BadGzipFile, EOFError, DecompressionError, IncompleteRead) as exc:
            raise ValueError("The downloaded PDB coordinate file is incomplete or invalid.") from exc
        except (URLError, OSError) as exc:
            if attempt:
                raise ValueError("Could not reach RCSB PDB. Check the internet connection and try again.") from exc
    if len(xml) > _MAX_XML:
        raise ValueError("The PDB coordinate file exceeds the editor's 64 MiB import limit.")
    try:
        return _read_record(xml, kind, identifier)
    except (ElementTree.ParseError, KeyError) as exc:
        raise ValueError("The downloaded PDB coordinate file is incomplete or invalid.") from exc


def load_pdb(kind, identifier):
    return load_pdb_record(kind, identifier).molecule
