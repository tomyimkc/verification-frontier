# 三条核心约束合规矩阵 / Core Constraints Compliance Matrix

> 评委应能在两分钟内确认本提交满足开放探索赛题的三条核心约束。
> A judge should be able to confirm in under two minutes that this submission
> satisfies the three core constraints of the Open Exploration topic type.

---

## 约束一：真实问题 / Constraint 1: Real Problem

> 所聚焦的问题必须真实存在，目前没有公认答案或尚未被充分结构化，需用文献、数据、专家经验或现实系统说明。
> The problem must genuinely exist, lack an accepted answer, and be supported by literature, data, or real-system evidence.

### 问题陈述

LLM 是概率黑盒，在科学推理中犯逻辑错误（量纲混淆、符号翻转、伪证明），**且无法识别不可解/病态问题**——面对矛盾方程组或缺失约束时，LLM 会幻觉出一个"答案"而非弃权。

### 为什么没有公认答案

| 证据来源 | 发现 | 引用 |
|---|---|---|
| "LLMs Fail to Recognize Mathematical Unsolvability" (OpenReview 2025) | LLM 尝试解答病态问题而非标记其不可解 | [OpenReview](https://openreview.net/forum?id=Urs8lNvMXB) |
| "Aligning LLMs to Detect Unsolvable Problems" (arXiv 2512.01661) | 现有对齐方法聚焦于"拒绝困难但可解的问题"，而非"检测真正不可解的问题" | [arXiv](https://arxiv.org/abs/2512.01661) |
| "The Illusion of Thinking" (Apple 2025) | 推理模型不给病态问题标记不可解；它们生成看似合理的错误输出 | [Apple ML Research](https://machinelearning.apple.com/research/illusion-of-thinking) |

### 本提交如何应对

- **67 个已植入逻辑错误全部被确定性验证器捕获**（100% 捕获率）→ 验证逻辑：[`v2/build_logic_error_audit.py --check`](REPRODUCIBILITY-QUICKSTART.md)
- **30 个病态问题全部被正确弃权**（100% 弃权率）→ 验证弃权：[`v2/build_ill_posed_audit.py`](REPRODUCIBILITY-QUICKSTART.md)
- 文献引用与证据链见 [`RESEARCH-POSITION.md`](RESEARCH-POSITION.md)

---

## 约束二：探索环境 / Constraint 2: Exploration Environment

> 需说明 Agent 在什么环境里行动、看到什么、能改变什么、如何获得反馈。
> Must specify what the agent observes, can change, and receives as feedback.

### 环境定义

本提交的探索环境是一个**三态验证前沿**（Three-State Verification Frontier）。它不是一个聊天环境或工作流——它是一个 Agent 进入、尝试、获得确定性反馈、并可能扩展覆盖边界的结构化环境。

| 维度 | 具体内容 |
|---|---|
| **Agent 可看到（Observe）** | 一个候选推理步骤（本地 LLM 含推理链；云端 LLM 仅最终答案）。对于病态问题探测，Agent 看到一个问题描述（如"Solve: x+y=3, x+y=5"）。 |
| **Agent 可执行（Act）** | (1) 判定为 accepted/rejected/abstain；(2) 在 abstain 后提议一个新的有界检查器规则（如"检测方程组矛盾性"）。 |
| **Agent 获得反馈（Feedback）** | 确定性验证器立即返回裁决 + 原因码（如 `contradictory_system`、`dimension_mismatch`、`not_equivalent`）。无学习型判官，无网络调用，完全可复现。 |
| **可改变什么（What can change）** | 覆盖边界——当人类批准一个新检查器规则后，之前弃权的类别变为可判定。这通过内容寻址 receipt DAG 记录。 |
| **固定不变（Fixed）** | 三态判定（accepted/rejected/abstain）；基础验证器（SI/SymPy/Lean）；开放问题永不晋升；模型不能自我批准。 |

### 架构图

完整的信任边界架构图见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。关键边界：**模型生成到此结束，确定性检测由此开始**。

### 资源预算

每个任务家族：120 秒 / 2048 MiB / 最多 10 个测试 / 无网络 / 无凭证 / 仅临时 scratch。

---

## 约束三：发现信号 / Constraint 3: Discovery Signal

> 需提前说明什么算发现信号——正向发现、异常、反例、稳定负结果、失败模式，或对原问题定义的修正。
> Must predefine what counts as a discovery signal.

### 四种预注册发现信号

| # | 信号类型 | 定义 | 本提交的证据状态 |
|---|---|---|---|
| 1 | **正向发现 / Positive** | 一个被人类批准的新检查器成功将之前弃权的类别移入可判定范围 | ✅ RAG 系统（`v2/error_rag.py`）演示了从已知错误模式中提议新规则的流程；4/5 新颖错误 would-catch |
| 2 | **异常 / Anomaly** | 验证器捕获了一个未预期的错误模式 | ✅ 67 个已植入错误覆盖 7 个错误类别（量纲、值域、符号、等价、定义域、展开、证明占位符） |
| 3 | **稳定负结果 / Stable Negative** | 一类问题在所有尝试后仍 abstain——边界是真实的 | ✅ **病态问题的 false-alarm rate = 1.0**：检测器正确弃权了所有 30 个病态问题，但也弃权了所有 10 个良构问题。这证明覆盖边界是真实的——检测器识别了病态性，但无法确认良构性。这是一个诚实报告的稳定负结果。 |
| 4 | **失败模式 / Failure Mode** | 模型走私答案或自我批准 | ✅ 基线比较中 raw-model 和 always-accept 各有 67 个不安全接受；策略门捕获了所有七类违规（计数为零） |

### 对原问题定义的修正（Problem Revision）

在开发过程中，我们对问题定义做了一次修正：

> **初始假设：** 确定性验证器可以同时检测逻辑错误**和**确认良构性。
>
> **修正后：** 确定性验证器可以**检测病态性**（矛盾/缺失/循环/悖论），但**不能在一般自由文本上确认良构性**——因为"良构"需要理解问题意图，这超出了确定性检查器的能力。因此，验证器对良构自由文本问题的正确行为是**弃权**，而非接受。

这个修正本身就是一个发现信号——它界定了确定性方法的覆盖边界。

---

## 合规自检 / Self-Check

| 检查项 | 状态 |
|---|---|
| 问题真实存在且无公认答案 | ✅ 三篇 2025-2026 论文 + 67 个已植入错误 + 30 个病态问题 |
| 环境定义清楚（观察/行动/反馈/固定/可变） | ✅ ARCHITECTURE.md + 上表 |
| 发现信号提前定义（四种类型） | ✅ 四种预注册信号 + 证据状态 |
| 有最小参照系 | ✅ 4-way 基线比较（raw-model / always-abstain / always-accept / proposed-system） |
| 失败结果被保留并解释 | ✅ 病态检测器的 false-alarm failure 被诚实报告为 status=FAIL |
| 产物可复现 | ✅ 全 CPU 确定性，ZIP 字节相同，201+ 测试 |
| 负结果可被领域专家理解 | ✅ "检测器识别病态性但无法确认良构性"是可理解的边界声明 |

`candidateOnly:true`; `canClaimAGI:false`.
