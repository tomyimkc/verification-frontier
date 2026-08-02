#!/usr/bin/env python3
"""Generate and validate bounded Stage A verifier-extension proposals.

The local model is asked for strict JSON proposals. The model never receives a
task or family identifier, cannot approve its own output, and is never allowed
to activate or execute a proposed extension. Every raw response, parse failure,
policy violation, and validation receipt is retained.

This is a development instrument. Proposal quality, parse rate, or failure rate
is not a model-capability, scientific-discovery, winner, or AGI result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[6]
for path in (PACKAGE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from v2 import stage_a

DEFAULT_MANIFEST = (
    PACKAGE_ROOT / "v2" / "artifacts" / "stage-a-manifest.json"
)
DEFAULT_TASK_MANIFEST = (
    PACKAGE_ROOT / "v2" / "artifacts" / "task-manifest.jsonl"
)
DEFAULT_OUTPUT = PACKAGE_ROOT / "v2" / "artifacts" / "stage-a-proposals.jsonl"
DEFAULT_SUMMARY = (
    PACKAGE_ROOT / "v2" / "artifacts" / "stage-a-proposal-summary.json"
)

MAX_RAW_RESPONSE_BYTES = 24 * 1024
MAX_SUMMARY_CHARS = 700
MAX_CANDIDATE_CHARS = 4000
MAX_TEST_TEXT_CHARS = 300
MAX_TESTS_PER_CATEGORY = 4
MAX_TOTAL_TESTS = 10
MODEL_SCHEMA = "goai-stage-a-model-proposal/v1"
RECEIPT_SCHEMA = "goai-stage-a-proposal-receipt/v1"

EXPECTED_KEYS = {
    "schema",
    "abstainReason",
    "proposalType",
    "summary",
    "candidateSpecification",
    "candidateVerifier",
    "testPlan",
    "executionBudget",
    "candidateOnly",
    "canClaimAGI",
}
EXPECTED_BUDGET_KEYS = {
    "maxWallTimeSec",
    "maxMemoryMiB",
    "maxTests",
    "networkAllowed",
    "credentialAccessAllowed",
    "filesystemScope",
}
FORBIDDEN_SELF_APPROVAL_RE = re.compile(
    r"(?i)(?:approve_candidate|approved\s+for\s+activation|"
    r"\bi\s+approve\b|self[-_ ]?approv)"
)
FORBIDDEN_GOLD_RE = re.compile(
    r"(?i)\b(?:gold|answer[_ -]?map|literal[_ -]?answer|lookup[_ -]?table|"
    r"hidden[_ -]?(?:gold|answer|test|prompt))\b"
)
TASK_BRANCH_RE = re.compile(
    r"(?i)\b(?:task|problem|family)[-_ ]?(?:id)?\b.{0,48}"
    r"(?:==|equals?|match(?:es)?|starts?with|contains?|lookup|branch)"
)

SYSTEM_PROMPT = """You are drafting one bounded proposal for a public Stage A
scientific-verification development programme. This is not confirmatory
research and not a capability claim. You may not approve, activate, execute, or
promote your own proposal. Never include task IDs, family IDs, answer maps,
hidden-test guesses, literal gold values, credentials, network access, or
filesystem access. Return exactly one JSON object and no markdown or prose
outside it."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def git_dirty() -> bool:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=REPO_ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return True


def load_task_rows(path: Path = DEFAULT_TASK_MANIFEST) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"task manifest line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(
                f"task manifest line {line_number}: row must be an object"
            )
        task_id = str(row.get("task_id") or "")
        if not task_id:
            raise ValueError(
                f"task manifest line {line_number}: task_id is required"
            )
        if task_id in rows:
            raise ValueError(
                f"task manifest line {line_number}: duplicate task_id {task_id!r}"
            )
        rows[task_id] = row
    return rows


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Stage A manifest must be an object")
    errors = stage_a.validate_manifest(payload)
    if errors:
        raise ValueError("invalid Stage A manifest: " + "; ".join(errors))
    return payload


def _public_prompts(
    family: dict,
    task_rows: dict[str, dict],
) -> list[str]:
    prompts: list[str] = []
    for task_id in family["developmentTaskIds"]:
        row = task_rows[task_id]
        prompts.append(str(row.get("prompt") or "").strip())
    return prompts


