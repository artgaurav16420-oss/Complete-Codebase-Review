"""Crash-safe pipeline state for the review orchestrator.

The state file is ground truth across turns. Writes are atomic so a crash
cannot leave a half-written ccr-state.json.
"""

import json
import os
import tempfile
from pathlib import Path

PHASES = (1, 2, 3, 4, 5)

GATES = (
    "p1_discovery",
    "p2_analysis",
    "p3_synthesis_da_roadmap",
    "p4_fixplan_approval",
    "p4_fixes_applied",
    "p5_local_loop_clean",
    "p5_tests_pass",
    "p5_pr_created",
)

# Gate that must be true before entering each phase.
PHASE_GATES = {
    2: "p1_discovery",
    3: "p2_analysis",
    4: "p3_synthesis_da_roadmap",
    5: "p4_fixplan_approval",
}

AGENT_STATES = ("completed", "failed")

# Fields that a hand-edited or older state file may omit. Values are copied
# so callers never share the mutable defaults.
DEFAULTS = {
    "skill_dir": "",
    "effort": "max",
    "current_step": "",
    "agents_completed": [],
    "agents_failed": [],
    "completed_count": 0,
    "total_agents": 0,
    "facts": {},
    "re_review_count": 0,
    "local_loop_iterations": 0,
    "external_fix_rounds": 0,
    "last_checkpoint_ts": "",
}


def _defaults_copy():
    """Return a fresh copy of the optional state fields."""
    copied = {}
    for key, value in DEFAULTS.items():
        if isinstance(value, dict):
            copied[key] = dict(value)
        elif isinstance(value, list):
            copied[key] = list(value)
        else:
            copied[key] = value
    return copied


def _apply_defaults(data):
    """Fill optional state fields on a loaded dict."""
    if "total_agents" not in data:
        data["total_agents"] = len(data["agents_planned"])
    for key, value in _defaults_copy().items():
        if key not in data:
            data[key] = value
    try:
        data["re_review_count"] = int(data.get("re_review_count") or 0)
    except (TypeError, ValueError, OverflowError):
        data["re_review_count"] = 0


def new_state(target_dir, skill_dir="", effort="max"):
    """Return a fresh state dict."""
    state = _defaults_copy()
    state.update({
        "target_dir": str(Path(target_dir).resolve()),
        "skill_dir": skill_dir,
        "effort": effort,
        "current_phase": 1,
        "agents_planned": [],
        "phase_gates": {name: False for name in GATES},
    })
    return state


class State:
    """Mutable view over a ccr-state.json file."""

    def __init__(self, path, data):
        self.path = Path(path)
        self.data = data

    @classmethod
    def load(cls, path):
        """Load state from disk. Returns None when the file is absent."""
        state_path = Path(path)
        if not state_path.exists():
            return None
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        cls._validate(data)
        _apply_defaults(data)
        return cls(state_path, data)

    @classmethod
    def create(cls, path, target_dir, skill_dir="", effort="max"):
        """Create and persist a fresh state file."""
        state = cls(path, new_state(target_dir, skill_dir, effort))
        state.save()
        return state

    @staticmethod
    def _validate(data):
        """Reject structurally broken state files."""
        if not isinstance(data, dict):
            raise ValueError("state must be a JSON object")
        for key in ("target_dir", "current_phase", "phase_gates", "agents_planned"):
            if key not in data:
                raise ValueError("state missing key: " + key)
        if not isinstance(data["phase_gates"], dict):
            raise ValueError("state phase_gates must be a JSON object")
        if not isinstance(data["agents_planned"], list):
            raise ValueError("state agents_planned must be a JSON array")
        if data["current_phase"] not in PHASES:
            raise ValueError("invalid phase: " + str(data["current_phase"]))
        for gate in data["phase_gates"]:
            if gate not in GATES:
                raise ValueError("unknown phase gate: " + gate)
        if data["current_phase"] != 1 and not data["phase_gates"].get("p1_discovery"):
            raise ValueError("phase > 1 requires p1_discovery gate")

    def save(self):
        """Write state atomically via a unique temp file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(self.data, f, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def set_step(self, step):
        """Record the current sub-step."""
        self.data["current_step"] = step
        self.save()

    def advance(self, phase):
        """Move to a phase, refusing to skip an unpassed gate."""
        if phase not in PHASES:
            raise ValueError("invalid phase: " + str(phase))
        if phase > self.data["current_phase"] + 1:
            raise ValueError("cannot skip phases: " + str(self.data["current_phase"]))
        required = PHASE_GATES.get(phase)
        if required and not self.data["phase_gates"].get(required):
            raise ValueError(required + " gate must pass before advancing")
        self.data["current_phase"] = phase
        self.save()

    def set_gate(self, name, value=True):
        """Set a phase gate by name."""
        if name not in GATES:
            raise ValueError("unknown phase gate: " + name)
        self.data["phase_gates"][name] = bool(value)
        self.save()

    def plan_agents(self, agent_ids):
        """Record the planned agent set."""
        self.data["agents_planned"] = list(agent_ids)
        self.data["total_agents"] = len(agent_ids)
        self.save()

    def record_agent(self, agent_id, status="completed"):
        """Record an agent result. Status is 'completed' or 'failed'."""
        if status not in AGENT_STATES:
            raise ValueError("invalid agent status: " + status)
        if agent_id not in self.data["agents_planned"]:
            raise ValueError("agent was not planned: " + agent_id)
        completed = self.data["agents_completed"]
        failed = self.data["agents_failed"]
        for bucket in (completed, failed):
            if agent_id in bucket:
                bucket.remove(agent_id)
        if status == "completed":
            completed.append(agent_id)
        else:
            failed.append(agent_id)
        self.data["completed_count"] = len(completed)
        self.save()

    def completion_ratio(self):
        """Return completed agents divided by planned agents (0.0 if none)."""
        total = self.data["total_agents"]
        if not total:
            return 0.0
        return len(self.data["agents_completed"]) / total

    def threshold_passed(self, manifest):
        """Return True when enough agents completed to continue."""
        key = "quick_completion" if self.data["effort"] == "min" else "full_completion"
        return self.completion_ratio() >= manifest["thresholds"][key]


def merge_resume(state, cache_dir):
    """Cross-check state against cached agent files; disk wins.

    Args:
        state: Loaded State object.
        cache_dir: Directory holding phase_<agent>.json files.

    Returns:
        list: Agent ids present on disk but not recorded as completed.
    """
    cache = Path(cache_dir)
    if not cache.is_dir():
        return []
    on_disk = sorted(
        p.stem[len("phase_"):]
        for p in cache.glob("phase_*.json")
        if p.stem.lower() != "phase_"
    )
    completed = set(state.data["agents_completed"])
    return [agent_id for agent_id in on_disk if agent_id not in completed]
