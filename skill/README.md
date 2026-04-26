# HKS Agent Skills

This directory exposes CLI-first repo-local agent guidance in a visible, non-hidden path.

Start here:

- `hks-knowledge-system/SKILL.md`: main `ks` CLI operating manual
- `hks-knowledge-system/README.md`: complete skill framework and file map
- `hks-knowledge-system/agents/claude.md`: Claude / Claude Code CLI handoff
- `hks-knowledge-system/agents/openclaw.md`: OpenClaw CLI handoff

For MCP / HTTP adapter usage, read `../mcp/README.md`. The `mcp/` directory is HTTP-first and adapter-specific.

The hidden `.codex/skills/hks-knowledge-system/` copy is kept for Codex skill discovery and may contain OpenAI-specific metadata such as `agents/openai.yaml`. Keep the two `SKILL.md` files in sync when changing runtime guidance.
