#!/usr/bin/env python
"""PreToolUse hook (Skill matcher).

When the `superpowers:brainstorming` skill is invoked, inject an instruction that
the spec-maintainer agent must run first as a BRAINSTORMING PLACEMENT GATE, so new
ideas are folded into existing features in docs/superpowers/CONSOLIDATED_SPEC.md
instead of spawning near-duplicate parallel functionality. For any other skill the
hook is a silent no-op.
"""
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

skill = ((data.get("tool_input") or {}).get("skill") or "")
if "brainstorm" in skill.lower():
    message = (
        "Brainstorming was invoked. Per project policy, BEFORE developing the idea, "
        "dispatch the `spec-maintainer` agent (.claude/agents/spec-maintainer.md) as a "
        "BRAINSTORMING PLACEMENT GATE. Give it the idea and have it read "
        "docs/superpowers/CONSOLIDATED_SPEC.md and report: where the idea best fits, which "
        "existing features/modules already overlap it, and a clear EXTEND-vs-CREATE "
        "recommendation with the specific integration point. Use its answer to steer the "
        "brainstorm toward folding the idea into an existing feature (or one cohesive "
        "complex feature) rather than adding a marginally-different parallel functionality. "
        "This up-front cost is intentional — it avoids the larger cost of building then "
        "correcting/overwriting redundant work."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        }
    }))

sys.exit(0)
