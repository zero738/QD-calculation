# Paper results boundary

This package does not make a paper-ready claim by itself. Old CP2K 2024.3 B0/C50 values are `historical_prototype_evidence`; the old C50 value -0.662188 eV/Å² remains `not_ready_for_paper`.

The only permitted coverage-energy name is **fixed-initial-geometry relative coverage formation energy**. It is not an absolute surface energy. It remains blank until CP2K 2024.1 B0/model strict success and the 3×3×3→4×4×4 Cu2Te bulk threshold are both satisfied. C50 is one periodic stripe morphology, not every 50% island morphology.

Raw CP2K Fermi energies are never compared directly across models. CP2K `total_dos.dat` is only a normalized histogram spectral-shape fraction, not raw total DOS or states/eV. No theoretical contact resistance in Ω·cm² is produced.
