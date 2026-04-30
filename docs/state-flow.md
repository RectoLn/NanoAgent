# NanoAgent State Flow

This document is the end-to-end map for session state, context compaction, Todo
state, and SSE persistence. Use it as the checkpoint before changing any of the
five moving parts again.

## Runtime Flow

```text
user message
  |
  v
server/task_manager starts ToolCallAgent.run_iter(question, history)
  |
  +-- emits message_delta(user)
  |     |
  |     +-- task_manager/server -> session.add_message()
  |           |
  |           +-- session.messages: visible + replayable raw message
  |           +-- session.display_messages: UI history
  |           +-- session.state: extracted user constraints
  |
  v
per-step loop
  |
  +-- micro_compact(messages)
  |     |
  |     +-- truncates old large tool messages
  |     +-- records tool observations into session.state.observations
  |
  +-- compression check
  |     |
  |     +-- if token/message threshold exceeded:
  |           |
  |           +-- auto_compact(messages)
  |                 |
  |                 +-- formats current messages for summary LLM
  |                 +-- parses JSON summary or uses deterministic fallback
  |                 +-- merges state_patch/file_knowledge into session.state
  |                 +-- build_compacted_messages()
  |                       |
  |                       +-- system prompt
  |                       +-- first user request
  |                       +-- authoritative session state
  |                       +-- compacted summary
  |                       +-- current Todo status
  |                       +-- latest user request, if different
  |                 +-- appends session.compression_history
  |           |
  |           +-- emits context_snapshot(messages)
  |                 |
  |                 +-- task_manager/server -> session.replace_messages_from_llm()
  |                       |
  |                       +-- session.messages: compacted LLM replay context
  |                       +-- session.display_messages: unchanged UI history
  |
  v
inject_authoritative_state(messages)
  |
  +-- removes stale authoritative state messages
  +-- inserts current session.state for the next LLM call
  |
  v
LLM call with tools
  |
  +-- stop
  |     |
  |     +-- emits final + message_delta(assistant) + done
  |
  +-- tool_calls
        |
        +-- emits message_delta(assistant with tool_calls)
        |
        +-- execute_tool_call()
              |
              +-- todo_add / todo_update / todo_replan
                    |
                    +-- TodoManager validates:
                    |     - one in_progress
                    |     - no duplicate ids
                    |     - no duplicate or near-duplicate task text
                    |     - no silent unrelated full replacement
                    |
                    +-- emits todo_update(items)
                          |
                          +-- task_manager/server -> session.tasks = items
        |
        +-- emits message_delta(tool result)
        |
        +-- next step lets LLM observe result
```

## Expected Invariants

- UI history and LLM context are intentionally separate:
  - `display_messages` preserves the readable conversation.
  - `messages` may be compacted and is the replay context sent to the model.
- A compacted context must still contain:
  - the first user goal,
  - authoritative state,
  - the compacted summary,
  - current Todo state,
  - the latest user request when needed.
- Todo state is owned by `TodoManager` during execution and persisted through
  `todo_update` events into `session.tasks`.
- A model may not create a second active task for work already represented in
  the Todo list. It must call `todo_update` instead.
- `invalidated_assumptions` must not contain the same text as active user
  constraints.

## Regression Anchor

`tests/test_state_flow.py` simulates a long-chain session that triggers
compaction and then attempts a duplicate Todo addition. It asserts that:

- compaction emits a context snapshot,
- Todo state survives compaction,
- duplicate Todo creation is rejected,
- persisted pre-existing duplicate tasks are cleaned on Agent restore,
- state normalization removes constraint/invalidated duplicates.
