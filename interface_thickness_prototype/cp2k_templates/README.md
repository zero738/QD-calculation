# CP2K template policy

Inputs are generated from validated coordinates by `scripts/generate_cp2k_inputs.py`.
The generator uses `PERIODIC XY` in both `CELL` and `POISSON`, the 2D-compatible
`ANALYTIC` solver, PBE/GTH, a common UCL TZVP-MOLOPT-SR basis family, Gamma-only
sampling, and Fermi-Dirac smearing. These are prototype settings, not converged
production settings.
