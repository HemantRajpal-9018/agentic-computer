"""Skill discovery and loading for the agentic-computer skill system.

Provides :class:`SkillLoader`, the central registry that discovers skills
from the filesystem (by scanning for ``SKILL.md`` manifest files), loads
built-in skills, and selects the best-matching skill for a given task.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import re
from pathlib import Path
from typing import Any

from agentic_computer.skills.base import BaseSkill, SkillMetadata

logger = logging.getLogger(__name__)

# Directory that contains the built-in skill modules.
_BUILTIN_DIR = Path(__file__).resolve().parent


class SkillLoader:
    """Discover, load, and select skills at runtime.

    A :class:`SkillLoader` maintains an internal list of loaded
    :class:`BaseSkill` instances.  Skills can come from three sources:

    1. **Built-in** -- the ``research``, ``coding``, and ``design`` skills
       shipped with the package (loaded via :pymeth:`load_builtin`).
    2. **Directory scan** -- external skill directories discovered by
       looking for ``SKILL.md`` manifest files (via :pymeth:`discover`).
    3. **Explicit load** -- a single skill directory loaded directly
       (via :pymeth:`load`).
    """

    def __init__(self) -> None:
        self._skills: list[BaseSkill] = []
        self._loaded: dict[str, BaseSkill] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def skills(self) -> list[BaseSkill]:
        """Return a shallow copy of the currently loaded skills."""
        return list(self._skills)

    def discover(self, directory: Path) -> list[SkillMetadata]:
        """Scan *directory* recursively for ``SKILL.md`` files and return their metadata.

        Each ``SKILL.md`` is parsed for YAML-like frontmatter that maps to
        a :class:`SkillMetadata`.  Discovered metadata is returned but the
        skills are **not** automatically loaded; call :pymeth:`load` to
        instantiate them.

        Args:
            directory: Root directory to scan.

        Returns:
            A list of :class:`SkillMetadata` found under *directory*.

        Raises:
            FileNotFoundError: If *directory* does not exist.
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise FileNotFoundError(f"Skill directory not found: {directory}")

        manifests = sorted(directory.rglob("SKILL.md"))
        metadata_list: list[SkillMetadata] = []

        for manifest_path in manifests:
            try:
                meta = self._parse_skill_md(manifest_path)
                if meta is not None:
                    metadata_list.append(meta)
                    logger.info("Discovered skill '%s' at %s", meta.name, manifest_path)
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", manifest_path, exc)

        logger.info("Discovered %d skill(s) under %s.", len(metadata_list), directory)
        return metadata_list

    def load(self, skill_path: Path) -> BaseSkill:
        """Load a skill from its directory and register it.

        The directory must contain a ``SKILL.md`` manifest and at least one of:

        * A ``skill.py`` module with a class that subclasses :class:`BaseSkill`.
        * A ``main.py`` module that exports a ``Skill`` class.
        * A Python package (``__init__.py``) that exports a :class:`BaseSkill`
          subclass.

        The first concrete :class:`BaseSkill` subclass found is instantiated
        and added to the internal registry.

        Args:
            skill_path: Path to the skill directory.

        Returns:
            The instantiated :class:`BaseSkill`.

        Raises:
            FileNotFoundError: If the directory does not exist.
            ValueError: If no valid skill class is found.
        """
        skill_path = Path(skill_path)
        if not skill_path.is_dir():
            raise FileNotFoundError(f"Skill path not found: {skill_path}")

        # Parse metadata from SKILL.md if present.
        skill_md = skill_path / "SKILL.md"
        meta: SkillMetadata | None = None
        if skill_md.exists():
            meta = self._parse_skill_md(skill_md)

        # Try loading from candidate files in priority order.
        candidates = [
            skill_path / "skill.py",
            skill_path / "main.py",
            skill_path / "__init__.py",
        ]

        for candidate in candidates:
            if candidate.is_file():
                skill_cls = self._load_skill_class_from_file(candidate)
                if skill_cls is not None:
                    instance = skill_cls()
                    self._skills.append(instance)
                    self._loaded[instance.metadata.name] = instance
                    logger.info("Loaded skill '%s' from %s", instance.metadata.name, candidate)
                    return instance

        raise ValueError(
            f"No valid BaseSkill subclass found in {skill_path}.  "
            f"Expected skill.py, main.py, or __init__.py with a BaseSkill subclass."
        )

    def load_builtin(self) -> list[BaseSkill]:
        """Load all built-in skills (research, coding, design) and register them.

        If a built-in skill is already registered (by name) it is skipped.

        Returns:
            The list of newly loaded :class:`BaseSkill` instances.
        """
        from agentic_computer.skills.coding import CodingSkill
        from agentic_computer.skills.design import DesignSkill
        from agentic_computer.skills.research import ResearchSkill

        builtin_classes: list[type[BaseSkill]] = [
            ResearchSkill,
            CodingSkill,
            DesignSkill,
        ]

        existing_names = {s.metadata.name for s in self._skills}
        loaded: list[BaseSkill] = []

        for cls in builtin_classes:
            instance = cls()
            name = instance.metadata.name
            if name in existing_names:
                logger.debug("Built-in skill '%s' already registered, skipping.", name)
                continue
            self._skills.append(instance)
            self._loaded[name] = instance
            loaded.append(instance)
            logger.info("Loaded built-in skill '%s'.", name)

        logger.info("Loaded %d built-in skill(s).", len(loaded))
        return loaded

    def get_best_skill(self, task: str, skills: list[BaseSkill] | None = None) -> BaseSkill:
        """Select the skill with the highest confidence for *task*.

        When *skills* is ``None`` the internal registry is used.

        Args:
            task: Natural-language task description.
            skills: Optional explicit skill list; defaults to all registered skills.

        Returns:
            The :class:`BaseSkill` with the highest ``can_handle`` score.

        Raises:
            ValueError: If the skill list is empty or all skills fail evaluation.
        """
        candidates = skills if skills is not None else self._skills
        if not candidates:
            raise ValueError("No skills available to evaluate.")

        scored: list[tuple[float, BaseSkill]] = []
        for skill in candidates:
            try:
                score = skill.can_handle(task)
                score = max(0.0, min(1.0, score))  # clamp to [0, 1]
                scored.append((score, skill))
                logger.debug(
                    "Skill '%s' scored %.2f for task: %s",
                    skill.metadata.name,
                    score,
                    task[:80],
                )
            except Exception as exc:
                logger.warning(
                    "Skill '%s' raised during can_handle: %s",
                    skill.metadata.name,
                    exc,
                )

        if not scored:
            raise ValueError("All skills failed during evaluation.")

        # Sort descending by score; ties broken by skill name for determinism.
        scored.sort(key=lambda pair: (-pair[0], pair[1].metadata.name))
        best_score, best_skill = scored[0]

        logger.info(
            "Best skill for task is '%s' (score=%.2f).",
            best_skill.metadata.name,
            best_score,
        )
        return best_skill

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_skill_md(path: Path) -> SkillMetadata | None:
        """Parse a ``SKILL.md`` manifest file and return its metadata.

        The expected format is a YAML-like frontmatter block delimited by
        ``---`` lines at the top of the file::

            ---
            name: my-skill
            description: Does amazing things.
            version: 1.0.0
            author: Alice
            tags: [search, analysis]
            ---

            # My Skill
            Extended documentation ...

        Args:
            path: Absolute or relative path to the ``SKILL.md`` file.

        Returns:
            A populated :class:`SkillMetadata`, or ``None`` if the
            frontmatter is missing or the ``name`` field is absent.
        """
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        # Extract frontmatter between --- delimiters.
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            return None

        frontmatter = fm_match.group(1)
        fields: dict[str, Any] = {}

        for line in frontmatter.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            colon_idx = line.find(":")
            if colon_idx == -1:
                continue
            key = line[:colon_idx].strip().lower()
            value = line[colon_idx + 1:].strip()

            # Handle list values like [tag1, tag2].
            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                fields[key] = [item.strip().strip("\"'") for item in items if item.strip()]
            else:
                fields[key] = value.strip("\"'")

        name = fields.get("name", "")
        if not name:
            return None

        # Normalise tags.
        raw_tags = fields.get("tags", [])
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.strip("[]")
            tags = [t.strip().strip("\"'") for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            tags = raw_tags
        else:
            tags = []

        return SkillMetadata(
            name=name,
            description=fields.get("description", ""),
            version=fields.get("version", "0.1.0"),
            author=fields.get("author", "unknown"),
            tags=tags,
        )

    @staticmethod
    def _load_skill_class_from_file(file_path: Path) -> type[BaseSkill] | None:
        """Dynamically import a Python file and find a BaseSkill subclass.

        Scans the module's top-level attributes for concrete classes that
        inherit from :class:`BaseSkill` (i.e. not abstract).  Also checks
        for a conventional ``Skill`` export name.

        Args:
            file_path: Path to the Python source file.

        Returns:
            The first concrete :class:`BaseSkill` subclass found, or
            ``None`` if none is found.
        """
        module_name = f"_skill_{file_path.stem}_{id(file_path)}"

        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            logger.warning("Cannot create module spec for %s", file_path)
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Failed to import %s: %s", file_path, exc)
            return None

        # Check for conventional "Skill" export first.
        if hasattr(module, "Skill"):
            obj = module.Skill
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseSkill)
                and not inspect.isabstract(obj)
            ):
                return obj

        # Fall back to scanning all attributes.
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseSkill)
                and obj is not BaseSkill
                and not inspect.isabstract(obj)
            ):
                return obj

        return None
