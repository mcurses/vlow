#!/usr/bin/env python3
"""Export Claude Code conversations for this repo to Markdown, then build a
zip of the repo (git archive) that additionally contains the exported
conversations even though they are gitignored.

Usage: python3 .claude/skills/repo-archive/archive_repo.py [--no-zip]

Output:
  agent-conversations/   one .md per session + README.md index (gitignored)
  dist/<repo>-<date>.zip git archive of HEAD + agent-conversations/
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TOOL_INPUT_LIMIT = 800
TOOL_RESULT_LIMIT = 1500
THINKING_LIMIT = 1500

REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
)
OUT_DIR = REPO_ROOT / "agent-conversations"


def project_dir() -> Path:
    """Claude Code stores sessions under ~/.claude/projects/<munged-cwd>/."""
    munged = re.sub(r"[^A-Za-z0-9]", "-", str(REPO_ROOT))
    return Path.home() / ".claude" / "projects" / munged


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n… [truncated, {len(text)} chars total]"


def strip_reminders(text: str) -> str:
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    return text.strip()


def fence(text: str, lang: str = "") -> str:
    """Code-fence text, growing the fence if the text contains backticks."""
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{lang}\n{text}\n{ticks}"


def details(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def tool_use_md(block: dict) -> str:
    name = block.get("name", "unknown")
    inp = block.get("input", {})
    if name == "Bash":
        summary = inp.get("description") or ""
        body = fence(truncate(inp.get("command", ""), TOOL_INPUT_LIMIT), "bash")
    elif name in ("Read", "Write", "Edit"):
        summary = inp.get("file_path", "")
        shown = {k: v for k, v in inp.items() if k != "file_path"}
        body = fence(truncate(json.dumps(shown, indent=2, ensure_ascii=False), TOOL_INPUT_LIMIT), "json")
    else:
        summary = ""
        body = fence(truncate(json.dumps(inp, indent=2, ensure_ascii=False), TOOL_INPUT_LIMIT), "json")
    label = f"🔧 <code>{name}</code>"
    if summary:
        label += f" — {summary}"
    return details(label, body)


def tool_result_text(block: dict) -> str:
    content = block.get("content", "")
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = "\n".join(parts)
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return strip_reminders(content)


def load_entries(path: Path) -> list:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def session_to_markdown(path: Path) -> dict | None:
    entries = load_entries(path)
    messages = [
        e for e in entries
        if e.get("type") in ("user", "assistant")
        and not e.get("isSidechain")
        and not e.get("isMeta")
    ]
    if not messages:
        return None

    # Map tool_use_id -> result text so results render next to their call.
    results = {}
    for e in messages:
        content = e.get("message", {}).get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    results[b.get("tool_use_id")] = b

    first_ts = messages[0].get("timestamp", "")
    last_ts = messages[-1].get("timestamp", "")
    branch = messages[0].get("gitBranch", "")
    session_id = path.stem

    lines = []
    first_prompt = None
    n_user = n_assistant = 0

    for e in messages:
        msg = e.get("message", {})
        role = e.get("type")
        content = msg.get("content")

        if role == "user":
            if isinstance(content, str):
                text = strip_reminders(content)
                if not text:
                    continue
                if text.startswith("<command-name>"):
                    m = re.search(r"<command-name>(.*?)</command-name>", text)
                    lines.append(f"**👤 Max:** *(ran `{m.group(1) if m else 'command'}`)*\n")
                    continue
                if text.startswith("<local-command-stdout>"):
                    continue
                n_user += 1
                if first_prompt is None:
                    first_prompt = text
                lines.append(f"**👤 Max:**\n\n{text}\n")
            elif isinstance(content, list):
                texts = []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        t = strip_reminders(b.get("text", ""))
                        if t and not t.startswith("<command-name>") and not t.startswith("<local-command-stdout>"):
                            texts.append(t)
                    elif b.get("type") == "image":
                        texts.append("*(attached an image)*")
                if texts:
                    n_user += 1
                    joined = "\n\n".join(texts)
                    if first_prompt is None:
                        first_prompt = joined
                    lines.append(f"**👤 Max:**\n\n{joined}\n")
            continue

        # assistant
        if not isinstance(content, list):
            continue
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            btype = b.get("type")
            if btype == "thinking":
                t = b.get("thinking", "").strip()
                if t:
                    parts.append(details("💭 Thinking", truncate(t, THINKING_LIMIT)))
            elif btype == "text":
                t = b.get("text", "").strip()
                if t:
                    parts.append(t)
            elif btype == "tool_use":
                parts.append(tool_use_md(b))
                res = results.get(b.get("id"))
                if res:
                    rtext = tool_result_text(res)
                    if rtext:
                        flag = "❌ Tool result (error)" if res.get("is_error") else "✅ Tool result"
                        parts.append(details(flag, fence(truncate(rtext, TOOL_RESULT_LIMIT))))
        if parts:
            n_assistant += 1
            lines.append("**🤖 Claude:**\n\n" + "\n\n".join(parts) + "\n")

    if first_prompt is None:
        return None

    date = first_ts[:10] if first_ts else "unknown-date"
    slug = re.sub(r"[^a-z0-9]+", "-", first_prompt.lower())[:60].strip("-")
    filename = f"{date}_{slug}_{session_id[:8]}.md"

    header = [
        f"# Session {session_id[:8]} — {date}",
        "",
        f"- **Session ID:** `{session_id}`",
        f"- **Started:** {first_ts}",
        f"- **Last message:** {last_ts}",
        f"- **Git branch:** `{branch}`" if branch else "",
        f"- **Messages:** {n_user} user / {n_assistant} assistant",
        "",
        "---",
        "",
    ]
    body = "\n".join(h for h in header if h is not None) + "\n" + "\n".join(lines)

    return {
        "filename": filename,
        "markdown": body,
        "date": date,
        "first_prompt": first_prompt,
        "n_user": n_user,
        "n_assistant": n_assistant,
        "session_id": session_id,
    }


def export_conversations() -> list:
    src = project_dir()
    if not src.is_dir():
        print(f"No Claude project directory found at {src}", file=sys.stderr)
        return []
    OUT_DIR.mkdir(exist_ok=True)
    sessions = []
    for jsonl in sorted(src.glob("*.jsonl")):
        info = session_to_markdown(jsonl)
        if info is None:
            print(f"  skipped (no conversation): {jsonl.name}")
            continue
        (OUT_DIR / info["filename"]).write_text(info["markdown"], encoding="utf-8")
        print(f"  wrote {info['filename']}")
        sessions.append(info)

    sessions.sort(key=lambda s: s["date"])
    index = [
        "# Agent Conversations",
        "",
        f"Claude Code sessions for `{REPO_ROOT.name}`, exported "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}. "
        "Subagent sidechains are omitted; long tool output is truncated.",
        "",
        "| Date | Session | Messages (user/asst) | First prompt |",
        "|---|---|---|---|",
    ]
    for s in sessions:
        prompt = s["first_prompt"].replace("\n", " ").replace("|", "\\|")
        if len(prompt) > 100:
            prompt = prompt[:100] + "…"
        index.append(
            f"| {s['date']} | [{s['session_id'][:8]}]({s['filename']}) "
            f"| {s['n_user']}/{s['n_assistant']} | {prompt} |"
        )
    (OUT_DIR / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"  wrote README.md ({len(sessions)} sessions)")
    return sessions


def build_zip() -> Path:
    dist = REPO_ROOT / "dist"
    dist.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    zip_path = dist / f"{REPO_ROOT.name}-{stamp}.zip"
    subprocess.run(
        ["git", "archive", "--format=zip", "-o", str(zip_path), "HEAD"],
        cwd=REPO_ROOT, check=True,
    )
    # git archive only packs tracked files; append the gitignored exports.
    subprocess.run(
        ["zip", "-r", "-q", str(zip_path), "agent-conversations"],
        cwd=REPO_ROOT, check=True,
    )
    return zip_path


def main() -> None:
    print("Exporting conversations …")
    sessions = export_conversations()
    if "--no-zip" in sys.argv:
        return
    print("Building archive …")
    zip_path = build_zip()
    size_mb = zip_path.stat().st_size / 1e6
    print(f"Done: {zip_path} ({size_mb:.1f} MB, {len(sessions)} conversations included)")


if __name__ == "__main__":
    main()
