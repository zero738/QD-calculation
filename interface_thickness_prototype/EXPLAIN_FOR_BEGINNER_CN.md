# 给初学者的 CdTe/Cu₂Te 界面厚度与 CP2K 说明

## 1. bulk、slab、interface 和 vacuum 是什么

- **bulk（体相）**：晶体在 x、y、z 三个方向无限重复，没有表面。这里用 8 原子 CdTe 和 6 原子 Cu₂Te 小晶胞先验证 CP2K 能否读取结构、基组和赝势。
- **slab（薄片）**：从体相沿某晶面切出有限厚度。B0 是 CdTe(111) slab。
- **interface（界面）**：两种材料直接接触的区域。H1/H2 中是 CdTe 顶部 Te 与 Cu₂Te 底部 Cu 接触。
- **vacuum（真空）**：z 方向没有原子的空白区，防止薄片上下表面错误相接。模型总真空为 18 Å，上下各约 9 Å。

## 2. 为什么厚度用完整重复单元表示

原子模型不能把膜连续地从 0.30 nm 调到 0.31 nm；最清楚的增厚方法是添加完整晶体重复单元。源 Cu₂Te 晶胞沿 c 方向有四个原子平面：

```text
Cu – Te – Te – Cu
```

因此一个完整重复单元的底部和顶部都是 Cu。H2 在 H1 的界面层与顶部之间增加另一个完整 c 重复，不删原子，也不使用含义不清的“半片”。这样厚度变化不会同时改变顶部终止。

## 3. B0、H1、H2 分别是什么

- **B0**：只有 78 原子的 CdTe(111) 基底，是裸 slab 对照。
- **H1**：相同基底 + 1 个完整 Cu₂Te c 重复，共 174 原子、4 个 Cu₂Te 原子平面，z-span 4.928 Å。
- **H2**：相同基底 + 2 个完整重复，共 270 原子、8 个 Cu₂Te 原子平面，z-span 12.175 Å。

H1/H2 都是 Cu 顶部终止、Cu 首接触层、相同横向晶胞、相同 -2.521% Cu₂Te 面内应变和相同初始界面堆叠。旧 T0/T1/T2 因半片定义导致顶部终止变化，只保留作历史比较。

## 4. 哪些原子固定，哪些可以移动

H1 的测试几何优化固定最下面两个 CdTe 原子平面，模拟更深处晶体对表面的支撑；其余 CdTe 和全部 Cu₂Te 原子可移动。`structure.extxyz` 用 `fixed`、`component` 和 `region` 字段记录分类，CP2K 用相同编号写入 `FIXED_ATOMS`。

## 5. 周期性边界是什么意思

bulk 在 XYZ 三方向重复。slab/界面只在 XY 平面重复，像无限铺开的地砖；z 方向不重复。CP2K 中 slab 的 `CELL` 和 `POISSON` 都设置 `PERIODIC XY`，体相则为 `PERIODIC XYZ`。

## 6. 为什么需要真空层

即使 z 不周期，电子密度仍应在计算盒边界前衰减。18 Å 只是 smoke-test 起点；正式计算必须增大真空并检查结果是否稳定，不能直接把当前设置当作功函数收敛值。

## 7. 为什么需要晶格匹配

两种表面 1×1 直接拼接约有 7.5% 长度差。当前原型使用面积因子 13 的 CdTe 表面超胞匹配 4×4 Cu₂Te，把未应变线性失配降到 2.586%；固定 CdTe，对 Cu₂Te 施加 -2.521% 双轴压缩。这是明确记录的人为应变，正式研究应继续寻找更大、失配更小的超胞和其他取向。

## 8. 单点与几何优化分别做什么

- **单点计算**：不移动原子，只求电子自洽和总能量。本轮为节省 smoke 成本使用 `RUN_TYPE ENERGY`，不额外计算原子力；几何优化才必须计算力。
- **几何优化**：多次做电子计算并移动未固定原子，直到力足够小。本项目 H1 最多只做 5 步，是管线测试，不是完整弛豫。

## 9. 什么叫“真正运行”和“真正收敛”

文件存在不等于成功。解析器要求同时看到：实际执行记录、`PROGRAM ENDED AT`、明确的 `SCF run converged in ... steps`、总 FORCE_EVAL 能量，而且没有 SCF 未收敛或 abort。几何优化还必须出现完成标志。每个任务的证据保存在 `output.out`、`run_metadata.json` 和 `output.parsed.json`。

## 10. 哪些结果只是代码测试

以下内容可以证明管线工作：结构能读取；H2 比 H1 更厚且原子更多；顶部和首接触终止一致；没有低于 1.8 Å 的异常距离；CP2K 能识别 q11/q12/q6 基组与赝势；两个小体相、B0 和 H1 单点都被真实运行并严格解析。

即使得到体相或 slab 总能量，也只证明该输入在该参数下运行成功。不同原子数模型的绝对总能量不能直接相减来判断哪种膜厚更稳定。

## 11. 哪些结果以后才可用于科研结论

必须先确认真实 Cu₂₋ₓTe 相和 x，再测试其他终止、配准和取向，收敛 slab 厚度、真空、cutoff、基组、k 点和展宽，完成充分几何优化，并定义守恒的表面/界面能参考。当前极性且很薄的 CdTe(111) slab 尤其不能用于正式 DOS、功函数、界面偶极或厚度稳定性结论，也不能预测器件效率和最佳实验膜厚。

## 12. 如何查看结构和结果

- VESTA：打开 `models/H1/structure.cif` 或 `models/H2/structure.cif`。
- OVITO：打开对应 `structure.xyz` 或 `structure.extxyz`。
- 不装图形软件：直接看 `models/B0|H1|H2/preview_side.png`，图中已标出基底、薄膜、界面、顶部终止和 z-span。
- 表格：先看 `results/model_summary.csv`，再看 `results/smoke_test_summary.csv`。

ASE 示例：

```python
from ase.io import read
from ase.visualize import view

atoms = read("interface_thickness_prototype/models/H2/structure.extxyz")
view(atoms)
```

正式扩大模型时要重新检查：相和 x、表面取向、终止、空位、横向失配、界面距离、slab/真空/固定层、总电荷和自旋、基组赝势 q 值、cutoff、k 点、展宽、SCF 与几何收敛。
