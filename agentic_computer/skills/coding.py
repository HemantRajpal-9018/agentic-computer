"""Coding skill for the agentic-computer skill system.

Implements a plan -> implement -> verify workflow for code generation
and modification tasks.  Uses ``code_executor`` and ``file_manager``
tools when available.
"""

from __future__ import annotations

import logging
import re
import textwrap
from typing import Any

from agentic_computer.skills.base import (
    BaseSkill,
    SkillContext,
    SkillMetadata,
    SkillResult,
)

logger = logging.getLogger(__name__)

# Keywords that indicate a coding-oriented task.
_CODING_KEYWORDS: list[str] = [
    "code",
    "implement",
    "fix",
    "refactor",
    "write a function",
    "write a class",
    "create a script",
    "debug",
    "test",
    "unittest",
    "pytest",
    "build",
    "compile",
    "deploy",
    "api",
    "endpoint",
    "bug",
    "error",
    "patch",
    "migrate",
    "optimize",
    "program",
    "develop",
    "scaffold",
]


class CodingSkill(BaseSkill):
    """Skill for code generation, modification, and review.

    The execution pipeline has three phases:

    1. **Plan** -- decompose the task into an implementation plan with
       file paths, changes, and dependencies.
    2. **Implement** -- generate or modify code according to the plan.
    3. **Verify** -- review the produced code for correctness, style,
       and potential issues.
    """

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="coding",
            description="Code generation, modification, and review with plan-implement-verify flow.",
            version="0.1.0",
            author="agentic-computer",
            tags=["coding", "development", "code-generation", "refactoring"],
        )

    def can_handle(self, task: str) -> float:
        """Return high confidence for code / implement / fix / refactor tasks."""
        return self._keyword_confidence(task, _CODING_KEYWORDS)

    def get_required_tools(self) -> list[str]:
        return ["code_executor", "file_manager"]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Run the full coding pipeline: plan -> implement -> verify.

        Args:
            context: Execution context carrying the task, tools, and config.

        Returns:
            A :class:`SkillResult` containing the generated/modified code
            and review notes.
        """
        task = context.task
        artifacts: list[dict[str, Any]] = []
        logger.info("CodingSkill starting for task: %s", task)

        # Phase 1 -- Plan
        try:
            plan = await self._plan_implementation(task, context)
            artifacts.append({
                "type": "implementation_plan",
                "phase": "plan",
                "data": plan,
            })
        except Exception as exc:
            logger.error("Planning phase failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Coding failed during planning phase: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "plan", "error": str(exc)},
            )

        # Phase 2 -- Implement
        try:
            code = await self._generate_code(plan, context)
            artifacts.append({
                "type": "generated_code",
                "phase": "implement",
                "data": code,
            })
        except Exception as exc:
            logger.error("Implementation phase failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Coding failed during implementation phase: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "implement", "error": str(exc)},
            )

        # Phase 3 -- Verify
        try:
            review = await self._review_code(code, context)
            artifacts.append({
                "type": "code_review",
                "phase": "verify",
                "data": review,
            })
        except Exception as exc:
            logger.error("Verification phase failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Coding failed during verification phase: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "verify", "error": str(exc)},
            )

        # Build final output
        output = self._format_output(plan, code, review)

        logger.info("CodingSkill completed successfully.")
        return SkillResult(
            success=True,
            output=output,
            artifacts=artifacts,
            metadata={
                "phase_reached": "verify",
                "files_affected": len(plan.get("files", [])),
                "issues_found": len(review.get("issues", [])),
            },
        )

    # ------------------------------------------------------------------
    # Internal phases
    # ------------------------------------------------------------------

    async def _plan_implementation(
        self,
        task: str,
        context: SkillContext,
    ) -> dict[str, Any]:
        """Decompose the task into a structured implementation plan.

        The plan dict contains:

        * ``"description"`` -- what the change accomplishes.
        * ``"language"`` -- detected or inferred programming language.
        * ``"files"`` -- list of file dicts (``path``, ``action``, ``description``).
        * ``"dependencies"`` -- external packages required.
        * ``"steps"`` -- ordered implementation steps.

        Args:
            task: The coding task description.
            context: Skill execution context.

        Returns:
            A structured plan dict.
        """
        language = self._detect_language(task)
        task_type = self._classify_task(task)

        # Determine files and steps based on task classification.
        files: list[dict[str, str]] = []
        steps: list[str] = []
        dependencies: list[str] = []

        if task_type == "create":
            file_path = self._infer_file_path(task, language)
            files.append({
                "path": file_path,
                "action": "create",
                "description": f"New {language} file implementing the requested functionality.",
            })
            steps = [
                f"Create new {language} file at {file_path}",
                "Implement the core logic with type hints and docstrings",
                "Add error handling and edge-case guards",
                "Write unit tests if applicable",
            ]
        elif task_type == "modify":
            files.append({
                "path": self._infer_file_path(task, language),
                "action": "modify",
                "description": "Modify existing code to satisfy the task.",
            })
            steps = [
                "Read the existing source file",
                "Identify the section to change",
                "Apply the modifications preserving existing style",
                "Verify no regressions in surrounding code",
            ]
        elif task_type == "fix":
            files.append({
                "path": self._infer_file_path(task, language),
                "action": "modify",
                "description": "Apply bug fix.",
            })
            steps = [
                "Reproduce or localise the bug from the description",
                "Identify root cause",
                "Apply minimal targeted fix",
                "Add a regression test",
            ]
        else:  # refactor
            files.append({
                "path": self._infer_file_path(task, language),
                "action": "modify",
                "description": "Refactor for clarity, performance, or maintainability.",
            })
            steps = [
                "Analyse current code structure",
                "Identify refactoring opportunities",
                "Apply refactoring while preserving external behavior",
                "Run existing tests to confirm no regressions",
            ]

        plan: dict[str, Any] = {
            "description": task,
            "language": language,
            "task_type": task_type,
            "files": files,
            "dependencies": dependencies,
            "steps": steps,
        }

        logger.info("Plan: %s (%s, %d files, %d steps)", task_type, language, len(files), len(steps))
        return plan

    async def _generate_code(
        self,
        plan: dict[str, Any],
        context: SkillContext,
    ) -> dict[str, Any]:
        """Generate or modify code based on the implementation plan.

        Returns a dict with:

        * ``"files"`` -- mapping of file paths to their full source content.
        * ``"language"`` -- the programming language.

        When a ``code_executor`` tool is available the generated code is
        syntax-checked by executing a no-op import/parse.

        Args:
            plan: The structured plan from the planning phase.
            context: Skill execution context.

        Returns:
            A dict containing generated source code per file.
        """
        language = plan.get("language", "python")
        task_type = plan.get("task_type", "create")
        description = plan.get("description", "")
        generated_files: dict[str, str] = {}

        file_manager = self._get_tool(context, "file_manager")

        for file_spec in plan.get("files", []):
            file_path = file_spec["path"]
            action = file_spec["action"]

            existing_content: str | None = None
            if action == "modify" and file_manager is not None:
                try:
                    existing_content = await file_manager("read", path=file_path)
                except Exception as exc:
                    logger.warning("Could not read %s: %s", file_path, exc)

            source = self._build_source(
                language=language,
                task=description,
                task_type=task_type,
                existing=existing_content,
            )
            generated_files[file_path] = source

            # Write the file if the tool is available.
            if file_manager is not None:
                try:
                    await file_manager("write", path=file_path, content=source)
                except Exception as exc:
                    logger.warning("Could not write %s: %s", file_path, exc)

        # Optional: syntax-check via code_executor.
        code_executor = self._get_tool(context, "code_executor")
        if code_executor is not None and language == "python":
            for path, source in generated_files.items():
                try:
                    check_result = await code_executor(
                        f"import ast; ast.parse({source!r}); print('OK')"
                    )
                    if isinstance(check_result, str) and "OK" not in check_result:
                        logger.warning("Syntax check warning for %s: %s", path, check_result)
                except Exception as exc:
                    logger.warning("Syntax check failed for %s: %s", path, exc)

        code: dict[str, Any] = {
            "files": generated_files,
            "language": language,
        }

        logger.info("Generated %d file(s) in %s.", len(generated_files), language)
        return code

    async def _review_code(
        self,
        code: dict[str, Any],
        context: SkillContext,
    ) -> dict[str, Any]:
        """Review the generated code for quality issues.

        Returns a dict with:

        * ``"issues"`` -- list of dicts (``severity``, ``file``, ``line``,
          ``message``).
        * ``"suggestions"`` -- list of improvement suggestions.
        * ``"passed"`` -- boolean indicating overall quality gate.

        Args:
            code: The generated code from the implementation phase.
            context: Skill execution context.

        Returns:
            A structured review dict.
        """
        issues: list[dict[str, Any]] = []
        suggestions: list[str] = []

        for file_path, source in code.get("files", {}).items():
            file_issues = self._static_analysis(file_path, source, code.get("language", "python"))
            issues.extend(file_issues)

        # Derive suggestions from issue patterns.
        severity_counts: dict[str, int] = {}
        for issue in issues:
            sev = issue.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        if severity_counts.get("error", 0) > 0:
            suggestions.append("Fix all error-level issues before merging.")
        if severity_counts.get("warning", 0) > 2:
            suggestions.append("Consider addressing warnings to improve maintainability.")
        if not issues:
            suggestions.append("Code looks clean -- no issues detected.")

        passed = severity_counts.get("error", 0) == 0

        review: dict[str, Any] = {
            "issues": issues,
            "suggestions": suggestions,
            "passed": passed,
            "severity_counts": severity_counts,
        }

        logger.info("Review: %d issues, passed=%s", len(issues), passed)
        return review

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_tool(context: SkillContext, name: str) -> Any:
        """Retrieve a tool callable from the context's tool registry."""
        if context.tools is None:
            return None
        if isinstance(context.tools, dict):
            return context.tools.get(name)
        return getattr(context.tools, name, None)

    @staticmethod
    def _detect_language(task: str) -> str:
        """Infer the programming language from the task description.

        Args:
            task: Task description.

        Returns:
            A language identifier string (e.g. ``"python"``).
        """
        language_signals: dict[str, list[str]] = {
            "python": ["python", ".py", "django", "flask", "fastapi", "pytest", "pip"],
            "javascript": ["javascript", ".js", "node", "npm", "react", "vue", "express"],
            "typescript": ["typescript", ".ts", ".tsx", "angular", "next.js", "nextjs"],
            "rust": ["rust", ".rs", "cargo", "tokio"],
            "go": [" go ", "golang", ".go", "goroutine"],
            "java": ["java", ".java", "spring", "maven", "gradle"],
            "ruby": ["ruby", ".rb", "rails", "gem"],
            "html": ["html", "webpage", "web page"],
            "css": ["css", "stylesheet", "tailwind"],
            "sql": ["sql", "query", "database", "table"],
        }
        task_lower = task.lower()
        best_lang = "python"
        best_hits = 0
        for lang, signals in language_signals.items():
            hits = sum(1 for s in signals if s in task_lower)
            if hits > best_hits:
                best_hits = hits
                best_lang = lang
        return best_lang

    @staticmethod
    def _classify_task(task: str) -> str:
        """Classify the task into create / modify / fix / refactor.

        Args:
            task: Task description.

        Returns:
            One of ``"create"``, ``"modify"``, ``"fix"``, or ``"refactor"``.
        """
        task_lower = task.lower()
        if any(kw in task_lower for kw in ("fix", "bug", "error", "broken", "crash", "patch")):
            return "fix"
        if any(kw in task_lower for kw in ("refactor", "clean up", "simplify", "restructure")):
            return "refactor"
        if any(kw in task_lower for kw in ("create", "new", "scaffold", "generate", "write", "implement", "add")):
            return "create"
        return "modify"

    @staticmethod
    def _infer_file_path(task: str, language: str) -> str:
        """Infer a plausible file path from the task and language.

        Looks for explicit paths in the task text first; falls back to a
        generic name based on the language extension.

        Args:
            task: Task description.
            language: Detected programming language.

        Returns:
            A file path string.
        """
        # Try to find an explicit file path in the task.
        path_match = re.search(r'[\w./\\-]+\.(?:py|js|ts|tsx|rs|go|java|rb|html|css|sql)', task)
        if path_match:
            return path_match.group(0)

        ext_map: dict[str, str] = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "rust": ".rs",
            "go": ".go",
            "java": ".java",
            "ruby": ".rb",
            "html": ".html",
            "css": ".css",
            "sql": ".sql",
        }
        ext = ext_map.get(language, ".py")
        return f"output{ext}"

    @staticmethod
    def _build_source(
        language: str,
        task: str,
        task_type: str,
        existing: str | None,
    ) -> str:
        """Build source code for a given language and task.

        For new files a template with boilerplate and a placeholder
        implementation is returned.  For modifications the existing
        content is returned with a change-marker comment appended.

        Args:
            language: Programming language.
            task: The task description.
            task_type: One of create / modify / fix / refactor.
            existing: Existing file content (if modifying).

        Returns:
            The full source code string.
        """
        if existing is not None and task_type != "create":
            marker = {
                "python": f'# TODO: {task}\n',
                "javascript": f'// TODO: {task}\n',
                "typescript": f'// TODO: {task}\n',
            }.get(language, f'// TODO: {task}\n')
            return existing.rstrip() + "\n\n" + marker

        if language == "python":
            return textwrap.dedent(f'''\
                """Module generated by CodingSkill.

                Task: {task}
                """

                from __future__ import annotations


                def main() -> None:
                    """Entry point."""
                    # TODO: implement - {task}
                    raise NotImplementedError("Implementation pending")


                if __name__ == "__main__":
                    main()
            ''')

        if language in ("javascript", "typescript"):
            ext_hint = "TypeScript" if language == "typescript" else "JavaScript"
            return textwrap.dedent(f'''\
                /**
                 * Module generated by CodingSkill.
                 * Task: {task}
                 * Language: {ext_hint}
                 */

                export function main(): void {{
                  // TODO: implement - {task}
                  throw new Error("Implementation pending");
                }}
            ''')

        if language == "html":
            return textwrap.dedent(f'''\
                <!DOCTYPE html>
                <html lang="en">
                <head>
                  <meta charset="UTF-8" />
                  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                  <title>Generated Page</title>
                  <!-- Task: {task} -->
                </head>
                <body>
                  <!-- TODO: implement - {task} -->
                </body>
                </html>
            ''')

        # Generic fallback
        return f"// Generated by CodingSkill\n// Task: {task}\n// TODO: implement\n"

    @staticmethod
    def _static_analysis(file_path: str, source: str, language: str) -> list[dict[str, Any]]:
        """Run lightweight static analysis on source code.

        Performs language-appropriate heuristic checks such as looking for
        TODO markers, overly long lines, missing docstrings, and common
        anti-patterns.

        Args:
            file_path: Path to the file being analysed.
            source: Full source code string.
            language: Programming language identifier.

        Returns:
            A list of issue dicts with ``severity``, ``file``, ``line``,
            and ``message`` keys.
        """
        issues: list[dict[str, Any]] = []
        lines = source.split("\n")

        for i, line in enumerate(lines, start=1):
            # Long lines.
            if len(line) > 120:
                issues.append({
                    "severity": "warning",
                    "file": file_path,
                    "line": i,
                    "message": f"Line exceeds 120 characters ({len(line)} chars).",
                })

            # TODO / FIXME markers.
            if re.search(r"\bTODO\b", line, re.IGNORECASE):
                issues.append({
                    "severity": "info",
                    "file": file_path,
                    "line": i,
                    "message": "Contains TODO marker.",
                })

            # Bare except (Python).
            if language == "python" and re.match(r"\s*except\s*:", line):
                issues.append({
                    "severity": "warning",
                    "file": file_path,
                    "line": i,
                    "message": "Bare except clause -- prefer catching specific exceptions.",
                })

            # console.log left in (JavaScript / TypeScript).
            if language in ("javascript", "typescript") and "console.log" in line:
                issues.append({
                    "severity": "info",
                    "file": file_path,
                    "line": i,
                    "message": "Leftover console.log statement.",
                })

        # Python-specific: check for module docstring.
        if language == "python" and lines and not lines[0].strip().startswith(('"""', "'''")):
            issues.append({
                "severity": "info",
                "file": file_path,
                "line": 1,
                "message": "Module is missing a docstring.",
            })

        return issues

    @staticmethod
    def _format_output(
        plan: dict[str, Any],
        code: dict[str, Any],
        review: dict[str, Any],
    ) -> str:
        """Format the combined output of all three phases.

        Args:
            plan: Structured plan from planning phase.
            code: Generated code from implementation phase.
            review: Review results from verification phase.

        Returns:
            A human-readable summary string.
        """
        sections: list[str] = []

        # Plan summary
        sections.append("## Implementation Plan\n")
        sections.append(f"**Task type:** {plan.get('task_type', 'unknown')}")
        sections.append(f"**Language:** {plan.get('language', 'unknown')}")
        for step in plan.get("steps", []):
            sections.append(f"- {step}")
        sections.append("")

        # Generated files
        sections.append("## Generated Code\n")
        for path, source in code.get("files", {}).items():
            lang = code.get("language", "")
            sections.append(f"### `{path}`\n")
            sections.append(f"```{lang}")
            sections.append(source)
            sections.append("```\n")

        # Review summary
        sections.append("## Code Review\n")
        passed = review.get("passed", False)
        status = "PASSED" if passed else "FAILED"
        sections.append(f"**Status:** {status}")
        for suggestion in review.get("suggestions", []):
            sections.append(f"- {suggestion}")
        if review.get("issues"):
            sections.append(f"\n**Issues ({len(review['issues'])}):**")
            for issue in review["issues"][:10]:
                sev = issue.get("severity", "info").upper()
                msg = issue.get("message", "")
                line = issue.get("line", "?")
                sections.append(f"  - [{sev}] line {line}: {msg}")

        return "\n".join(sections)
