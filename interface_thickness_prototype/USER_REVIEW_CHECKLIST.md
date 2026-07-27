# 用户审查清单

本清单中的“完整本地路径”以你的实际项目根目录为准：

`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype`

如果刚从 GitHub 查看或拉取分支，请先确认当前分支是 `agent/cdte-cu2te-interface-prototype`。

## 1. 运行前硬门

- 文件：`results/pre_run_gates.json`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\results\pre_run_gates.json`
- 搜索：`"all_gates_passed"`
- 正确时应看到：值为 `true`；各子项包括 31 项测试、PDOS/LDOS 一致性、尺寸倍增、19 条既有 ELPA 警告、C0/C100 别名唯一性、界面组和 10/10 CP2K 输入检查。
- 异常时会看到：`false`，并且至少一个子项 `"passed": false`。
- 这证明：大模型启动前的代码、结构分组、解析器和输入语法门禁已通过。
- 这不能证明：SCF 一定收敛、模型物理正确或参数已达到科研级收敛。

## 2. 所有任务的真实状态

- 文件：`results/final_model_status.csv`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\results\final_model_status.csv`
- 搜索：`cu2te_bulk_k222`、`B0`、`C50`、`H1`、`H2`
- 正确时应看到：每行分别记录 `actually_run`、`energy_valid`、`electronic_outputs_complete`、SCF 步数、能量、警告数、时间和停止原因；C0 只作为 B0 别名，C100 只作为 H1 别名。
- 异常时会看到：未运行任务却出现能量，或超时/失败任务被标成 `energy_valid=True`。
- 这证明：哪些任务真实运行、哪些通过严格门禁、哪些因依赖停止。
- 这不能证明：有效能量之间已经可以作发表级热力学比较。

## 3. B0 原始 CP2K 成功证据

- 文件：`research_lite/runs/B0/output.out`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\research_lite\runs\B0\output.out`
- 搜索：`SCF run converged`、`ENERGY| Total FORCE_EVAL`、`PROGRAM ENDED AT`
- 正确时应看到：三个标志都存在；ELPA 警告仍保留。
- 异常时会看到：`SCF run NOT converged`、`ABORT`，或缺少正常结束标志。
- 这证明：B0 的 CP2K 进程真实运行、SCF 明确收敛并正常结束。
- 这不能证明：Gamma、400 Ry、固定几何或极性 CdTe(111) 已完成科研级收敛。

## 4. C50/H1/H2 原始输出或依赖停止

- 文件：`research_lite/runs/C50/output.out`、`research_lite/runs/H1/output.out`、`research_lite/runs/H2/output.out`
- 完整本地路径：
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\research_lite\runs\C50\output.out`
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\research_lite\runs\H1\output.out`
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\research_lite\runs\H2\output.out`
- 搜索：与 B0 相同的三个成功标志。
- 正确时应看到：C50 具有三个成功标志；H1 已真实启动但在 7200 s 硬超时后停止，缺少收敛和正常结束标志；H2 因门控未启动，所以其 `output.out` 不存在。
- 异常时会看到：输出缺少收敛/正常结束标志，但汇总仍填入有效能量。
- 这证明：依赖顺序没有被绕过，失败轨迹没有被隐藏。
- 这不能证明：H1 延长时间后必然收敛，也不能证明未运行的 H2 会以相同参数收敛。

## 5. 固定初始几何相对覆盖形成能

- 文件：`results/relative_coverage_formation_energy.csv`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\results\relative_coverage_formation_energy.csv`
- 搜索：`fixed_geometry_relative_coverage_formation_energy`
- 正确时应看到：每个覆盖模型只有在“该模型、B0 和 2×2×2 Cu₂Te 参考能”分别有效时才出现数值；因此 C50 有原型数值，H1/C100 因 H1 能量无效而为空。
- 异常时会看到：使用 smoke 能量、无效能量或未运行任务填出覆盖能。
- 这证明：参考式、面积归一化和每 Cu₂Te 化学式单位归一化已按严格状态执行。
- 这不能证明：数值是绝对表面能、弛豫后形成能或实验稳定性排序。

## 6. 规范化电子结构代理

- 文件：`results/dft_proxy_summary.csv`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\results\dft_proxy_summary.csv`
- 搜索：`KS_orbital_density_near_EF_per_ev_per_substrate_area`、`Cu2Te_projected_spectral_weight`、`interface_projected_spectral_weight`
- 正确时应看到：总谱按基底面积归一化，Cu₂Te 投影按化学式单位归一化，界面投影按界面原子数归一化；B0 的 Cu₂Te 字段为空而不是 0。
- 异常时会看到：`raw_total_DOS` 字段，或不同原子数模型只比较未经归一化的总 DOS。
- 这证明：不同尺寸模型使用了可审计的规范化代理。
- 这不能证明：投影谱权重等于严格总态数、界面电导或真实接触电阻。

