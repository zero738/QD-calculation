# CdTe/Cu₂Te 界面厚度：最小可运行核心

该目录与仓库原有配体修饰量子点项目隔离。它完成一条尽量短、可核查的路径：

```text
已记录来源的 CIF → B0/H1/H2 → 静态验证 → CP2K 输入
→ 按依赖顺序运行 smoke test → 严格解析 SCF/正常结束/能量 → CSV 报告
```

这仍是结构和计算管线原型。实验尚未确认真实样品唯一的 Cu₂₋ₓTe 晶相、x 和界面取向。

## 当前模型

| 模型 | 定义 | Cu₂Te 完整 c 重复 | Cu₂Te 原子平面 | 顶部终止 | 原子数 | Cu₂Te z-span |
|---|---|---:|---:|---|---:|---:|
| B0 | 裸 CdTe(111) slab | 0 | 0 | 无 | 78 | 0 Å |
| H1 | CdTe + 1 个完整 Cu₂Te c 重复 | 1 | 4 | Cu | 174 | 4.928 Å |
| H2 | CdTe + 2 个完整 Cu₂Te c 重复 | 2 | 8 | Cu | 270 | 12.175 Å |

源 Cu₂Te 完整重复单元沿 z 的原子平面次序是 `Cu–Te–Te–Cu`，因此 H1/H2 的首接触层和顶部终止都为 Cu。增厚时没有删除原子，也没有继续使用含义模糊的 half sheet。旧 T0/T1/T2 文件保留在 `models/T*`，只用于追溯第一版，生成器不再覆盖它们。

## 从零生成和检查

