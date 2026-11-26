# Results and spectra from the command line

Use `orcaview results FILE` for a JSON inventory of geometry revisions, frames, datasets, property series and spectrum tables. The input may be an OrcaView project, an ORCA output or a supported structure file. Source line numbers and entry numbers start at one. Entry numbers work across repeated imports of the same log. Projects also retain the stable geometry and dataset IDs.

```sh
orcaview results Examples/water-sp.out
orcaview results Examples/water-sp.out --dataset mulliken-charge --format csv -o charges.csv
orcaview results Examples/hydroxyl-populations.out --dataset mulliken-spin --format csv -o spin.csv
orcaview results Examples/hydroxyl-populations.out --dataset mbis-electrons --format csv -o populations.csv
orcaview render Examples/hydroxyl-populations.out spin.png --population mulliken-spin --population-scale bwr --population-symmetric --labels --rotate y:75
orcaview results Examples/water-sp.out --property "Final single-point energy" --format tsv
orcaview results work.oview.json --geometry 2 --format csv -o frame.csv
orcaview results work.oview.json --evidence -o sources.json
orcaview results work.oview.json --all -o full-results.json
```

Select a geometry by its entry number, snapshot ID or frame ID. Select a dataset by number, persisted ID or unique kind. A per-atom CSV uses the coordinates and stable atom identities of the dataset's own frame. The status column distinguishes missing values, atoms outside its axis, and externally stored values. JSON retains shape, axis identities, units, quality notes, source records and the external array reference. The raw log remains separate from geometry-bound results. Use `--properties` for every parsed observation with its context, unit and original line, or select an individual series with `--property`.

## Spectra

Running `orcaview spectrum FILE` lists the available tables, including their kind, title, row count and source line. Use their entry numbers if a log contains multiple tables of the same kind. The table number is optional for a file with a single spectrum when an explicit format is selected.

```sh
orcaview spectrum Examples/water-raman.out
orcaview spectrum Examples/water-raman.out --table ir --format table -o ir-lines.csv
orcaview spectrum Examples/water-nmr.out --table 1 -o nmr.csv
orcaview spectrum Examples/water-nmr.out --table 1 --element H -o h-shielding.png
orcaview spectrum Examples/water-nmr.out --table 1 --element H --reference-ppm 32.115 --format sticks -o h-shifts.csv
orcaview spectrum Examples/water-nmr.out --table 2 -o hh-coupling.png
orcaview spectrum Examples/peroxide-uv-cd.out --table 1 --format sticks --unit eV -o sticks.csv
orcaview spectrum Examples/water-raman.out --table ir --format curve --fwhm 18 --normalize -o ir-curve.csv
orcaview spectrum Examples/water-raman.out --table ir --format png --shape pseudo-voigt \
  --mix 0.4 --range 1300 3900 --layers both --color '#214477' --stroke-width 2.5 -o ir.png
```

| Format | Output |
| --- | --- |
| `table` | All printed table columns and rows as CSV. Supports frequency lists, NMR shieldings and couplings as well as IR, Raman and optical spectra. |
| `sticks` | Positions and signed strengths as CSV. For NMR shielding, the second column counts nuclei at each position. |
| `curve` | Sampled and broadened curve as CSV. |
| `png` | The desktop spectrum figure, drawn offscreen at 1800 × 1100 pixels. A filename ending in `.png` also selects this format. |

IR, Raman, UV–visible, CD and NMR shielding tables support sticks, curves and PNG. Optical axes accept `nm`, `eV` or `cm-1`. The vibrational unit is `cm-1`. FWHM uses the active axis unit. Adjust the shape with `--shape gaussian|lorentzian|pseudo-voigt`, the pseudo-Voigt Lorentzian fraction with `--mix 0…1`, and the sampling grid with `--points`. Narrow peaks gain extra local samples where needed. `--normalize` scales the curve by the largest absolute value in the selected range.

NMR plots show one element at a time. The default is H when present. Each printed site contributes one count, summed at identical positions. By default the figure shows absolute shielding σ in ppm with 0.05 ppm Lorentzian broadening. Supply `--reference-ppm` to plot δ = σref − σ on a decreasing axis. Use a reference for the same element and calculation method. The 32.115 ppm example uses TMS calculated with HF/def2-SVP. The curve represents uncoupled sites. A J table exports directly to a signed chart in Hz with `--format png` or to the original pairs with `--format table`. [ORCA NMR manual](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/nmr.html)

The PNG accepts `--layers both|curve|sticks`, `--grid` or `--no-grid`, `--reverse` or `--no-reverse`, `--color '#RRGGBB'` and `--stroke-width` from 0.5 to 6. The direction defaults to decreasing wavenumber for IR. The raw stick CSV retains the printed intensities with every appearance setting.

JSON and CSV/TSV commands run without Qt. PNG export requires the optional Qt offscreen renderer. Successful file exports are quiet. Commands report invalid input or a failed export on standard error with a nonzero exit status.
