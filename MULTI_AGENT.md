# Shweta Multi-Agent Brain

Shweta now uses an **Agent Hub** instead of sending every request through one
large, rigid tool list.

## Agents

- **Friend** — natural Hinglish conversation, emotional support and continuity.
- **Desktop** — apps, files, media, system controls and timers.
- **Researcher** — web research, comparison and shopping tasks.
- **Memory** — durable user facts and preferences.
- **Planner** — multi-part requests and browser workflows.

The coordinator selects a specialist from the user's intent, adds persistent
memory and usage context, then asks the configured AI providers to return one
validated desktop action. If providers are unavailable, local intent routing
still handles time, date, weather, screenshots, music and memory commands.

## Provider behavior

Only configured keys create clients. The hub tries OpenAI, GitHub Models and
Groq in the order available, then falls back to local routing. Empty keys no
longer create a broken client or crash the first user request.

## Memory behavior

Free-form facts are stored in `user_memory.json` under `facts`, so they survive
restarts and are included in future agent context. The old working-directory
`memory.txt` append path is no longer used.
