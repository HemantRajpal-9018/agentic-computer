---
name: example-skill
description: A reference skill demonstrating the agentic-computer skill interface.
version: 0.1.0
author: agentic-computer
tags:
  - example
  - reference
  - template
tools:
  - memory
triggers:
  - example task
  - demonstrate skill
  - test the skill system
---

# Example Skill

A minimal but complete skill implementation that serves as a starting point for building your own skills. This skill handles simple demonstration tasks by echoing the input, storing a memory, and returning a structured result.

## Instructions

When this skill is activated, follow these steps:

1. Parse the task description to understand what is being requested.
2. If the task is a simple echo or demonstration request, process it directly.
3. Store the task and result in memory for future reference.
4. Return a structured SkillResult with the output and any artifacts.

Keep responses concise and well-formatted. This skill is meant to validate that the skill system is working correctly, not to perform complex analysis.

## Tools Required

- **memory** -- Used to store task results for future retrieval. If memory is unavailable, the skill still functions but does not persist results.

## Constraints

- This skill should only handle simple demonstration tasks.
- Do not attempt complex reasoning or multi-step operations.
- Maximum output length: 500 characters.

## Output Format

The skill returns a `SkillResult` with:
- `output`: A plain-text summary of what was processed.
- `artifacts`: An optional list containing a single dict with the key `type` set to `"echo"` and `content` containing the echoed input.
- `metadata`: Contains the original task and a timestamp.

## Examples

### Example 1: Basic echo

**Input task:** "Run the example skill with the message: Hello, world!"

**Expected output:**
```
Example skill executed successfully.
Input: Run the example skill with the message: Hello, world!
Echo: Hello, world!
```

**Expected artifacts:**
```json
[{"type": "echo", "content": "Hello, world!"}]
```

### Example 2: System check

**Input task:** "Test the skill system"

**Expected output:**
```
Example skill executed successfully.
The skill system is operational. This response confirms that skill
discovery, confidence scoring, context injection, and execution
are all working correctly.
```

### Example 3: No matching content

**Input task:** "Analyze quarterly revenue data"

This task should receive a low confidence score (< 0.2) from `can_handle()`, and the framework should route it to a more appropriate skill instead.
