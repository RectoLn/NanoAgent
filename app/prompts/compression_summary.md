Compress the following conversation history into a structured summary.
Return ONLY a JSON object, no prose, no markdown fences, in exactly this shape:

{
  "progress_summary": "concise bullet list of completed steps, key decisions, and current status",
  "file_knowledge": [
    {"path": "file or url that was read", "conclusion": "key conclusion from reading it, max 100 chars"}
  ],
  "state_patch": {
    "constraints": ["explicit constraints or rules the user stated"],
    "facts": ["verified facts established during the conversation"],
    "invalidated_assumptions": ["assumptions that were explicitly corrected"]
  }
}

Only include a file in file_knowledge if the conversation contains a tool result from reading that file AND a subsequent assistant message drawing a conclusion from it.
Do not invent conclusions.

{messages}
