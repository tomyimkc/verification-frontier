# 安全扩展科学 Agent 的验证边界

**GOAI 2026 前沿探索 / AI for Research — 开放探索赛题**<br/>
**团队：** Yim Kin Cheong（Tom），独立研究者，香港<br/>
**许可：** Apache-2.0<br/>
**证据边界：** `candidateOnly:true`，`canClaimAGI:false`，
`winnerLevelEligible:false`，`winnerLevelGateMet:false`

<!-- PAGE 1 -->

## 1. 研究问题与拟议贡献

科学 Agent 在每一步都必须区分三种情况：

1. 当前可执行检查能够确认候选；
2. 当前检查能够证伪候选；
3. 候选超出当前验证器的覆盖范围。

若把第三种情况当成“没有发现错误”，就会形成静默通过；但若只会弃权，科研流程又会停滞。
因此，本项目提出可证伪问题：

> 模型提出、经人类批准的验证器扩展，能否在密封迁移任务上安全提高一个冻结科学验证栈的
> 可执行覆盖率？

本项目不声称发明量纲分析、SymPy、Lean、RLVR、Agent 弃权或“验证边界”概念。拟议贡献
是把这些组成部分集成为一个前瞻性实验：

- 带类型的覆盖缺口；
- 有边界的规格/验证器提案；
- 所有者与独立专家 AI 双重批准；
- 正例、反例和失效闭合的可执行测试；
- 隐藏迁移样本与成对安全陷阱；
- 回滚和覆盖增量记录。

提交物是环境与验证信号，不声称科学发现、递归自我改进、模型能力或 AGI。

<!-- PAGE 2 -->

## 2. 探索环境

基础环境输出三值结果：

| 结果 | 合同含义 |
|---|---|
| `accepted` | 适用的确定性检查确认候选成立 |
| `rejected` | 适用检查确认了具体错误 |
| `abstain` | 没有适用的可执行检查能够判断；绝不静默通过 |

v2 状态机为：

```text
观察 -> 提案 -> 验证
  accepted：保留
  rejected：修正或停止
  abstain：分类缺口 -> 提出有边界扩展
    -> 所有者 + 专家 AI 审批 -> 执行测试
    -> 重新验证 -> 局部激活或继续弃权
```

模型不能批准自己的扩展；看过汇总确认性结果的评审不计入审批；开放问题控制项永远不能被
提升为 accepted。

三个确定性领域：

- **物理：** SI 量、仿射单位、向量、不确定度、守恒残差与参考系；
- **符号数学：** 定义域、假设、奇点、分段边界与不等式方向；
- **Lean：** 固定 Lean 4.24.0 + Mathlib 内核检查，并显式核对自然语言/形式合同。

公开免登录 Demo 只暴露公共验证器、参照 episode、合成审批流程与 seal 元数据，绝不暴露
密封任务、答案或凭证。

内容寻址证据 DAG：

```text
proposal# -> owner-review# + expert-AI-review# -> typed-tests# -> activation#
          -> transfer# -> protected-suite# -> rollback# -> extension-chain#
```

<!-- PAGE 3 -->

## 3. 预注册评测与当前里程碑

### 目标确认性设计

主计分 benchmark 为 **144 个任务 / 72 个匹配对**，另设 120 个任务的辅助迁移包：

| 组成 | 物理 | 符号数学 | Lean | 总计 |
|---|---:|---:|---:|---:|
| frontier 有效项+安全项匹配对 | 20 | 20 | 20 | 60 |
| 辅助迁移有效项+安全项匹配对 | 20 | 20 | 20 | 60 |
| 已覆盖控制匹配对 | 4 | 4 | 4 | 12 |
| 完整研究任务数 | 88 | 88 | 88 | 264 |

60 个主计分 frontier 匹配对必须来自 **30 个独立扩展/生成器家族**。每个家族含两个
主计分匹配对，并另设两个不进入 SFPA 分母的密封迁移匹配对，共增加 120 个迁移任务；
完整研究语料为 264 个任务。统计推断按家族聚类，而不是把迁移任务、参数变体或模型
replicate 当成独立样本。

主指标为 **安全边界匹配对准确率（SFPA）**。只有当有效项被机器正确判断、安全项被拒绝或
弃权、且相关扩展通过迁移与回归门时，该匹配对才算成功。

预注册的 winner-level 门槛：

- 60 个 frontier 安全项中零不安全接受；
- 相对最强非 oracle 基线的 `delta_SFPA >= +20 个百分点`；
- 95% 分层 cluster bootstrap 置信区间下界大于 0；
- 成对 sign-flip 检验 `p < 0.05`；
- 每个必需模型家族都相对其最强非 oracle 基线取得正点估计；
- 每个计分扩展通过两个密封有效迁移任务及其配对安全任务；
- 已覆盖控制集与受保护测试集无回归。

### 截至 2026 年 8 月 1 日已完成

- 紧凑 v1 Demo 与确定性参照策略：可运行；
- 公共开发/回归包：150 行，每领域 50 行；
- 公共 Stage A 计划：**24 个家族（每领域 8 个）**，30 个公共 frontier-gap
  任务均仅绑定一次哈希，3 个 Lean 开放问题控制项不可提升，并冻结
  正例/反例/畸形输入/安全/回滚测试计划；
