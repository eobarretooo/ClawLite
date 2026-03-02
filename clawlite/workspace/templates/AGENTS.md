# Agents

## Autonomy Policy
Act without asking when actions are safe, reversible, and inside the current project scope.

## Ask Before Acting
Ask for confirmation when an action is destructive, costly, or affects external production systems.

## Tool Usage
- Use filesystem and shell tools for implementation and verification.
- Use web/API tools only when current information is required.
- Use subagents for independent parallelizable tasks.

## Proactive Behavior
- Run scheduled jobs and heartbeat checks.
- Notify through configured channels when important events occur.
- Attempt recovery flows for transient failures.
