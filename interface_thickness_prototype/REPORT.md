# CdTe/Cu₂Te 最小可运行核心报告

日期：2026-07-17
状态：B0/H1/H2 完整重复单元模型、CP2K 输入、带逐任务超时的顺序运行器和严格解析已完成；两个小体相、B0 与 H1 单点均在 CP2K 2024.3 中真实收敛。

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
- 300 Ry cutoff、40 Ry relative cutoff、Gamma 点、`EPS_SCF=1e-4`、`MAX_SCF=100`；
- 单点使用 `RUN_TYPE ENERGY` 和 `PRINT_LEVEL LOW`，不计算本轮不需要的原子力；
- CdTe bulk、B0 和 H1 使用低内存 OT（DIIS、`FULL_SINGLE_INVERSE`、`ENERGY_GAP 0.001`），不设 `ADDED_MOS`；
- Cu₂Te bulk 保留对角化、12 个额外空轨道、500 K Fermi–Dirac 展宽与 Broyden mixing；
- bulk 使用 `PERIODIC XYZ`；slab 使用 `CELL/POISSON PERIODIC XY` 与 `PSOLVER ANALYTIC`；
- H1 测试优化最多 5 步。

这些名称已对照 CP2K 官方 `BASIS_MOLOPT` 和 `GTH_POTENTIALS` 核实，五个当前输入还通过了 CP2K 2024.3 的 `--check` 语法检查。以上是为跑通管线而设的低成本参数，没有完成科研级 basis、cutoff、k 点、SCF 阈值或展宽收敛研究。尤其 H1 可能导电，OT 结果只证明该输入可运行；正式电子结构必须重新采用适合金属/小带隙体系的对角化、展宽与收敛测试。

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
| 01 CdTe bulk SP | 是 | 是 | 是 | 45 | -216.86602655342176 | 32.518768 s |
| 02 Cu₂Te bulk SP | 是 | 是 | 是 | 15 | -208.1206883249572 | 22.027180 s |
| 03 B0 slab SP | 是 | 是 | 是 | 49 | -2114.539469479587 | 772.206806 s |
| 04 H1 interface SP | 是 | 是 | 是 | 36 | -5470.2873350273885 | 1456.533034 s |
| 05 H1 short GEO_OPT | 否 | 否 | 否 | — | — | — |

最终 B0/H1 均使用 4 线程，分别受 900 s 和 1800 s 运行器硬上限约束；二者都在上限内以返回码 0 正常结束，`timed_out=false`、`termination_reason=process_exit_0`。解析器同时确认 `PROGRAM ENDED AT`、显式 SCF 收敛标志和总能量，才记录为成功。几何优化和 H2 没有运行。

旧 B0 的退出码 137 记录不能证明是人工停止、超时、OOM 或混合问题。旧输出末尾只可确认出现编号 1、2 的两行迭代记录，没有显式 SCF 收敛、总能量或正常结束标志，停止来源在旧 metadata 中未分类。后续一次 600 s 超时由新运行器机器确认并记录为 `runner_timeout`；另一次外部会话中断因无法确认子进程停止来源而记录为 `external_interruption_unclassified`。这些失败证据保存在 `attempt_history`，没有被改写成成功。

每个当前成功任务的完整证据保存在对应 `smoke_tests/<calculation_id>` 的 `input.executed.inp`、`output.out`、`run_metadata.json` 和 `output.parsed.json`。汇总见 `results/smoke_test_summary.csv`。这些绝对总能量只证明输入在当前低成本参数下真实运行成功；不同组成的 B0/H1 能量不能直接相减来判断膜厚稳定性或界面形成能。

## 7. 三轮自查与修正

1. **结构/输入轮**：改为完整 c 重复，生成 B0/H1/H2；结构验证通过。发现 H1/H2 都能自然保持 `Cu–...–Cu` 终止，无需删原子。
2. **真实运行/解析轮**：首次 CdTe bulk 实际输出明确 SCF 收敛和正常结束，但解析器误把 CP2K 正常页脚 `PROGRAM STOPPED IN /work` 当异常。已删除该错误规则并增加回归测试；同一输出随后被正确识别为成功。
3. **成本/可复现轮**：把单点从 `ENERGY_FORCE` 改为 `ENERGY`，降低打印、网格和额外空轨道成本；为 B0/H1 采用明确标注为非科研级的低内存 OT。运行器新增逐任务超时、启动即写 metadata、输入 SHA-256、停止原因分类和失败尝试归档。旧退出码 137 不再被过度解释；超时只有在运行器确实触发停止时才标记。

最终自动测试为 `19 passed`；10 条警告均来自 ASE 与 NumPy 2.5 的上游弃用提示，不是模型验证失败。

## 8. 严格解析规则

单点只有同时满足以下条件才标为成功：存在实际运行记录、返回码为 0、未超时、`PROGRAM ENDED AT`、明确 SCF 收敛步数、总 FORCE_EVAL 能量，且没有 SCF 未收敛/abort 标志。几何优化还必须出现几何优化完成标志。缺失输出、外部中断、运行器超时、非零退出、正常结束但无显式 SCF 收敛和 5 步未达到几何阈值都不会被标成成功。

