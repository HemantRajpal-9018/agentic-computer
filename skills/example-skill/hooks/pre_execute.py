"""Pre-execution hook for the example-skill.

This module demonstrates the hook pattern used by the agentic-computer skill
system. The framework calls ``pre_execute`` before dispatching to the skill's
``execute()`` method, giving you a chance to validate inputs, enrich the
context, or abort execution early.

Hook contract:
    - The function MUST be named ``pre_execute``.
    - It MUST be async.
    - It receives a ``SkillContext`` and an optional config dict.
    - It MUST return a ``SkillContext`` (the same or a modified copy).
    - To abort execution, raise any exception (e.g., ``ValueError``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


async def pre_execute(
    context: Any,
    config: dict[str, Any] | None = None,
) -> Any:
    """Validate and enrich the skill context before execution.

    This reference implementation performs three checks:

    1. **Non-empty task** -- rejects blank task descriptions.
    2. **Default config** -- injects default configuration values if
       ``context.config`` is ``None``.
    3. **Timestamp** -- stamps the context config with the current UTC
       time so downstream code can measure latency.

    Args:
        context: The ``SkillContext`` that will be passed to the skill's
            ``execute()`` method. Typed as ``Any`` to avoid a hard import
            dependency on the framework (hooks should stay lightweight).
        config: Optional hook-specific configuration provided by the
            skill runner. Not used in this example.

    Returns:
        The (possibly modified) context object.

    Raises:
        ValueError: If the task description is empty or whitespace-only.

    Example::

        from agentic_computer.skills.base import SkillContext
        from skills.example_skill.hooks.pre_execute import pre_execute

        ctx = SkillContext(task="demonstrate the example skill")
        ctx = await pre_execute(ctx)
        assert ctx.config is not None
        assert "hook_timestamp" in ctx.config
    """
    logger.info(
        "example-skill pre_execute hook invoked for task: %.80s",
        getattr(context, "task", "<no task>"),
    )

    # ------------------------------------------------------------------
    # 1. Validate: reject empty tasks
    # ------------------------------------------------------------------
    task = getattr(context, "task", "")
    if not task or not task.strip():
        raise ValueError(
            "pre_execute hook: task description is empty. "
            "Provide a non-blank task string."
        )

    # ------------------------------------------------------------------
    # 2. Inject default configuration
    # ------------------------------------------------------------------
    if getattr(context, "config", None) is None:
        context.config = {}

    # Set defaults without overwriting caller-provided values.
    context.config.setdefault("max_output_length", 500)
    context.config.setdefault("store_to_memory", True)
    context.config.setdefault("echo_input", True)

    # ------------------------------------------------------------------
    # 3. Stamp with hook execution time
    # ------------------------------------------------------------------
    context.config["hook_timestamp"] = datetime.now(timezone.utc).isoformat()

    logger.debug(
        "example-skill pre_execute hook completed. Config keys: %s",
        list(context.config.keys()),
    )

    return context
