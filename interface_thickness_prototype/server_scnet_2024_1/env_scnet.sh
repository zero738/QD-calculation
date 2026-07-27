#!/bin/bash

# SCNet East China 1 (Kunshan), partition kshctest02.
# Source this file from a Slurm allocation; do not run CP2K on a login node.

SCNET_CP2K_EXE=/public/software/apps/cp2k/2024.1/exe/local/cp2k.popt
SCNET_CP2K_DATA_DIR=/public/software/apps/cp2k/2024.1/data

scnet_activate_environment() {
    module purge >/dev/null 2>&1 || true
    module load compiler/gnu/9.3.0
    module load compiler/intel/2021.3.0
    module load mpi/intelmpi/2021.3.0

    export CP2K_DATA_DIR="$SCNET_CP2K_DATA_DIR"
    export PATH=/public/software/apps/cp2k/2024.1/exe/local:"${PATH}"
    export LD_LIBRARY_PATH=/public/software/apps/cp2k/2024.1/lib:"${LD_LIBRARY_PATH:-}"
    export OMP_NUM_THREADS=1
    export MKL_NUM_THREADS=1
    export OPENBLAS_NUM_THREADS=1

    if [[ ! -x "$SCNET_CP2K_EXE" ]]; then
        echo "ERROR: CP2K executable is not available: $SCNET_CP2K_EXE" >&2
        return 2
    fi
    if [[ ! -d "$SCNET_CP2K_DATA_DIR" ]]; then
        echo "ERROR: CP2K data directory is not available: $SCNET_CP2K_DATA_DIR" >&2
        return 2
    fi
}

scnet_prepare_run() {
    local package_root="$1"
    local task_id="$2"
    local input_source="$3"
    local run_dir="$package_root/runs/$task_id"

    if [[ -e "$run_dir/output.out" || -e "$run_dir/run_metadata.tsv" ]]; then
        echo "ERROR: refusing to overwrite existing evidence in $run_dir" >&2
        echo "Archive the whole directory before a controlled rerun." >&2
        return 3
    fi
    mkdir -p "$run_dir"
    cp "$input_source" "$run_dir/input.executed.inp"
    local structure_source
    structure_source="$(dirname "$input_source")/structure.extxyz"
    if [[ -f "$structure_source" ]]; then
        cp "$structure_source" "$run_dir/structure.extxyz"
    fi
    printf '%s\n' "$run_dir"
}

scnet_record_environment() {
    local package_root="$1"
    local input_file="$2"
    local run_dir="$3"
    {
        echo "recorded_at=$(date --iso-8601=seconds)"
        echo "hostname=$(hostname)"
        echo "job_id=${SLURM_JOB_ID:-not_in_slurm}"
        echo "partition=${SLURM_JOB_PARTITION:-unknown}"
        echo "ntasks=${SLURM_NTASKS:-unknown}"
        echo "cpus_per_task=${SLURM_CPUS_PER_TASK:-unknown}"
        echo "cp2k_executable=$SCNET_CP2K_EXE"
        echo "cp2k_data_dir=$SCNET_CP2K_DATA_DIR"
        echo "input_sha256=$(sha256sum "$input_file" | awk '{print $1}')"
        echo "git_commit=$(git -C "$package_root/../.." rev-parse HEAD 2>/dev/null || echo unavailable)"
        echo "cp2k_version_begin"
        "$SCNET_CP2K_EXE" --version
        echo "cp2k_version_end"
        echo "module_list_begin"
        module list 2>&1 || true
        echo "module_list_end"
        echo "ulimit_begin"
        ulimit -a
        echo "ulimit_end"
        echo "memory_begin"
        grep -E 'MemTotal|MemAvailable' /proc/meminfo || true
        free -h || true
        echo "memory_end"
    } > "$run_dir/environment.txt"
}

scnet_write_metadata() {
    local run_dir="$1"
    local task_id="$2"
    local input_file="$3"
    local started_at="$4"
    local finished_at="$5"
    local wall_seconds="$6"
    local return_code="$7"
    local expected_electronic_outputs="$8"
    local kpoint_mesh="$9"

    {
        printf 'task_id\t%s\n' "$task_id"
        printf 'started_at\t%s\n' "$started_at"
        printf 'finished_at\t%s\n' "$finished_at"
        printf 'wall_time_seconds\t%s\n' "$wall_seconds"
        printf 'return_code\t%s\n' "$return_code"
        printf 'slurm_job_id\t%s\n' "${SLURM_JOB_ID:-not_in_slurm}"
        printf 'partition\t%s\n' "${SLURM_JOB_PARTITION:-unknown}"
        printf 'ntasks\t%s\n' "${SLURM_NTASKS:-unknown}"
        printf 'cp2k_executable\t%s\n' "$SCNET_CP2K_EXE"
        printf 'input_sha256\t%s\n' "$(sha256sum "$input_file" | awk '{print $1}')"
        printf 'expected_electronic_outputs\t%s\n' "$expected_electronic_outputs"
        printf 'kpoint_mesh\t%s\n' "$kpoint_mesh"
    } > "$run_dir/run_metadata.tsv"
}

# Run with the task directory as the process working directory.  CP2K writes
# DOS/PDOS/LDOS/cubes/WFN/restart relative to cwd, so absolute -i/-o paths are
# not a substitute for this cd.
scnet_run_cp2k() {
    local run_dir="$1"
    (
        cd "$run_dir"
        srun --mpi=pmix_v3 "$SCNET_CP2K_EXE" -i input.executed.inp -o output.out
    )
}
