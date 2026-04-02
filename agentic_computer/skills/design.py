"""UI/UX design skill for the agentic-computer skill system.

Implements an analyze -> design -> generate workflow that produces
Tailwind CSS based React/HTML component code from natural-language
design requirements.
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

# Keywords that indicate a design-oriented task.
_DESIGN_KEYWORDS: list[str] = [
    "design",
    "ui",
    "ux",
    "layout",
    "wireframe",
    "mockup",
    "component",
    "interface",
    "prototype",
    "responsive",
    "style",
    "theme",
    "color scheme",
    "typography",
    "navigation",
    "dashboard",
    "form",
    "modal",
    "card",
    "button",
    "sidebar",
    "header",
    "footer",
    "landing page",
    "tailwind",
]

# --- Tailwind utility palettes used by the generator ---

_COLOR_PALETTES: dict[str, dict[str, str]] = {
    "default": {
        "primary": "blue-600",
        "primary_hover": "blue-700",
        "secondary": "gray-600",
        "accent": "indigo-500",
        "background": "white",
        "surface": "gray-50",
        "text": "gray-900",
        "text_muted": "gray-500",
        "border": "gray-200",
        "error": "red-500",
        "success": "green-500",
        "warning": "amber-500",
    },
    "dark": {
        "primary": "blue-400",
        "primary_hover": "blue-500",
        "secondary": "gray-400",
        "accent": "indigo-400",
        "background": "gray-900",
        "surface": "gray-800",
        "text": "gray-100",
        "text_muted": "gray-400",
        "border": "gray-700",
        "error": "red-400",
        "success": "green-400",
        "warning": "amber-400",
    },
}

# Mapping from component keywords to template generators.
_COMPONENT_TYPES: list[str] = [
    "card",
    "button",
    "form",
    "modal",
    "navbar",
    "sidebar",
    "hero",
    "footer",
    "table",
    "list",
    "dashboard",
    "login",
    "pricing",
    "profile",
]


class DesignSkill(BaseSkill):
    """Skill for UI/UX design intelligence and component generation.

    The execution pipeline has three phases:

    1. **Analyze** -- parse the task to extract design requirements such as
       component type, colour scheme, layout constraints, and interactions.
    2. **Design** -- produce a structured design specification including
       layout grid, spacing, typography, and colour tokens.
    3. **Generate** -- emit production-ready React (JSX/TSX) or plain HTML
       code using Tailwind CSS utility classes.
    """

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="design",
            description="UI/UX design intelligence with Tailwind CSS component generation.",
            version="0.1.0",
            author="agentic-computer",
            tags=["design", "ui", "ux", "tailwind", "react", "components"],
        )

    def can_handle(self, task: str) -> float:
        """Return high confidence for design / ui / ux / layout tasks."""
        return self._keyword_confidence(task, _DESIGN_KEYWORDS)

    def get_required_tools(self) -> list[str]:
        return []

    async def execute(self, context: SkillContext) -> SkillResult:
        """Run the full design pipeline: analyze -> design -> generate.

        Args:
            context: Execution context carrying the task and configuration.

        Returns:
            A :class:`SkillResult` with generated component code and the
            design specification.
        """
        task = context.task
        artifacts: list[dict[str, Any]] = []
        logger.info("DesignSkill starting for task: %s", task)

        # Phase 1 -- Analyze requirements
        try:
            requirements = await self._analyze_requirements(task, context)
            artifacts.append({
                "type": "design_requirements",
                "phase": "analyze",
                "data": requirements,
            })
        except Exception as exc:
            logger.error("Requirements analysis failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Design failed during requirements analysis: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "analyze", "error": str(exc)},
            )

        # Phase 2 -- Generate design spec
        try:
            spec = await self._generate_design_spec(requirements)
            artifacts.append({
                "type": "design_spec",
                "phase": "design",
                "data": spec,
            })
        except Exception as exc:
            logger.error("Design specification failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Design failed during specification: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "design", "error": str(exc)},
            )

        # Phase 3 -- Generate component code
        try:
            component_code = await self._generate_component_code(spec, requirements)
            artifacts.append({
                "type": "component_code",
                "phase": "generate",
                "data": component_code,
            })
        except Exception as exc:
            logger.error("Code generation failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Design failed during code generation: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "generate", "error": str(exc)},
            )

        output = self._format_output(requirements, spec, component_code)

        logger.info("DesignSkill completed successfully.")
        return SkillResult(
            success=True,
            output=output,
            artifacts=artifacts,
            metadata={
                "phase_reached": "generate",
                "component_type": requirements.get("component_type", "unknown"),
                "framework": requirements.get("framework", "react"),
            },
        )

    # ------------------------------------------------------------------
    # Internal phases
    # ------------------------------------------------------------------

    async def _analyze_requirements(
        self,
        task: str,
        context: SkillContext,
    ) -> dict[str, Any]:
        """Extract structured design requirements from the task.

        Returns a dict with:

        * ``"component_type"`` -- detected component kind.
        * ``"framework"`` -- ``"react"`` or ``"html"``.
        * ``"color_scheme"`` -- ``"default"`` or ``"dark"``.
        * ``"responsive"`` -- whether responsiveness was requested.
        * ``"interactions"`` -- list of interaction descriptions.
        * ``"content_hints"`` -- extracted content placeholders.
        * ``"raw_task"`` -- original task string.

        Args:
            task: The design task description.
            context: Skill execution context.

        Returns:
            A requirements dict.
        """
        task_lower = task.lower()

        # Detect component type.
        component_type = "card"  # default
        for ct in _COMPONENT_TYPES:
            if ct in task_lower:
                component_type = ct
                break

        # Detect framework preference.
        framework = "react"
        if any(kw in task_lower for kw in ("html", "plain html", "vanilla")):
            framework = "html"

        # Detect colour scheme.
        color_scheme = "default"
        if any(kw in task_lower for kw in ("dark", "dark mode", "dark theme")):
            color_scheme = "dark"

        # Detect responsiveness request.
        responsive = any(kw in task_lower for kw in ("responsive", "mobile", "adaptive", "breakpoint"))

        # Extract interaction hints.
        interaction_keywords = [
            "hover", "click", "submit", "toggle", "expand",
            "collapse", "drag", "scroll", "animate", "transition",
        ]
        interactions = [kw for kw in interaction_keywords if kw in task_lower]

        # Extract content hints from quoted strings or capitalised nouns.
        content_hints = re.findall(r'"([^"]+)"', task)
        if not content_hints:
            content_hints = re.findall(r"'([^']+)'", task)

        requirements: dict[str, Any] = {
            "component_type": component_type,
            "framework": framework,
            "color_scheme": color_scheme,
            "responsive": responsive,
            "interactions": interactions,
            "content_hints": content_hints,
            "raw_task": task,
        }

        logger.info(
            "Requirements: type=%s, framework=%s, scheme=%s, responsive=%s",
            component_type, framework, color_scheme, responsive,
        )
        return requirements

    async def _generate_design_spec(
        self,
        requirements: dict[str, Any],
    ) -> dict[str, Any]:
        """Produce a structured design specification from requirements.

        The spec includes layout, spacing, typography, and colour tokens
        expressed as Tailwind utility references.

        Args:
            requirements: Requirements from the analysis phase.

        Returns:
            A design specification dict.
        """
        color_scheme = requirements.get("color_scheme", "default")
        palette = _COLOR_PALETTES.get(color_scheme, _COLOR_PALETTES["default"])
        component_type = requirements.get("component_type", "card")
        responsive = requirements.get("responsive", False)

        # Layout spec based on component type.
        layout = self._layout_for_component(component_type, responsive)

        spec: dict[str, Any] = {
            "palette": palette,
            "typography": {
                "heading": "text-2xl font-bold",
                "subheading": "text-lg font-semibold",
                "body": "text-base font-normal",
                "caption": "text-sm text-{text_muted}".format_map(palette),
            },
            "spacing": {
                "section_gap": "space-y-6",
                "element_gap": "space-y-4",
                "padding": "p-6",
                "margin": "my-4",
            },
            "layout": layout,
            "border_radius": "rounded-lg",
            "shadow": "shadow-md",
            "transitions": self._transitions_for_interactions(
                requirements.get("interactions", [])
            ),
        }

        logger.info("Design spec generated for %s component.", component_type)
        return spec

    async def _generate_component_code(
        self,
        spec: dict[str, Any],
        requirements: dict[str, Any],
    ) -> dict[str, str]:
        """Generate React (TSX) or plain HTML component code.

        Returns a dict mapping file names to source code strings.

        Args:
            spec: Design specification from the design phase.
            requirements: Original requirements.

        Returns:
            A dict of ``{filename: source_code}``.
        """
        framework = requirements.get("framework", "react")
        component_type = requirements.get("component_type", "card")
        palette = spec.get("palette", _COLOR_PALETTES["default"])

        if framework == "react":
            code = self._react_component(component_type, spec, requirements, palette)
            filename = f"{self._pascal_case(component_type)}.tsx"
        else:
            code = self._html_component(component_type, spec, requirements, palette)
            filename = f"{component_type}.html"

        return {filename: code}

    # ------------------------------------------------------------------
    # Component generators
    # ------------------------------------------------------------------

    def _react_component(
        self,
        component_type: str,
        spec: dict[str, Any],
        requirements: dict[str, Any],
        palette: dict[str, str],
    ) -> str:
        """Generate a React TSX component with Tailwind classes.

        Args:
            component_type: The kind of component to generate.
            spec: Full design specification.
            requirements: Original requirements.
            palette: Colour palette mapping.

        Returns:
            Complete TSX source code.
        """
        name = self._pascal_case(component_type)
        content_hints = requirements.get("content_hints", [])
        title = content_hints[0] if content_hints else f"Sample {name}"
        subtitle = content_hints[1] if len(content_hints) > 1 else "A brief description goes here."

        bg = f"bg-{palette['background']}"
        surface = f"bg-{palette['surface']}"
        text_color = f"text-{palette['text']}"
        muted = f"text-{palette['text_muted']}"
        primary = f"bg-{palette['primary']}"
        primary_hover = f"hover:bg-{palette['primary_hover']}"
        border = f"border-{palette['border']}"
        radius = spec.get("border_radius", "rounded-lg")
        shadow = spec.get("shadow", "shadow-md")
        padding = spec["spacing"]["padding"]
        transitions = " ".join(spec.get("transitions", []))

        generators: dict[str, str] = {
            "card": textwrap.dedent(f"""\
                import React from "react";

                interface {name}Props {{
                  title?: string;
                  subtitle?: string;
                  children?: React.ReactNode;
                }}

                /**
                 * {name} component -- a flexible content card with Tailwind CSS styling.
                 *
                 * @param props - Component properties.
                 * @returns A styled card element.
                 */
                export default function {name}({{ title = "{title}", subtitle = "{subtitle}", children }}: {name}Props) {{
                  return (
                    <div className="{surface} {radius} {shadow} {padding} {transitions} border {border}">
                      <h2 className="text-2xl font-bold {text_color}">{{title}}</h2>
                      <p className="mt-2 {muted}">{{subtitle}}</p>
                      <div className="mt-4 {text_color}">{{children}}</div>
                    </div>
                  );
                }}
            """),
            "button": textwrap.dedent(f"""\
                import React from "react";

                interface {name}Props {{
                  label?: string;
                  onClick?: () => void;
                  variant?: "primary" | "secondary" | "outline";
                  disabled?: boolean;
                }}

                /**
                 * {name} component -- a versatile button with multiple variants.
                 */
                export default function {name}({{ label = "{title}", onClick, variant = "primary", disabled = false }}: {name}Props) {{
                  const baseClasses = "inline-flex items-center justify-center px-4 py-2 {radius} font-medium {transitions} focus:outline-none focus:ring-2 focus:ring-offset-2";

                  const variants = {{
                    primary: "{primary} text-white {primary_hover} focus:ring-{palette['primary']}",
                    secondary: "bg-{palette['secondary']} text-white hover:bg-gray-700 focus:ring-{palette['secondary']}",
                    outline: "border {border} {text_color} hover:{surface} focus:ring-{palette['primary']}",
                  }};

                  return (
                    <button
                      type="button"
                      onClick={{onClick}}
                      disabled={{disabled}}
                      className={{`${{baseClasses}} ${{variants[variant]}} ${{disabled ? "opacity-50 cursor-not-allowed" : ""}}`}}
                    >
                      {{label}}
                    </button>
                  );
                }}
            """),
            "form": textwrap.dedent(f"""\
                import React, {{ useState }} from "react";

                interface FormData {{
                  [key: string]: string;
                }}

                interface {name}Props {{
                  onSubmit?: (data: FormData) => void;
                  fields?: string[];
                }}

                /**
                 * {name} component -- a styled form with dynamic fields.
                 */
                export default function {name}({{ onSubmit, fields = ["Name", "Email", "Message"] }}: {name}Props) {{
                  const [formData, setFormData] = useState<FormData>(
                    Object.fromEntries(fields.map((f) => [f.toLowerCase(), ""]))
                  );

                  const handleChange = (field: string, value: string) => {{
                    setFormData((prev) => ({{ ...prev, [field]: value }}));
                  }};

                  const handleSubmit = (e: React.FormEvent) => {{
                    e.preventDefault();
                    onSubmit?.(formData);
                  }};

                  return (
                    <form onSubmit={{handleSubmit}} className="{surface} {radius} {shadow} {padding} space-y-4">
                      <h2 className="text-2xl font-bold {text_color}">{title}</h2>
                      {{fields.map((field) => (
                        <div key={{field}} className="space-y-1">
                          <label className="block text-sm font-medium {text_color}">{{field}}</label>
                          {{field.toLowerCase() === "message" ? (
                            <textarea
                              className="w-full {radius} border {border} {padding} {text_color} focus:ring-2 focus:ring-{palette['primary']} focus:border-transparent"
                              rows={{4}}
                              value={{formData[field.toLowerCase()]}}
                              onChange={{(e) => handleChange(field.toLowerCase(), e.target.value)}}
                            />
                          ) : (
                            <input
                              type={{field.toLowerCase() === "email" ? "email" : "text"}}
                              className="w-full {radius} border {border} px-3 py-2 {text_color} focus:ring-2 focus:ring-{palette['primary']} focus:border-transparent"
                              value={{formData[field.toLowerCase()]}}
                              onChange={{(e) => handleChange(field.toLowerCase(), e.target.value)}}
                            />
                          )}}
                        </div>
                      ))}}
                      <button
                        type="submit"
                        className="{primary} text-white px-6 py-2 {radius} {primary_hover} {transitions} focus:outline-none focus:ring-2 focus:ring-{palette['primary']}"
                      >
                        Submit
                      </button>
                    </form>
                  );
                }}
            """),
            "modal": textwrap.dedent(f"""\
                import React from "react";

                interface {name}Props {{
                  isOpen: boolean;
                  onClose: () => void;
                  title?: string;
                  children?: React.ReactNode;
                }}

                /**
                 * {name} component -- an overlay modal dialog.
                 */
                export default function {name}({{ isOpen, onClose, title = "{title}", children }}: {name}Props) {{
                  if (!isOpen) return null;

                  return (
                    <div className="fixed inset-0 z-50 flex items-center justify-center">
                      {{/* Backdrop */}}
                      <div
                        className="absolute inset-0 bg-black bg-opacity-50 {transitions}"
                        onClick={{onClose}}
                      />
                      {{/* Panel */}}
                      <div className="relative {bg} {radius} {shadow} {padding} max-w-lg w-full mx-4 {transitions}">
                        <div className="flex items-center justify-between mb-4">
                          <h2 className="text-xl font-bold {text_color}">{{title}}</h2>
                          <button
                            onClick={{onClose}}
                            className="{muted} hover:{text_color} {transitions}"
                          >
                            &times;
                          </button>
                        </div>
                        <div className="{text_color}">{{children}}</div>
                      </div>
                    </div>
                  );
                }}
            """),
            "navbar": textwrap.dedent(f"""\
                import React, {{ useState }} from "react";

                interface NavItem {{
                  label: string;
                  href: string;
                }}

                interface {name}Props {{
                  brand?: string;
                  items?: NavItem[];
                }}

                /**
                 * {name} component -- a responsive navigation bar.
                 */
                export default function {name}({{ brand = "{title}", items = [] }}: {name}Props) {{
                  const [mobileOpen, setMobileOpen] = useState(false);

                  return (
                    <nav className="{surface} {shadow} border-b {border}">
                      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="flex items-center justify-between h-16">
                          <span className="text-xl font-bold {text_color}">{{brand}}</span>
                          {{/* Desktop links */}}
                          <div className="hidden md:flex space-x-8">
                            {{items.map((item) => (
                              <a
                                key={{item.href}}
                                href={{item.href}}
                                className="{muted} hover:{text_color} {transitions} text-sm font-medium"
                              >
                                {{item.label}}
                              </a>
                            ))}}
                          </div>
                          {{/* Mobile toggle */}}
                          <button
                            className="md:hidden {muted} hover:{text_color}"
                            onClick={{() => setMobileOpen(!mobileOpen)}}
                          >
                            &#9776;
                          </button>
                        </div>
                      </div>
                      {{mobileOpen && (
                        <div className="md:hidden px-4 pb-4 space-y-2">
                          {{items.map((item) => (
                            <a
                              key={{item.href}}
                              href={{item.href}}
                              className="block {muted} hover:{text_color} text-sm"
                            >
                              {{item.label}}
                            </a>
                          ))}}
                        </div>
                      )}}
                    </nav>
                  );
                }}
            """),
            "hero": textwrap.dedent(f"""\
                import React from "react";

                interface {name}Props {{
                  heading?: string;
                  subheading?: string;
                  ctaLabel?: string;
                  onCta?: () => void;
                }}

                /**
                 * {name} component -- a full-width hero section.
                 */
                export default function {name}({{
                  heading = "{title}",
                  subheading = "{subtitle}",
                  ctaLabel = "Get Started",
                  onCta,
                }}: {name}Props) {{
                  return (
                    <section className="relative {surface} py-20 px-6 text-center">
                      <h1 className="text-4xl md:text-6xl font-extrabold {text_color}">{{heading}}</h1>
                      <p className="mt-4 text-xl {muted} max-w-2xl mx-auto">{{subheading}}</p>
                      <button
                        onClick={{onCta}}
                        className="mt-8 {primary} text-white px-8 py-3 {radius} text-lg {primary_hover} {transitions} focus:outline-none focus:ring-2 focus:ring-{palette['primary']}"
                      >
                        {{ctaLabel}}
                      </button>
                    </section>
                  );
                }}
            """),
        }

        # Use a matching generator or fall back to a generic card.
        return generators.get(component_type, generators["card"])

    def _html_component(
        self,
        component_type: str,
        spec: dict[str, Any],
        requirements: dict[str, Any],
        palette: dict[str, str],
    ) -> str:
        """Generate a plain HTML page with embedded Tailwind CDN.

        Args:
            component_type: The kind of component.
            spec: Full design specification.
            requirements: Original requirements.
            palette: Colour palette mapping.

        Returns:
            Complete HTML source code.
        """
        content_hints = requirements.get("content_hints", [])
        title = content_hints[0] if content_hints else f"Sample {component_type.title()}"
        subtitle = content_hints[1] if len(content_hints) > 1 else "A brief description goes here."

        surface = f"bg-{palette['surface']}"
        text_color = f"text-{palette['text']}"
        muted = f"text-{palette['text_muted']}"
        primary = f"bg-{palette['primary']}"
        primary_hover = f"hover:bg-{palette['primary_hover']}"
        border = f"border-{palette['border']}"
        radius = spec.get("border_radius", "rounded-lg")
        shadow = spec.get("shadow", "shadow-md")
        padding = spec["spacing"]["padding"]

        inner_html = textwrap.dedent(f"""\
            <div class="{surface} {radius} {shadow} {padding} border {border} max-w-md mx-auto mt-10">
              <h2 class="text-2xl font-bold {text_color}">{title}</h2>
              <p class="mt-2 {muted}">{subtitle}</p>
              <button class="mt-4 {primary} text-white px-4 py-2 {radius} {primary_hover} transition-colors">
                Action
              </button>
            </div>
        """)

        return textwrap.dedent(f"""\
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8" />
              <meta name="viewport" content="width=device-width, initial-scale=1.0" />
              <title>{title}</title>
              <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-{palette['background']} min-h-screen">
            {textwrap.indent(inner_html, "  ")}
            </body>
            </html>
        """)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _layout_for_component(component_type: str, responsive: bool) -> dict[str, str]:
        """Return Tailwind layout classes for a given component type.

        Args:
            component_type: Component kind.
            responsive: Whether to include responsive breakpoint classes.

        Returns:
            A dict with ``"container"``, ``"grid"``, and ``"wrapper"`` keys.
        """
        base_layouts: dict[str, dict[str, str]] = {
            "card": {
                "container": "max-w-md mx-auto",
                "grid": "",
                "wrapper": "p-6",
            },
            "dashboard": {
                "container": "max-w-7xl mx-auto",
                "grid": "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
                "wrapper": "p-4",
            },
            "form": {
                "container": "max-w-lg mx-auto",
                "grid": "",
                "wrapper": "p-6",
            },
            "navbar": {
                "container": "max-w-7xl mx-auto",
                "grid": "flex items-center justify-between",
                "wrapper": "px-4 py-3",
            },
            "hero": {
                "container": "max-w-4xl mx-auto text-center",
                "grid": "",
                "wrapper": "py-20 px-6",
            },
            "modal": {
                "container": "max-w-lg mx-auto",
                "grid": "",
                "wrapper": "p-6",
            },
            "sidebar": {
                "container": "w-64 min-h-screen",
                "grid": "flex flex-col",
                "wrapper": "p-4",
            },
            "footer": {
                "container": "max-w-7xl mx-auto",
                "grid": "grid grid-cols-1 md:grid-cols-3 gap-8",
                "wrapper": "py-12 px-6",
            },
        }

        layout = base_layouts.get(component_type, base_layouts["card"]).copy()

        if responsive and "md:" not in layout["grid"]:
            layout["grid"] = layout["grid"] or "grid grid-cols-1 md:grid-cols-2 gap-4"

        return layout

    @staticmethod
    def _transitions_for_interactions(interactions: list[str]) -> list[str]:
        """Map interaction hints to Tailwind transition utility classes.

        Args:
            interactions: Interaction keywords from requirements.

        Returns:
            A list of Tailwind class strings.
        """
        mapping: dict[str, str] = {
            "hover": "transition-colors duration-200",
            "click": "active:scale-95 transition-transform",
            "toggle": "transition-all duration-300",
            "expand": "transition-all duration-300 ease-in-out",
            "collapse": "transition-all duration-300 ease-in-out",
            "animate": "transition-all duration-500",
            "transition": "transition-all duration-200",
            "scroll": "scroll-smooth",
            "drag": "cursor-grab active:cursor-grabbing",
        }
        classes: list[str] = []
        for interaction in interactions:
            tw = mapping.get(interaction)
            if tw and tw not in classes:
                classes.append(tw)
        if not classes:
            classes.append("transition-colors duration-200")
        return classes

    @staticmethod
    def _pascal_case(name: str) -> str:
        """Convert a lowercase or kebab-case name to PascalCase.

        Args:
            name: Input string.

        Returns:
            PascalCase version.
        """
        return "".join(word.capitalize() for word in re.split(r"[-_ ]+", name))

    @staticmethod
    def _format_output(
        requirements: dict[str, Any],
        spec: dict[str, Any],
        component_code: dict[str, str],
    ) -> str:
        """Format the combined output of all three phases.

        Args:
            requirements: Design requirements.
            spec: Design specification.
            component_code: Generated code files.

        Returns:
            A human-readable summary string.
        """
        sections: list[str] = []

        sections.append("## Design Output\n")
        sections.append(f"**Component:** {requirements.get('component_type', 'card')}")
        sections.append(f"**Framework:** {requirements.get('framework', 'react')}")
        sections.append(f"**Color scheme:** {requirements.get('color_scheme', 'default')}")
        sections.append(f"**Responsive:** {requirements.get('responsive', False)}")

        if requirements.get("interactions"):
            sections.append(f"**Interactions:** {', '.join(requirements['interactions'])}")
        sections.append("")

        # Typography tokens
        sections.append("### Design Tokens\n")
        for key, value in spec.get("typography", {}).items():
            sections.append(f"- **{key}:** `{value}`")
        sections.append("")

        # Generated code
        sections.append("### Generated Code\n")
        for filename, source in component_code.items():
            lang = "tsx" if filename.endswith(".tsx") else "html"
            sections.append(f"#### `{filename}`\n")
            sections.append(f"```{lang}")
            sections.append(source)
            sections.append("```\n")

        return "\n".join(sections)
