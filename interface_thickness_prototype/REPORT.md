# CdTe/Cu₂Te 最小可运行核心报告

日期：2026-07-17
状态：B0/H1/H2 完整重复单元模型、CP2K 输入、顺序运行器和严格解析已完成；两个小体相单点已在 CP2K 2024.3 中真实收敛。

> **醒目警告：CdTe(111) slab 很薄而且有极性。当前 B0/H1/H2 只用于运行与结构管线测试。不得用这些模型的能量、DOS、功函数、电荷或偶极得出厚度稳定性、器件效率或最佳实验膜厚结论。**

## 1. 本轮解决的核心问题

第一版 T1/T2 使用 Cu₂Te 半片，导致 T1 顶部为 Te、T2 顶部为 Cu，把厚度和表面终止混在一起。本轮读取原 AFLOW/ICSD 来源 CIF 后确认，一个完整 Cu₂Te c 重复单元有四个原子平面：

```text
Cu – Te – Te – Cu
```

因此可以不删原子地构造：B0 裸 CdTe、H1 一个完整 c 重复、H2 两个完整重复。H2 在相同界面与顶部之间增加完整重复，H1/H2 都保持 Cu 首接触层和 Cu 顶部终止。旧 T0/T1/T2 保留在 `models/T*`，并有 `results/legacy_T_model_summary.csv` 说明，不再被生成器或测试使用。

## 2. 结构来源与未确认假设

- CdTe：zinc-blende `F-43m` (No. 216)，Materials Project `mp-406` / AFLOW `AB_cF8_216_a_c-001`，起始 a=6.48 Å，原型表面为 Te 终止 CdTe(111)。
- Cu₂Te：AFLOW `A2B_hP6_191_h_e-001` / ICSD 655706，`P6/mmm` (No. 191)，a=4.237 Å、c=7.24700717 Å，原型表面为 (001)，暂设 x=0。
- 横向匹配：面积因子 13 的 CdTe 表面胞对 4×4 Cu₂Te；未应变线性失配 2.586%，保持 CdTe 不变，对 Cu₂Te 施加 -2.521% 双轴压缩。
- 真空：总计 18 Å；测试几何优化固定最底部两个 CdTe 原子平面。

这些结构有可核查来源，但实验尚未确认真实样品唯一的 Cu₂₋ₓTe 晶相、x、取向和界面终止。采用它们是原型假设，不是相鉴定结论。

## 3. 新厚度模型的静态结果

| 模型 | 完整 c 重复 | Cu₂Te 平面 | 顶部 | 首接触 | Cd/Te/Cu | 总原子数 | Cu₂Te z-span | 界面最短距离 |
|---|---:|---:|---|---|---|---:|---:|---:|
| B0 | 0 | 0 | 无 | 无 | 39/39/0 | 78 | 0 Å | 无 |
| H1 | 1 | 4 | Cu | Cu | 39/71/64 | 174 | 4.927965 Å | 2.600000 Å |
| H2 | 2 | 8 | Cu | Cu | 39/103/128 | 270 | 12.174972 Å | 2.600000 Å |

机器检查确认：

- H2 原子数和 z-span 都大于 H1；
- H1/H2 的 78 个 CdTe 基底原子坐标完全相同；
- 第一 Cu₂Te 接触平面的元素与坐标相同；
- 顶部都只有 Cu；
- 横向晶胞、应变、初始界面距离和总真空相同；
- 全局最近距离分别为 B0 2.806 Å、H1 2.385 Å、H2 2.319 Å，均高于 1.8 Å 重叠阈值；H2 的 2.319 Å 来自所选 Cu₂Te 完整重复内部/相邻重复的结构，不是界面重叠。

详见 `results/model_summary.csv` 和 `results/validation.json`。

## 4. CP2K 最小设置

默认 smoke profile 使用：

- PBE；官方 `BASIS_MOLOPT`；
- Cu `DZVP-MOLOPT-SR-GTH-q11` / `GTH-PBE-q11`；
- Cd `DZVP-MOLOPT-SR-GTH-q12` / `GTH-PBE-q12`；
- Te `DZVP-MOLOPT-SR-GTH-q6` / `GTH-PBE-q6`；
- 400 Ry cutoff、60 Ry relative cutoff、Gamma 点；
- 500 K Fermi–Dirac 展宽、对角化和 Broyden mixing；
- bulk 使用 `PERIODIC XYZ`；slab 使用 `CELL/POISSON PERIODIC XY` 与 `PSOLVER ANALYTIC`；
- H1 测试优化最多 5 步。

这些名称已对照 CP2K 官方 `BASIS_MOLOPT` 和 `GTH_POTENTIALS` 核实，五个当前输入还通过了 CP2K 2024.3 的 `--check` 语法检查。它们没有完成科研级 basis、cutoff、k 点或展宽收敛研究。TZVP 只保留为以后可选方向，不是 smoke 默认值。

