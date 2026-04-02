"""Skills module — discoverable, composable agent capabilities."""

from agentic_computer.skills.base import BaseSkill, SkillContext, SkillMetadata, SkillResult
from agentic_computer.skills.loader import SkillLoader
from agentic_computer.skills.research import ResearchSkill
from agentic_computer.skills.coding import CodingSkill
from agentic_computer.skills.design import DesignSkill

__all__ = [
    "BaseSkill",
    "SkillContext",
    "SkillLoader",
    "SkillMetadata",
    "SkillResult",
    "ResearchSkill",
    "CodingSkill",
    "DesignSkill",
]