## 7. 覆盖能和覆盖电子代理图片

- 文件：`plots/coverage_formation_energy.png`、`plots/coverage_electronic_proxies.png`
- 完整本地路径：
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\plots\coverage_formation_energy.png`
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\plots\coverage_electronic_proxies.png`
- 查看：0%、50%、100% 三个覆盖点。
- 正确时应看到：只绘制有效值；无有效结果的位置明确写出缺失，不用 0 伪造。
- 异常时会看到：未运行模型出现平滑趋势线或数值点。
- 这证明：图与严格状态表一致。
- 这不能证明：覆盖率趋势已经代表实验浓度、膜厚或器件效率趋势。

## 8. H1/H2 厚度谱比较

- 文件：`plots/thickness_H1_H2_DOS.png`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\plots\thickness_H1_H2_DOS.png`
- 查看：横轴必须是 `E−EF (eV)`，曲线应包括每面积 KS 轨道谱、每化学式单位 Cu₂Te 投影谱和每界面原子投影谱。
- 正确时应看到：只有 H1/H2 都有完整输出时才显示相应曲线；否则显示缺失说明。
- 异常时会看到：原始 CP2K Fermi 能量被直接作为跨模型绝对能量轴，或只比较整个薄膜未归一化 PDOS。
- 这证明：厚度比较没有把原子数增长误当成 DOS 增长。
- 这不能证明：H1/H2 的绝对能级已经真空对齐或接触电阻发生了确定变化。

## 9. 顶部功函数代理

- 文件：`plots/work_function_trend.png`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\plots\work_function_trend.png`
- 查看：B0、C50、H1、H2 的顶部平台状态。
- 正确时应看到：仅可靠连续真空平台才绘制数值；平台不可靠时标记失败并保持空白。
- 异常时会看到：用单个势能最大值或原始 Fermi 能量生成“功函数”。
- 这证明：真空能级检测使用了连续、低密度、平坦区域门槛。
- 这不能证明：极性薄片的绝对功函数已可信，或已经得到真实势垒。

## 10. 论文表述边界

- 文件：`PAPER_RESULTS_SUMMARY.md`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\PAPER_RESULTS_SUMMARY.md`
- 搜索：`当前不能声称`
- 正确时应看到：真实结果、合理解释、需实验验证的推断和禁止结论分开书写。
- 异常时会看到：DFT 直接给出接触电阻、最佳膜厚、器件效率，或声称当前结构就是实验唯一 Cu₂₋ₓTe 相。
- 这证明：结果陈述与原型证据等级一致。
- 这不能证明：论文结论已经完成同行评审或实验验证。

## 11. Cu₂Te 最低 k 点检查

- 文件：`results/kpoint_reference_check.csv`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\results\kpoint_reference_check.csv`
- 搜索：`delta_E_k222_minus_gamma_ev_per_Cu2Te_formula_unit`
- 正确时应看到：Gamma 和 2×2×2 两个真实有效总能量、每胞 2 个 Cu₂Te 化学式单位，以及 `E₂×₂×₂−EΓ` 的每化学式单位差值；限制列明确写着这不是 k 点收敛研究。
- 异常时会看到：缺少任一参考能、把总胞差值误当每化学式单位差值，或声称 2×2×2 已完成收敛。
- 这证明：最低 k 点检查的能差已按化学式单位可复算地记录。
- 这不能证明：Gamma 或 2×2×2 中任一个已经是科研级收敛参考。

## 12. 最终三轮审计

- 文件：`results/final_audit.json`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\results\final_audit.json`
- 搜索：`"all_passed"`、`"passed_count"`、`"check_count"`
- 正确时应看到：`all_passed=true` 且 `passed_count=32`、`check_count=32`；三轮分别是程序/门禁、原始输出对 CSV、科学量纲/归一化/参考态/结论范围。
- 异常时会看到：`all_passed=false`，并在对应检查项看到失败原因。
- 这证明：最终派生表与当前原始输出一致，未运行/无效结果保持空白，关键科学定义通过机器检查。
- 这不能证明：模型相、界面取向、k 点、slab 厚度或实验对应关系已完成科研级验证。

## 13. 超算运行包入口

- 文件：`server_scnet_2024_1/README_SCNET_CN.md`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\README_SCNET_CN.md`
- 搜索：`服务器任务尚未运行`、`手动运行顺序`、`H1 最小修正`。
- 正确时应看到：服务器路径建议为 ASCII；所有任务需人工按顺序 `sbatch`；H1 未严格成功前禁止 H2；总硬上限约 1036.17 CPU·h。
- 异常时会看到：声称服务器任务已成功、自动批量提交、跨节点、`--exclusive`，或直接加载有缺陷的 CP2K 模块。
- 这证明：上传和提交方法、资源边界及失败处理已明确。
- 这不能证明：超算模块、队列和 CP2K 2024.1 在实际作业中一定正常。