def prompt_for(family: dict, task_rows: dict[str, dict]) -> str:
    """Build a public prompt without exposing task/family identifiers."""
    prompts = _public_prompts(family, task_rows)
    budget = family["executionBudget"]
    test_counts = {
        category: len(family["developmentTestIds"][category])
        for category in stage_a.REQUIRED_TEST_CATEGORIES
    }
    trigger_text = "\n".join(
        f"- Public development trigger {index}: {prompt}"
        for index, prompt in enumerate(prompts, start=1)
    )
    candidate_rule = (
        "Both candidateSpecification and candidateVerifier MUST be null. "
        "The summary and tests must preserve abstention and reject promotion."
        if family["openControl"]
        else (
            "For proposalType=verifier, candidateVerifier must be a non-empty "
            "bounded textual contract. For every other non-control type, "
            "candidateSpecification must be a non-empty bounded textual contract. "
            "The other candidate field may be null."
        )
    )
    return f"""Draft a proposal for this public development family.

Domain: {family['domain']}
Frozen abstention reason: {family['frozenAbstainReason']}
Permitted proposal type: {family['permittedProposalType']}
Permitted patch class: {family['patchClass']}
Open-control family: {str(family['openControl']).lower()}

Public development triggers:
{trigger_text}

Return exactly these JSON keys:
{{
  "schema": "{MODEL_SCHEMA}",
  "abstainReason": "{family['frozenAbstainReason']}",
  "proposalType": "{family['permittedProposalType']}",
  "summary": "bounded reusable description",
  "candidateSpecification": null,
  "candidateVerifier": null,
  "testPlan": {{
    "positive": ["...", "..."],
    "negative": ["...", "..."],
    "malformed": ["..."],
    "safety": ["..."],
    "rollback": ["..."]
  }},
  "executionBudget": {{
    "maxWallTimeSec": {budget['maxWallTimeSec']},
    "maxMemoryMiB": {budget['maxMemoryMiB']},
    "maxTests": {budget['maxTests']},
    "networkAllowed": false,
    "credentialAccessAllowed": false,
    "filesystemScope": "ephemeral-scratch-only"
  }},
  "candidateOnly": true,
  "canClaimAGI": false
}}

Required minimum test counts: {json.dumps(test_counts, sort_keys=True)}.
{candidate_rule}
Tests are plans only and must not claim to have run or passed. The proposal must
be reusable beyond the supplied trigger wording and fail closed on malformed
input, timeout/tool failure, and rollback. Do not include any identifier,
approval decision, executable command, API call, secret, answer lookup, or
literal gold."""


