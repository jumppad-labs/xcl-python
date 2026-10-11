# xcl for Python

XCL, the declarative configuration language, for Python. The package drives
the same engine Go programs use, built as a shared library and bundled in the
wheel, so a Python program validates, diffs, applies, loads and destroys
configuration exactly as a Go program does, uses the same Go plugins, and
adds its own Python functions to configuration.

- Engine and Go library: [github.com/jumppad-labs/xcl](https://github.com/jumppad-labs/xcl)
- Language and documentation: [xcl.dev](https://xcl.dev)

## Install

```
pip install xcl-lang
```

The distribution is `xcl-lang` on PyPI and is imported as `xcl`. No Go toolchain and no C compiler are needed: each wheel bundles the engine
for its platform. Wheels are published for

- Linux x86-64 and arm64, glibc 2.28 or later (`manylinux_2_28`) and musl (`musllinux_1_2`);
- macOS 11 or later, x86-64 and arm64;
- Windows x86-64 and arm64;

for CPython 3.10 and later. The package version is the xcl release it
bundles, and it refuses to run against any other engine.

## Getting started

A Python program describes its entity types as dataclasses, registers them
and any plugins on a registry, and creates a configuration. This program
uses the Docker example plugin, published as a signed GitHub release, to
create a network and a container:

```python
from dataclasses import dataclass

import xcl

# the jumppad-labs release key, from https://xcl.dev/keys/jumppad-labs-releases.asc
RELEASE_KEY = open("jumppad-labs-releases.asc").read()


@xcl.entity("settings")
@dataclass
class Settings(xcl.Resource):
    image: str
    replicas: int = 1


github = xcl.GitHubRegistry(trusted_keys=[RELEASE_KEY])
github.register_plugin("jumppad-labs/xcl-plugin-docker", "v0.2.0")

local = xcl.LocalRegistry()
local.register_type(Settings)

with xcl.Config(registries=[local, github], state_path=".xcl") as cfg:
    cfg.apply("./infra")

    settings = cfg.find(Settings, "settings.web")
    print(settings.image, settings.replicas)

    network = cfg.find(None, "docker.network.main")
    print(network.address, network.subnet, network.docker_id)

    cfg.destroy()
```

with the configuration in `infra/main.xcl`:

```hcl
settings "web" {
  image = "nginx:1.27-alpine"
}

docker "network" "main" {
  subnet = "10.73.0.0/24"
}

docker "container" "web" {
  image = settings.web.image

  network {
    name = docker.network.main.meta.name
  }
}
```

`apply` runs to completion before returning; other Python threads keep
running while it works. `find` returns an instance of the registered class
for a type the program registered, and an `xcl.Entity`, a read-only mapping
with `.meta` and `.address`, for a plugin's type: `network.subnet` and
`network["subnet"]` both read an attribute.

### Entity types

A dataclass decorated with `@xcl.entity(type)`, or `@xcl.entity(type, subtype)`
for a type written `database "postgres" "main" {}`, describes a block type
through its annotations:

```python
@dataclass
class Volume:
    source: str
    name: str = xcl.field(label=True, default="")   # the block's name, volume "data" {}


@dataclass
class Listener:
    port: int
    name: str = xcl.field(label=True, default="")


@xcl.entity("app")
@dataclass
class App(xcl.Resource):
    image: str                                       # required
    replicas: int = 2                                # optional, with a default
    region: str | None = None                        # optional
    password: xcl.Sensitive[str] | None = None       # sensitive: masked in events and state
    endpoint: xcl.Computed[str] = None               # set by the provider, never in configuration
    health: Health | None = None                     # a nested block
    volume: list[Volume] = xcl.field(default_factory=list)        # a list of blocks, in order
    listener: dict[str, Listener] = xcl.field(default_factory=dict)  # named blocks, keyed by name
```

Configuration is checked against the class as it is against a Go type: a
missing required field, a computed field set in configuration or an unknown
attribute is reported with its file and line. A looked-up `Sensitive` value
prints as `(sensitive)` and `reveal()` returns `None`; real values never leave
the engine through a lookup.

### Functions

A Python function registered on a local registry is callable from
configuration by name. Its annotations give its signature: `str`, `bool`,
`int` and `float` parameters and result, and lists and dicts of those.

```python
def slugify(title: str) -> str:
    return title.lower().replace(" ", "-")

local.register_function(slugify)
```

```hcl
app "web" {
  name = slugify("My App")
}
```

The result is filled in exactly like a built-in function's, and a result
computed from a sensitive argument is held as sensitive. A name a builtin or
another function already uses raises `xcl.FunctionNameClashError` when the
configuration is created.

### Variables, state and events

```python
cfg = xcl.Config(
    registries=[local],
    variables={"region": "us"},                # variable.region in configuration
    state_path="./.xcl",                        # or state_store=MyStore()
    state_mask=xcl.mask.aes256gcm(key),         # encrypt sensitive values in state
    on_event=lambda e: print(e.operation, e.phase, e.resource_id),
    event_data="processed",                     # carry the entity on events, masked
)
```

A custom state store is any object with `load() -> list[bytes]`,
`save(records: list[bytes])`, `exists() -> bool` and `clear()`; it receives
each entity's JSON record. The engine's events arrive at `on_event` as
`xcl.Event`, with the same data levels and masking a Go program has;
`event.entity()` hydrates the entity an event carries.

Lookups: `entities()`, `entity_count()`, `find(cls, address)`,
`find_by_type(cls, *path)`, `find_one(cls, *path)`, `all(cls)`,
`outputs()` and `encode_saved_entity(record)`. Pass `None` as the class to
get the registered class, or an `xcl.Entity` for an unregistered type.

## Asyncio

`xcl.aio.Config` offers every operation and lookup as an awaitable that
never blocks the event loop. Registered functions, the event handler and the
state store's methods may be `async def`:

```python
import asyncio
import xcl.aio


async def slugify(title: str) -> str:
    return title.lower().replace(" ", "-")


async def main():
    local = xcl.LocalRegistry()
    local.register_type(App)
    local.register_function(slugify)

    async with xcl.aio.Config(registries=[local], state_path=".xcl", on_event=on_event) as cfg:
        await cfg.apply("./infra")
        web = await cfg.find(App, "app.web")
        print(web.name)


async def on_event(event):
    print(event.operation, event.phase, event.resource_id)


asyncio.run(main())
```

The engine is polled from a thread, and each task it posts runs as an
asyncio task, so a web service keeps answering requests during a long
apply. Cancelling the task that awaits an operation cancels the engine's
work: no further provider call starts, the progress made is saved, and
`asyncio.CancelledError` is raised once the engine has stopped.

## Errors

Every failure is an exception under `xcl.Error`, one class per kind of
error, carrying `message`, `details` and `causes`: `xcl.NotFoundError`,
`xcl.NotUniqueError`, `xcl.ConfigError` (whose `problems` list each problem
with its file, line and column), `xcl.PluginVerificationError`,
`xcl.FunctionNameClashError`, `xcl.CancelledError` and so on. A plugin
release whose signature does not verify against the trusted keys is refused.

## Forking

The engine is a Go runtime, which cannot survive `fork()`. `import xcl`
loads nothing, so a process that imports the package and forks before using
it is unaffected. A process that used the package and then forks, as
gunicorn's prefork or `multiprocessing` with the `fork` start method do, gets
`xcl.ForkedProcessError` in the child. Two ways out: use the `spawn` start
method (`multiprocessing.set_start_method("spawn")`), or create the
configuration after the fork, in gunicorn's `post_fork` hook or celery's
`worker_process_init` signal, so each child loads its own engine.

## Development

The package is built against a checkout of xcl: `make protos` generates the
message classes from its `proto/` with protoc, `make libxcl` builds the
engine into `xcl/_lib` with Go and a C compiler, `make plugins` builds the
fixture plugins the integration tests use, and `make test` runs the suite.
`PARITY.md` lists every Go operation and lookup with its Python equivalent. The distribution is published as `xcl-lang`, since the name `xcl` on PyPI belongs to another project; the import name is `xcl`.

## Licence

Apache-2.0, as xcl.
