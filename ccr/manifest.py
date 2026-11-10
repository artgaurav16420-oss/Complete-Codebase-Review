"""Manifest loading and validation for the review pipeline.

`ccr/pipeline.json` is the single source of truth for agent identities,
env vars, enums, thresholds, and tech-debt floors.
"""

import json
import math
from pathlib import Path

from . import findings as findings_mod
from . import providers as providers_mod
from . import report as report_mod

MANIFEST_PATH = Path(__file__).resolve().parent / "pipeline.json"

REQUIRED_KEYS = [
    "version", "env_vars", "agents", "severities", "da_verdicts",
    "health", "thresholds", "tech_debt_floors",
]


def apply_settings(data):
    """Point the engine's process-wide settings at one manifest.

    The findings engine keeps agent identity and calibration at module level
    so direct callers work without a manifest. ``load`` applies them for the
    manifest it just read, which means a second load overwrites the first.
    ``pipeline.synthesize`` re-applies the manifest it was handed, so a report
    depends on that manifest and not on whichever one was loaded last.
    """
    # ADR-005: agent identity lives in the manifest, not in a literal here.
    findings_mod.set_security_agent_id(data.get("security_agent_id"))
    # ADR-007: so do the calibration numbers that decide report output.
    findings_mod.set_calibration(data.get("calibration"))


def load(path=None):
    """Load the manifest from disk and validate it.

    Args:
        path: Optional override path. Defaults to ccr/pipeline.json.

    Returns:
        dict: The validated manifest.

    Raises:
        FileNotFoundError: If the manifest does not exist.
        ValueError: If the manifest is structurally invalid.
    """
    manifest_path = Path(path) if path else MANIFEST_PATH
    if not manifest_path.exists():
        raise FileNotFoundError("manifest not found: " + str(manifest_path))
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    validate(data)
    apply_settings(data)
    return data


def _validate_agents(data):
    """Check the agent roster; returns the declared ids in order."""
    agent_ids = []
    for agent in data["agents"]:
        for field in ("id", "name", "report", "coverage", "skill"):
            if field not in agent:
                raise ValueError("agent missing field: " + field)
        for field in ("id", "name", "report"):
            if not isinstance(agent[field], str):
                raise ValueError(
                    "agent {} field {} must be a string".format(
                        agent["id"], field
                    )
                )
        # An id is also a file-name stem (phase_<id>.json), so an empty id
        # would name the file phase_.json and discovery would strip the prefix
        # back to nothing: the planned result could never be found.
        if not agent["id"].strip():
            raise ValueError("agent id must not be empty")
        # An id is also a file-name stem (phase_<id>.json). Reserving the
        # prefix keeps the canonical layout unambiguous: without it, a bare
        # fixture for an agent called phase_security is indistinguishable from
        # the canonical result of an agent called security.
        prefix = providers_mod.PHASE_PREFIX
        if agent["id"][:len(prefix)].lower() == prefix:
            raise ValueError(
                "agent id must not start with the reserved prefix "
                + prefix + ": " + agent["id"]
            )
        agent_ids.append(agent["id"])
    if len(agent_ids) != len(set(agent_ids)):
        raise ValueError("duplicate agent id in manifest")
    if len(agent_ids) < 12:
        raise ValueError("manifest must define at least 12 agents")
    return agent_ids


def _validate_base_agents(data, agent_ids):
    """Check the default agent roster references declared ids."""
    base_agents = data.get("base_agents", [])
    if not base_agents:
        raise ValueError("manifest must define base_agents")
    for agent_id in base_agents:
        if not isinstance(agent_id, str):
            raise ValueError("base agent id must be a string: " + repr(agent_id))
        if agent_id not in agent_ids:
            raise ValueError("unknown base agent: " + agent_id)


def _validate_env_vars(data):
    """Check env-var names are unique and fully specified."""
    var_names = [v["name"] for v in data["env_vars"]]
    if len(var_names) != len(set(var_names)):
        raise ValueError("duplicate env var in manifest")
    for var in data["env_vars"]:
        for field in ("name", "default", "description"):
            if field not in var:
                raise ValueError("env var missing field: " + field)


def _validate_thresholds(data, agent_ids):
    """Check completion thresholds and Quick Mode agent ids."""
    thresholds = data["thresholds"]
    for key in ("full_completion", "quick_completion"):
        value = thresholds.get(key)
        if not isinstance(value, (int, float)) or not 0 < value < 1:
            raise ValueError("threshold out of range: " + key)
    for agent_id in thresholds.get("quick_agents", []):
        if agent_id not in agent_ids:
            raise ValueError("quick agent not in manifest: " + agent_id)


def _enum_mismatch(declared, enforced):
    """Return the first declared/enforced enum disagreement, or None."""
    for value in declared:
        if value not in enforced:
            return "unexpected value: " + str(value)
    for value in enforced:
        if value not in declared:
            return "missing value: " + value
    return None


