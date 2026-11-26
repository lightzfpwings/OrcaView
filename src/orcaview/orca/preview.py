"""Map an edited preview back to the calculation and geometry that produce it."""

from dataclasses import replace
import re

from ..core._block_catalog import NUMERICAL_FREQUENCY_OPTIONS
from ..core.block_options import BlockOverride, available_options, parse_option_value
from ..core.integrals import auxiliary_options, basis_options, grid_options, integral_options, orbital_and_aux_input, scalar_options
from ..core.methods import (
    ACTIVE_SPACE_METHODS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS, METHODS, REFERENCE_FUNCTIONAL_METHODS,
    RESPONSE_FUNCTIONALS, dispersion_options, pno_options, reference_options,
)
from ..core.models import CalculationSpec, SCF_CONVERGENCE
from ..core.solvation import MODELS
from ._preview_deck import CONTROL_WORDS, edited_geometry, read_deck, template_fields
from .input import method_input, render_input


_JOBS = {"sp": "SP", "opt": "OPT", "freq": "FREQ", "numfreq": "FREQ", "optts": "OPT_TS", "irc": "IRC"}
_SLOTS = {"aux_j": "auxj", "aux_jk": "auxjk", "aux_c": "auxc", "cabs": "cabs"}


def _take(words, choices, default=None):
    matches = [value for value in choices if value.casefold() in words]
    if len(matches) > 1:
        raise ValueError("Conflicting input keywords: " + ", ".join(matches))
    if not matches:
        return default
    words.remove(matches[0].casefold())
    return matches[0]


def _resource(value, label):
    if not re.fullmatch(r"[+]?[0-9]+", str(value)) or not 1 <= int(value) <= 2147483647:
        raise ValueError(f"{label} requires a positive 32-bit integer")
    return int(value)


def _job(words):
    jobs = set(_JOBS).intersection(words)
    words.difference_update(jobs)
    if not jobs:
        return "SP"
    if len(jobs) == 1:
        return _JOBS[next(iter(jobs))]
    if jobs in ({"opt", "freq"}, {"opt", "numfreq"}):
        return "OPT_FREQ"
    raise ValueError("Conflicting job keywords: " + ", ".join(sorted(jobs)))


def _method_candidates(words, fields, base, job, multiplicity):
    """Match the writer's method recipes, including methods distinguished by block values."""
    reference = next((name for name in RESPONSE_FUNCTIONALS if name.casefold() in words), None)
    root_count = next((fields[block, "nroots"] for block in ("tddft", "mcrpa", "rocis", "mdci", "casscf")
                       if (block, "nroots") in fields), None)
    candidates = []
    for name, preset in METHODS.items():
        if job not in preset.job_types:
            continue
        state = {}
        if name in ACTIVE_SPACE_METHODS:
            if ("casscf", "nel") not in fields or ("casscf", "norb") not in fields:
                continue
            state.update(active_electrons=int(fields["casscf", "nel"]), active_orbitals=int(fields["casscf", "norb"]))
        if name in EXCITED_STATE_METHODS:
            if root_count is None:
                continue
            state["nroots"] = int(root_count)
        if name in REFERENCE_FUNCTIONAL_METHODS:
            state["reference_functional"] = reference
        if name in ELECTRON_CHANNEL_METHODS:
            state["electron_channel"] = next((s for s in ("alpha", "beta")
                                              if fields.get(("mdci", "do" + s)) == "true"), None)
        spec = CalculationSpec(method=name, job_type=job, **state)
        try:
            keywords, lines = method_input(spec, multiplicity)
        except ValueError:
            continue
        route = set(keywords.casefold().split())
        if not route <= words:
            continue
        template = template_fields(lines)
        if all(fields.get(k) == v for k, v in template.items()):
            # Preserve the selected preset when two controls emit identical native text.
            candidates.append((name == base.method, len(route) + len(template), spec, route, template))
    return sorted(candidates, key=lambda candidate: candidate[:2], reverse=True)


def _solvent(spec, words, fields):
    settings = []
    for word in tuple(words):
        tag, paren, tail = word.partition("(")
        if tag.upper() in MODELS and paren and tail.endswith(")"):
            model, solvent = tag.upper(), tail[:-1]
            if model == "ALPB":
                solvent = {"woctanol": "octanol(wet)", "cs2": "carbon disulfide",
                           "diethylether": "diethyl ether", "ethylacetate": "ethyl acetate"}.get(solvent, solvent)
            settings.append((model, solvent))
            words.remove(word)
    if "cpcm" in words or any(("cpcm", key) in fields for key in ("solvent", "smdsolvent")):
        words.discard("cpcm")
        model = "SMD" if fields.get(("cpcm", "smd")) == "true" else "CPCM"
        if model == "SMD":
            del fields["cpcm", "smd"]
        solvent = fields.pop(("cpcm", "smdsolvent" if model == "SMD" else "solvent"), None)
        settings.append((model, solvent))
    for tag in MODELS:
        if fields.get(("xtb", "do" + tag.lower())) == "true":
            del fields["xtb", "do" + tag.lower()]
            settings.append((tag, fields.pop(("xtb", tag.lower() + "solvent"), None)))
    if len(settings) > 1:
        raise ValueError("Conflicting solvent settings in the input preview")
    return replace(spec, solvation_model=settings[0][0], solvent=settings[0][1]) if settings else spec