在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r interface_thickness_prototype\requirements.txt
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\build_models.py
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\generate_cp2k_inputs.py
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\validate_models.py
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\summarize_results.py
.\.venv\Scripts\python.exe -m pytest interface_thickness_prototype\tests -q
```

Linux 把 Python 路径替换为 `.venv/bin/python`。详细 CP2K 运行方式见 `RUN_CP2K.md`。

## Smoke-test 阶梯

运行器严格按以下顺序执行；前一步未同时通过正常结束、显式 SCF 收敛和能量检查时，不启动下一步：

1. 8 原子 CdTe bulk 单点；
2. 6 原子 Cu₂Te bulk 单点；
3. B0 slab 单点；
4. H1 界面单点；
5. H1 最多 5 步测试几何优化。

默认基组为官方 `BASIS_MOLOPT` 中的 DZVP-MOLOPT-SR-GTH q11/q12/q6，配套 GTH-PBE 赝势。TZVP 只保留为以后可选的 production 方向，不是本地 smoke test 默认值。

当前 CP2K 2024.3/Docker 实测中，B0 单点以 49 个 SCF 步、772.206806 s 正常结束，H1 单点以 36 个 SCF 步、1456.533034 s 正常结束；两者都通过返回码、超时、SCF、能量和程序页脚的严格检查。这些是低成本管线 smoke 结果，不是可比较的科研总能量。

## 最值得先看

- `results/model_summary.csv`：B0/H1/H2 的层数、终止、原子数、厚度和界面距离。
- `results/smoke_test_summary.csv`：每个真实/未运行任务的版本、SCF、能量和运行时间。
- `results/validation.json`：相同终止、相同界面、基底一致性和输入检查的机器可读证据。
- `models/H1/preview_side.png` 与 `models/H2/preview_side.png`：本科生可直接读懂的侧视图。
- `REPORT.md`：实际做了什么、哪些失败或未运行，以及科学警告。
- `EXPLAIN_FOR_BEGINNER_CN.md`：概念和结果解释。

请勿把不同原子数模型的绝对总能量直接相减，也不要由本原型声称得到稳定膜厚、科研级 DOS/功函数、器件效率或真实 Cu₂₋ₓTe 相。

## 覆盖度与 research_lite

- `coverage_models/C0`, `C50`, `C100`：0%、50%、100% 覆盖结构及侧/俯视图；C50 只删除完整横向 Cu₂Te 单元。
- `research_lite/inputs/*`：唯一任务为 Cu₂Te bulk、B0、C50、H1、H2；C0 引用 B0，C100 引用 H1。Gamma 主输入以及 bulk 2×2×2、薄片 2×2×1 可选检查输入共 10 个，均通过 CP2K 2024.3 `--check`。
- `research_lite/runs/cu2te_bulk`：修正后的隐式 Gamma 小测试真实生成 DOS、PDOS/LDOS、Fermi 和势输出，严格状态为 `energy_valid=true`、`electronic_outputs_complete=true`。旧显式 KPOINTS 部分成功证据保存在 `history/attempt_01_explicit_gamma_kpoints`。
- `research_lite/runs/cu2te_bulk_k222`、`B0`、`C50`：已真实运行并通过各自门禁；H1 已真实尝试但在 runner 的 7200 s 硬上限处停止且未收敛，H2 因门控未运行。原始输入、输出、metadata 和严格解析文件均保留。
- `results/coverage_model_summary.csv`：覆盖度、原子数、终止和条带周期性。
- `results/final_model_status.csv`：真实运行、返回码、超时、SCF、能量、电子输出完整性、警告和停止原因；未运行模型的数值保持空白。
- `results/relative_coverage_formation_energy.csv`：旧 CP2K 2024.3 固定初始几何诊断值；全部行明确标记 `not_ready_for_paper`，C50 数值不得进入论文结论。
- `results/dft_proxy_summary.csv`：比较由唯一 KS 轨道列表统一展宽得到的每面积轨道谱、按 Cu₂Te 化学式单位归一化的投影谱，以及按界面原子归一化的界面谱；CP2K 自带 DOS 只作为归一化直方图证据，不能冒充总 KS 轨道 DOS。
- `PAPER_RESULTS_SUMMARY.md` 与 `USER_REVIEW_CHECKLIST.md`：分别给出论文表述边界和逐文件人工复核方法。
- `results/experiment_data_template.csv`：以后对接膜厚、覆盖度、效率和接触电阻的实验数据表头。

## 超算互联网 CP2K 2024.1 运行包

`server_scnet_2024_1/` 是国家超算互联网华东一区昆山 `kshctest02` 分区的独立运行包。它不会覆盖 `research_lite/runs/`。上传后运行一次 `bash submit_pipeline.sh` 即建立受控 Slurm 依赖链；只有这个登录节点包装脚本调用 `sbatch`，计算脚本不会递归提交。服务器任务当前全部为 `not_run`；本地只完成静态检查和 CP2K 2024.3 `--check` 语法预检。

- `server_scnet_2024_1/README_SCNET_CN.md`：一键提交、监控、取消、资源和失败处理；
- `server_scnet_2024_1/env_scnet.sh`：绕过有缺陷 CP2K 模块，手动加载 GNU/Intel/Intel MPI 并使用 `cp2k.popt`；
- `server_scnet_2024_1/scripts/`：服务器 2024.1 输入检查、Gamma→2×2×2→3×3×3→4×4×4、B0、C50、H1、H2 和两条 finalizer 的单节点作业；
- `server_scnet_2024_1/verify_server_outputs.py`：严格解析返回码、版本、SCF、能量、PDOS/LDOS、cube、谱积分和最高 MO 警告；
- `server_scnet_2024_1/results/`：初始空白状态、静态审计及本地语法预检证据。

H1 在一个 16 小时作业内最多运行 attempt_A 和一次受控 attempt_B。持续最高 MO 警告只增加 `ADDED_MOS/NLUMO` 到 160；无该警告但残差振荡只把 `ALPHA/NBROYDEN` 改为 0.05/16；硬配置错误不重试。`EPS_SCF=1e-6`、结构和物理模型不变。H2 在 `srun` 前重新验证 H1，并从 `H1_SUCCESS.json` 动态继承实际成功参数；H1 未成功时自动阻断。

资源由 Slurm 文件自动复算，全部作业硬上限约 1102.17 CPU·h，低于 1800 CPU·h 门槛。详细边界、8/8 输入语法预检和 59/59 静态审计分别见运行包 README、`results/syntax_precheck_cp2k_2024_3.json` 与 `results/static_audit.json`。本地 2024.3 语法通过不代表服务器 2024.1 已运行或一定收敛。

Windows 上传包可在 `interface_thickness_prototype` 目录运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\make_scnet_bundle.ps1` 生成 `scnet_upload_bundle.zip`；脚本会校验 SHA256，并排除 `.git`、虚拟环境、缓存、旧 runs、WFN、restart 和 cube。
