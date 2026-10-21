"""Agent prompt generation and result ingestion.

The CLI cannot spawn sub-agents itself, so the pipeline meets the host
runtime at this boundary: `record` writes one prompt per agent, the host
executes them, then `synthesize` ingests the JSON results.
"""

import json
from pathlib import Path

from .fileio import write_text

PROMPT_TEMPLATE = """You are auditing the {domain} of {target}.

SKILL_DIR={skill_dir}
Load 'karpathy-guidelines' from SKILL_DIR. Follow it: surface assumptions,
simplicity/YAGNI, surgical changes only, verify before claiming done.

Coverage: {coverage}

Return your report as JSON with this shape:
{{
  "agent": "{agent_id}",
  "score": 0,
  "findings": [
    {{
      "finding": "[path/file.py:42] \\u2014 concrete flaw \\u2192 exact failure mode",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "est_hours": 2,
      "finding_type": "optional tech-debt floor key",
      "tags": ["optional-issue-id"],
      "evidence": "metric or observation"
    }}
  ]
}}

Rules:
- Every finding MUST start with [file:line] and contain the arrow separator.
- No weasel words (might, likely, could potentially, best practice suggests).
- Only report flaws that CURRENTLY exist. No generic advice.
- Quantify tech debt in hours per finding. Set finding_type when it matches a
  floor key (circular_dependency, hardcoded_secret, missing_test_coverage, ...).
End with "GATE: COMPLETE" only if you actually performed the analysis.
"""


def build_prompt(agent, target, skill_dir, manifest_version=""):
    """Return the hardened prompt for one specialist agent."""
    return PROMPT_TEMPLATE.format(
        domain=agent["coverage"],
        target=target,
        skill_dir=skill_dir or "<SKILL_DIR>",
        coverage=agent["coverage"],
        agent_id=agent["id"],
    )


def prompt_path(out_dir, agent_id):
    """Return the path of an agent prompt file."""
    return Path(out_dir) / "phase_{}.prompt.md".format(agent_id)


def result_path(out_dir, agent_id):
    """Return the path of an agent result file."""
    return Path(out_dir) / "phase_{}.json".format(agent_id)


def write_prompts(manifest, plan, out_dir, skill_dir=""):
    """Write one prompt file per planned agent. Returns the paths."""
    cache = Path(out_dir)
    cache.mkdir(parents=True, exist_ok=True)
    written = []
    for agent_id in plan["agents"]:
        agent = next(a for a in manifest["agents"] if a["id"] == agent_id)
        path = prompt_path(cache, agent_id)
        write_text(path, build_prompt(agent, plan["target"], skill_dir))
        written.append(path)
    return written


def load_result(path, agent_id):
    """Load and validate one agent result file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("agent result must be an object: " + str(path))
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("agent result missing findings list: " + str(path))
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValueError("finding {} must be an object: {}".format(index, path))
        if "finding" not in finding:
            raise ValueError("finding {} missing text: {}".format(index, path))
    data.setdefault("agent", agent_id)
    return data


def load_results(out_dir, agent_ids, required=True):
    """Load results for the planned agents.

    Accepts either phase_<id>.json (record/synthesize workflow) or
    <id>.json (fixture replay). Missing results raise when required.

    Args:
        out_dir: Cache directory.
        agent_ids: Planned agent ids.
        required: When True, missing results raise FileNotFoundError.

    Returns:
        dict: agent id -> result dict (only those present when not required).

    Raises:
        FileNotFoundError: If required results are missing.
    """
    results = {}
    missing = []
    for agent_id in agent_ids:
        path = result_path(out_dir, agent_id)
        if not path.exists():
            path = Path(out_dir) / (agent_id + ".json")
        if path.exists():
            results[agent_id] = load_result(path, agent_id)
        else:
            missing.append(agent_id)
    if missing and required:
        raise FileNotFoundError(
            "missing agent results: " + ", ".join(missing)
        )
    return results


class RecordedProvider:
    """Replay agent results from a fixture directory (used by eval)."""

    def __init__(self, fixtures_dir):
        self.dir = Path(fixtures_dir)

    def agent_ids(self):
        """Return agent ids discovered in the fixture directory."""
        ids = []
        for path in sorted(self.dir.glob("*.json")):
            stem = path.stem
            if stem.startswith("phase_"):
                stem = stem[len("phase_"):]
            ids.append(stem)
        return ids

    def get(self, agent_id):
        """Return the recorded result for an agent."""
        path = self.dir / ("phase_" + agent_id + ".json")
        if not path.exists():
            path = self.dir / (agent_id + ".json")
        return load_result(path, agent_id)
