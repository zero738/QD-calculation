# 第一阶段实施报告

日期：2026-07-16
状态：结构与输入工作流完成；本机未安装 CP2K，因此未实际执行 DFT。

## 1. 检查到的旧仓库与环境

原仓库主要包含配体钝化 CdTe 量子点、CAT 装配、CP2K 输入、SLURM 脚本和 DOS 分析。
旧 CdTe 输入采用 PBE、GTH、MOLOPT 基组和 350–400 Ry 截断，但其孤立量子点计算写为
`PERIODIC XYZ`，不适合直接复制到二维 slab。旧 SLURM 脚本还带有特定 NERSC account、
Shifter 镜像和资源设置，因此新脚本只保留通用资源骨架，不复制站点专用值。

环境为 Windows 11、Python 3.12.7。项目独立 `.venv` 中安装并实际使用 ASE 3.26.0、
NumPy 2.5.1、PyYAML 6.0.3、Matplotlib 3.11.0 和 pytest 9.1.1。检查不到 `cp2k`、
`cp2k.psmp`、`cp2k.popt`、MPI、`srun` 或 `sbatch`。详情见 `results/environment.json`。

## 2. 晶体结构来源与判断

CdTe 使用 zinc-blende `F-43m` (No. 216)，交叉标识 Materials Project `mp-406`，并由
AFLOW 原型 `AB_cF8_216_a_c-001` 生成参考 CIF；起始实验晶格常数取 6.48 Å。

Cu–Te 使用可验证的化学计量 Cu₂Te Ch 原型：AFLOW `A2B_hP6_191_h_e-001`、
ICSD 655706、`P6/mmm` (No. 191)。AFLOW 参数为 a=4.237 Å、c/a=1.71041、
z(Te)=0.306、z(Cu)=0.16，原始结构文献为 H. Nowotny (1946)。参考页：

- https://materialsproject.org/materials/mp-406/
- https://aflow.org/p/AB_cF8_216_a_c-001
- https://aflow.org/p/A2B_hP6_191_h_e-001

这不是对实验 Cu₂₋ₓTe 相的认定。由于 x、室温/退火后相和取向尚未确定，原型暂设 x=0，
并把该相当作经过验证的代表结构。没有使用凭记忆手写的未知晶体，也没有生成玩具晶格。

## 3. 选定界面和匹配

只实现一种构型：Te 终止 CdTe(111) / Cu₂Te(001)。CdTe 采用三双层（六个原子平面）的
极性 slab，底部两个原子平面固定。界面初始竖直间距为 2.60 Å，横向平移为 (0,0)。

直接 1×1 六方表面长度约为 CdTe 4.582 Å、Cu₂Te 4.237 Å，差异约 7.5%，不宜安静强拼。
原型采用 CdTe 的面积因子 13（矩阵 `[[3,1],[-1,4]]`）匹配 Cu₂Te 4×4（面积因子 16），
把线性失配降到 2.586%。保持 CdTe 不变并对 Cu₂Te 施加 -2.521% 双轴压缩。
该应变仍不可忽略；正式模型应搜索更大超胞、其他低指数面和不同应变分配。

没有探索的构型包括 Cd 终止 CdTe(111)、CdTe(110)/(100)、Cu₂Te 其他表面、不同横向平移、
反向 Cu/Te 终止、Cu 空位位置以及重构界面。

## 4. 生成模型与静态结果

| 模型 | Cd | Te | Cu | 总原子数 | Cu₂Te 结构片 | 初始厚度 Å | 最短距离 Å |
|---|---:|---:|---:|---:|---:|---:|---:|
| T0 | 39 | 39 | 0 | 78 | 0 | 0.000 | 2.806 |
| T1 | 39 | 55 | 32 | 126 | 1 | 1.058 | 2.385 |
| T2 | 39 | 71 | 64 | 174 | 2 | 4.928 | 2.385 |

横向面积统一为 236.371 Å²，总真空统一为 18 Å。T0/T1/T2 的 78 个 CdTe 基底原子坐标
完全相同。T1/T2 的结构片数、Cu 数和厚度单调增加。1.8 Å 重叠阈值没有被触发。

T1 的厚度较小是因为“一个结构片”只包含同一个 Cu₂Te 化学计量片内的相邻 Cu/Te 平面；
T2 厚度还包含两个片之间的间隔。它是基于所选晶相的几何定义，不是普适实验膜厚。

## 5. CP2K 输入判断

