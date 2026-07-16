# Ordered CP2K smoke tests

`manifest.json` is the machine-readable execution order. Run the ladder through `../scripts/run_smoke_tests.py`; do not launch a later directory before its prerequisite passed strict parsing.

The two bulk jobs use `PERIODIC XYZ`. B0/H1 slab jobs use `PERIODIC XY` in both CELL and POISSON with the ANALYTIC solver. H1 geometry optimization is capped at five steps and is not a production relaxation.
