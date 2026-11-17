"""Checks framework: automated findings per workflow stage.

Every module can register check functions for a stage. A check receives
(ctx, project) and returns a list of Finding objects. The same checks are
used by:
  - the stage gate in `advance` (any FAIL blocks; --force overrides),
  - `python -m factory check <project>`,
  - (later milestones) the QC report.

Levels:
  FAIL  blocks the stage gate
  WARN  reported, does not block
  INFO  informational
"""

from collections import namedtuple

FAIL, WARN, INFO = "FAIL", "WARN", "INFO"
LEVELS = (FAIL, WARN, INFO)

Finding = namedtuple("Finding", "level code message file")
Finding.__new__.__defaults__ = ("",)  # file is optional

_REGISTRY = {}  # stage id -> [check functions], in registration order


def register(stage):
    """Decorator: @register("script") def check_x(ctx, project): ..."""
    def decorate(func):
        _REGISTRY.setdefault(stage, [])
        if func not in _REGISTRY[stage]:
            _REGISTRY[stage].append(func)
        return func
    return decorate


def registered(stage=None):
    """Registered check functions for one stage, or a {stage: [...]} copy."""
    if stage is not None:
        return list(_REGISTRY.get(stage, []))
    return {s: list(funcs) for s, funcs in _REGISTRY.items()}


def run_checks(ctx, project, stage=None):
    """Run the checks for `stage` (default: the project's current stage).
    Findings are sorted FAIL → WARN → INFO, keeping registration order."""
    stage = stage or project.stage
    ctx.config.stage(stage)  # validates the stage id
    findings = []
    for func in _REGISTRY.get(stage, []):
        for finding in func(ctx, project) or []:
            if finding.level not in LEVELS:
                raise ValueError(f"{func.__name__} returned an unknown level: {finding.level}")
            findings.append(finding)
    order = {level: i for i, level in enumerate(LEVELS)}
    return sorted(findings, key=lambda f: order[f.level])


def failures(findings):
    return [f for f in findings if f.level == FAIL]


def format_finding(finding):
    where = f" [{finding.file}]" if finding.file else ""
    return f"{finding.level} {finding.code}{where}: {finding.message}"
