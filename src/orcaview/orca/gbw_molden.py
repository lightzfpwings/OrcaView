"""Convert real, spherical-basis ORCA 6.1 GBW wavefunctions to the ORCA Molden dialect."""

from concurrent.futures import CancelledError
import math
import struct

from orcaview.core.elements import ATOMIC_NUMBERS


_HEADER = struct.Struct("<6q")
_ATOM = struct.Struct("<6d2i")
_SHELL = struct.Struct("<4i37d37d")
_SYMBOLS = {z: symbol for symbol, z in ATOMIC_NUMBERS.items()}
_UNSUPPORTED = "Unsupported GBW layout. Choose the matching orca_2mkl or open an exported .molden.input file."


def has_builtin_layout(header):
    return len(header) >= 24 and struct.unpack_from("<2q", header) == (-1, 149839)


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise CancelledError()


def _block(raw, offsets, start):
    end = min((p for p in offsets if p > start), default=len(raw))
    if not 72 <= start < end <= len(raw):
        raise ValueError("Invalid GBW section offsets.")
    return memoryview(raw)[start:end]


def _geometry(data):
    count, = struct.unpack_from("<i", data)
    if not 0 < count <= (len(data)-4)//_ATOM.size:
        raise ValueError("Incomplete GBW geometry.")
    atoms = []
    for x, y, z, effective, _, _, number, _ in _ATOM.iter_unpack(data[4:4+count*_ATOM.size]):
        if (number not in _SYMBOLS or not all(map(math.isfinite, (x, y, z))) or
                not effective.is_integer() or not 0 < effective <= number):
            raise ValueError(_UNSUPPORTED)
        atoms.append((_SYMBOLS[number], number, x, y, z, int(effective)))
    return atoms


def _write_basis(out, data, natoms, size, cancel):
    # The first basis is the orbital basis. Further records can be auxiliary bases.
    group_count, centers = struct.unpack_from("<2i", data)
    if group_count < 1 or centers != natoms:
        raise ValueError(_UNSUPPORTED)
    pos = 8
    order = []
    out.write("[GTO]\n")
    for center in range(centers):
        _check_cancel(cancel)
        index, count = struct.unpack_from("<2i", data, pos)
        pos += 8
        if index != center or not 0 <= count <= (len(data)-pos)//_SHELL.size:
            raise ValueError("Incomplete GBW orbital basis.")
        out.write(f" {center+1} 0\n")
        for _ in range(count):
            angular, first, n, _, *rows = _SHELL.unpack_from(data, pos)
            pos += _SHELL.size
            if not (0 <= angular <= 5 and first == len(order) and 1 <= n <= 37):
                raise ValueError(_UNSUPPORTED)
            out.write(f"{'spdfgh'[angular]} {n} 1.0\n")
            for exponent, weight in zip(rows[:n], rows[37:37+n]):
                if not math.isfinite(exponent) or exponent <= 0 or not math.isfinite(weight):
                    raise ValueError("Invalid GBW Gaussian primitive.")
                out.write(f" {exponent:.16g} {weight:.16g}\n")
            # GBW p shells use z,x,y. Molden uses x,y,z; spherical d and up
            # already follow 0,+1,-1,+2,-2,... in the ORCA convention.
            offsets = (1, 2, 0) if angular == 1 else range(2*angular+1)
            order.extend(first+k for k in offsets)
        out.write("\n")
    if len(order) != size:
        raise ValueError("GBW orbital and basis dimensions disagree.")
    return order


def _write_mos(out, data, sets, size, order, cancel):
    # Stored AO-major. Each spin block also contains occupations, energies,
    # numerical irreps and core flags. Keep the recorded irrep identifier.
    pos = 12
    for spin in ("Alpha", "Beta")[:sets]:
        occ = pos + 8*size*size
        energy, irrep = occ+8*size, occ+16*size
        for mo in range(size):
            _check_cancel(cancel)
            e, = struct.unpack_from("<d", data, energy+8*mo)
            n, = struct.unpack_from("<d", data, occ+8*mo)
            symmetry, = struct.unpack_from("<i", data, irrep+4*mo)
            if not math.isfinite(e) or not math.isfinite(n):
                raise ValueError("Invalid GBW orbital metadata.")
            out.write(f" Sym= {symmetry+1}\n Ene= {e:.16g}\n Spin= {spin}\n Occup= {n:.16g}\n")
            for i, ao in enumerate(order, 1):
                value, = struct.unpack_from("<d", data, pos+8*(ao*size+mo))
                if not math.isfinite(value):
                    raise ValueError("Invalid GBW orbital coefficients.")
                if value:
                    out.write(f" {i} {value:.16g}\n")
        pos = occ+24*size


def write_gbw_molden(raw, output, cancel=None):
    if not has_builtin_layout(raw):
        raise ValueError(_UNSUPPORTED)
    _check_cancel(cancel)
    try:
        offsets = _HEADER.unpack_from(raw, 24)
        geometry, basis, orbitals = (_block(raw, offsets, p) for p in offsets[1:4])
        atoms = _geometry(geometry)
        sets, size = struct.unpack_from("<iq", orbitals)
        if sets not in (1, 2) or size < 1 or 12+sets*(8*size*size+24*size) != len(orbitals):
            raise ValueError(_UNSUPPORTED)
        with output.open("w", encoding="ascii", newline="\n") as out:
            out.write("[Molden Format]\n[Title]\n OrcaView GBW export (orca_2mkl conventions)\n\n[Atoms] AU\n")
            for i, (symbol, number, x, y, z, _) in enumerate(atoms, 1):
                out.write(f"{symbol} {i} {number} {x:.16g} {y:.16g} {z:.16g}\n")
            pseudo = [(i, a) for i, a in enumerate(atoms, 1) if a[1] != a[5]]
            if pseudo:
                out.write("[Pseudo]\n")
                for i, a in pseudo:
                    out.write(f"{a[0]} {i} {a[5]}\n")
            order = _write_basis(out, basis, len(atoms), size, cancel)
            out.write("[5D]\n[7F]\n[9G]\n[11H]\n[MO]\n")
            _write_mos(out, orbitals, sets, size, order, cancel)
    except struct.error as exc:
        raise ValueError("Incomplete GBW wavefunction.") from exc
    return output
