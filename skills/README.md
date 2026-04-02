# Community Skills Directory

This directory contains community-contributed skills for the **agentic-computer** framework. Skills are self-contained capabilities that extend the agent's ability to handle specialized tasks -- from data analysis and code generation to research synthesis and design automation.

---

## What Are Community Skills?

Community skills are modular extensions written by contributors that plug into the agentic-computer skill system. Each skill:

- Lives in its own subdirectory under `skills/`
- Contains a `SKILL.md` file that declares metadata and instructions
- Implements the `BaseSkill` interface (see `agentic_computer/skills/base.py`)
- Optionally includes pre/post execution hooks for validation and enrichment

The framework automatically discovers skills in this directory at startup. When a task is submitted, the system scores every skill's `can_handle()` confidence and dispatches to the best match.

---

## Directory Structure

```
skills/
  README.md                      # This file
  example-skill/                 # A reference skill implementation
    SKILL.md                     # Skill metadata and instructions
    __init__.py                  # Package init exporting the skill class
    skill.py                     # Skill implementation
    hooks/                       # Optional execution hooks
      pre_execute.py             # Runs before skill execution
      post_execute.py            # Runs after skill execution
  your-custom-skill/             # Your skill goes here
    SKILL.md
    __init__.py
    skill.py
    hooks/
      ...
```

### Required Files

| File | Required | Description |
|------|----------|-------------|
| `SKILL.md` | Yes | Metadata frontmatter (name, description, version, author, tags) and instructions. |
| `__init__.py` | Yes | Exports the skill class for auto-discovery. |
| `skill.py` | Yes | Contains the class that extends `BaseSkill`. |
| `hooks/pre_execute.py` | No | Pre-execution hook for validation and context enrichment. |
| `hooks/post_execute.py` | No | Post-execution hook for result processing and cleanup. |

---

## Available Skills

| Skill | Version | Description | Author |
|-------|---------|-------------|--------|
| [example-skill](./example-skill/) | 0.1.0 | A reference implementation demonstrating the skill interface. | agentic-computer |

Want to see your skill listed here? Submit a pull request.

---

## How to Submit a Skill

### 1. Fork and clone the repository

```bash
git clone https://github.com/<your-username>/agentic-computer.git
cd agentic-computer
```

### 2. Create your skill directory

```bash
mkdir -p skills/my-skill/hooks
```

### 3. Implement the required files

Follow the [Skills Guide](../docs/skills-guide.md) for a detailed walkthrough. At minimum you need:

- `SKILL.md` with valid frontmatter
- `__init__.py` that exports your skill class
- `skill.py` with a class extending `BaseSkill`

### 4. Add tests

Create test files under `tests/skills/`:

```bash
mkdir -p tests/skills
# Add test_my_skill.py with at least:
#   - test for can_handle() with relevant and irrelevant tasks
#   - test for execute() with mocked dependencies
```

### 5. Update this README

Add your skill to the **Available Skills** table above.

### 6. Submit a pull request

Open a PR against the `main` branch with:
- A clear title (e.g., "Add web-scraping skill")
- Description of what the skill does and when it should be used
- Example usage showing the task input and expected output

---

## Skill Quality Guidelines

All submitted skills are expected to meet these quality standards:

### Naming

- Use lowercase with hyphens for the directory name: `my-skill-name/`
- The `name` field in SKILL.md must match the directory name
- Choose a descriptive, specific name (prefer `web-scraping` over `scraper`)

### Documentation

- The `SKILL.md` must include a complete `Instructions` section
- Include at least one concrete example in the `Examples` section
- Document any external dependencies or API keys required
- Specify the expected output format

### Implementation

- `can_handle()` must return meaningful confidence scores:
  - 0.0 - 0.1 for completely irrelevant tasks
  - 0.3 - 0.5 for partially relevant tasks
  - 0.7 - 1.0 for tasks the skill is designed to handle
- `get_required_tools()` must list every tool the skill calls
- `execute()` must never raise unhandled exceptions; always return `SkillResult(success=False, ...)` on failure
- Handle edge cases: empty input, missing tools, timeout scenarios

### Versioning

- Follow [Semantic Versioning](https://semver.org/)
- Start at `0.1.0` for initial submissions
- Increment the minor version for new features, patch for bug fixes
- Increment the major version for breaking changes to the skill interface

### Testing

- Include at least one unit test for `can_handle()` covering both positive and negative cases
- Include at least one integration test for `execute()` using mocked tools
- Tests must pass in CI before the PR can be merged

### Code Quality

- Follow the project's coding standards (Ruff linting, mypy type checking)
- Use type annotations for all public methods
- Add docstrings to the skill class and its public methods
- Keep the skill focused -- one skill should do one thing well
