"""Agent prompt generation and result ingestion.

The CLI cannot spawn sub-agents itself, so the pipeline meets the host
runtime at this boundary: `record` writes one prompt per agent, the host
executes them, then `synthesize` ingests the JSON results.
"""

import json
import re
from pathlib import Path

from .fileio import write_text

# Any control character (including newlines) collapses to a space so a value
# interpolated into the prompt template cannot add lines of its own.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def _one_line(text):
    """Return text safe to interpolate into a single prompt line."""
    return _CONTROL_RE.sub(" ", str(text)).strip()

PROMPT_TEMPLATE = """You are auditing the {domain} of {target}.

Focus ONLY on {domain}. Do NOT flag adjacent domains: another specialist owns
those, and cross-domain duplicates inflate the report. If a finding is real
but belongs to another domain, omit it.

SKILL_DIR={skill_dir}
MANIFEST_VERSION={manifest_version}
Load 'karpathy-guidelines' from SKILL_DIR. Follow it: surface assumptions,
simplicity/YAGNI, surgical changes only, verify before claiming done.

Coverage: {coverage}

Domain checks (verify each, or state why not applicable):
{checks}

Return your report as JSON with this shape:
{{
  "agent": "{agent_id}",
  "score": 0,
  "findings": [
    {{
      "finding": "[path/file.py:42] \\u2014 concrete flaw \\u2192 exact failure mode",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "est_hours": 2,
      "da_verdict": "CONFIRMED|PLAUSIBLE|QUESTIONABLE|REJECTED|DA-ESCALATION",
      "finding_type": "optional tech-debt floor key, or design_note",
      "tags": ["optional-issue-id"],
      "evidence": "metric or observation"
    }}
  ]
}}

Rules:
- Every finding MUST start with [file:line] and contain the arrow separator.
- No weasel words (might, likely, could potentially, best practice suggests).
- Only report flaws that CURRENTLY exist. No generic advice.
- est_hours is the cost of the FIX, not of the observation. A finding that
  should not be fixed carries est_hours 0.
- Deliberate design trade-offs are not debt: report them with
  finding_type "design_note", severity INFO, and est_hours 0.
- CRITICAL and HIGH require a reproduction path: the exact input, call path,
  or command that triggers the failure. Without one, use MEDIUM at most.
- Documentation-only findings are at most MEDIUM. Test-only reliability
  findings are at most MEDIUM unless they disable a release gate.
- Set finding_type when it matches a floor key
  (circular_dependency, hardcoded_secret, missing_test_coverage, ...).
- Set da_verdict to CONFIRMED when you reproduced the failure, PLAUSIBLE when
  the evidence is strong but unreproduced, or QUESTIONABLE when uncertain.
  A missing da_verdict is treated as PLAUSIBLE so the finding stays visible.
End with "GATE: COMPLETE" only if you actually performed the analysis.
"""


def build_prompt(agent, target, skill_dir, manifest_version=""):
    """Return the hardened prompt for one specialist agent."""
    checks = agent.get("checks") or []
    checks_text = (
        "\n".join("- " + _one_line(check) for check in checks)
        if checks else "- none beyond the coverage above"
    )
    return PROMPT_TEMPLATE.format(
        domain=_one_line(agent["name"]),
        target=_one_line(target),
        skill_dir=_one_line(skill_dir or "<SKILL_DIR>"),
        manifest_version=_one_line(manifest_version or "unknown"),
        coverage=_one_line(agent["coverage"]),
        agent_id=_one_line(agent["id"]),
        checks=checks_text,
    )


# The result-file convention lives here and nowhere else: record writes it,
# synthesize reads it, and state resume and fixture replay discover it.
PHASE_PREFIX = "phase_"
PROMPT_SUFFIX = ".prompt.md"
RESULT_SUFFIX = ".json"

# Top-level keys the pipeline's own documents carry and an agent result
# never has. The report JSON opens with "report"; the model a baseline is
# read from carries the rest. A file named for an agent that has one of them
# is that document, not the agent's result.
DOCUMENT_KEYS = frozenset({
    "report", "per_domain_scores", "overall_health", "agent_status",
})


