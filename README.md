# AI Commit Message Agent

`commit-ai-agent.py` is a standalone Python tool that automatically generates clear git commit messages using a Google GenAI model.
It analyzes both staged and unstaged changes in your repository and outputs a fully-formatted `git commit` command ready to paste into the terminal.

---

## Features

* Extracts **staged** and **unstaged** diffs.
* Builds a detailed prompt for the AI model, including the full diff.
* Generates commit messages following **Conventional Commits** guidelines.
* Produces commit subject, body, and an internal analysis of the changes.
* Outputs the final result as a ready-to-run:

```
git commit -m "subject" -m "body..."
```

---

## Requirements

* Python 3.10+
* A valid Google GenAI API key.

Set the environment variable:

```
API_KEY=your_api_key_here
```

---

## Usage

Run the script from a git repository:

```
python commit-ai-agent.py
```

If changes are detected, the script will:

1. Collect diffs (staged + unstaged).
2. Request an AI-generated commit message.
3. Display a complete `git commit` command for you to execute.

If no changes exist, the script exits gracefully.

---

## How It Works

1. The script runs:

   * `git diff --cached` for staged changes
   * `git diff` for unstaged changes
2. It combines both diffs with clear section labels.
3. A structured prompt is sent to the GenAI model, requesting:

   * A commit subject
   * A descriptive body
   * A short analysis of the changes
4. The response is parsed and converted into a `git commit` command.

---

## Example Output

```
git commit -m "feat: introduce AI-powered commit message generator" \
 -m "Adds commit-ai-agent.py, a tool that uses Google GenAI..." \
 -m "..."
```

Just copy and run.

---

## Notes

This project is intentionally simple: a single script acting as an AI-powered assistant for generating commit messages. It does not run background processes, daemons, or agents — it simply executes when you run it and returns a result based on the current git state.

---

## License

MIT License.
