# 国家超算互联网运行说明（CP2K 2024.1）

本目录只用于国家超算互联网华东一区昆山、分区 `kshctest02`。服务器建议路径为：

```text
~/QD-calculation/interface_thickness_prototype/server_scnet_2024_1
```

所有服务器文件名和相对路径均为 ASCII 且不含空格。附件同时要求中文 README 文件名和“所有路径无中文”，两者冲突，因此本文件采用服务器安全名称 `README_SCNET_CN.md`，正文仍为中文。

## 1. 科学状态

- 本包中的服务器任务尚未运行；`runs/` 和 `results/` 初始状态只会显示 `not_run`。
- 旧 CP2K 2024.3 B0/C50 是历史原型和管线证据，不是 CP2K 2024.1 论文基线。
- 旧 C50 `-0.662188 eV/Å²` 不得进入论文结论；统一版本重跑和 Cu₂Te 体相 k 点检查完成前，覆盖形成能状态为 `not_ready_for_paper`。
- 功函数没有可靠连续真空平台时必须为空；`E−EF` 只能比较相对谱形。
- 普通 DFT 不直接给出真实接触电阻，也不能据此确定最佳膜厚、浓度或器件效率。
- C50 是沿 B 方向连续、沿 A 方向周期重复的半面积条带，不代表所有 50% 岛状形貌。

## 2. 环境与上传检查

不要加载有缺陷的 `apps/cp2k/2024.1/intel2021` 模块，也不要在登录节点直接运行 CP2K。先在本地确认上传完整；服务器进入本目录后运行：

```bash
sha256sum -c upload_manifest.txt
sbatch scripts/00_check_environment.slurm
```

环境作业应确认：分区为 `kshctest02`、单节点、`cp2k.popt` 显示 CP2K 2024.1、数据目录存在、动态库无缺失，并可找到 `python3`。环境脚本手动加载 GNU 9.3.0、Intel 2021.3.0 和 Intel MPI 2021.3.0，不加载 CP2K 模块。

## 3. 手动运行顺序

本包不含任何自动 `sbatch` 或自动依赖提交命令。每一步完成后运行 `./collect_results.sh` 并检查 CSV，再手动提交下一步。

```bash
sbatch scripts/01_cu2te_bulk_gamma.slurm
sbatch scripts/02_cu2te_bulk_k222.slurm
sbatch scripts/03_cu2te_bulk_k333.slurm
sbatch scripts/04_cu2te_bulk_k444.slurm
./collect_results.sh

sbatch scripts/10_B0.slurm
./collect_results.sh
sbatch scripts/20_C50.slurm
./collect_results.sh
sbatch scripts/30_H1.slurm
./collect_results.sh
```

只有以下命令返回 0，才允许手动提交 H2：

```bash
python3 verify_server_outputs.py --gate-h2
sbatch scripts/40_H2.slurm
```

`40_H2.slurm` 在执行 `srun` 前还会再次运行同一门控。不要同时提交 H1 和 H2。

## 4. H1 最小修正与严格成功条件

H1 不改变结构、晶胞、真空、终止、电荷、多重度、PBE、基组/赝势、400/60 Ry、Gamma、标准对角化、500 K 展宽或 `EPS_SCF=1e-6`。只修改：

- `ADDED_MOS=100`；
- `PDOS NLUMO=100`；
- `MIXING ALPHA=0.08`；
- `NBROYDEN=12`；
- `MAX_SCF=250`。

H1 只有在返回码 0、CP2K 正常结束、SCF 明确收敛、有总能量、最高 MO 占据警告不再持续、DOS/PDOS/LDOS/cube 完整、MO 列表一致且谱积分检查通过时才算严格成功。不能把超时、部分输出或单纯出现能量行当作成功。

H2 使用与成功 H1 相同的 SCF 参数。门控还会比较 H1 实际执行输入和 H2 输入的关键 SCF 参数；若 H1 后续受控修改过而 H2 未同步，门控会拒绝运行。

## 5. 资源上限

| 任务 | MPI tasks | 时间上限 | 最大核时 |
|---|---:|---:|---:|
| 环境检查 | 1 | 00:10 | 0.17 |
| 4个 Cu₂Te bulk 任务合计 | 4/任务 | 3 h合计 | 12 |
| B0 | 16 | 06:00 | 96 |
| C50 | 16 | 10:00 | 160 |
| H1 | 16 | 12:00 | 192 |
| H2 | 24 | 24:00 | 576 |

全部作业的硬上限合计约 `1036.17 CPU·h`，低于 2000 核时免费额度。H2 选择 24 MPI tasks，是因为它有 270 个原子、明显大于 H1 的 174 个原子，同时保留 8 个节点核心和内存余量；仍为单节点。表中是最坏请求上限，不是实际消耗预测。

## 6. 结果文件

每个任务写入独立目录 `runs/<task_id>/`，不会覆盖 `research_lite/runs/`。至少保留：

- `input.executed.inp`：真实执行输入；
- `output.out`：CP2K 原始输出；
- `environment.txt`：日期、主机、作业号、分区、模块、版本、SHA256、Git提交、ulimit和内存；
- `run_metadata.tsv`：返回码、墙钟时间、任务数和输入哈希；
- WFN/restart、DOS/PDOS/LDOS和cube（任务要求时）。

`collect_results.sh` 生成：

- `results/server_task_status.csv`；
- `results/bulk_kpoint_convergence.csv`；
- `results/server_coverage_metrics.csv`；
- `results/server_verification.json`。

Cu₂Te k 点初筛只有当相邻网格差值小于 `0.01 eV/Cu₂Te formula unit` 才标记通过。若 3×3×3 到 4×4×4 仍未通过，只记录“以后需要 5×5×5”；本包不会自动生成或提交 5×5×5。

覆盖曲率代理定义为 `E(H1)+E(B0)-2E(C50)`。只有 B0、C50、H1 均为 CP2K 2024.1、同一主要物理参数且严格成功时才输出；该组合抵消 Cu₂Te 体相化学势，但仍只是固定初始几何、周期性条带构型的代理。

## 7. 失败处理

- `return_code != 0`：先看 Slurm `.err` 和 `output.out`，不能填写能量结论。
- 缺少正常结束或 SCF 收敛标记：计算失败。
- H1 仍持续出现最高 MO 占据警告：不要启动 H2；保留整个 H1 目录后再讨论受控修正。
- 作业被调度器杀死但 `run_metadata.tsv` 未写完：验证器会判失败，不能自行猜测是 OOM 或人为停止。
- 真空平台不可靠：功函数字段必须保持空白，不放宽阈值强行取值。
