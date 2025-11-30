import os
import subprocess
import json
import sys
import re
from collections import defaultdict
from google import genai
from google.genai import types

# Settings
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    print("Error: Environment Variable API_KEY was not defined.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

def split_diff_by_file(diff_text: str):
    files = {}
    current_file = None
    buffer = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if current_file:
                files[current_file] = "\n".join(buffer)
            buffer = []
            match = re.search(r"a/(.*?) b/(.*)", line)
            if match:
                current_file = match.group(2)
        if current_file:
            buffer.append(line)

    if current_file:
        files[current_file] = "\n".join(buffer)

    return files

def run_git(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors='replace'
        )
        return result
    except Exception as e:
        print(f"Error executing git: {e}")
        sys.exit(1)

def get_git_diff():
    
    diff_staged = run_git(["diff", "--cached"]).stdout
    
    diff_unstaged = run_git(["diff"]).stdout
    
    if not diff_staged.strip and not diff_unstaged.strip():
        return ""
    
    combined = []
    
    if diff_staged.strip():
        combined.append("### STAGED CHANGES\n")
        combined.append(diff_staged)
        
    if diff_unstaged.strip():
        combined.append("\n### UNSTAGED CHANGES\n")
        combined.append(diff_unstaged)

    return "\n".join(combined)

def generate_commit_groups(file_diffs: dict):
    prompt = f"""
        Act as a senior software engineer and Git expert.

        You will receive multiple file diffs.
        Your task is to group them into multiple atomic commits.

        RULES (MANDATORY):
        - Allowed types ONLY:
        feat, fix, refactor, chore, style, test, docs
        - The subject MUST strictly follow:
        <type>: <short description>
        - Example:
        refactor: extract auth service
        - Never invent new commit types.
        - Never omit the type.
        - Never return invalid JSON.

        For EACH commit group, generate:
        - type (one of the allowed)
        - subject (starting with <type>:)
        - body (detailed explanation)
        - analysis (technical reasoning)
        - paths (list of file paths)

        Return STRICT VALID JSON in this format:

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
        {json.dumps(file_diffs)[:30000]}
        ```
        """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)["commits"]
    except Exception as e:
        print(f"API Error: {e}")
        sys.exit(1)

def create_commit_block(commit):
    title = commit["subject"]
    body = commit["body"]
    paths = commit["paths"]

    add_command = "git add " + " ".join(paths)

    commit_command = [f'git commit -m "{title}"']
    for line in body.strip().split("\n"):
        line = line.replace('"', '\\"')
        commit_command.append(f'-m "{line}"')

    return {
        "add": add_command,
        "commit": " ".join(commit_command)
    }


def create_git_commit_command(title: str, body: str):
    parts = [f'git commit -m "{title}"']
    for line in body.strip().split("\n"):
        line = line.replace('"', '\\"')
        parts.append(f'-m "{line}"')
    return " ".join(parts)

def main():
    print("Analyzing git changes...")
    diff = get_git_diff()

    if not diff.strip():
        print("No changes detected.")
        sys.exit(0)

    file_diffs = split_diff_by_file(diff)

    print("Generating commit suggestions...")
    commits = generate_commit_groups(file_diffs)

    print("=" * 60)

    for i, commit in enumerate(commits, start=1):
        print(f"COMMIT {i}")
        print("-" * 60)

        print("Analysis:")
        print(commit.get("analysis", "N/A"))
        print("")

        print("Subject:")
        print(commit["subject"])
        print("")

        print("Body:")
        print(commit["body"])
        print("")

        commands = create_commit_block(commit)

        print("Stage files:")
        print(commands["add"])
        print("")

        print("Commit command:")
        print(commands["commit"])
        print("")
        print("=" * 60)

if __name__ == "__main__":
    main()
