from __future__ import annotations
import shutil
import subprocess

SKILL_NAME = "github"
SKILL_DESCRIPTION = 'Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries.'

def run(command: str = "") -> str:
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    proc = subprocess.run(command, shell=True, text=True, capture_output=True)
    if proc.returncode != 0:
        return proc.stderr.strip() or "erro"
    return proc.stdout.strip()

def info() -> str:
    return '---\nname: github\ndescription: "Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries."\n---\n# GitHub Skill\nUse the `gh` CLI to interact with GitHub. Always specify `--repo owner/repo` when not in a git directory, or use URLs directly.\n## Pull Requests\nCheck CI status on a PR:\n```bash\ngh pr checks 55 --repo owner/repo\n```\nList recent workflow runs:\n```bash\ngh run list --repo owner/repo --limit 10\n```\nView a run and see which steps failed:\n```bash\ngh run view <run-id> --repo owner/repo\n```\nView logs for failed steps only:\n```bash\ngh run view <run-id> --repo owner/repo --log-failed\n```\n## API for Advanced Queries\nThe `gh api` command is useful for accessing data not available through other subcommands.\nGet PR with specific fields:\n```bash\ngh api repos/owner/repo/pulls/55 --jq \'.title, .state, .user.login\'\n```\n## JSON Output\nMost commands support `--json` for structured output.  You can use `--jq` to filter:\n```bash\ngh issue list --repo owner/repo --json number,title --jq \'.[] | "\\(.number): \\(.title)"\'\n```'