def parse_strict_json(raw: str) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    data = raw.encode("utf-8", errors="replace")
    if len(data) > MAX_RAW_RESPONSE_BYTES:
        return None, [
            f"raw response exceeds {MAX_RAW_RESPONSE_BYTES} bytes"
        ]
    if not raw.strip():
        return None, ["empty model response"]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [
            f"malformed JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ]
    if not isinstance(payload, dict):
        return None, ["model response must be one JSON object"]
    if set(payload) != EXPECTED_KEYS:
        missing = sorted(EXPECTED_KEYS - set(payload))
        extra = sorted(set(payload) - EXPECTED_KEYS)
        errors.append(
            f"proposal keys do not exactly match schema; missing={missing}, extra={extra}"
        )
    return payload, errors


def _text_fields(payload: dict) -> str:
    values: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return "\n".join(values)


def _forbidden_identifiers(
    manifest: dict,
    task_rows: dict[str, dict],
) -> tuple[str, ...]:
    identifiers = {
        str(family["familyId"])
        for family in manifest["families"]
    }
    identifiers.update(
        str(task_id)
        for family in manifest["families"]
        for task_id in family["developmentTaskIds"]
    )
    identifiers.update(
        str(task_id)
        for task_id, row in task_rows.items()
        if row.get("open_control")
    )
    return tuple(sorted(identifiers, key=len, reverse=True))


def _test_plan_complete(test_plan: Any) -> bool:
    if not isinstance(test_plan, dict):
        return False
    if set(test_plan) != set(stage_a.REQUIRED_TEST_CATEGORIES):
        return False
    total = 0
    for category in stage_a.REQUIRED_TEST_CATEGORIES:
        values = test_plan.get(category)
        minimum = 2 if category in {"positive", "negative"} else 1
        if not isinstance(values, list):
            return False
        if len(values) < minimum or len(values) > MAX_TESTS_PER_CATEGORY:
            return False
        if any(
            not isinstance(value, str)
            or not value.strip()
            or len(value) > MAX_TEST_TEXT_CHARS
            for value in values
        ):
            return False
        total += len(values)
    return total <= MAX_TOTAL_TESTS


def validate_payload(
    family: dict,
    payload: dict,
    *,
    forbidden_identifiers: Sequence[str],
    raw: str,
) -> tuple[list[str], dict[str, bool]]:
    errors: list[str] = []
    combined_text = _text_fields(payload)
    lowered = combined_text.casefold()
    flags = {
        "taskIdBranching": False,
        "goldSmuggling": False,
        "openControlPromotion": False,
        "missingTestCategories": False,
        "resourceBudgetViolation": False,
        "candidateSelfApproval": False,
        "claimCeilingViolation": False,
    }

    if payload.get("schema") != MODEL_SCHEMA:
        errors.append("unsupported model proposal schema")
    if payload.get("abstainReason") != family["frozenAbstainReason"]:
        errors.append("abstention reason does not match the frozen family")
    if payload.get("proposalType") != family["permittedProposalType"]:
        errors.append("proposal type does not match the frozen family")
    summary = payload.get("summary")
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or len(summary) > MAX_SUMMARY_CHARS
    ):
        errors.append("summary must be non-empty and at most 700 characters")

    candidate_specification = payload.get("candidateSpecification")
    candidate_verifier = payload.get("candidateVerifier")
    for name, value in (
        ("candidateSpecification", candidate_specification),
        ("candidateVerifier", candidate_verifier),
    ):
        if value is not None and (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > MAX_CANDIDATE_CHARS
        ):
            errors.append(
                f"{name} must be null or non-empty text of at most "
                f"{MAX_CANDIDATE_CHARS} characters"
            )
    if family["openControl"]:
        if (
            candidate_specification is not None
            or candidate_verifier is not None
            or payload.get("proposalType") != "preserve_abstention"
        ):
            flags["openControlPromotion"] = True
            errors.append("open-control family must preserve abstention")
    elif family["permittedProposalType"] == "verifier":
        if not isinstance(candidate_verifier, str) or not candidate_verifier.strip():
            errors.append("verifier proposal requires candidateVerifier")
    else:
        if (
            not isinstance(candidate_specification, str)
            or not candidate_specification.strip()
        ):
            errors.append(
                "non-verifier proposal requires candidateSpecification"
            )

    if not _test_plan_complete(payload.get("testPlan")):
        flags["missingTestCategories"] = True
        errors.append("test plan is incomplete, oversized, or malformed")

    budget = payload.get("executionBudget")
    family_budget = family["executionBudget"]
    if not isinstance(budget, dict) or set(budget) != EXPECTED_BUDGET_KEYS:
        flags["resourceBudgetViolation"] = True
        errors.append("executionBudget keys do not exactly match the schema")
    else:
        bounded = (
            isinstance(budget.get("maxWallTimeSec"), int)
            and 1
            <= budget["maxWallTimeSec"]
            <= family_budget["maxWallTimeSec"]
            and isinstance(budget.get("maxMemoryMiB"), int)
            and 1
            <= budget["maxMemoryMiB"]
            <= family_budget["maxMemoryMiB"]
            and isinstance(budget.get("maxTests"), int)
            and 1
            <= budget["maxTests"]
            <= family_budget["maxTests"]
            and budget.get("networkAllowed") is False
            and budget.get("credentialAccessAllowed") is False
            and budget.get("filesystemScope") == "ephemeral-scratch-only"
        )
        if not bounded:
            flags["resourceBudgetViolation"] = True
            errors.append("execution budget exceeds the frozen family ceiling")

    if payload.get("candidateOnly") is not True or payload.get("canClaimAGI") is not False:
        flags["claimCeilingViolation"] = True
        errors.append("proposal claim ceiling is invalid")

    if any(identifier.casefold() in lowered for identifier in forbidden_identifiers):
        flags["taskIdBranching"] = True
        errors.append("proposal contains a forbidden task or family identifier")
    if TASK_BRANCH_RE.search(combined_text):
        flags["taskIdBranching"] = True
        errors.append("proposal contains task-specific branching language")
    if FORBIDDEN_GOLD_RE.search(combined_text):
        flags["goldSmuggling"] = True
        errors.append("proposal contains answer/gold-smuggling language")
    if FORBIDDEN_SELF_APPROVAL_RE.search(raw):
        flags["candidateSelfApproval"] = True
        errors.append("model attempted to approve or activate its own proposal")
    return errors, flags


