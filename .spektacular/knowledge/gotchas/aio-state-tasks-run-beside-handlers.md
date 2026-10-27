---
tags: [python, asyncio, events, state, testing]
---

# Under asyncio, state tasks do not wait for the event handler

`xcl.aio.Config._drive` starts each state task and function task it polls as its own asyncio task, while events go, in order, to one consumer task that calls `on_event`. The synchronous driver calls `on_event` between polls, so the SAVE that follows a create success event is not answered until the handler returns. Under asyncio that SAVE can complete while the handler for the preceding event is still running, or before that handler starts. So under asyncio, "the engine is still mid-apply inside my handler" is not guaranteed by a Python state store alone. A test that needs it must gate the store's `save` on an `asyncio.Event` that the handler sets. Gate only the save that follows the event, such as one holding the created record: an earlier save gated the same way waits until its timeout.
