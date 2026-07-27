# SCNet server run report

SCNet CP2K 2024.1 tasks actually represented by evidence: **0/8**. Strict successes: **0/8**.

| Task | Status | Strict success | Energy (Ha) |
|---|---|---:|---:|
| cu2te_bulk_gamma | not_run | False |  |
| cu2te_bulk_k222 | not_run | False |  |
| cu2te_bulk_k333 | not_run | False |  |
| cu2te_bulk_k444 | not_run | False |  |
| B0 | not_run | False |  |
| C50 | not_run | False |  |
| H1 | not_run | False |  |
| H2 | not_run | False |  |

## Interpretation boundary

- Energies are fixed-geometry proxies under the unified 500 K electronic smearing setup; they are not silently described as strict 0 K energies.
- Work function fields remain blank unless both top/bottom platform tests independently satisfy the documented density, width, standard-deviation and slope gates.
- `EF_minus_CdTe_reference_potential_ev` is a CdTe-internal-reference aligned relative Fermi-level proxy, not an absolute Fermi energy.
- The electronic indicators are theoretical proxies for interface charge transport, energy-level matching and contact-barrier changes. Real contact resistance still requires experimental TLM, series-resistance or other electrical measurements.
- H1/H2 provide only a thinner-versus-thicker comparison, not a continuous thickness function, optimal film thickness or optimal concentration.
- CdTe(111) is polar and all interface structures are fixed initial geometries.

Paper-ready gate: `False`. Missing values are not replaced by zero.