## 14. 服务器任务初始真实状态

- 文件：`server_scnet_2024_1/results/server_task_status.csv`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\results\server_task_status.csv`
- 搜索：`not_run`、`strict_success`、`total_energy_hartree`。
- 正确时应看到：8 个未来任务全部 `actually_run=False`、`status=not_run`、能量为空。
- 异常时会看到：没有原始服务器输出却出现 CP2K 2024.1 能量、SCF 步数或成功状态。
- 这证明：本轮没有伪造服务器结果，旧 `research_lite/runs/` 也未被覆盖。
- 这不能证明：以后上传后任务会自动成功或满足队列时间限制。

## 15. H1 最小修正与 H2 硬门控

- 文件：`server_scnet_2024_1/inputs/H1/input.inp`、`server_scnet_2024_1/scripts/40_H2.slurm`、`server_scnet_2024_1/verify_server_outputs.py`
- 完整本地路径：
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\inputs\H1\input.inp`
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\scripts\40_H2.slurm`
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\verify_server_outputs.py`
- 搜索：`ADDED_MOS 100`、`NLUMO 100`、`ALPHA 0.08`、`NBROYDEN 12`、`MAX_SCF 250`、`EPS_SCF 1e-06`、`--gate-h2`。
- 正确时应看到：H1 只改五个最小 SCF/输出参数；H2 的 `--gate-h2` 位于 `srun` 之前；验证器还检查 CP2K 2024.1、返回码、SCF、能量、最高 MO 警告、PDOS/LDOS、cube、谱积分和 H1/H2 参数一致性。
- 异常时会看到：`EPS_SCF=1e-4`、OT、结构/晶胞变化，或 H2 在门控前启动。
- 这证明：旧 H1 的未占据轨道不足和混合振荡得到最小、可审计的处理，H2 不会绕过失败门控。
- 这不能证明：H1 使用这些参数后必然收敛，也不能排除需要新的受控调整。

## 16. 体相 k 点与覆盖派生量接口

- 文件：`server_scnet_2024_1/results/bulk_kpoint_convergence.csv`、`server_scnet_2024_1/results/server_coverage_metrics.csv`
- 完整本地路径：
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\results\bulk_kpoint_convergence.csv`
  - `C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\results\server_coverage_metrics.csv`
- 搜索：`delta_from_previous_ev_per_Cu2Te_formula_unit`、`not_ready_for_paper`、`coverage_curvature_E_H1_plus_E_B0_minus_2E_C50`。
- 正确时应看到：服务器未运行时全部能量/差值为空；相邻 k 点阈值为 0.01 eV/Cu₂Te 化学式单位；覆盖形成能和曲率都为空且 `not_ready_for_paper`。
- 异常时会看到：复用旧 2024.3 C50 数值填充服务器表，或 H1 未成功却输出覆盖曲率。
- 这证明：Gamma→2×2×2→3×3×3→4×4×4 以及化学势抵消曲率代理已有严格状态接口。
- 这不能证明：未来 4×4×4 一定满足收敛；若仍失败，只能人工评估后续 5×5×5。

## 17. 本地预检与静态审计

- 文件：`server_scnet_2024_1/results/local_validation_summary.json`、`server_scnet_2024_1/results/static_audit.json`、`server_scnet_2024_1/results/syntax_precheck_cp2k_2024_3.json`
- 完整本地路径：`C:\Users\Xu\OneDrive\桌面\重要事务\SRP离子交换电池方法\QD-calculation\interface_thickness_prototype\server_scnet_2024_1\results\local_validation_summary.json`
- 搜索：`server_cp2k_calculations_actually_run`、`31`、`8`、`CP2K version 2024.3`、`target_server_version`。
- 正确时应看到：服务器实际运行是 `false`；46 个 Python 测试、33/33 静态审计、11 个 shell 文件语法通过、8/8 输入通过本地 CP2K 2024.3 `--check`。
- 异常时会看到：把 2024.3 语法预检写成 2024.1 服务器计算成功，或静态审计存在失败项。
- 这证明：当前包结构、输入语法和门控逻辑在本地通过预检。
- 这不能证明：服务器 CP2K 2024.1 运行时兼容、性能、SCF 收敛或科学收敛。
