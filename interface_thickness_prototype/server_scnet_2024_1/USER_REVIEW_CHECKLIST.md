# User review checklist

1. `results/server_cp2k_2024_1_input_checks.json`: all eight checks must pass before any dependent job starts.
2. `pipeline_jobs.json`: verify the afterok chain and the two afterany finalizers.
3. `runs/H1/H1_SUCCESS.json`: absent means H2 must stay blocked; at most attempt_A and attempt_B may exist.
4. `results/final_model_status.csv`: missing/failed tasks must have blank energies.
5. `results/bulk_kpoint_convergence.csv`: only a <0.01 eV/formula-unit 3×3×3→4×4×4 delta permits the current bulk reference.
6. `results/relative_fermi_alignment.csv` and `results/work_function_status.csv`: unreliable fields must be blank, not zero.
7. `large_optional_files_manifest.txt`: cubes/WFN/restarts stay on the server and are not placed in the default tar bundle.

Static checks cannot prove that H1 or H2 will converge, that the prototype phase is the experimental phase, or that any proxy predicts real contact resistance or optimal thickness.
