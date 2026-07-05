---
name: repo-archive
description: Export all Claude Code conversations for this repo to human-readable Markdown in agent-conversations/, then build a zip of the repo (git archive) that also contains those conversations even though they are gitignored. Use when the user asks to archive, export, or snapshot the repo including its agent conversations.
---

# Repo archive with agent conversations

Run the bundled script from the repo root:

```bash
python3 .claude/skills/repo-archive/archive_repo.py
```

What it does:

1. **Export** — reads every session file in `~/.claude/projects/<munged-repo-path>/*.jsonl` and writes one readable Markdown file per session into `agent-conversations/` (user/assistant messages, collapsible thinking, tool calls and truncated tool results), plus a `README.md` index. Subagent sidechains are skipped.
2. **Archive** — runs `git archive --format=zip HEAD` into `dist/<repo>-<date>.zip`, then appends `agent-conversations/` to the zip with `zip -r`. This second step is required because `git archive` only packs *tracked* files and `agent-conversations/` is gitignored on purpose.

Options:

- `--no-zip` — only export the Markdown, skip building the archive.

After running, report the zip path, its size, and how many conversations were exported. If a session file is skipped as "no conversation", that is normal (empty or tool-only sessions).

Notes:

- `agent-conversations/` and `dist/` are gitignored; never commit them.
- The currently running session is exported too but will be incomplete up to the moment of export — mention this to the user.
