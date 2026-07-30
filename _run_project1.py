from pathlib import Path
from app.autonomy.build_orchestrator import BuildOrchestrator
import time, json

t0 = time.time()
orch = BuildOrchestrator()
result = orch.build("Build a complete Python calculator package with unit tests")

print(f"\n===== PROJECT 1 RESULT =====")
print(f"Total time: {time.time()-t0:.1f}s")
print(f"Status: {result.status}")
print(f"Error: {result.error[:500] if result.error else None}")
print(f"\nStages:")
for k, s in result.stages.items():
    out_info = ""
    if s.output:
        if isinstance(s.output, dict):
            keys = list(s.output.keys())
            out_info = f" keys={keys}"
            if "tests_passed" in s.output:
                out_info += f' tp={s.output["tests_passed"]} tf={s.output["tests_failed"]}'
            if "success" in s.output:
                out_info += f' ok={s.output["success"]}'
    print(f"  {k}: {s.status} ({s.duration_ms:.0f}ms, retries={s.retries}){out_info}")
    if s.error:
        print(f"    error: {s.error[:300]}")

ads = result.stages.get("ads_generate")
if ads and ads.output:
    ap = ads.output.get("artifact_path", "")
    print(f"\nArtifact path: {ap}")
    if ap and Path(ap).exists():
        for f in Path(ap).iterdir():
            print(f"  File: {f.name} ({f.stat().st_size}b)")
            if f.suffix == ".py" and f.name != "__init__.py":
                content = f.read_text(encoding="utf-8")
                print(f"  Content ({len(content)} chars):")
                lines = content.split("\n")
                for i, line in enumerate(lines[:40]):
                    print(f"    {i+1}: {line}")
                if len(lines) > 40:
                    print(f"    ... ({len(lines)} total lines)")
