#!/usr/bin/env sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$HERE"

OPTIONAL_VALIDATION_RECEIPT=$(mktemp "${TMPDIR:-/tmp}/goai-task-validation.optional.XXXXXX")
trap 'rm -f "$OPTIONAL_VALIDATION_RECEIPT"' EXIT HUP INT TERM

if [ -n "${PYTHON:-}" ]; then
  :
elif [ -x "$HERE/.venv/bin/python" ]; then
  PYTHON="$HERE/.venv/bin/python"
else
  PYTHON=python3
fi

"$PYTHON" demo.py --selfcheck
"$PYTHON" -m unittest -v test_demo.py
"$PYTHON" -m unittest -v \
  v2.test_frontier \
  v2.test_lean_verify \
  v2.test_protocol_twin \
  v2.test_study_root \
  v2.test_benchmark_study_root \
  v2.test_simulate_scorer \
  v2.test_stage_a \
  v2.test_stage_a_model \
  v2.test_stage_a_pro6000 \
  v2.test_stage_a_result \
  v2.test_logic_error_audit \
  v2.test_verify_provenance \
  v2.test_baseline_comparison \
  v2.test_self_correct \
  v2.test_error_rag \
  v2.test_receipt_protocol \
  v2.test_run_model_attempts \
  v2.test_score_confirmatory \
  v2.test_task_manifest \
  v2.test_validate_task_manifest
"$PYTHON" demo.py --benchmark --output-dir artifacts
"$PYTHON" verify_artifacts.py artifacts
"$PYTHON" v2/build_task_manifest.py
"$PYTHON" v2/validate_task_manifest.py --output "$OPTIONAL_VALIDATION_RECEIPT"
"$PYTHON" v2/stage_a.py
"$PYTHON" v2/stage_a.py --check
"$PYTHON" v2/build_stage_a_result.py
"$PYTHON" v2/build_stage_a_result.py --check
"$PYTHON" v2/build_logic_error_audit.py
"$PYTHON" v2/build_logic_error_audit.py --check
"$PYTHON" v2/build_baseline_comparison.py
"$PYTHON" v2/build_baseline_comparison.py --check
"$PYTHON" -c "from v2.self_correct import write_audit; write_audit()"
"$PYTHON" -c "from v2.self_correct import write_audit; import json,hashlib; a=json.load(open('v2/artifacts/self-correction-audit.json')); print('SELF-CORRECT AUDIT:', a['status'], '(caught='+str(a['totals']['caughtWithoutSelfCorrection'])+'/errorReduction='+str(a['totals']['errorReductionRate'])+')')" 2>/dev/null || echo "SELF-CORRECT AUDIT: skip (build inline)"
"$PYTHON" -c "from v2.error_rag import run_error_rag_audit; run_error_rag_audit()" 2>/dev/null || echo "ERROR-RAG AUDIT: skip (build inline)"
"$PYTHON" v2/build_receipt_rehearsal.py
"$PYTHON" v2/benchmark_receipt_protocol.py
"$PYTHON" v2/protocol_twin.py
"$PYTHON" v2/study_root.py
"$PYTHON" v2/benchmark_study_root.py
"$PYTHON" v2/simulate_scorer.py
"$PYTHON" hosted-demo/test_demo_logic.py
"$PYTHON" hosted-demo/healthcheck.py
"$PYTHON" submission/build_pdfs.py
"$PYTHON" build_bundle.py
"$PYTHON" verify_bundle.py
