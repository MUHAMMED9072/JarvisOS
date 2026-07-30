"""End-to-end validation of all 5 projects after hardening fixes."""
import sys, time, json, shutil
from pathlib import Path
from app.autonomy.build_orchestrator import BuildOrchestrator
from app.tools.git_tool import GitTool

PROJECTS = [
    ("Calculator library", "Build a complete Python calculator package with unit tests"),
    ("Key-Value Store", "Build a file-based key-value store with JSON persistence and pytest tests"),
    ("FastAPI CRUD API", "Build a FastAPI CRUD Todo API with SQLite storage and pytest tests"),
    ("CLI Password Manager", "Build a CLI password manager with encryption and pytest tests"),
    ("Markdown Doc Generator", "Build a markdown documentation generator with pytest tests"),
]

def clean_runtime():
    for d in ["runtime/build_checkpoints", "runtime/build_history", "runtime/installed"]:
        p = Path(d)
        if p.exists():
            for f in p.glob("*"):
                if f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
                else:
                    f.unlink(missing_ok=True)

def run_project(label: str, request: str) -> dict:
    clean_runtime()
    orch = BuildOrchestrator(git_tool=GitTool())
    t0 = time.time()
    result = orch.build(request)
    elapsed = time.time() - t0
    ads_stage = result.stages.get("ads_generate")
    ads_stages = []
    if ads_stage and ads_stage.output and "stages" in ads_stage.output:
        ads_stages = ads_stage.output["stages"]
    sandbox_ok = True
    test_tp = 0
    test_tf = 0
    for k, s in result.stages.items():
        out = s.output or {}
        if k == "sandbox":
            sandbox_ok = out.get("success", True)
        elif k == "test":
            test_tp = out.get("tests_passed", 0)
            test_tf = out.get("tests_failed", 0)
    registration_ok = all(
        st.get("status") != "failed" or "registration" not in st.get("stage_name", "")
        for st in ads_stages
    )
    return {
        "label": label,
        "status": result.status.name,
        "error": result.error,
        "duration_s": round(elapsed, 1),
        "sandbox_ok": sandbox_ok,
        "tests_passed": test_tp,
        "tests_failed": test_tf,
        "registration_ok": registration_ok,
        "commit_hash": result.commit_hash or "",
        "ai_calls": result.ai_calls,
        "sandbox_executions": result.sandbox_executions,
        "fix_attempts": result.fix_attempts,
        "stages": {k: {"status": s.status, "retries": s.retries, "duration_ms": round(s.duration_ms, 2)} for k, s in result.stages.items()},
        "artifact_path": result.artifact_path,
        "diagnostics": result.diagnostics,
    }

def print_summary(results):
    passed = 0
    failed = 0
    print(f"\n{'='*70}")
    print(f"{'VALIDATION RESULTS':^70}")
    print(f"{'='*70}")
    print(f"{'Project':30s} {'Status':10s} {'Tests':12s} {'Fix':6s} {'Time':8s}")
    print(f"{'-'*70}")
    for r in results:
        status = "PASS" if r["status"] == "COMPLETED" and r["error"] is None else "FAIL"
        tests = f"{r['tests_passed']}p/{r['tests_failed']}f" if r["tests_passed"] or r["tests_failed"] else "N/A"
        fix = f"{r['fix_attempts']}x" if r['fix_attempts'] else "-"
        print(f"{r['label']:30s} {status:10s} {tests:12s} {fix:6s} {r['duration_s']:>6.1f}s")
        if r["error"]:
            print(f"{'':30s} Error: {r['error'][:80]}")
        if status == "PASS":
            passed += 1
        else:
            failed += 1
    print(f"{'='*70}")
    print(f"Passed: {passed}/{len(results)}  Failed: {failed}/{len(results)}")
    print(f"{'='*70}")

if __name__ == "__main__":
    results = []
    for label, request in PROJECTS:
        print(f"\n>>> Running: {label}")
        print(f"    Request: {request[:80]}")
        r = run_project(label, request)
        results.append(r)
        print(f"    Status: {r['status']}, Tests: {r['tests_passed']}p/{r['tests_failed']}f, Duration: {r['duration_s']}s")
        with open(f"runtime/validate_{label.lower().replace(' ', '_')}.json", "w") as f:
            json.dump(r, f, indent=2)
    print_summary(results)
    # Return exit code
    all_pass = all(r["status"] == "COMPLETED" and r["error"] is None for r in results)
    sys.exit(0 if all_pass else 1)
