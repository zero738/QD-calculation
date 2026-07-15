# CdTe/Cu₂Te 界面厚度 DFT 建模：最小可运行原型

这是一个与旧配体量子点项目隔离的第一阶段原型。它能从已记录来源的 CdTe 和 Cu₂Te
结构生成 T0/T1/T2，检查重叠、真空、原子数和基底一致性，输出 CIF/XYZ/预览图，
并生成 CP2K 单点和有限 5 步几何优化输入。它不声称给出了真实 Cu₂₋ₓTe 相、收敛能量、
最佳实验膜厚或器件效率。

## 模型

| 模型 | 含义 | 原子数 | Cu–Te 初始几何厚度 |
|---|---|---:|---:|
| T0 | 裸 CdTe(111) slab | 78 | 0 Å |
| T1 | CdTe + 1 个 Cu₂Te 结构片 | 126 | 1.058 Å (0.1058 nm) |
| T2 | CdTe + 2 个 Cu₂Te 结构片 | 174 | 4.928 Å (0.4928 nm) |

“结构片”是从 AFLOW Cu₂Te 原胞按 z 方向切出的化学计量 Cu₂Te 单元，包含相邻的 Cu/Te
原子平面。它只是原型中的离散厚度定义，不应直接解释为实验连续薄膜厚度。

## 从零重建和测试

在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r interface_thickness_prototype\requirements.txt
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\inspect_environment.py
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\build_models.py
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\validate_models.py
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\generate_cp2k_inputs.py
.\.venv\Scripts\python.exe -m pytest interface_thickness_prototype\tests -q
.\.venv\Scripts\python.exe interface_thickness_prototype\scripts\summarize_results.py
```

Linux/macOS 把 Python 路径替换成 `.venv/bin/python`。

## 运行 CP2K（本项目没有自动运行或提交）

进入一个模型目录后，可在已安装 CP2K 的机器上运行：

```bash
./run_local.sh single_point.inp
./run_local.sh test_geo_opt.inp
```

Windows PowerShell：

```powershell
.\run_local.ps1 single_point.inp
```

集群脚本 `job.slurm` 需要先按站点补充 account、partition、module 或容器设置；确认无误后
才可由用户手动 `sbatch job.slurm`。本原型不会主动提交。

## 关键输出

- `assumptions.yaml`：所有相、取向、失配、应变、真空与固定层假设。
- `models/T*/structure.cif|xyz|extxyz`：可视化结构；extxyz 保留区域和固定原子标签。
- `models/T*/preview_side.png`：无图形界面生成的侧视预览。
- `models/T*/single_point.inp`：PBE/GTH 单点力与能量输入。
- `models/T*/test_geo_opt.inp`：最多 5 步的管线测试优化，不是完整优化。
- `results/validation.json`：结构检查结果。
- `results/model_summary.csv`：原子数、厚度、距离、面积、失配及严格收敛状态。
- `EXPLAIN_FOR_BEGINNER_CN.md`：面向初学者的中文解释。
- `REPORT.md`：实施判断、已运行内容与局限。
