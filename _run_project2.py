from pathlib import Path
from app.autonomy.build_orchestrator import BuildOrchestrator
from app.tools.git_tool import GitTool
import time, json, sys

for d in ["runtime/build_checkpoints", "runtime/build_history", "runtime/installed"]:
    p = Path(d)
    if p.exists():
        for f in p.glob("*"):
            if f.is_dir():
                import shutil
                shutil.rmtree(f, ignore_errors=True)
            else:
                f.unlink(missing_ok=True)

t0 = time.time()
orch = BuildOrchestrator(git_tool=GitTool())
result = orch.build("Build a file-based key-value store with JSON persistence and pytest tests")
total_time = time.time() - t0

ads_stages = []
ads_stage = result.stages.get("ads_generate")
if ads_stage and ads_stage.output and "stages" in ads_stage.output:
    ads_stages = ads_stage.output["stages"]

print("=" * 60)
print("PROJECT 2: File-based Key-Value Store")
print("=" * 60)
print(f"Status: {result.status.name}")
print(f"Total time: {total_time:.1f}s")
print(f"Error: {result.error or 'None'}")
print()

print("--- Pipeline Stages ---")
for k, s in result.stages.items():
    out = s.output or {}
    extra = ""
    if "tests_passed" in out:
        extra = f" tp={out['tests_passed']} tf={out['tests_failed']} tt={out.get('total_tests', '?')}"
    if "success" in out:
        extra += f" ok={out['success']}"
    if "sandbox" in out:
        extra += f" sandbox={out['sandbox']}"
    print(f"  {k:20s} {s.status:8s} {s.duration_ms:8.0f}ms retries={s.retries}{extra}")

print()
print("--- ADS Pipeline Stages ---")
for st in ads_stages:
    sname = st.get("stage_name", "?")
    sstat = st.get("status", "?")
    sdur = st.get("duration_ms", 0)
    serr = st.get("error", "")
    print(f"  {sname:25s} {sstat:8s} {sdur:8.0f}ms  {serr}")

print()
print("--- Artifact ---")
ads_out = ads_stage.output if ads_stage else {}
ap = ads_out.get("artifact_path", "")
print(f"Path: {ap}")
if ap and Path(ap).exists():
    for f in sorted(Path(ap).iterdir()):
        if f.is_file() and f.name not in (".pytest_cache", "__pycache__"):
            content = f.read_text(encoding="utf-8") if f.suffix in (".py", ".json", ".md", ".txt") else ""
            preview = content[:300].replace("\n", "\\n") if content else "(binary)"
            print(f"  {f.name:40s} {f.stat().st_size:>6}b  {preview}")

print()
print("--- Metrics ---")
print(f"  Build duration:           {total_time:.1f}s")
print(f"  Retry count:              {sum(s.retries for s in result.stages.values())}")
print(f"  AI calls (est):           3+ (interpret, plan, generate_code, generate_tests, auto_fix*)")
print(f"  Test count:               {ads_out.get('_test_out', {}).get('total_tests', '?')}")
print(f"  Simulation passed:        {result.stages.get('simulate', '').output.get('passed', '?') if result.stages.get('simulate') else '?'}")
print(f"  Governance action:        {result.stages.get('govern', '').output.get('action', '?') if result.stages.get('govern') else '?'}")
print(f"  Git commit:               {result.commit_hash or 'None'}")
for stage in ("sandbox", "test"):
    s = result.stages.get(stage)
    if s and s.output:
        out = s.output
        if "stderr" in out:
            err = out["stderr"][:500]
            if err.strip():
                print(f"  {stage} stderr: {err.strip()}")
        if "stdout" in out:
            o = out["stdout"][:300]
            if o.strip():
                print(f"  {stage} stdout: {o.strip()}")

print()
print("=== VERIFICATION ===")
if ap and Path(ap).exists():
    py_files = [f for f in Path(ap).iterdir() if f.suffix == ".py" and not f.name.startswith("test_") and f.name != "__init__.py"]
    for pf in py_files:
        mod_name = pf.stem
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(mod_name, str(pf))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                print(f"  Module {mod_name}.py loaded OK")
        except Exception as e:
            print(f"  Module {mod_name}.py load FAILED: {e}")

print()
if result.status.name == "COMPLETED" and result.error is None:
    print(">>> PROJECT 2: PASS")
else:
    print(">>> PROJECT 2: FAIL")
    sys.exit(1)
