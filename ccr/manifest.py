"""Manifest loading and validation for the review pipeline.

`ccr/pipeline.json` is the single source of truth for agent identities,
env vars, enums, thresholds, and tech-debt floors.
"""

import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent / "pipeline.json"

REQUIRED_KEYS = [
    "version", "env_vars", "agents", "severities", "da_verdicts",
    "health", "thresholds", "tech_debt_floors",
]


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


def _validate_enums(data):
    """Check the severity and DA-verdict enums carry required members."""
    severities = data["severities"]
    if "CRITICAL" not in severities or "HIGH" not in severities:
        raise ValueError("severities must include CRITICAL and HIGH")

    verdicts = data["da_verdicts"]
    if "REJECTED" not in verdicts:
        raise ValueError("da_verdicts must include REJECTED")


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