每个模型都有 `single_point.inp` 和 `test_geo_opt.inp`。输入采用：

- `CELL PERIODIC XY` 与 `POISSON PERIODIC XY`；
- CP2K 2022.1 可用的二维 `PSOLVER ANALYTIC`；
- PBE；GTH-PBE q11(Cu)、q12(Cd)、q6(Te)；
- 官方 UCL 文件中三种元素共同具备的 `TZVP-MOLOPT-SR-GTH`；
- 400 Ry / 60 Ry 截断、Gamma 点；
- 对角化、Broyden mixing、500 K Fermi–Dirac 展宽和 50 个额外轨道；
- restart 波函数、原子力、轨迹和 restart 结构输出；
- 测试优化最多 5 步，固定底部两个 CdTe 原子平面。

选择 TZVP 而非建议的 DZVP，是因为当前官方 CP2K 数据中可核验的 Cu DZVP 与 Cd/Te 可用集合
并不统一，而三者都明确存在同一 UCL TZVP-SR 家族。代价是计算更贵。正式运行前应在目标 CP2K
版本上确认数据文件路径，并重新做基组、截断、k 点和展宽收敛测试。

Gamma 点与三双层 CdTe 仅适合首轮管线测试。极性 CdTe(111) slab 可能产生明显偶极和人工表面态；
正式界面工作需要更厚、可能对称或钝化的 slab，并评估电势/偶极处理。不同原子数模型的绝对总能量
也不能直接相减判断最稳定厚度，必须定义守恒的化学势或界面/吸附能参照。

## 6. 自动检查与测试

执行 `pytest interface_thickness_prototype/tests -q`，结果为 `8 passed`。测试覆盖：

1. 三个模型可读取并通过总体验证；
2. 原子数关系与 T2 > T1 的 Cu 数；
3. T2 > T1 的 Cu–Te 厚度；
4. 三个模型的 CdTe 基底坐标与横向晶胞相同；
5. x/y 周期、z 非周期；
6. 总真空不小于 18 Å；
7. 最短距离不低于 1.8 Å；
8. 只含 Cd/Te/Cu；
9. CP2K 中几何和静电均为 `PERIODIC XY`，无 `PERIODIC XYZ`；
10. q11/q12/q6 赝势设置存在；
11. 缺失输出会清楚报错且不标成功；
12. 含“SCF NOT converged”的输出不标成功；
13. 同时具有显式 SCF 收敛、能量和正常结束标志的测试输出才标成功。
14. 几何优化即使正常结束，只要没有达到优化收敛标准，也不会被标为成功。

ASE/NumPy 组合产生 6 条第三方弃用警告，不影响测试结论，项目代码没有忽略验证失败。

## 7. 实际执行记录

实际执行了以下类型的命令：

```text
git clone https://github.com/chamber523/QD-calculation.git <目标目录>/QD-calculation
python -m venv .venv
.venv/Scripts/python -m pip install ase==3.26.0 PyYAML pytest
.venv/Scripts/python interface_thickness_prototype/scripts/build_models.py
.venv/Scripts/python interface_thickness_prototype/scripts/validate_models.py
.venv/Scripts/python interface_thickness_prototype/scripts/generate_cp2k_inputs.py
.venv/Scripts/python interface_thickness_prototype/scripts/inspect_environment.py
.venv/Scripts/python interface_thickness_prototype/scripts/summarize_results.py
.venv/Scripts/python -m pytest interface_thickness_prototype/tests -q
```

没有执行 `cp2k`、`mpiexec`、`srun` 或 `sbatch`，没有远程提交，也没有 DFT 总能量。
`results/model_summary.csv` 因而如实写为 `CP2K_completed=False`、`SCF_converged=False`、
能量空白、警告“CP2K not run or not proven converged”。

## 8. 可信范围和下一步

可信的是结构来源记录、当前原型假设、T0/T1/T2 几何文件、原子分类、厚度定义、失配/应变、
真空与重叠检查、CP2K 输入文本和解析器逻辑。尚不可信的是任何能量、稳定性、能带、功函数、
界面势垒、最佳膜厚或器件性能结论。

下一阶段最重要的不是立刻批量算 T0–T2，而是先用实验确定 Cu₂₋ₓTe 的晶相和 x；随后在小模型上
验证目标 CP2K 版本能读取基组/赝势，并跑通 T0 单点。再依次做 CdTe slab 厚度、真空、k 点、截断、
界面匹配和堆叠收敛，最后才比较经过充分优化且能量参照守恒的界面模型。
