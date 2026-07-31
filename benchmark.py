import time
from tests.test_pipeline import validate_improvement_roadmap

md_content = """
## Improvement Roadmap
### Phase 1
""" + "\n".join([f"- Item {i}" for i in range(10000)])

findings = [{"da_verdict": "REJECTED", "finding": f"Item {i}"} for i in range(10000)]

start_time = time.time()
validate_improvement_roadmap(md_content, findings)
end_time = time.time()

print(f"Time taken: {end_time - start_time:.4f} seconds")
