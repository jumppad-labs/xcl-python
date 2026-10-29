---
tags: [python, asyncio, events, state, testing]
---

# Neither driver guarantees a handler runs before the next state task is answered

The engine can post the SAVE that follows a create success event before the event itself (see `gotchas/events-race-state-tasks.md` in the xcl store), so on either driver the operation may already be over when the handler for that event runs.

- **Synchronous driver** (`xcl/_poll.py`): it calls `on_event` between polls, but if the SAVE is polled first it is answered first, and the apply can finish before the handler starts. A state store cannot hold it back, because the driver answers it on the same thread that would deliver the event. A test that needs the apply to still be running in its handler must keep the apply busy instead: give it a second slow resource that `depends_on` the first and takes a second to create, and act only on the first resource's create success (`SLOW_PAIR` in `tests/integration/test_sync.py`).
- **asyncio driver** (`xcl.aio.Config._drive`): each state task and function task runs as its own asyncio task, beside the one consumer task that calls `on_event` in order. A test can gate the store's `save` on an `asyncio.Event` the handler sets (`GatedStore` in `tests/integration/test_aio.py`). Gate only the save that follows the event, such as one holding the created record: an earlier save gated the same way waits until its timeout.

Plugin log lines (`phase == "log"`) reach the engine on their own stream, so how many arrive before an operation ends, and where they fall among the other events, varies between runs. Compare event sequences without them.
