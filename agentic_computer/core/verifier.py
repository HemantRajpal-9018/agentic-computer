"""Output verification for agentic-computer.

The :class:`Verifier` agent inspects execution results for correctness,
completeness, and code quality.  It can validate individual outputs, check
Python code for syntax and structural issues, and confirm that every subtask
in a plan has been addressed.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Any

from agentic_computer.config import LLMConfig, get_settings
from agentic_computer.core.agent import (
    AgentRole,
    AgentState,
    BaseAgent,
    Plan,
    Result,
)
from agentic_computer.core.planner import SubTaskStatus, TaskPlan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Outcome of a verification check.

    Attributes:
        passed: ``True`` if no blocking issues were found.
        issues: List of problems discovered during verification.
        suggestions: Non-blocking improvement recommendations.
        metadata: Arbitrary extra context.
    """

    passed: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """One-line human-readable summary."""
        if self.passed:
            tag = "PASS"
        else:
            tag = f"FAIL ({len(self.issues)} issue(s))"
        suggestion_note = (
            f", {len(self.suggestions)} suggestion(s)" if self.suggestions else ""
        )
        return f"[{tag}{suggestion_note}]"


# ---------------------------------------------------------------------------
# Verifier agent
# ---------------------------------------------------------------------------

_VERIFY_SYSTEM_PROMPT = """\
You are a meticulous verification assistant.  Given a task description and the
output that was produced, evaluate whether the output correctly and completely
addresses the task.

Return a JSON object with exactly these keys:
  - "passed" (boolean): true if the output is satisfactory.
  - "issues" (array of strings): problems found (empty if none).
  - "suggestions" (array of strings): optional improvements.

Return ONLY valid JSON — no markdown fences, no commentary.
"""

_CODE_REVIEW_SYSTEM_PROMPT = """\
You are a senior code reviewer.  Analyse the following code for:
1. Correctness — does the logic look right?
2. Security — any obvious vulnerabilities?
3. Style — is it readable and idiomatic?
4. Edge cases — are boundary conditions handled?

Return a JSON object with:
  - "passed" (boolean): true if the code is acceptable.
  - "issues" (array of strings): problems found.
  - "suggestions" (array of strings): improvement ideas.

Return ONLY valid JSON — no markdown fences, no commentary.
"""