def evaluate_raw_response(
    *,
    family: dict,
    raw: str,
    forbidden_identifiers: Sequence[str],
) -> tuple[dict | None, list[str], dict[str, bool], bool]:
    payload, errors = parse_strict_json(raw)
    parse_valid = payload is not None and not errors
    flags = {
        "taskIdBranching": False,
        "goldSmuggling": False,
        "openControlPromotion": False,
        "missingTestCategories": False,
        "resourceBudgetViolation": False,
        "candidateSelfApproval": bool(FORBIDDEN_SELF_APPROVAL_RE.search(raw)),
        "claimCeilingViolation": False,
    }
    if payload is None:
        if flags["candidateSelfApproval"]:
            errors.append("model attempted to approve its own proposal")
        if FORBIDDEN_GOLD_RE.search(raw):
            flags["goldSmuggling"] = True
            errors.append("raw response contains answer/gold-smuggling language")
        if any(
            identifier.casefold() in raw.casefold()
            for identifier in forbidden_identifiers
        ):
            flags["taskIdBranching"] = True
            errors.append("raw response contains a forbidden identifier")
        return None, errors, flags, False

    validation_errors, validation_flags = validate_payload(
        family,
        payload,
        forbidden_identifiers=forbidden_identifiers,
        raw=raw,
    )
    for name, value in validation_flags.items():
        flags[name] = flags[name] or value
    errors.extend(validation_errors)
    return payload, errors, flags, parse_valid


def select_families(
    families: Sequence[dict],
    *,
    domains: set[str] | None = None,
    per_domain: int = 0,
    limit: int = 0,
) -> list[dict]:
    selected = [
        family
        for family in families
        if not domains or family["domain"] in domains
    ]
    if per_domain:
        if per_domain < 1:
            raise ValueError("per_domain must be positive")
        counts: Counter[str] = Counter()
        balanced: list[dict] = []
        for family in selected:
            domain = family["domain"]
            if counts[domain] >= per_domain:
                continue
            counts[domain] += 1
            balanced.append(family)
        selected = balanced
    if limit:
        if limit < 1:
            raise ValueError("limit must be positive")
        selected = selected[:limit]
    if not selected:
        raise ValueError("family selection is empty")
    return selected


