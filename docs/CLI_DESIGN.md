# Molecular design from the command line

Run `orcaview design INPUT` to print the editable geometry, ordered atoms, bonds, charge, multiplicity, 2D sketch, diagnostic messages and available geometry revisions as JSON. The input can be a supported structure, calculation result or OrcaView project. Pass `--finite` to choose the finite representation of a periodic input. These operations run without a display server or Qt. The desktop distribution includes the Open Babel backend used for force-field optimization, sketch layout and bond-order perception.

For example, this command moves the second atom and measures its new distance to the first atom. Coordinates and lengths are in ångströms.

```sh
orcaview design examples/water.xyz \
  --apply '{"op":"set-bond-length","atom_ids":[1,2],"target":1.02}' \
  --apply '{"op":"measure","atom_ids":[1,2]}' \
  -o water-edited.oview.json
```

Use `--apply` repeatedly for short batches. For longer jobs, pass `--script edits.json`, or pipe a JSON array to `--script -`. OrcaView runs the operations in order and prints one JSON report. The `operations` array contains each result and its snapshot ID. Use `-o` to save a project after all steps succeed. Omitting `-o` leaves results on standard output. A failed edit or project validation returns an error and preserves an existing output file.

```sh
orcaview design water-edited.oview.json --script - <<'JSON'
[
  {"op":"select","atom_ids":[2,1,3]},
  {"op":"measure","kind":"angle"},
  {"op":"symmetry"},
  {"op":"diagnostics"}
]
JSON
```

Each atom reference may be an integer row number **starting at 1** in the current step, or the atom's stable ID as a JSON string. A structural edit can change row numbers. Stored projects retain atom IDs between invocations. Separate imports of a raw structure create separate documents. The report lists each atom's `row` and `id`, and each edit reports newly added atom IDs.

## Operations

In the desktop Design workspace, choose **Protein…** or **DNA…**, enter a PDB ID or a sequence, and click **Generate structure**. A PDB ID retrieves the first deposited model from RCSB and keeps the selected polymer type. The coordinates retain deposited hydrogens where present. Check the total charge and spin multiplicity before using deposited coordinates in a calculation. Unspecified atomic charges default to zero and the initial multiplicity is the lowest compatible with that electron count.

