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

## 最值得先看

- `results/model_summary.csv`：B0/H1/H2 的层数、终止、原子数、厚度和界面距离。
- `results/smoke_test_summary.csv`：每个真实/未运行任务的版本、SCF、能量和运行时间。
- `results/validation.json`：相同终止、相同界面、基底一致性和输入检查的机器可读证据。
- `models/H1/preview_side.png` 与 `models/H2/preview_side.png`：本科生可直接读懂的侧视图。
- `REPORT.md`：实际做了什么、哪些失败或未运行，以及科学警告。
- `EXPLAIN_FOR_BEGINNER_CN.md`：概念和结果解释。

请勿把不同原子数模型的绝对总能量直接相减，也不要由本原型声称得到稳定膜厚、DOS、功函数、器件效率或真实 Cu₂₋ₓTe 相。
