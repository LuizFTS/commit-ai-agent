import os
import subprocess
import json
import sys
from google import genai
from google.genai import types

# Settings
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    print("Error: Environment Variable API_KEY was not defined.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

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

def generate_commit_message(diff_content):
    if not diff_content.strip():
        print("Any changes detected at git.")
        sys.exit(0)

    prompt = f"""
    Act as a senior software engineer and git expert.
    Analyze the following 'git diff' output and generate a high-quality commit message.
    
    Configuration:
    - Style: Conventional Commits (e.g., feat: ..., fix: ...)
    - Tone: professional
    - Language: English
    - Use Emoji: No
    - Detect Breaking Changes: Yes (add footer BREAKING CHANGE: <desc>)

    Input Diff:
    ```
    {diff_content[:30000]}
    ```

    Instructions:
    1. Analyze the diff to understand the semantic meaning.
    2. Separate 'subject' (max 50-72 chars) from 'body'.
    3. Return strictly valid JSON with keys: subject, body, analysis.
    4. Return the suggested commit with a git commit terminal code
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "subject": {"type": "STRING"},
                        "body": {"type": "STRING"},
                        "analysis": {"type": "STRING"}
                    },
                    "required": ["subject", "body"]
                }
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"API Error: {e}")
        sys.exit(1)

def create_git_commit_command(title: str, body: str):
    parts = [f'git commit -m "{title}"']
    for line in body.strip().split("\n"):
        line = line.replace('"', '\\"')
        parts.append(f'-m "{line}"')
    return " ".join(parts)

def main():
    print("Analyzing git changes...")
    diff = get_git_diff()
    
    print("Creating the commit message...")
    result = generate_commit_message(diff)
    
    print("-" * 40)
    print("Analysis:")
    print("")
    print(f"{result.get('analysis', 'N/A')}")
    print("-" * 40)
    print(f"Suggested Commit:")
    print("")
    print(f"{result['subject']}")
    print(f"{result['body']}")
    print("-" * 40)
    print("")
    command = create_git_commit_command(result['subject'], result['body'])
    print(command)
    print("-" * 40)

if __name__ == "__main__":
    main()
