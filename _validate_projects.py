"""Run validation projects and report results."""
import sys, time, json, shutil, traceback
from pathlib import Path
from app.autonomy.build_orchestrator import BuildOrchestrator
from app.tools.git_tool import GitTool

PROJECTS = [
    ("1. Calculator", "Build a complete Python calculator package with unit tests"),
    ("2. Key-Value Store", "Build a file-based key-value store with JSON persistence and pytest tests"),
    ("3. FastAPI CRUD API", "Build a FastAPI CRUD Todo API with SQLite storage and pytest tests"),
    ("4. CLI Password Manager", "Build a CLI password manager with encryption and pytest tests"),
    ("5. Markdown Doc Generator", "Build a markdown documentation generator with pytest tests"),
]

def clean():
    for d in ["runtime/build_checkpoints", "runtime/build_history", "runtime/installed"]:
        p = Path(d)
        if p.exists():
            for f in p.glob("*"):
                if f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
                else:
                    f.unlink(missing_ok=True)

def run_one(label, request):
    clean()
    orch = BuildOrchestrator(git_tool=GitTool())
    t0 = time.time()
    result = orch.build(request)
    elapsed = time.time() - t0

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

    ads_stage = result.stages.get("ads_generate")
    reg_ok = True
    if ads_stage and ads_stage.output and "stages" in ads_stage.output:
        for st in ads_stage.output["stages"]:
            if st.get("stage_name") == "registration" and st.get("status") == "failed":
                reg_ok = False

    passed = result.status.name == "COMPLETED" and not result.error
    print("-" * 60)
    print(f"{label}")
    print(f"  Status:       {result.status.name}")
    print(f"  Duration:     {elapsed:.1f}s")
    print(f"  Error:        {result.error or 'None'}")
    print(f"  Sandbox OK:   {sandbox_ok}")
    print(f"  Tests:        {test_tp}p/{test_tf}f")
    print(f"  Reg OK:       {reg_ok}")
    print(f"  Commit:       {result.commit_hash or 'None'}")
    print(f"  AI calls:     {result.ai_calls}")
    print(f"  Sandbox exec: {result.sandbox_executions}")
    print(f"  Fix attempts: {result.fix_attempts}")
    for k, s in result.stages.items():
        out = s.output or {}
        extra = ""
        if "success" in out:
            extra += f" ok={out['success']}"
        if "tests_passed" in out:
            extra += f" tp={out['tests_passed']} tf={out['tests_failed']}"
        if "security_violations" in out:
            extra += f" sec={out['security_violations']}"
        print(f"    {k:20s} {s.status:8s} {s.duration_ms:8.0f}ms retries={s.retries}{extra}")
    return passed

def main():
    passed_count = 0
    projects_to_run = PROJECTS
    if len(sys.argv) > 1:
        idx = int(sys.argv[1])
        projects_to_run = [PROJECTS[idx]]
    for label, request in projects_to_run:
        try:
            ok = run_one(label, request)
            if ok:
                passed_count += 1
            else:
                print(f"  >>> FAILED")
        except Exception as e:
            traceback.print_exc()
            print(f"  >>> CRASHED: {e}")

    print()
    print("=" * 60)
    print(f"RESULTS: {passed_count}/{len(PROJECTS)} passed")
    print("=" * 60)
    sys.exit(0 if passed_count == len(PROJECTS) else 1)

if __name__ == "__main__":
    main()
