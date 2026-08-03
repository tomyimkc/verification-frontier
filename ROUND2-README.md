# 复赛可运行环境 / Round-2 Runnable Environment

> **GOAI 2026 前沿探索 / AI for Research — Open Exploration — Round 2 (复赛)**
>
> 复赛要求：最小可运行探索环境、至少一次完整运行日志、参照系设计、README 与复现说明。
> Round-2 requirement: minimal runnable exploration environment, at least one complete
> execution log, baseline designs, README, and reproduction instructions.

---

## 一键复现 / One-Command Reproduction

```bash
# 全量确定性证据——一条命令运行所有模块
python3 v2/run_full_evidence.py

# 或分步运行（等价）
./run_all.sh
```

这会运行 201+ 个确定性测试，覆盖逻辑错误捕获率、病态问题检测、基线比较、自我修正、
RAG 新颖错误识别、Stage A 校验，并生成一份完整的执行日志。

This runs 201+ deterministic tests covering logic-error catch-rate, ill-posedness
detection, baseline comparison, self-correction, RAG novel-error ID, Stage A validation,
and produces a complete execution log.

---

## 探索环境 / Exploration Environment

### 环境接口

| 维度 | 内容 |
|---|---|
| **观察 (Observe)** | 候选推理步骤或待求解问题描述 |
| **行动 (Act)** | (1) 判定 accepted/rejected/abstain；(2) 提议新检查器 |
| **反馈 (Feedback)** | 确定性验证器即时返回裁决 + 原因码 |
| **固定 (Fixed)** | 三态判定；基础验证器冻结；开放问题永不晋升；模型不能自我批准 |
| **可变 (Changeable)** | 覆盖边界——人类批准新检查器后扩展 |
| **预算 (Budget)** | 120s / 2048 MiB / 无网络 / 无凭证 / 临时 scratch |

### 验证器层级 / Verifier Tiers

| 层级 | 检查什么 | 模块 |
|---|---|---|
| SI 物理 | 量纲与数值 | `demo.py:verify_physics` |
| SymPy 符号 | 表达式等价 | `demo.py:verify_math` |
| Lean 证明 | 内核证明 + 占位符拒绝 | `demo.py:verify_problem` |
| 病态性检测 | 矛盾系统/缺失约束/循环依赖/悖论 | `v2/verify_ill_posed.py` |
| 良构确认 | 方程组唯一解/算术 | `v2/verify_well_posed.py` |
| 归因验证 | 哲学归因真伪 | `v2/verify_provenance.py` |

---

## 完整运行日志 / Complete Execution Log

执行 `v2/run_full_evidence.py` 后，日志位于：

- **逐模块日志：** `v2/artifacts/execution-log.jsonl`
- **汇总：** `v2/artifacts/execution-summary.json`

### 关键指标 / Key Metrics

| 指标 | 结果 | 证明什么 |
|---|---|---|
| 逻辑错误捕获率 | **67/67 (100%)** | 确定性验证器捕获全部已植入逻辑错误 |
| 病态问题弃权率 | **30/30 (100%)** | 检测器正确弃权全部不可解问题 |
| 良构误判率 | 10/10 (100%) → **status=FAIL** | 诚实负结果：检测器无法确认自由文本良构性 |
| 基线比较：proposed-system | catchRate=1.0, unsafeAccepts=0 | 同时优于全部三个参照 |
| 自我修正错误下降率 | 83.6% | 修正棘轮有效（SI/SymPy 100%修正成功） |
| RAG 新颖错误捕获 | 4/5 would-catch | 1 个 fail-closed（无匹配模式→不提议） |
| Stage A (GPU) | 23/24 parse-valid | 真实 Qwen2.5-7B 结构化输出合规 |

---

## 参照系设计 / Baseline Designs

四种策略在 83 个项目（67 个已植入错误 + 16 个正确答案）上比较：

| 策略 | 错误捕获率 | 不安全接受 | 覆盖率 | 判决准确率 |
|---|---|---|---|---|
| raw-model (无验证器) | 0% | 67 | 100% | 15.7% |
| always-abstain | 0% | 0 | 0% | 3.6% |
| always-accept | 0% | 67 | 100% | 15.7% |
| **proposed-system** | **100%** | **0** | 15.7% | **100%** |

proposed-system 是唯一同时拥有零不安全接受和 100% 捕获率的策略。

---

## 复现说明 / Reproduction Instructions

### 最低要求 / Minimum Requirements

- Python 3.12+
- 标准库（核心验证）
- SymPy（可选符号验证层；`pip install sympy`）

### 不需要 / Not Required

- ❌ GPU（核心证据全 CPU）
- ❌ 网络
- ❌ 模型凭证
- ❌ 登录

### 确定性保证 / Determinism Guarantee

- 两次连续 ZIP 构建字节相同
- 每个公开 JSON 携带声明边界
- 内容寻址 receipt DAG 可审计

---

## 发现信号总结 / Discovery Signals Summary

| 信号类型 | 发现 | 证据 |
|---|---|---|
| 正向发现 | RAG 提议的新检查器可捕获 4/5 新颖错误 | `v2/artifacts/error-rag-audit.json` |
| 异常 | 67 个已植入错误覆盖 7 个类别，全部捕获 | `v2/artifacts/logic-error-catch-rate.json` |
| 稳定负结果 | 检测器无法确认自由文本良构性 → false-alarm rate=100% | `v2/artifacts/ill-posed-audit.json` (status=FAIL) |
| 问题修正 | 确定性方法可检测病态性但不能确认良构性 | 问题边界被修正 |

负结果被明确允许——关键是能清晰解释探索过程说明了什么。
Negative results are explicitly permitted — the key is clearly explaining what the exploration process reveals.

---

`candidateOnly:true`; `canClaimAGI:false`.