- **唯一一次授权的 24 家族 Stage A 开发运行已完成（Pro6000 Blackwell，
  Qwen2.5-7B-Instruct，运行 `30742115988`）：8/8/8 家族平衡，23/24 结构化
  输出有效，1 条格式错误的 Lean 响应被原样保留，2/2 开放控制保持为不可晋升
  弃权，七类策略违规计数全部为零**——仅为结构化输出/策略合规证据，非验证器
  扩展或能力结果；
- 真实 Lean 验证：开发包 **150/150** 有效；
- 内容寻址 receipt 协议：**3 条链 / 34 个 receipt / 60 个证据 blob**；
- 确定性对抗 receipt benchmark：**7/7** 通过；
- CPU-only Protocol Twin：**B0-B6 / 8 个消融组 / 13 个显式变体 / 2,160 个
  确定性执行单元**，含 108 条冻结 trajectory，模型调用与网络调用均为 0；
- 开发态 Study Root v3：**756 条构造 arm 结果 / 108 条 B6 fixture /
  1,404 条构造消融结果 / 6 条后代迁移执行 receipt / 同一有效 DAG 拓扑的
  24 个序列化变体 + 164 个无效变异 / 24,000 次 scorer 模拟 + 12 个负对照**；
- 合成 rehearsal：144 个任务 / 72 对，明确标记
  `confirmatoryEligible:false`；
- rehearsal 验证：**144/144**，包括 48 个 Lean 项，但只有 15 个生成器家族，并存在
  已知结构泄漏与重复 prompt；
- Z.AI GLM 直接开发 smoke：成功，无跨 provider fallback。
- Pro6000 守护通道：先验证存储再接触 CUDA，固定经审查的 7B 本地模型与不可变
  revision，精确 holder 的 GPU claim/release，并输出严格提案合规 receipt；
  开发提案运行已完成，但尚未纳入任何审批、测试、激活或确认性结果。

以上只证明基础设施机制；没有确认性 seal 或确认性结果。

Study Root v3 已绑定完整的构造结果清单与后代迁移执行 receipt，因此开发态 scorer
可报告 `studyRootBound:true`、`constructedB6FixtureRowsValidated:true`、
`constructedAblationFixtureRowsValidated:true` 与
`transferExecutionReceiptsValidated:true`。由于尚无真实确认性研究，它仍固定报告
`studyRootScorerInputsBound:false`、`actualB6RowsValidated:false`、
`actualAblationRowsValidated:false`、`protocolValid:false`、
`winnerLevelEligible:false` 与 `winnerLevelGateMet:false`。当前模拟仅为低重采样
实现 smoke，不是确认性 power 或 MDE 证据。

若出现任一不安全接受、任一必需模型家族相对其最强基线为负、任一 receipt 断链、已覆盖
控制集回归，或 CI / p-value 门未通过，则 winner-level 结论被证伪。

<!-- PAGE 4 -->

## 4. 基线、创新边界、披露与后续

必需实验臂包括：原始模型；固定三值验证器；固定验证器+等预算修正；仅作答/弃权而无可执行
扩展；等预算纯人工扩展；拟议的人类审批系统；专家编写 oracle ceiling。关键消融包括移除
人类审批、可执行 patch、迁移义务、显式弃权，以及逐个移除验证层。

已提交的 CPU-only twin 会在构造 fixture 上执行完整协议形状，并对缺失实验臂、缺失消融
变体、replay 哈希漂移或预算不对称失效闭合；它不是有效性实验。

直接相关工作包括 RLVP（arXiv:2607.10474）、EG-VAR（arXiv:2607.12650）、
Recursive Epistemic Engines 的 Novelty Horizon，以及 AgentAbstain
（arXiv:2607.10059）。最大的创新风险来自既有“受保护验证器扩展”工作。因此，可辩护贡献
是前瞻性实证与可复现仪器，而不是宣称发明验证边界。

**预先存在的 Sophia 基础设施：** SI 与符号验证器、Lean 检查/评测、来源与防过度声明门、
既有候选阶梯证据。<br/>
**竞赛期新增：** 三值环境包装、typed frontier 协议、匹配对生成器与 seal、内容寻址
receipt 协议、人类审批合同、模型 runner、统计程序、双语材料与 hosted-demo 包。
竞赛期工作还包括 24 家族 Stage A 计划与带 GPU claim/存储边界的本地模型通道。

当前建议为：**确认性执行 NO-GO；作为基础设施提案参加初赛为 CONDITIONAL GO**。只有在
真正私有的 30 家族 benchmark、提示、模型、预算与扩展 bundle 全部冻结，并以真实独立审批、
隐藏迁移、受保护套件与回滚执行实例化 receipt 协议后，才能开始确认性模型评分。

```bash
./run_all.sh
python3 v2/build_stage_a_result.py --check
python3 v2/validate_confirmatory_pack.py --lean-project <pinned-project> --require-lean
```

限制：尚无确认性 benchmark 或有效性结果；当前 rehearsal 是人工构造且结构已泄漏；
Stage A 开发提案运行已完成（23/24，1 条格式错误响应被保留），但所有者/专家 AI 决策与
可执行扩展测试尚未完成；仍需人类与领域专家评审。
`candidateOnly:true`，`canClaimAGI:false`，`winnerLevelEligible:false`，
`winnerLevelGateMet:false`。
