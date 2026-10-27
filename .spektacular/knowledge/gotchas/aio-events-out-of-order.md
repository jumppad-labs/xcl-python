---
tags: [python, asyncio, events, ordering]
---

# The asyncio client delivers events in order (it did not before the pretty logger)

Since spec 20261023075328-741138ee-python-prettylog, `xcl.aio.Config._drive` puts every event on a per-operation `asyncio.Queue` drained by one consumer task (`_deliver_events`). `on_event` is called once per event, in the order the engine sent them, and the next call starts only after the previous one (a plain handler on the default executor, or an `async def` handler's coroutine) has finished, as Go and the synchronous client deliver them. The consumer is in the pending set, so the operation returns only after the last event is handled and cancellation cancels it; a handler's exception is still dropped.

State-store and function tasks are still separate concurrent asyncio tasks, so they can run beside the handler (see `aio-state-tasks-run-beside-handlers.md`).

Releases before this change ran each event as its own task, so plain handlers ran concurrently and could see events out of order; code written against an older release must not assume ordering.