# Enums the code enforces, keyed by manifest field. Adding a value here means
# changing the constant the loader compares against, not just pipeline.json.
ENUM_SOURCES = (
    ("severities", findings_mod.SEVERITIES, "ccr.findings.SEVERITIES"),
    ("da_verdicts", findings_mod.VERDICTS, "ccr.findings.VERDICTS"),
    ("health", report_mod.HEALTH_VALUES, "ccr.report.HEALTH_VALUES"),
)


def _validate_security_agent(data, agent_ids):
    """Check the security agent id names a declared agent.

    The findings engine promotes HIGH findings from this agent to Phase 1, so
    an id that names nothing would silently demote them. Absent means the
    historical default, which keeps older manifests loadable.
    """
    agent_id = data.get("security_agent_id")
    if agent_id is None:
        return
    if not isinstance(agent_id, str) or agent_id not in agent_ids:
        raise ValueError("security_agent_id is not a declared agent: " + repr(agent_id))


def _validate_enums(data):
    """Check manifest enum lists match the constants the code enforces.

    A manifest value outside the enforced set would only be coerced later
    (LOW / QUESTIONABLE), silently down-ranking findings and zeroing tech
    debt, so drift is rejected at load instead.
    """
    for key, enforced, source in ENUM_SOURCES:
        declared = data[key]
        if not isinstance(declared, list):
            raise ValueError("manifest " + key + " must be a list")
        mismatch = _enum_mismatch(declared, enforced)
        if mismatch:
            raise ValueError(
                "manifest " + key + " must match " + source + ": " + mismatch
            )


# Calibration key -> (exclusive lower bound, inclusive upper bound or None).
# The ranges live in the engine so a direct caller of set_calibration is held
# to the same bounds the schema enforces here.
CALIBRATION_RANGES = findings_mod.CALIBRATION_RANGES


def _validate_calibration(data):
    """Calibration values are finite numbers in the range the engine expects.

    The block is optional so a manifest written before ADR-007 still loads and
    keeps the engine defaults.
    """
    calibration = data.get("calibration")
    if calibration is None:
        return
    if not isinstance(calibration, dict):
        raise ValueError("manifest calibration must be an object")
    for key in calibration:
        if key not in CALIBRATION_RANGES:
            raise ValueError("manifest calibration unknown key: " + key)
    for key, (low, high) in CALIBRATION_RANGES.items():
        if key not in calibration:
            continue
        value = calibration[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("manifest calibration " + key + " must be a number")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            # An int too large for a float: out of range, not a crash.
            finite = False
        if not finite or value <= low:
            raise ValueError("manifest calibration " + key + " out of range")
        if high is not None and value > high:
            raise ValueError("manifest calibration " + key + " out of range")


def _validate_tech_debt_labels(data):
    """Every floor key carries the label the generated SKILL.md table shows.

    The table is generated from these labels, so a missing one would drop a
    row silently. Absent labels are allowed for older manifests; the generator
    then falls back to the key itself.
    """
    labels = data.get("tech_debt_labels")
    if labels is None:
        return
    if not isinstance(labels, dict):
        raise ValueError("manifest tech_debt_labels must be an object")
    floors = data["tech_debt_floors"]
    for key in floors:
        label = labels.get(key)
        if not isinstance(label, str) or not label:
            raise ValueError("manifest tech_debt_labels missing: " + key)
    for key in labels:
        if key not in floors:
            raise ValueError("manifest tech_debt_labels unknown floor: " + key)


def validate(data):
    """Validate manifest structure. Raises ValueError on the first problem."""
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError("manifest missing key: " + key)

    agent_ids = _validate_agents(data)
    _validate_base_agents(data, agent_ids)
    _validate_env_vars(data)
    _validate_thresholds(data, agent_ids)
    _validate_calibration(data)
    _validate_tech_debt_labels(data)
    _validate_security_agent(data, agent_ids)
    _validate_enums(data)


def agent_ids(manifest):
    """Return agent identifiers in manifest order."""
    return [agent["id"] for agent in manifest["agents"]]


def agent_by_id(manifest, agent_id):
    """Return an agent dict by id, or None."""
    for agent in manifest["agents"]:
        if agent["id"] == agent_id:
            return agent
    return None


def report_name(manifest, agent_id):
    """Return the human-readable report name for an agent id."""
    agent = agent_by_id(manifest, agent_id)
    if agent is None:
        raise ValueError("unknown agent: " + agent_id)
    return agent["report"]


def env_var_names(manifest):
    """Return env var names in manifest order."""
    return [var["name"] for var in manifest["env_vars"]]


def floor_for(manifest, key):
    """Return the tech-debt floor for a finding type, or 1.0 if unknown."""
    return float(manifest["tech_debt_floors"].get(key, 1.0))