def prompt_name(agent_id):
    """Return the canonical file name of an agent prompt."""
    return PHASE_PREFIX + agent_id + PROMPT_SUFFIX


def result_name(agent_id):
    """Return the canonical file name of an agent result."""
    return PHASE_PREFIX + agent_id + RESULT_SUFFIX


def prompt_path(out_dir, agent_id):
    """Return the path of an agent prompt file."""
    return Path(out_dir) / prompt_name(agent_id)


def result_path(out_dir, agent_id):
    """Return the path of an agent result file."""
    return Path(out_dir) / result_name(agent_id)


def is_canonical_name(filename):
    """True when filename uses the phase_<id>.json name the pipeline writes.

    The prefix is matched case-insensitively because the phase_*.json globs
    behind it match case-insensitively on Windows.
    """
    stem = Path(filename).stem
    return stem[:len(PHASE_PREFIX)].lower() == PHASE_PREFIX


def agent_id_from_name(filename):
    """Return the agent id a result file name encodes, or None."""
    stem = Path(filename).stem
    if is_canonical_name(filename):
        stem = stem[len(PHASE_PREFIX):]
    return stem or None


def _is_result_candidate(path):
    """True when path holds something load_result should be asked about.

    The canonical phase_<id>.json name is written by the pipeline for an agent
    and nothing else, so anything under it is a result however broken, and
    load_result is the right place to say what is wrong. The one exception is
    a file that parses as one of the pipeline's own documents: a report saved
    under that name is that document, not the agent's result. In the bare
    fixture layout a stray json of any kind may sit beside the fixtures, so
    there a json object without a findings list (a baseline, a report, a state
    file) is not a result: the findings list is what says the file is an
    agent result at all. One that is not even an object is kept so
    load_result can name that too.

    A result may carry more than the three keys the prompt asks for and the
    loader accepts it, so the rule is not a whitelist of the result keys: it
    is the pipeline's own documents, the only files that carry a findings
    list and are not an agent result.
    """
    if not path.is_file():
        return False
    if is_canonical_name(path):
        return not is_pipeline_document(path)
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return True
    if not isinstance(data.get("findings"), list):
        return False
    return not (set(data) & DOCUMENT_KEYS)


def is_pipeline_document(path):
    """True when path holds one of the pipeline's own documents.

    The report JSON and the model a baseline is read from both carry keys an
    agent result never has. A file named for an agent that is one of them is
    that document, not the agent's result: reading the report as an agent
    would put the report's own findings into the report, and archiving it as
    a result would move the report out of the cache.
    """
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    return bool(set(data) & DOCUMENT_KEYS)


def _result_paths(root):
    """Return the entries of root with a result suffix, canonical names first.

    The tree is listed instead of globbed because a glob is case-sensitive on
    POSIX: ``.JSON`` would be invisible to discovery while ``find_result``
    reads it, so the two would disagree about the same directory.

    Only regular files are returned. The suffix alone is not enough: a
    directory can be named ``security.json``, and discovery with a known id
    set trusts the name without opening the entry, so it would hand back
    something no loader can read. Links are skipped for the same reason a
    link-like cache or install is refused elsewhere: a result is a file this
    pipeline wrote, and following a link would read whatever sits outside the
    cache.
    """
    try:
        entries = sorted(Path(root).iterdir())
    except OSError:
        # Absent, unreadable or removed while we looked: no results, which is
        # what an empty glob used to return.
        return []
    canonical = []
    bare = []
    for path in entries:
        if path.suffix.lower() != RESULT_SUFFIX:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if is_canonical_name(path):
            canonical.append(path)
        else:
            bare.append(path)
    return canonical + bare