## 9. 当前可信与不可信范围

可信：CIF 来源记录、完整重复单元构造、B0/H1/H2 几何文件、终止/界面一致性、静态距离和真空检查、低成本 CP2K 输入，以及 CdTe bulk、Cu₂Te bulk、B0 和 H1 四个真实 smoke 单点的执行与严格解析。

不可信：真实样品唯一晶相或 x、厚度稳定性、表面/界面能、正式结构弛豫、DOS、功函数、电荷转移、界面偶极、空穴势垒、最佳实验膜厚和器件效率。

## 10. 下一步最小建议

本轮核心已跑通，不要继续自动运行几何优化或 H2。下一步最小工作应先由实验确认 Cu₂₋ₓTe 晶相和 x；若要进入科研计算，再为可能导电的 H1 建立对角化+展宽配置并做 cutoff、SCF、k 点、真空和 slab 厚度收敛，而不是解释当前 OT smoke 总能量。

## 11. 覆盖度与 research_lite 最小论文框架（更新至 2026-07-23）

本轮没有改写或重跑既有 B0/H1 smoke 证据。`smoke_tests/` 中的输入、输出、metadata、历史失败归档和成功结果保持原样；smoke 总能量仍只能证明管线可运行。

新增覆盖度系列使用同一个 CdTe 基底和横向晶胞：C0 是 B0 的精确副本（78 原子，0%）；C50 保留 H1 中相邻两列、共 8/16 个完整横向 Cu₄Te₂ 单元（126 原子，50%）；C100 是 H1 的精确副本（174 原子，100%）。C50 薄膜为沿晶胞 B 矢量连续并周期重复的半面积条带，薄膜仍是一个完整 c 重复、Cu:Te=2:1，界面距离、应变、首接触 Cu 层和顶部 Cu 终止与 C100 相同。数据见 `results/coverage_model_summary.csv`，侧视/俯视图见 `coverage_models/C*/preview_*.png`。

CP2K 配置明确分成 `smoke_ot` 与 `research_lite`。后者采用 PBE、当前 DZVP-MOLOPT-SR-GTH/GTH-PBE、400/60 Ry、`EPS_SCF=1e-6`、最多 150 步、标准对角化、500 K Fermi–Dirac 展宽、40 个未占据轨道和 Broyden mixing。研究任务现在只有 Cu₂Te bulk、B0、C50、H1、H2；C0 唯一引用 B0，C100 唯一引用 H1，不再创建重复任务。默认 Gamma 输入不写 `KPOINTS`；bulk 的可选检查为 2×2×2，XY 薄片为 2×2×1。10/10 个输入通过 CP2K 2024.3 `--check`。显式 k 点输入按 CP2K 2024.3 限制不请求 PDOS/LDOS。

按本轮要求，只重新运行了一次 6 原子 Cu₂Te bulk 隐式 Gamma 测试。CP2K 2024.3 使用 4 线程，在 300 s 硬上限内以返回码 0 正常结束：SCF 18 步收敛，墙钟时间 68.130354 s，总能量 -208.11415857615756 Ha，Fermi energy 为 0.25768275978693 Ha。DOS、Cu/Te kind PDOS、两个区域 LDOS、电子密度 cube、Hartree 势 cube 与平面平均势均真实生成；严格状态为 `energy_valid=true`、`electronic_outputs_complete=true`。旧显式 Gamma/KPOINTS 运行完整保存在 `research_lite/runs/cu2te_bulk/history/attempt_01_explicit_gamma_kpoints/`，其能量有效但电子输出不完整。

当前 raw 总 DOS 代理为 EF 附近 0.20 eV 窗口内平均 bin density 0.011025，对应按 bin 宽换算的 0.2204995330 /eV；Cu₂Te 区域 LDOS 投影权重按两个 Cu₂Te 化学式单位归一化后为 7.5 /eV/formula-unit。前者仍是 CP2K 原始归一化直方图代理，不能单独比较不同原子数模型。bulk 没有“基底面积”，所以面积归一化 DOS 合理保持空值。2×2×2 能量检查没有实跑，因此当前 Gamma bulk 能量明确只是未完成 k 点检查的参考测试值。

`results/relative_coverage_formation_energy.csv` 已实现“相对覆盖形成能”接口：

```text
[E(Cθ) - E(C0) - n Ebulk(Cu2Te/formula unit)] / substrate area
```

形成能现在只依赖 `energy_valid`，不会因 PDOS 缺失而丢弃真实有效能量；电子文件完整性由独立的 `electronic_outputs_complete` 表示。因为 B0/C50/H1 尚未运行 research_lite，覆盖形成能仍保持空白；没有使用 smoke 能量填充。`results/dft_proxy_summary.csv` 明确分列 raw DOS、按基底面积归一化 DOS、按 Cu₂Te 化学式单位归一化投影 DOS；功函数、界面电荷转移和势垒代理仍为空。极性、很薄的 CdTe(111) slab 只能支持未来完成收敛后的相对趋势。

最终自动测试结果为 `29 passed`；另有 12 条 ASE/NumPy 上游弃用提醒，不是结构或 CP2K 验证失败。
