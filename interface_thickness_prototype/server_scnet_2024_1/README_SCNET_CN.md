# SCNet 华东一区昆山一键运行说明（CP2K 2024.1）

本包用于 `kshctest02` 分区，上传建议目录：

```text
~/QD-calculation/interface_thickness_prototype/server_scnet_2024_1
```

服务器目录及文件名全部使用 ASCII、无空格。要求中的中文 README 文件名与该约束冲突，因此采用 `README_SCNET_CN.md`，正文为中文。

## 最小用户操作

```bash
cd ~/QD-calculation/interface_thickness_prototype/server_scnet_2024_1
sha256sum -c upload_manifest.txt
bash submit_pipeline.sh
bash monitor_pipeline.sh
```

完成后下载：

```text
scnet_results_bundle.tar.gz
```

`submit_pipeline.sh` 只在登录节点调用 `sbatch` 建立依赖，不在登录节点运行 CP2K。任何 `.slurm` 计算脚本都不会再次调用 `sbatch`。用户不需要逐项提交，也不需要修改 CP2K 输入。不要把账号、密码或 Token 写入脚本。

## 依赖流水线

```text
environment + CP2K 2024.1 --check (8 inputs)
  -> bulk Gamma -> 2x2x2 -> 3x3x3 -> 4x4x4
  -> B0 -> C50 -> H1 -> H2
```

主链均为 `afterok`。环境作业会用服务器真实
`/public/software/apps/cp2k/2024.1/exe/local/cp2k.popt --check`
检查 8 份输入；任一失败，后续大任务不会启动。

H1 在同一个 16 核、16 小时作业内最多运行两次：

- `attempt_A`：`ADDED_MOS=100`、`NLUMO=100`、`ALPHA=0.08`、`NBROYDEN=12`，内部硬上限 7 小时；
- 只有持续最高 MO 占据警告时，`attempt_B` 改为 `ADDED_MOS/NLUMO=160`；
- 只有没有持续最高 MO 警告但残差振荡时，`attempt_B` 改为 `ALPHA=0.05`、`NBROYDEN=16`；
- 语法、基组、赝势、MPI、动态库、哈希或 CP2K ABORT 等硬配置错误不重试；
- `EPS_SCF` 始终为 `1e-6`，不使用 OT，不改变结构、晶胞、真空、电荷或多重度。

只有 H1 返回码、正常结束、SCF、能量、CP2K 2024.1、哈希、最高 MO 警告、DOS/PDOS/LDOS、两类 cube、MO 列表和谱积分全部通过，才生成 `H1_SUCCESS.flag/json`。H2 会重新验证 H1，并动态继承实际成功 attempt 的 SCF signature；H1 失败时 H2 自动阻断。失败证据仍由独立 finalizer 整理，不会伪装成功。

## 环境和资源

脚本禁止加载损坏的 `apps/cp2k/2024.1/intel2021` module，使用：

```bash
module purge >/dev/null 2>&1 || true
module load compiler/gnu/9.3.0
module load compiler/intel/2021.3.0
module load mpi/intelmpi/2021.3.0
```

CP2K：`/public/software/apps/cp2k/2024.1/exe/local/cp2k.popt`；数据目录：`/public/software/apps/cp2k/2024.1/data`；启动方式：`srun --mpi=pmix_v3`。全部单节点、无 `--exclusive`，线程库均固定为 1。资源预算由 `pipeline_state.py` 直接解析 Slurm 文件复算，不能只相信配置文件手写总数；当前硬上限约 1102.17 CPU·h，小于 1800 CPU·h。

## 输出目录修复

每个普通任务都在 `runs/<task_id>/` 内 `cd` 后，用相对路径运行：

```bash
srun --mpi=pmix_v3 cp2k.popt -i input.executed.inp -o output.out
```

因此 DOS、PDOS、LDOS、cube、WFN、restart 不会落到包根目录，也不会被其他任务覆盖。H1 使用互相隔离的 `runs/H1/attempt_A` 和 `attempt_B`。

## 监控与取消

`bash monitor_pipeline.sh` 显示 `squeue`、`sacct`、任务依赖、H1 两次尝试、门控和结果路径。

`bash cancel_pipeline.sh` 只读取当前 `pipeline_jobs.json` 中的 job ID，打印后要求输入 `CANCEL_CURRENT_PIPELINE`，不会取消用户其他作业，也不会删除证据。

## 科学边界

- 服务器初始 8 个计算任务均为 `not_run`，能量为空；本地 CP2K 2024.3 的 8/8 `--check` 只是语法预检，不能替代服务器 2024.1 检查。
- 旧 CP2K 2024.3 B0/C50 是 `historical_prototype_evidence`；旧 C50 `-0.662188 eV/Å²` 继续为 `not_ready_for_paper`。
- 能量称为“固定几何、统一 500 K 电子展宽下的能量代理”；覆盖能只能称“固定初始几何相对覆盖形成能”，不是绝对表面能。
- Cu2Te bulk 必须满足 3x3x3 到 4x4x4 差值小于 `0.01 eV/Cu2Te formula unit`，否则形成能为空，只提示以后可能需要 5x5x5。
- CP2K `total_dos.dat` 只称归一化直方图谱形，不是 raw total DOS 或 states/eV。外部 KS 谱来自唯一 kind-PDOS MO 列表、0.10 eV FWHM、无自旋简并乘数。
- 原始 CP2K Fermi energy 不跨模型比较；只在可靠时给出 CdTe 内部参考势对齐的相对费米能级代理。
- 顶部/底部真空平台各自不满足密度、宽度、标准差和斜率门槛时，功函数字段保持空白。
- CdTe(111) 为极性薄片且几何未弛豫；C50 是周期性条带，不代表全部 50% 岛状形貌。
- DFT 指标只是界面电荷输运、能级匹配和接触势垒变化的理论代理；真实接触电阻仍需实验 TLM、串联电阻或其他电学测试。
- H1/H2 只能称较薄与较厚模型对比，不能称连续厚度函数、最佳膜厚或最佳浓度。

## 结果包

`collect_results.sh` 或 finalizer 会生成 CSV、JSON、Markdown、可用时的图片，以及 `scnet_results_bundle.tar.gz`。默认 tar 包不包含 WFN、restart、Hartree cube 和 density cube，也不会删除它们；这些大文件记录在 `large_optional_files_manifest.txt`，包含绝对/相对路径、大小、SHA256、任务和 attempt。服务器没有 matplotlib 时，核心 CSV/JSON/Markdown 仍完成，图片状态为 `pending_local_plot`，可在本地运行 `python plot_results.py`。