def discover_results(out_dir, known=None):
    """Return (agent_id, path) pairs for the agent results in a directory.

    This is the one definition of "a result file", shared by fixture replay,
    synthesize's cache scan and state resume. Discovering and loading agree:
    an agent reported here always loads. The finder answers a different
    question — the caller named the agent, so the file named after it is that
    agent's result and the loader says what is wrong with it — which is why a
    file this skips can still be named by find_result. The canonical name
    wins a tie against the bare fixture layout, matching find_result.

    ``known`` is the id set a manifest declares. Only those ids are returned,
    and the name alone is enough: naming a planned agent makes the file its
    result, so a corrupt one reaches load_result and is reported by path
    instead of disappearing with the stray json. A file that is one of the
    pipeline's own documents is excluded either way: it is not an agent's
    result, and find_result refuses it.
    """
    found = []
    seen = set()
    for path in _result_paths(out_dir):
        agent_id = agent_id_from_name(path)
        if agent_id is None or agent_id in seen:
            continue
        if known is None:
            if not _is_result_candidate(path):
                continue
        elif agent_id not in known:
            continue
        elif is_pipeline_document(path):
            # A document named for a planned agent is that document, not the
            # agent's result. find_result refuses it, so counting it here
            # would put an agent in the roster that the loader cannot load.
            continue
        seen.add(agent_id)
        found.append((agent_id, path))
    return found


def find_result(out_dir, agent_id):
    """Return an agent's result path, or None when it is absent.

    Both layouts are accepted, but the canonical one comes first so a
    directory holding both reads the result the pipeline itself wrote. The
    match is made on the directory entries rather than a constructed path
    because the prefix is matched case-insensitively, and a case-sensitive
    filesystem would otherwise hide the very file discovery found.

    A file named for the agent is that agent's result, whatever it holds: the
    loader judges the content and names a broken file by path. The exception
    is a file that is one of the pipeline's own documents, such as the
    synthesis report: reading that as an agent would put the report's own
    findings into the report. The canonical name is no exception — a report
    saved as phase_<id>.json is that report, not the agent's result.
    """
    for path in _result_paths(out_dir):
        if agent_id_from_name(path) != agent_id:
            continue
        if not is_pipeline_document(path):
            return path
    return None


def write_prompts(manifest, plan, out_dir, skill_dir=""):
    """Write one prompt file per planned agent. Returns the paths."""
    cache = Path(out_dir)
    cache.mkdir(parents=True, exist_ok=True)
    written = []
    for agent_id in plan["agents"]:
        agent = next(a for a in manifest["agents"] if a["id"] == agent_id)
        path = prompt_path(cache, agent_id)
        write_text(
            path,
            build_prompt(
                agent, plan["target"], skill_dir,
                manifest_version=manifest.get("version", ""),
            ),
            root=cache,
        )
        written.append(path)
    return written


def load_result(path, agent_id):
    """Load and validate one agent result file."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as exc:
        # Name the file: the json error on its own says where in the text,
        # not which result it belongs to.
        raise ValueError(
            "agent result is not valid JSON: {} ({})".format(path, exc)
        )
    if not isinstance(data, dict):
        raise ValueError("agent result must be an object: " + str(path))
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("agent result missing findings list: " + str(path))
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValueError(f"finding {index} must be an object: {path}")
        if "finding" not in finding:
            raise ValueError(f"finding {index} missing text: {path}")
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
        path = find_result(out_dir, agent_id)
        if path is not None:
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

    def agent_ids(self, known=None):
        """Return agent ids discovered in the fixture directory.

        ``known`` limits the result to the ids a manifest declares. Those are
        the run's agents, so a file named for one is its result even when
        broken: the loader reports it by path. A stray json that merely looks
        like a result no longer becomes an agent id, and replay no longer
        aborts on an agent the run never planned.
        """
        return [
            agent_id for agent_id, _path in discover_results(self.dir, known)
        ]

    def get(self, agent_id):
        """Return the recorded result for an agent."""
        path = find_result(self.dir, agent_id)
        if path is None:
            # The finder is the one place that decides what an agent's file
            # is. Loading the bare name here anyway would read a file the
            # finder rejected, such as the report, as the agent's result.
            raise ValueError(
                "no agent result for " + agent_id + " in " + str(self.dir)
            )
        return load_result(path, agent_id)
