import os
import subprocess
import json
import sys
import re
from dataclasses import dataclass
from google import genai
from google.genai import types

# ── Constants ────────────────────────────────────────────────────────────────

API_KEY = os.environ.get("API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
MAX_DIFF_CHARS = 30_000
ALLOWED_COMMIT_TYPES = {"feat", "fix", "refactor", "chore", "style", "test", "docs"}

COMMIT_PROMPT_TEMPLATE = """
Act as a senior software engineer and Git expert.

You will receive multiple file diffs, including diffs for brand-new (untracked) files.
Your task is to group them into atomic commits.

RULES (MANDATORY):
- Allowed types ONLY: feat, fix, refactor, chore, style, test, docs
- Subject MUST follow: <type>: <short description>
- Example: refactor: extract auth service
- Never invent new commit types.
- Never omit the type.
- Never return invalid JSON.

For EACH commit group, generate:
- type      (one of the allowed types)
- subject   (starting with <type>:)
- body      (detailed explanation)
- analysis  (technical reasoning)
- paths     (list of file paths included in this commit)

Return STRICT VALID JSON:

{{
    "commits": [
        {{
            "type": "refactor",
            "subject": "refactor: extract validation logic",
            "body": "Detailed explanation...",
            "analysis": "Why this change exists...",
            "paths": ["src/a.py", "src/b.py"]
        }}
    ]
}}

Here are the diffs:

```
{diffs}
```
"""

# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class CommitGroup:
    type: str
    subject: str
    body: str
    analysis: str
    paths: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> "CommitGroup":
        return cls(
            type=data["type"],
            subject=data["subject"],
            body=data["body"],
            analysis=data.get("analysis", "N/A"),
            paths=data["paths"],
        )

# ── Git helpers ───────────────────────────────────────────────────────────────

def run_git(*args: str) -> subprocess.CompletedProcess:
    """Run a git command and return the CompletedProcess result."""
    try:
        return subprocess.run(
            ["git", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        print(f"Error executing git: {exc}")
        sys.exit(1)


def get_staged_diff() -> str:
    return run_git("diff", "--cached").stdout


def get_unstaged_diff() -> str:
    return run_git("diff").stdout


def get_untracked_files() -> list[str]:
    """Return a list of untracked (new) files not yet staged."""
    output = run_git("ls-files", "--others", "--exclude-standard").stdout
    return [f.strip() for f in output.splitlines() if f.strip()]


def get_untracked_diff(paths: list[str]) -> str:
    """
    Build a pseudo-diff for untracked files by comparing /dev/null to each file.
    This makes new files visible to the AI with the same format as regular diffs.
    """
    diffs: list[str] = []
    for path in paths:
        result = run_git("diff", "--no-index", "/dev/null", path)
        if result.stdout.strip():
            diffs.append(result.stdout)
    return "\n".join(diffs)


def collect_all_diffs() -> str:
    """Collect staged, unstaged, and untracked diffs into a single string."""
    sections: list[str] = []

    staged = get_staged_diff()
    if staged.strip():
        sections.append("### STAGED CHANGES\n" + staged)

    unstaged = get_unstaged_diff()
    if unstaged.strip():
        sections.append("### UNSTAGED CHANGES\n" + unstaged)

    untracked_paths = get_untracked_files()
    if untracked_paths:
        untracked_diff = get_untracked_diff(untracked_paths)
        if untracked_diff.strip():
            sections.append("### NEW (UNTRACKED) FILES\n" + untracked_diff)

    return "\n\n".join(sections)

# ── Diff parsing ──────────────────────────────────────────────────────────────

def split_diff_by_file(diff_text: str) -> dict[str, str]:
    """Split a combined diff string into a dict keyed by file path."""
    files: dict[str, str] = {}
    current_file: str | None = None
    buffer: list[str] = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if current_file:
                files[current_file] = "\n".join(buffer)
            buffer = []
            match = re.search(r"b/(.*)", line)
            current_file = match.group(1) if match else None

        if current_file:
            buffer.append(line)

    if current_file:
        files[current_file] = "\n".join(buffer)

    return files

# ── AI interaction ────────────────────────────────────────────────────────────

def build_client() -> genai.Client:
    if not API_KEY:
        print("Error: environment variable API_KEY is not set.")
        sys.exit(1)
    return genai.Client(api_key=API_KEY)


def generate_commit_groups(file_diffs: dict[str, str], client: genai.Client) -> list[CommitGroup]:
    prompt = COMMIT_PROMPT_TEMPLATE.format(
        diffs=json.dumps(file_diffs)[:MAX_DIFF_CHARS]
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw_commits: list[dict] = json.loads(response.text)["commits"]
        return [CommitGroup.from_dict(c) for c in raw_commits]
    except (KeyError, json.JSONDecodeError) as exc:
        print(f"Failed to parse API response: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"API error: {exc}")
        sys.exit(1)

# ── Command building ──────────────────────────────────────────────────────────

def quote_path(path: str) -> str:
    return f'"{path}"' if " " in path else path


def build_full_command(commit: CommitGroup) -> str:
    """Build a single copy-pasteable shell command that stages and commits."""
    paths_str = " ".join(quote_path(p) for p in commit.paths)

    m_flags: list[str] = [f'-m "{commit.subject}"']
    for line in commit.body.strip().splitlines():
        escaped = line.replace('"', '\\"')
        m_flags.append(f'-m "{escaped}"')

    return f"git add {paths_str} && git commit {' '.join(m_flags)}"


def print_commit_block(index: int, commit: CommitGroup) -> None:
    print("=" * 60)
    print(f"COMMIT {index}")
    print("-" * 60)
    print(f"Analysis:\n{commit.analysis}\n")
    print(f"Subject:\n{commit.subject}\n")
    print(f"Body:\n{commit.body}\n")
    print("Command (copy & paste):")
    print("·" * 60)
    print(build_full_command(commit))
    print("·" * 60)
    print()

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Analyzing git changes...")

    diff = collect_all_diffs()
    if not diff.strip():
        print("No changes detected (staged, unstaged, or untracked).")
        sys.exit(0)

    file_diffs = split_diff_by_file(diff)
    if not file_diffs:
        print("No parseable file diffs found.")
        sys.exit(0)

    print(f"Found changes in {len(file_diffs)} file(s). Generating commit suggestions...\n")

    client = build_client()
    commits = generate_commit_groups(file_diffs, client)

    for i, commit in enumerate(commits, start=1):
        print_commit_block(i, commit)

    print("=" * 60)
    print(f"Total suggested commits: {len(commits)}")


if __name__ == "__main__":
    main()