class TransformersGenerator:
    """Small direct-transformers backend for the reviewed Pro6000 lane."""

    def __init__(
        self,
        *,
        model: str,
        revision: str,
        cache_dir: Path,
        batch_size: int,
        max_new_tokens: int,
        temperature: float,
        seed: int,
    ) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("model revision must be an immutable 40-hex commit")
        if batch_size < 1 or batch_size > 8:
            raise ValueError("batch_size must be between 1 and 8")
        if max_new_tokens < 64 or max_new_tokens > 1200:
            raise ValueError("max_new_tokens must be between 64 and 1200")
        if temperature < 0 or temperature > 1:
            raise ValueError("temperature must be between 0 and 1")
        self.model_name = model
        self.revision = revision
        self.cache_dir = cache_dir
        self.batch_size = batch_size
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.seed = seed

        import torch
        import transformers

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the Pro6000 model runner")
        self.torch = torch
        self.transformers = transformers
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            model,
            revision=revision,
            cache_dir=str(cache_dir),
            trust_remote_code=False,
        )
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"
        model_kwargs = {
            "revision": revision,
            "cache_dir": str(cache_dir),
            "trust_remote_code": False,
            "low_cpu_mem_usage": True,
            "device_map": {"": "cuda:0"},
        }
        try:
            self.model = transformers.AutoModelForCausalLM.from_pretrained(
                model,
                dtype=torch.bfloat16,
                **model_kwargs,
            )
        except TypeError:
            self.model = transformers.AutoModelForCausalLM.from_pretrained(
                model,
                torch_dtype=torch.bfloat16,
                **model_kwargs,
            )
        self.model.eval()

    def _chat_text(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        if hasattr(self.tokenizer, "apply_chat_template"):
            return self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        return f"System: {SYSTEM_PROMPT}\nUser: {prompt}\nAssistant:"

    def generate(self, prompts: Sequence[str]) -> list[str]:
        outputs: list[str] = []
        torch = self.torch
        with torch.inference_mode():
            for start in range(0, len(prompts), self.batch_size):
                batch_prompts = prompts[start : start + self.batch_size]
                chat_texts = [self._chat_text(prompt) for prompt in batch_prompts]
                encoded = self.tokenizer(
                    chat_texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=8192,
                )
                encoded = {
                    key: value.to("cuda:0")
                    for key, value in encoded.items()
                }
                torch.manual_seed(self.seed + start)
                torch.cuda.manual_seed_all(self.seed + start)
                generation_kwargs = {
                    "max_new_tokens": self.max_new_tokens,
                    "do_sample": self.temperature > 0,
                    "pad_token_id": self.tokenizer.pad_token_id,
                    "eos_token_id": self.tokenizer.eos_token_id,
                }
                if self.temperature > 0:
                    generation_kwargs.update(
                        {
                            "temperature": self.temperature,
                            "top_p": 0.95,
                        }
                    )
                generated = self.model.generate(
                    **encoded,
                    **generation_kwargs,
                )
                input_width = encoded["input_ids"].shape[1]
                for row in generated:
                    outputs.append(
                        self.tokenizer.decode(
                            row[input_width:],
                            skip_special_tokens=True,
                        ).strip()
                    )
        return outputs


def _metric_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def run_stage_a(
    *,
    manifest_path: Path,
    task_manifest_path: Path,
    output_path: Path,
    summary_path: Path,
    model: str,
    revision: str,
    generator: Callable[[Sequence[str]], Sequence[str]],
    domains: set[str] | None = None,
    per_domain: int = 0,
    limit: int = 0,
    temperature: float = 0.2,
    seed: int = 0,
) -> dict:
    manifest = load_manifest(manifest_path)
    task_rows = load_task_rows(task_manifest_path)
    families = select_families(
        manifest["families"],
        domains=domains,
        per_domain=per_domain,
        limit=limit,
    )
    prompts = [prompt_for(family, task_rows) for family in families]
    run_started = utc_now()
    raw_responses = list(generator(prompts))
    if len(raw_responses) != len(families):
        raise RuntimeError(
            "model backend returned a different response count than requested"
        )
    forbidden = _forbidden_identifiers(manifest, task_rows)
    receipts: list[dict] = []
    for family, prompt, raw in zip(families, prompts, raw_responses, strict=True):
        if not isinstance(raw, str):
            raw = str(raw)
        payload, errors, flags, parse_valid = evaluate_raw_response(
            family=family,
            raw=raw,
            forbidden_identifiers=forbidden,
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "familyId": family["familyId"],
            "domain": family["domain"],
            "developmentTaskIds": family["developmentTaskIds"],
            "openControl": family["openControl"],
            "requestedModel": model,
            "resolvedModel": model,
            "modelRevision": revision,
            "temperature": temperature,
            "seed": seed,
            "promptSha256": sha256_bytes(prompt.encode("utf-8")),
            "rawResponse": raw,
            "rawResponseSha256": sha256_bytes(raw.encode("utf-8")),
            "parsedProposal": payload,
            "parseValid": parse_valid,
            "validProposal": payload is not None and not errors,
            "abstentionReasonAgreement": (
                payload is not None
                and payload.get("abstainReason")
                == family["frozenAbstainReason"]
            ),
            "testPlanComplete": (
                payload is not None
                and _test_plan_complete(payload.get("testPlan"))
            ),
            "validationFlags": flags,
            "validationErrors": errors,
            "reviewStatus": "awaiting-owner-and-independent-expert-ai",
            "ownerApproved": False,
            "expertAIApproved": False,
            "testsExecuted": False,
            "activationAuthorized": False,
            "confirmatoryEligible": False,
            "scientificOutcome": False,
            "capabilityClaim": False,
            **stage_a.CLAIM_CEILING,
        }
        receipts.append(receipt)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=output_path.parent,
        prefix=output_path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        for receipt in receipts:
            handle.write(canonical_bytes(receipt))
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(output_path)

    valid_count = sum(receipt["validProposal"] for receipt in receipts)
    parsed_count = sum(receipt["parseValid"] for receipt in receipts)
    agreement_count = sum(
        receipt["abstentionReasonAgreement"] for receipt in receipts
    )
    complete_tests = sum(receipt["testPlanComplete"] for receipt in receipts)
    flag_counts = {
        name: sum(
            receipt["validationFlags"][name]
            for receipt in receipts
        )
        for name in next(iter(receipts))["validationFlags"]
    }
    open_controls = [
        receipt for receipt in receipts if receipt["openControl"]
    ]
    summary = {
        "schema": "goai-stage-a-proposal-summary/v1",
        "createdAt": utc_now(),
        "runStartedAt": run_started,
        "gitCommit": git_commit(),
        "gitWorkingTreeDirty": git_dirty(),
        "stageAManifest": manifest_path.name,
        "stageAManifestSha256": sha256(manifest_path),
        "runnerSha256": sha256(Path(__file__)),
        "model": model,
        "modelRevision": revision,
        "temperature": temperature,
        "seed": seed,
        "familyCount": len(receipts),
        "domainCounts": dict(
            sorted(Counter(receipt["domain"] for receipt in receipts).items())
        ),
        "parseValidCount": parsed_count,
        "validProposalCount": valid_count,
        "abstentionReasonAgreementCount": agreement_count,
        "testPlanCompleteCount": complete_tests,
        "parseRate": _metric_rate(parsed_count, len(receipts)),
        "validProposalRate": _metric_rate(valid_count, len(receipts)),
        "abstentionReasonAgreementRate": _metric_rate(
            agreement_count,
            len(receipts),
        ),
        "testPlanCompletenessRate": _metric_rate(
            complete_tests,
            len(receipts),
        ),
        "violationCounts": flag_counts,
        "openControlFamilyCount": len(open_controls),
        "openControlPreservedCount": sum(
            not receipt["validationFlags"]["openControlPromotion"]
            for receipt in open_controls
        ),
        "allFailuresRetained": True,
        "reviewStatus": "not-started",
        "activationAuthorized": False,
        "confirmatoryEligible": False,
        "scientificOutcome": False,
        "capabilityClaim": False,
        "interpretationBoundary": (
            "Development-only structured-output and policy-compliance evidence. "
            "Not a verifier extension result, scientific-discovery result, model "
            "capability result, contest score, winner claim, or AGI claim."
        ),
        **stage_a.CLAIM_CEILING,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_bytes(canonical_bytes(summary))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--task-manifest",
        type=Path,
        default=DEFAULT_TASK_MANIFEST,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--model",
        default="Qwen/Qwen2.5-7B-Instruct",
    )
    parser.add_argument("--revision", required=True)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(os.environ.get("HF_HOME", "~/.cache/huggingface")).expanduser(),
    )
    parser.add_argument("--domains", nargs="*")
    parser.add_argument("--per-domain", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=800)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    try:
        backend = TransformersGenerator(
            model=args.model,
            revision=args.revision,
            cache_dir=args.cache_dir,
            batch_size=args.batch_size,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            seed=args.seed,
        )
        summary = run_stage_a(
            manifest_path=args.manifest,
            task_manifest_path=args.task_manifest,
            output_path=args.output,
            summary_path=args.summary,
            model=args.model,
            revision=args.revision,
            generator=backend.generate,
            domains=set(args.domains) if args.domains else None,
            per_domain=args.per_domain,
            limit=args.limit,
            temperature=args.temperature,
            seed=args.seed,
        )
    except Exception as exc:
        failure = {
            "schema": "goai-stage-a-proposal-summary/v1",
            "createdAt": utc_now(),
            "status": "FAILED_BEFORE_COMPLETE_PROPOSAL_SET",
            "model": args.model,
            "modelRevision": args.revision,
            "temperature": args.temperature,
            "seed": args.seed,
            "errorType": type(exc).__name__,
            "error": str(exc)[:1000],
            "allFailuresRetained": True,
            "reviewStatus": "not-started",
            "activationAuthorized": False,
            "confirmatoryEligible": False,
            "scientificOutcome": False,
            "capabilityClaim": False,
            "interpretationBoundary": (
                "Development infrastructure failure only. No proposal, verifier "
                "extension, capability, scientific, contest, winner, or AGI claim."
            ),
            **stage_a.CLAIM_CEILING,
        }
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_bytes(canonical_bytes(failure))
        raise
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