class Verifier(BaseAgent):
    """Agent that validates outputs from other agents.

    Provides three main verification modes:

    * :pymeth:`verify_output` — LLM-powered assessment of whether an output
      satisfies a task description.
    * :pymeth:`verify_code` — static analysis (syntax) combined with an
      LLM code review.
    * :pymeth:`verify_completeness` — structural check that all subtasks in
      a plan reached a terminal state and produced output.

    Parameters:
        llm_config: Optional LLM configuration override.
    """

    def __init__(self, llm_config: LLMConfig | None = None) -> None:
        super().__init__(name="Verifier", role=AgentRole.VERIFIER, llm_config=llm_config)

    # ------------------------------------------------------------------
    # Public verification API
    # ------------------------------------------------------------------

    async def verify_output(self, task: str, result: Result) -> VerificationResult:
        """Assess whether *result* adequately addresses *task*.

        Uses the LLM to judge correctness and completeness.

        Args:
            task: The original task description.
            result: The execution result to verify.

        Returns:
            A :class:`VerificationResult` with pass/fail and details.
        """
        self.state = AgentState.THINKING

        # Fast-path: if the result itself failed, report immediately.
        if not result.success:
            self.state = AgentState.DONE
            return VerificationResult(
                passed=False,
                issues=[f"Execution failed: {result.error or 'unknown error'}"],
            )

        try:
            vr = await self._llm_verify(
                system_prompt=_VERIFY_SYSTEM_PROMPT,
                user_content=(
                    f"Task:\n{task}\n\nOutput:\n{result.output}"
                ),
            )
            self.state = AgentState.DONE
            return vr
        except Exception as exc:
            self.state = AgentState.ERROR
            logger.error("verify_output failed: %s", exc)
            return VerificationResult(
                passed=False,
                issues=[f"Verification process error: {exc}"],
            )

    async def verify_code(self, code: str) -> VerificationResult:
        """Validate *code* with static analysis and an LLM review.

        Static checks (currently Python-only):
          - Syntax validation via :func:`ast.parse`.

        The LLM review layer adds semantic correctness, security, style,
        and edge-case analysis.

        Args:
            code: Source code string to verify.

        Returns:
            Aggregated :class:`VerificationResult`.
        """
        self.state = AgentState.THINKING
        issues: list[str] = []
        suggestions: list[str] = []

        # --- Static analysis (Python) -----------------------------------
        syntax_ok = self._check_python_syntax(code)
        if not syntax_ok.passed:
            issues.extend(syntax_ok.issues)

        # --- LLM review --------------------------------------------------
        try:
            llm_result = await self._llm_verify(
                system_prompt=_CODE_REVIEW_SYSTEM_PROMPT,
                user_content=code,
            )
            issues.extend(llm_result.issues)
            suggestions.extend(llm_result.suggestions)
        except Exception as exc:
            logger.warning("LLM code review failed; relying on static analysis only: %s", exc)
            suggestions.append("LLM review unavailable; consider manual review.")

        passed = len(issues) == 0
        self.state = AgentState.DONE
        return VerificationResult(passed=passed, issues=issues, suggestions=suggestions)

    def verify_completeness(
        self,
        task: str,
        plan: TaskPlan,
        results: dict[str, Result],
    ) -> VerificationResult:
        """Check that every subtask in *plan* has been executed.

        This is a purely structural check — it does **not** call the LLM.

        Args:
            task: Original high-level task description.
            plan: The plan that was executed.
            results: Mapping of subtask ID -> :class:`Result`.

        Returns:
            :class:`VerificationResult` summarising completeness.
        """
        issues: list[str] = []
        suggestions: list[str] = []

        total = len(plan.subtasks)
        completed = 0
        failed = 0
        skipped = 0
        missing = 0

        for st in plan.subtasks:
            if st.id not in results:
                missing += 1
                issues.append(f"Subtask {st.id!r} ({st.description[:60]}) has no result.")
                continue
            r = results[st.id]
            if st.status == SubTaskStatus.COMPLETED and r.success:
                completed += 1
            elif st.status == SubTaskStatus.FAILED:
                failed += 1
                issues.append(
                    f"Subtask {st.id!r} failed: {r.error or 'unknown error'}"
                )
            elif st.status == SubTaskStatus.SKIPPED:
                skipped += 1
                suggestions.append(
                    f"Subtask {st.id!r} was skipped (dependency failure)."
                )
            else:
                # Still pending or in-progress — shouldn't happen post-execution.
                issues.append(
                    f"Subtask {st.id!r} is in unexpected state: {st.status.value}"
                )

        passed = (failed == 0) and (missing == 0)
        metadata = {
            "total": total,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "missing": missing,
        }

        return VerificationResult(
            passed=passed,
            issues=issues,
            suggestions=suggestions,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    async def think(self, task: str) -> Plan:
        """Verifiers produce a single-step plan: verify the output."""
        return Plan(
            description=f"Verify output for: {task}",
            steps=["Run verification checks on the execution result."],
        )

    async def execute(self, plan: Plan) -> Result:
        """Verifiers do not execute general plans; use the verify_* methods."""
        return Result(
            success=True,
            output="Use verify_output(), verify_code(), or verify_completeness() directly.",
            metadata={"note": "Verifier does not execute generic plans."},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _llm_verify(
        self,
        system_prompt: str,
        user_content: str,
    ) -> VerificationResult:
        """Send content to the LLM for structured verification.

        Parses the JSON response into a :class:`VerificationResult`.
        """
        import json

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        raw = await self.llm_call(messages)
        return self._parse_verification(raw)

    @staticmethod
    def _parse_verification(raw_json: str) -> VerificationResult:
        """Parse the LLM's JSON response into a :class:`VerificationResult`."""
        import json

        text = raw_json.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse verifier JSON response.")
            return VerificationResult(
                passed=False,
                issues=["Verification response was not valid JSON."],
            )

        return VerificationResult(
            passed=bool(data.get("passed", False)),
            issues=list(data.get("issues", [])),
            suggestions=list(data.get("suggestions", [])),
        )

    @staticmethod
    def _check_python_syntax(code: str) -> VerificationResult:
        """Attempt to parse *code* as Python and report syntax errors.

        Returns:
            A :class:`VerificationResult` that passes if the code is
            syntactically valid Python.
        """
        try:
            ast.parse(code)
            return VerificationResult(passed=True)
        except SyntaxError as exc:
            location = ""
            if exc.lineno is not None:
                location = f" (line {exc.lineno}"
                if exc.offset is not None:
                    location += f", col {exc.offset}"
                location += ")"
            return VerificationResult(
                passed=False,
                issues=[f"Python syntax error{location}: {exc.msg}"],
            )
