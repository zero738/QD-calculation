# 如何运行 CP2K smoke tests

## 1. 先生成并验证输入

在仓库根目录执行：

```bash
python interface_thickness_prototype/scripts/build_models.py
python interface_thickness_prototype/scripts/generate_cp2k_inputs.py
python interface_thickness_prototype/scripts/validate_models.py
```

只有 `results/validation.json` 中 `ok: true` 时才继续。

## 2. 统一运行器

运行器按 CdTe bulk → Cu₂Te bulk → B0 → H1 单点 → H1 短优化的固定顺序执行。前一项没有明确 SCF 收敛和正常结束时，后一项会跳过。

原生 Linux CP2K：

```bash
python interface_thickness_prototype/scripts/run_smoke_tests.py \
  --mode native --cp2k-command cp2k.psmp --threads 4
```

Docker（官方固定版本镜像）：

```bash
docker pull cp2k/cp2k:2024.3
python interface_thickness_prototype/scripts/run_smoke_tests.py \
  --mode docker --docker-image cp2k/cp2k:2024.3 --threads 4
```

只运行到较小任务仍保持前置顺序，例如只到 B0：

```bash
python interface_thickness_prototype/scripts/run_smoke_tests.py \
  --mode docker --through 03_b0_slab_sp --threads 4
```

Windows PowerShell 使用同一 Python 脚本即可；Docker Desktop 必须已启动。

## 3. SLURM

先按站点修改 account、partition 和 module/container 命令，然后由用户手动提交：

```bash
sbatch interface_thickness_prototype/smoke_tests/run_smoke_tests.slurm
```

项目不会自动提交远程任务。

## 4. 输出判断

每个已运行任务目录包含：

- `input.inp`：当前生成器给出的完整 CP2K 输入；
- `input.executed.inp`：真实运行前冻结的输入快照，并在 metadata 中记录 SHA-256；
- `output.out`：完整 CP2K 输出；
- `run_metadata.json`：版本、脱敏后的执行命令、线程、耗时和退出码；
- `output.parsed.json`：严格解析结果。

只有以下条件同时成立，单点任务才标记 `program_completed=true`：

1. 确实存在运行记录；
2. 输出出现 `PROGRAM ENDED AT`；
3. 输出出现明确 `SCF run converged in ... steps`；
4. 没有 SCF 未收敛或 CP2K abort 标志；
5. 找到总 FORCE_EVAL 能量。

短几何优化还必须出现 `GEOMETRY OPTIMIZATION COMPLETED` 才算几何收敛。最多 5 步未收敛并不奇怪，解析器会如实标记失败，但仍保留运行证据。

## 5. 计算数据位置

CP2K 容器内置官方数据目录。输入使用：

| 元素 | 基组 | 赝势 |
|---|---|---|
| Cu | DZVP-MOLOPT-SR-GTH-q11 | GTH-PBE-q11 |
| Cd | DZVP-MOLOPT-SR-GTH-q12 | GTH-PBE-q12 |
| Te | DZVP-MOLOPT-SR-GTH-q6 | GTH-PBE-q6 |

如果站点 CP2K 找不到 `BASIS_MOLOPT` 或 `GTH_POTENTIALS`，设置站点的 `CP2K_DATA_DIR`，或把输入中的数据文件名改为管理员提供的绝对路径。不要改动 q 值配对。

这些设置只为跑通首次计算，未完成基组、cutoff、k 点、展宽或 slab 收敛测试。
