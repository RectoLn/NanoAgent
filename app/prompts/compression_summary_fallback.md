Compress the following conversation history.
Return ONLY a JSON object, with no prose and no markdown fences, in exactly this shape:

{
  "progress_summary": "...",
  "state_patch": {
    "constraints": ["..."],
    "facts": ["..."],
    "invalidated_assumptions": ["..."]
  }
}

{messages}