def _options(spec, base, words, fields):
    bases = basis_options(spec.method)
    basis = _take(words, bases)
    if bases and basis is None:
        raise ValueError("Missing or unsupported orbital basis in the ! line")
    if words.intersection(("split-ri-j", "nosplit-ri-j")):
        words.discard("ri")  # The writer emits both RI and its splitting mode.
    approx = _take(words, integral_options(spec.method, spec.job_type), "Auto")
    spec = replace(spec, basis=basis or base.basis, integral_approximation=approx,
                   relativity=_take(words, scalar_options(spec.method, basis), "Auto"),
                   integration_grid=_take(words, grid_options(spec.method, approx), "Auto"),
                   dispersion=_take(words, dispersion_options(spec.method), "Auto"),
                   wavefunction=_take(words, reference_options(spec.method, spec.job_type), "Auto"),
                   pno_preset=_take(words, pno_options(spec.method), "Auto"),
                   scf_convergence=_take(words, SCF_CONVERGENCE, "Auto"),
                   frozen_core=_take(words, ("NoFrozenCore",), "Auto"))
    if fields.get(("method", "frozencore")) == "fc_electrons":
        if spec.frozen_core != "Auto":
            raise ValueError("Conflicting frozen-core settings")
        spec = replace(spec, frozen_core="FrozenCore")
        del fields["method", "frozencore"]
    spec = _solvent(spec, words, fields)
    numerical = tuple(BlockOverride(o.block, o.key, parse_option_value(o, fields["freq", o.key.casefold()]))
                      for o in NUMERICAL_FREQUENCY_OPTIONS if ("freq", o.key.casefold()) in fields)
    if numerical:
        spec = replace(spec, block_options=numerical)
    catalog = {(item.block.casefold(), item.key.casefold()): item for item in available_options(spec)}
    overrides = []
    for key, value in tuple(fields.items()):
        option = catalog.get(key)
        if option is not None:
            overrides.append(BlockOverride(option.block, option.key, parse_option_value(option, value)))
            del fields[key]
    spec = replace(spec, block_options=tuple(overrides))
    fits = {}
    for slot, choices in auxiliary_options(spec.method, spec.basis, approx, spec.block_options).items():
        key = ("basis", _SLOTS[slot])
        if key in fields:
            value = fields.pop(key)
            fit = next((v for v in choices if v.casefold() == value), None)
            if fit is None:
                raise ValueError(f"Unsupported %{key[0]} {key[1]} {value}")
        else:
            fit = _take(words, (c for c in choices if c != "AutoAux" and not (slot == "aux_j" and "/JK" in c)))
        fits[slot] = fit
    if fields:
        block, key = next(iter(fields))
        raise ValueError(f"Unsupported preview setting: %{block} {key}")
    if words:
        raise ValueError("Unsupported or conflicting ! keywords: " + " ".join(sorted(words)))
    spec = replace(spec, **fits)
    # Keep implicit selections implicit when the exact same input lines result.
    for attr in ("relativity", *fits):
        default = "Auto" if attr == "relativity" else None
        if getattr(spec, attr) == default or (spec.method == base.method and getattr(base, attr) == getattr(spec, attr)):
            continue
        implicit = replace(spec, **{attr: default})
        if orbital_and_aux_input(implicit) == orbital_and_aux_input(spec):
            spec = implicit
    return spec


def parse_preview(text, molecule, base):
    """Validate the whole draft before returning geometry, its old-row mapping, settings and canonical text."""
    deck = read_deck(text)
    molecule, mapping = edited_geometry(molecule, deck)
    molecule.validate()
    words, fields = set(deck.words), deck.fields.copy()
    pal_word = _take(words, ("PAL" + str(n) for n in (*range(2, 9), 16, 32, 64)))
    cores = fields.pop(("pal", "nprocs"), None)
    if pal_word and cores is not None and int(cores) != int(pal_word[3:]):
        raise ValueError("Conflicting PAL keyword and %pal nprocs")
    common = dict(cores=_resource(cores or (pal_word[3:] if pal_word else CalculationSpec.cores), "nprocs"),
                  maxcore_mb=_resource(fields.pop(("", "maxcore"), CalculationSpec.maxcore_mb), "%maxcore"),
                  input_comments=deck.comments)
    job = _job(words)
    # Most edits change only resources, electronic state, coordinates or whitespace.
    # This also preserves optional and method-specific settings with identical syntax.
    previous = replace(base, **common)
    try:
        previous_text = render_input(molecule, previous)
    except ValueError:
        previous_text = None
    if previous_text is not None:
        original = read_deck(previous_text)
        if set(original.words) == set(deck.words) and original.fields == deck.fields:
            return molecule, mapping, previous, previous_text
    candidates = _method_candidates(words, fields, base, job, molecule.multiplicity)
    error = None
    first_match = None
    for _, _, spec, route, template in candidates:
        try:
            spec = _options(replace(spec, **common), base, words - route,
                            {k: v for k, v in fields.items() if k not in template})
            normalized = render_input(molecule, spec)
            rendered_words = next(line.casefold().split() for line in normalized.splitlines() if line.startswith("!"))
            for keyword in ("freq", "numfreq"):
                if keyword in deck.words and keyword not in rendered_words:
                    raise ValueError(f"The selected settings require {'NumFreq' if keyword == 'freq' else 'Freq'}")
        except ValueError as exc:
            if error is None:
                error = exc
            continue
        result = molecule, mapping, spec, normalized
        if tuple(word for word in rendered_words[1:] if word not in CONTROL_WORDS) == deck.words:
            return result
        if first_match is None:
            first_match = result
    if first_match is not None:
        return first_match
    raise error or ValueError("No supported calculation method matches the ! line and input blocks")