A plain sequence or a single FASTA record builds a starting geometry offline. Protein accepts the 20 standard one-letter amino acid codes and builds an idealized helical peptide. DNA accepts A, C, G and T in 5′ to 3′ order and builds the antiparallel complementary strand. **Undo** restores the previous structure. [PDB coordinate files](https://www.rcsb.org/docs/programmatic-access/file-download-services) · [Open Babel FASTA reader](https://openbabel.org/docs/FileFormats/FASTA_format.html)

The 2D sketch traces the N–Cα–C backbone of each peptide and the sugar–phosphate backbone of each DNA strand with smooth curves. Each chain has its own color. In a projection of a 3D structure, the nearer strand appears darker and wider at crossings. An independently edited 2D layout keeps its atom positions. Ligands retain their usual atom-and-bond drawing. Selecting a backbone atom and copying its molecule includes the side chains or bases. The 3D preview and ORCA input use all atoms. A 2D image exported from Design or with `render --view 2d` uses the same backbone drawing.

For a protein or DNA structure, point at a region in either Design view and scroll to zoom up to 8× its fitted size. **Fit sketch** fits the left-hand drawing again. **Reset view** restores the 3D view.

In the desktop Design workspace, select an atom of the molecule you want to position. Hold Alt (Option on macOS) and drag with the left mouse button to rotate the molecule about its center, or with the right button to translate it. In 3D, translation follows the screen plane. In the sketch, both operations act in XY. Release to commit the edit or press Esc to cancel.

With the molecule selected, press Ctrl+C and Ctrl+V (⌘C and ⌘V on macOS) to place a separate copy. The pasted atoms are selected together, ready to rotate or translate. An intermolecular hydrogen bond leaves the two partners independently selectable.

To mark a hydrogen bond, choose **Hydrogen bond** from the single-bond menu and click the explicit hydrogen and its acceptor. **Optimize H-bonds…** in the 3D preview relaxes participating molecules together using MMFF94 or UFF. Set the target H···A distance and D–H···A angle for the marked contacts. The default starting targets are 1.90 Å and 170°. Choose targets appropriate for your complex. Other molecules and the 2D sketch keep their positions.

The tables show the fields that accompany `op`. An atom object has the fields `element`, `x`, `y` and `z`, for example `{"element":"O","x":1.4,"y":0,"z":0}`. Element symbols are case-sensitive.

| Operation | Fields and behavior |
| --- | --- |
| `select` | An ordered `atom_ids` array. Use `[]` to clear the selection. |
| `measure` | `atom_ids` in measurement order, with `kind` of `distance` (default), `angle` or `dihedral`. Angles and signed dihedrals use degrees. |
| `symmetry` | Optional positive `tolerance` in ångströms (default 0.05). Returns the estimated geometric point group and principal axis. |
| `diagnostics` | Reports electronic-state and bonding issues for the current structure. |
| `add-atoms` | An `atoms` array of new atom objects. |
| `attach-atom` | `anchor_id`, new `atom`, bond `order`, optional `style`. |
| `replace-element` | `atom_id` and `element`. Preserves the atom ID. |
| `move-atom` | `atom_id`, `x`, `y`, `z`. Sets the Cartesian coordinates. |
| `translate-fragment` | `atom_id`, `dx`, `dy`, `dz` in ångströms. Moves the entire bonded component of that atom with fixed connectivity. For a translation in the XY plane, set `move_sketch` to `true` to move the component in an independent 2D layout as well. |
| `rotate-fragment` | `atom_id`, unit `axis` as `[x,y,z]` in Cartesian coordinates, and signed `degrees`. The pivot is the component's centroid. Set `move_sketch` to `true` for a rotation around the Z axis that also rotates the 2D drawing. |
| `move-sketch-atom` | `atom_id`, `x`, `y`. Edits the 2D depiction independently. |
| `set-sketch-layout` | `xy` as an array of all `[x,y]` pairs in the current atom order. |
| `delete-atoms` | `atom_ids` to delete. An empty design can be saved as a project draft. |
| `reorder-atoms` | `atom_ids` listing every current atom once in its new order. |
| `set-bond` | Ordered `atom_a`, `atom_b`, `order` (0 removes, 1–3 sets), optional `style`. For directional bonds the first atom is the donor or narrow end. |
| `set-bond-length` | `atom_ids` ordered as fixed end, moving end, and positive `target`. For an acyclic bond the entire moving side translates rigidly. Reverse the endpoints to move the other side. |
| `set-distance` | `atom_ids` ordered as fixed end, moving end, positive `target`, explicit `moving_atom_ids` and optional `fixed_atom_ids`. |
| `insert-ring` | Set `size` to 3–12 for a carbon ring, or set `benzene` to true with size 6. For a heterocycle, set the matching size and use `heterocycle` with `pyrrole`, `furan`, `thiophene`, `imidazole`, `pyrazole`, `pyridine`, `pyrimidine` or `pyrazine`. Set `plane` to `XY`, `XZ` or `YZ` and supply either `anchor_id` or a `center` given as `[x,y,z]`. |
| `add-hydrogen` | `anchor_id` for a single explicit bonded hydrogen. |
| `add-hydrogens` | Fill missing hydrogens for a supported neutral singlet. |
| `clean-2d` | Tidy the 2D sketch. Preserves the physical coordinates. |
| `optimize-3d` | Pre-optimize the geometry with Open Babel MMFF94 or UFF and report the force field used. Requires a bonded neutral singlet. |
| `optimize-hbonds` | Restrain all explicit `hydrogen_bond` contacts during force-field pre-optimization of a neutral singlet. Optional `distance` (H···A, Å) and `angle` (D–H···A, degrees) default to 1.90 and 170. Each H needs a covalently bonded donor. |
| `set-electronic-state` | Integer `charge` and positive integer `multiplicity`. Project saving checks the final state. |
| `undo`, `redo` | Undo or redo an edit made within this invocation. |
| `use-geometry` | `snapshot` as a revision number or a snapshot ID string selected from `history`. Adopt a saved revision or result frame as an undoable edit. |

For `delete-atoms`, `measure`, `set-distance` and `set-bond-length`, omitting `atom_ids` uses the current selection. The design report follows the editor's stored or default inferred connectivity and records the source in `bond_source`. The visual cutoff and color scheme are display preferences.

Available bond styles by order:

| Order | Style |
| --- | --- |
| 1 | `plain`, `hydrogen_bond` (noncovalent H···A contact), `coordinate`, `coordinate_arrow`, `wedge`, `hashed_wedge`, `hollow_wedge`, `wavy`, `bold`, `hashed`, `wavy_wedge` |
| 2 | `plain`, `aromatic`, `crossed`, `bold`, `dashed` |
| 3 | `plain`, `partial_triple` |