## 5. 真实运行环境和顺序

环境没有原生 `cp2k`、MPI 或 SLURM；已安装的 Docker Desktop 可运行。使用 CP2K 官方容器：

- 镜像：`cp2k/cp2k:2024.3`；
- CP2K：`CP2K version 2024.3`，源码 revision `git:6712648`；
- Docker server：28.3.2；
- CPU：4 个线程；
- 脱敏后的命令记录在每个 `run_metadata.json`；
- 真实运行前保存 `input.executed.inp` 和 SHA-256。

统一运行器的固定阶梯是：

```text
CdTe bulk → Cu2Te bulk → B0 slab → H1 single point → H1 5-step geometry test
```

只有前一任务通过严格成功条件，才启动下一任务。

## 6. 真实 CP2K 结果

| 任务 | 实际运行 | 正常结束 | SCF 收敛 | SCF 步数 | 总能量 (Ha) | 墙钟时间 |
|---|---|---|---|---:|---:|---:|
| 01 CdTe bulk SP | 是 | 是 | 是 | 12 | -216.86598115423214 | 15.407626 s |
| 02 Cu₂Te bulk SP | 是 | 是 | 是 | 18 | -208.11415684737275 | 50.125061 s |
| 03 B0 slab SP | 是，测试性尝试 | 否 | 否 | 无完整 SCF | 无 | 102.425199 s |
| 04 H1 interface SP | 否 | 否 | 否 | — | — | — |
| 05 H1 short GEO_OPT | 否 | 否 | 否 | — | — | — |

B0 每个早期 SCF 步约 20–25 秒，在前两步仍未接近收敛。为控制本地成本，任务被人工停止，退出码为 137；它不是“达到 MAX_SCF 后证明不收敛”，只能说该次尝试没有正常结束、没有完成一个 SCF，也没有能量。严格依赖门因此阻止 H1 和短优化启动。

完整证据分别保存在 `smoke_tests/01_cdte_bulk_sp`、`02_cu2te_bulk_sp` 和 `03_b0_slab_sp` 的执行输入快照、完整/截至停止时的 CP2K 输出、metadata 和 parsed JSON 中。汇总见 `results/smoke_test_summary.csv`。

这些绝对总能量只证明两个不同组成的小体相输入真实运行成功；二者不能互相相减形成反应能，也不能与 B0/H1/H2 直接比较膜厚稳定性。

## 7. 三轮自查与修正

1. **结构/输入轮**：改为完整 c 重复，生成 B0/H1/H2；结构验证通过。发现 H1/H2 都能自然保持 `Cu–...–Cu` 终止，无需删原子。
2. **真实运行/解析轮**：首次 CdTe bulk 实际输出明确 SCF 收敛和正常结束，但解析器误把 CP2K 正常页脚 `PROGRAM STOPPED IN /work` 当异常。已删除该错误规则并增加回归测试；同一输出随后被正确识别为成功。
3. **成本/可复现轮**：发现默认 restart 输出对 6–8 原子也产生 23–42 MB 文件。已删除这些非必要大文件、加入 `.gitignore`，并在当前 smoke 输入中显式设置 `RESTART OFF`。运行器现会冻结执行输入并记录 SHA-256。环境检查还修复了无 WSL 发行版时的 Windows 编码输出问题。

最终自动测试为 `14 passed`；10 条警告均来自 ASE 与 NumPy 2.5 的上游弃用提示，不是模型验证失败。

## 8. 严格解析规则

单点只有同时满足以下条件才标为成功：存在实际运行记录、`PROGRAM ENDED AT`、明确 SCF 收敛步数、总 FORCE_EVAL 能量，且没有 SCF 未收敛/abort 标志。几何优化还必须出现几何优化完成标志。缺失输出、正常结束但无显式 SCF 收敛、人工停止和 5 步未达到几何阈值都不会被标成成功。

## 9. 当前可信与不可信范围

可信：CIF 来源记录、完整重复单元构造、B0/H1/H2 几何文件、终止/界面一致性、静态距离和真空检查、低成本 CP2K 输入、两个真实体相 smoke 运行及其严格解析。

不可信：真实样品唯一晶相或 x、厚度稳定性、表面/界面能、正式结构弛豫、DOS、功函数、电荷转移、界面偶极、空穴势垒、最佳实验膜厚和器件效率。

## 10. 下一步最小建议

不要立即运行 H1。先针对 B0 只做一项小改进：在不改变模型科学范围的前提下测试更稳健的半导体 slab SCF 初始化/混合，并设置明确的时间上限；B0 单点正常结束后，再按同一阶梯尝试 H1。正式科研比较仍应优先由实验确认 Cu₂₋ₓTe 晶相和 x。
