# xcl for Python

XCL, the declarative configuration language, for Python. The package drives
the same engine Go programs use, bundled in the wheel as a small program that
the package runs as a subprocess, the same way on every platform, Alpine
included, with the same API and the same results everywhere. A Python program
validates, diffs, applies, loads and destroys configuration exactly as a Go
program does, uses the same Go plugins, and adds its own Python functions to
configuration.

- Engine and Go library: [github.com/jumppad-labs/xcl](https://github.com/jumppad-labs/xcl)
- Language and documentation: [xcl.dev](https://xcl.dev)
- Python API reference: [xcl.dev/api/python](https://xcl.dev/api/python/)
- Getting started guide: [Using XCL with Python](https://xcl.dev/using-xcl-with-python/)

## Install

```
pip install xcl-lang
```

The distribution is `xcl-lang` on PyPI and is imported as `xcl`. No Go
toolchain and no C compiler are needed: each wheel bundles the engine
program, `xcl-core`, for its platform, and contains no compiled extension,
so one wheel per platform serves every CPython 3.11 and later. Wheels are
published for

- Linux x86-64 and arm64 on glibc 2.28 or later (`manylinux_2_28`);
- Linux x86-64 and arm64 on musl (`musllinux_1_2`), Alpine included;
- macOS 11 or later on Apple silicon (arm64);
- Windows x86-64 and arm64.

The engine runs as a subprocess on every platform. `import xcl` starts
nothing: the engine starts the first time a configuration is used, is shared
by every configuration in the process, and stops on its own when the last
configuration is closed or the interpreter exits. It never outlives its
host, even one that is killed, and its diagnostics go to your standard
error. The package has its own version, and bundles the xcl engine release
pinned in `xcl-ref.txt` when it was built; `xcl.engine_version()` reports
it. The package refuses to run against any other engine.

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


@dataclass
class Settings:
    image: str
    replicas: int = 1
    meta: xcl.Meta | None = None


github = xcl.GitHubRegistry(trusted_keys=[RELEASE_KEY])
github.register_plugin("jumppad-labs/xcl-plugin-docker", "v0.3.0")

local = xcl.LocalRegistry()
local.register_type(Settings, "settings")

with xcl.Config(registries=[local, github], state_path=".xcl") as cfg:
    cfg.apply("./infra")

    settings = cfg.find(Settings, "settings.web")
    print(settings.image, settings.replicas)

    network = cfg.find(None, "docker.network.main")
    print(network.meta.id, network.subnet, network.docker_id)

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
with `.meta`, for a plugin's type: `network.subnet` and
`network["subnet"]` both read an attribute.

### Entity types

A plain dataclass describes a block type through its annotations; it needs
no base class and no decorator. Its type name is given when it is registered,
as in Go: `local.register_type(App, "app")` is written `app "web" {}`, and
`local.register_type(Database, "database", "postgres")` is written
`database "postgres" "main" {}`.

```python
@dataclass
class Volume:
    source: str
    name: str = xcl.field(label=True, default="")   # the block's name, volume "data" {}


@dataclass
class Listener:
    port: int
    name: str = xcl.field(label=True, default="")


@dataclass
class Health:
    path: str = "/"
    interval: int = 10


@dataclass
class App:
    image: str                                       # required
    replicas: int = 2                                # optional, with a default
    region: str | None = None                        # optional
    password: xcl.Sensitive[str] | None = None       # sensitive: masked in events and state
    endpoint: xcl.Computed[str] = None               # set by the provider, never in configuration
    health: Health | None = None                     # a nested block
    volume: list[Volume] = xcl.field(default_factory=list)        # a list of blocks, in order
    listener: dict[str, Listener] = xcl.field(default_factory=dict)  # named blocks, keyed by name
    meta: xcl.Meta | None = None                     # the block's metadata, meta.id its address


local.register_type(App, "app")
```

A field called `meta`, an `xcl.Meta | None`, is not part of the class's
schema: it receives the block's metadata. `meta.id` is the block's address,
and `meta.disabled` and `meta.depends_on` are what configuration set on it.
Configuration may set `disabled` and `depends_on` on any block, so `meta`,
`disabled` and `depends_on` are held by every block, and a class declaring
another field by one of those names, or a wrongly typed `meta`, raises
`xcl.SchemaError` when it is registered. As for any dataclass, fields
with defaults come after the required ones, or the class is declared
`@dataclass(kw_only=True)`.

An entity type reads its label one of two ways: through its `meta` field,
which holds the label as `meta.name` beside the rest of the entity's
metadata, or with a field marked `xcl.field(label=True)`, filled from the
block's label; a type with a subtype takes two such fields, the subtype and
the label. A type with neither cannot read a label, so it is a singleton:
its block is written without labels, a module holds one of it, and it is
found by its type alone.

```python
@dataclass
class Runner:
    server: str                                      # runner { server = "..." }


@dataclass
class Agent:
    model: str
    handle: str = xcl.field(label=True, default="")  # agent "claude" {} gives handle "claude"


local.register_type(Runner, "runner")
local.register_type(Agent, "agent")
```

`cfg.find(Runner, "runner")` returns the runner, and configuration reads it
as `runner.server`. A singleton takes no subtype.

Configuration is checked against the class as it is against a Go type: a
missing required field, a computed field set in configuration or an unknown
attribute is reported with its file and line. A looked-up `Sensitive` value
prints as `(sensitive)` and `reveal()` returns `None`; real values never leave
the engine through a lookup. To show a looked-up entity with its real values,
encode it with `cfg.encode_entity(entity, reveal_sensitive=True)`, see
[Encoding entities as configuration](#encoding-entities-as-configuration).

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
  image  = "nginx:1.27-alpine"
  region = slugify("US East")
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
    event_data=xcl.EventDataLevel.PROCESSED,    # carry the entity on events, masked
)
```

A custom state store is any object with `load() -> list[bytes]`,
`save(records: list[bytes])`, `exists() -> bool` and `clear()`; it receives
each entity's JSON record. The engine's events arrive at `on_event` as
`xcl.Event`, with the same data levels and masking a Go program has. The
level is an `xcl.EventDataLevel`: `NONE` (the default), `RAW` or `PROCESSED`;
`event.entity()` hydrates the entity an event carries into the class
registered on the configuration that emitted it, or an `xcl.Entity`.

Lookups: `entities()`, `entity_count()`, `find(cls, address)`,
`find_by_type(cls, *path)`, `find_one(cls, *path)`, `all(cls)`,
`outputs()`, `encode_entity(entity)` and `encode_saved_entity(record)`. Each
configuration has its own classes, those registered on its registries. Pass
`None` as the class to get the class registered on this configuration for the
entity's type, or an `xcl.Entity` for a type it did not register; a class this
configuration did not register raises `xcl.NotRegisteredError`.

### Encoding entities as configuration

`cfg.encode_entity(entity)` turns an entity into xcl configuration text, the
same text Go's `xcl.EncodeEntity` writes for it:

```python
app = cfg.find(App, "app.web")
print(cfg.encode_entity(app))
print(cfg.encode_entity(app, reveal_sensitive=True))
```

For an `app "web"` block that sets `image = "nginx:1.27-alpine"` and
`password = "s3cret"`, the first call prints:

```hcl
app "web" {
  image    = "nginx:1.27-alpine"
  replicas = 2
  password = "(sensitive)"
}
```

The entity can be one returned by any lookup or carried by an event, an
instance of a registered class built by hand, or the `xcl.Entity` a lookup
returns for a plugin's type. Changes made to a looked-up entity show in the
text. The engine renders the text, so Python and Go give identical text for
the same entity. Four keyword choices, all off by default, match Go's encode
options:

- `include_computed=True` also writes the fields a provider filled in.
- `include_empty=True` also writes attributes that are unset or at their
  zero value: `""`, `[]`, `{}`, or the zero value of a nullable attribute.
- `reveal_sensitive=True` writes each sensitive value for real rather than as
  `(sensitive)`. A looked-up entity holds only the marker, so the engine shows
  its own configured value; a value the entity holds for real, such as an
  edit or one set by hand, is shown as it is. An entity taken from an event
  and encoded after its operation shows the engine's current value, where
  Go's event data always shows the marker.
- `show_references=True` writes each field that referred to another entity as
  the configuration wrote it, rather than its value. A hand-built entity has
  no references, so its values are written as they are.

`cfg.encode_saved_entity(record)` renders a saved record, as a state
store holds it and events carry it, and takes the same keywords.

To print the text rather than get it, in plain text, terminal colour or any
other format, use `cfg.print_entity(entity)` and
`cfg.print_saved_entity(record)`, which take the same keywords; see
[Printing and highlighting](#printing-and-highlighting).

`cfg.encode_saved_entity` works at any time, including from an `on_event`
handler while an operation runs, because it reads none of the configuration's
entities. With `event_data=xcl.EventDataLevel.PROCESSED`, each create success
event carries the resource's saved record, so a program can print each
created resource beneath its success event as the apply goes, with no
waiting for the apply to finish:

```python
def on_event(e):
    print(e.operation, e.phase, e.resource_id)
    if e.operation == "create" and e.phase == "success":
        print(cfg.encode_saved_entity(e.data, include_computed=True))

cfg = xcl.Config(
    registries=[local],
    on_event=on_event,
    event_data=xcl.EventDataLevel.PROCESSED,
)
cfg.apply("./config")
```

The text is the same as the same call gives after the apply. Variables and
outputs have create success events too; their records are not configuration
and raise `xcl.NotEncodableError`.

A looked-up entity is encoded from the data the engine returned for it, so
only the fields you change differ from Go's text: a default the dataclass
filled in, such as `Health.interval`, is not written unless you set it. A
copy of a looked-up entity, such as one made with `dataclasses.replace`, is
encoded from its values like a hand-built one, defaults included.

Encoding a value that is not an entity, a variable, output or module, or a
value with no configuration form raises `xcl.NotEncodableError`; an instance
of a class this configuration did not register raises
`xcl.NotRegisteredError`; and `cfg.encode_entity` while an operation runs,
including from an event handler, raises `xcl.OperationInProgressError`,
because it reads the engine's own copy of the entity, which the operation is
still changing. From a handler, render `event.data` with
`cfg.encode_saved_entity` instead. With `xcl.aio.Config` the calls are
`await cfg.encode_entity(entity)` and `await cfg.encode_saved_entity(record)`.

## Printing and highlighting

The engine lays out what a person reads, the report of a configuration
error, a resource's configuration text and a change summary, and sends it
as labelled text: a list of `xcl.highlight.Token`, each a piece of text
labelled with its `xcl.highlight.Kind`, such as an attribute name or a line
comment. Python prints it in the format you choose, the same bytes Go
prints. Every default is plain text: the package never colours output on its
own.

### Printing errors

`xcl.print_error(err)` prints any xcl error for a person, to `sys.stderr`
unless you pass a stream, and `xcl.format_error(err)` returns the same text,
following `traceback.print_exception` and `traceback.format_exception`. A
configuration problem prints as the report Go prints: severity and summary,
where it is, the numbered source lines with the fault marked, and the detail,
wrapped at 80 columns:

```python
try:
    cfg.apply("./config")
except xcl.Error as err:
    xcl.print_error(err, formatter=xcl.highlight.for_stream(sys.stderr))
    sys.exit(1)
```

```text
Error: Unsupported block type

  on config/main.xcl line 7, in app.api, field timeout[0]:
     5 | app "api" {
     6 |   image = "nginx"
     7 |   timeout {
     8 |     seconds = 5
     9 |   }

Blocks of type "timeout" are not expected here.
```

`width=40` wraps the detail at 40 columns, and `width=0` or `width=None`
never wraps it; source lines are never wrapped. Any other exception, and an
xcl error holding no configuration problem, prints as its message and a line
break.

You need no code to see the report on an error you do not handle. Every xcl
error holding a configuration problem carries its plain report as an
exception note, so an uncaught error's traceback, `logging.exception(...)`,
`exc_info=True`, rich tracebacks and loguru's `logger.exception` all show it
after the message. `str(err)` stays the engine's message, Go's `Error()`: one
line for one problem, one line per problem for a configuration error holding
several. `err.tokens` is the report as labelled text, empty for an error
without one.

### Printing resources and change summaries

```python
cfg.print_entity(db, include_computed=True)                 # to sys.stdout
cfg.print_saved_entity(event.data, formatter=xcl.highlight.TERMINAL)
xcl.print_diff(cfg.diff("./config"), formatter=xcl.highlight.for_stream(sys.stdout))
```

`print_entity` and `print_saved_entity` take the four encode keywords and
print the text `encode_entity` and `encode_saved_entity` return.
`print_saved_entity` works from an `on_event` handler while an operation
runs, as `encode_saved_entity` does. `cfg.entity_tokens(...)` and
`cfg.saved_entity_tokens(...)` return the labelled text instead.
`xcl.print_diff` prints the git-style change summary of a diff that
`cfg.diff` returned, whose labelled text is `diff.tokens`; a `Diff` built by
hand has none and raises `ValueError`. With `xcl.aio.Config`, the
configuration's methods are awaited.

### Output formats

Every print call takes `formatter=` and `theme=`:

- `xcl.highlight.PLAIN`, the default: the text as it is.
- `xcl.highlight.TERMINAL`: terminal colour codes, reset before every line
  break.
- `xcl.highlight.HTML`: `<pre class="xcl">` with a classed `<span>` per
  piece, for a page that styles it.
- `xcl.highlight.HTML_INLINE`: the same markup with inline `style=`
  attributes, for an email.
- `xcl.highlight.SVG`: a standalone image.

`xcl.highlight.for_stream(stream)` chooses for you: `TERMINAL` when the
stream is a terminal and `NO_COLOR` is unset or empty, `PLAIN` otherwise.

### Themes

A theme says how each kind looks, as the style strings Go uses: `bold`,
`italic`, `underline`, `dim`, a colour written `#rrggbb` or named (`red`,
`bright-black`, ...) and a background `bg:#rrggbb`. Give only the kinds you
want to change; a kind a theme does not style takes its category's style,
then `TEXT`'s, so a comment style covers line, hash and block comments:

```python
from xcl.highlight import DEFAULT_THEME, Kind, validate

theme = DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800", Kind.COMMENT: "italic #6a9955"}
validate(theme)                  # raises xcl.InvalidStyleError naming each unknown word
cfg.print_entity(db, formatter=xcl.highlight.TERMINAL, theme=theme)
```

`DEFAULT_THEME` cannot be changed in place; `|` gives a new theme. Printing
with a style word it does not understand skips the word rather than failing.

To use a VS Code colour theme, load it; only the kinds it styles come back,
so extend the default to keep the rest:

```python
theme = DEFAULT_THEME | xcl.highlight.load_vscode_theme("monokai.json")
```

The engine converts the theme with the same scopes the xcl VS Code extension
uses, so attribute names take the theme's property colour. A theme the
engine cannot use raises `xcl.InvalidThemeError`, whose `details["reason"]`
says what was wrong.

### On a website

`xcl.highlight.HTML` writes the same class names as Go, such as
`xcl-attribute` and `xcl-comment xcl-line-comment`, under a `<pre
class="xcl">`. `xcl.highlight.css(theme)` generates a stylesheet for them
from any theme, identical to Go's:

```python
Path("static/xcl.css").write_text(xcl.highlight.css(DEFAULT_THEME))
html = xcl.format_error(err, formatter=xcl.highlight.HTML)   # already escaped
```

### Writing a format

A format is any object with a `format(out, theme, tokens)` method, the
`xcl.highlight.Formatter` protocol, and every print call accepts one. It is
given the whole labelled text at once and writes to the stream it is given.
`xcl.highlight.style_for(theme, kind)` resolves a kind's style through its
category. A kind from a newer engine that this package does not know arrives
as its number and falls back to its category:

```python
class Markdown:
    def format(self, out, theme, tokens):
        out.write("```hcl\n" + "".join(token.text for token in tokens) + "```\n")


cfg.print_entity(db, formatter=Markdown())
```

## Logging

One line sends a configuration's events to Python's standard logging, at
the levels and with the messages Go's `events.SlogHandler` uses:

```python
cfg = xcl.Config(registries=[local], on_event=xcl.logging_handler(logging.getLogger("app")))
```

A plugin's log event is written at its own level with its own message;
every other event is written as `"<operation> <phase>"`, such as
`"create success"`, at info, at error for an error and at warning for a
blocked entity. The logger's level is checked first. Each record carries the
event's time and, as attributes, `source`, `operation`, `phase`, `resource`,
`type`, `file`, `duration`, `error` and the event's details, plus
`xcl_event`, the `xcl.Event` itself. JSON and key-value formatters, structlog
through its `ProcessorFormatter` and loguru through its standard logging
integration see them as fields, with no adapter.

To show a logged xcl error's report in colour on a console, give the handler
`xcl.highlight.LogFormatter`, which takes `logging.Formatter`'s own options
and writes the traceback followed by the report in the format you choose:

```python
handler = logging.StreamHandler()
handler.setFormatter(xcl.highlight.LogFormatter("%(levelname)s %(message)s", formatter=xcl.highlight.for_stream(sys.stderr)))
```

### Pretty logging

`xcl.prettylog` is a ready-made pretty logger, the Python form of the one
Go's examples share (`example/prettylog`), set up in one line. Each event is
a readable line, and each created resource's configuration, with the values
the provider filled in, appears beneath its creation line as it happens:

```python
cfg = xcl.Config(
    registries=[local],
    on_event=xcl.prettylog.handler(sys.stderr, xcl.prettylog.level_from_env()),
    event_data=xcl.EventDataLevel.PROCESSED,   # puts each created resource on its event
)
```

```text
3:04PM INFO apply start source=core operation=apply phase=start
3:04PM INFO create start source=core operation=create phase=start resource=resource.recording.one type=recording.one file=/work/main.xcl
3:04PM INFO create success source=core operation=create phase=success resource=resource.recording.one type=recording.one file=/work/main.xcl duration=509µs
  resource "recording" "one" {
    log    = "/work/log.jsonl"
    value  = "a"
    output = "one-a" # set by the provider
  }
3:04PM INFO apply success source=core operation=apply phase=success duration=5.246ms
```

Each line is the event's time, level and message, then its source,
operation, phase, resource and other details as `key=value`, in the layout
Go's example writes, so a Python run reads exactly as a Go run does. The
source, operation and resource are highlighted, and the configuration is
coloured by `xcl.highlight`'s default theme, when the stream is a terminal
and `NO_COLOR` is unset; anything else gets plain text, or pass
`formatter=` to choose.

- **Level.** `handler(file, level)` takes a standard `logging` level,
  `logging.INFO` when not given. `xcl.prettylog.level_from_env()` reads it
  from `XCL_LOG_LEVEL` (`xcl.prettylog.LEVEL_ENV`), the variable Go's
  example reads: `debug`, `info`, `warn` or `error` in any letter case, info
  when unset or anything else.
- **Created resources.** At info and below, beneath each `create success`
  line, the resource's configuration is rendered from the event's saved
  record. That needs `event_data=xcl.EventDataLevel.PROCESSED`; without it
  one line says how to turn it on, once. Variables, outputs and modules have
  no configuration form and show nothing, and a resource that cannot be
  shown gets one `WARN unable to show configuration` line, and the run
  carries on.
- **Configuration mistakes.** Beneath the line reporting a configuration
  mistake, at every level, comes its report: the summary, the file and line,
  the block and field, the numbered source lines with the fault marked, and
  the detail, each problem once.
- **Above info**, such as `warn`, only event lines and reports are written.
- **Your own logging.** `handler(logger=logging.getLogger("app"))` sends the
  same lines through a logger instead of a stream: each event is one record,
  at the event's level and time, whose message is the line and anything
  beneath it, plain unless `formatter=` says otherwise. A handler formatting
  `%(message)s` prints exactly what the stream would get, and the records
  carry the event's fields as `xcl.logging_handler`'s do.

The same handler works unchanged on the asyncio client, also in one line:

```python
cfg = xcl.aio.Config(registries=[local], on_event=xcl.prettylog.handler(sys.stderr), event_data=xcl.EventDataLevel.PROCESSED)
```

It never raises into the operation: a write that fails is ignored.

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
    local.register_type(App, "app")
    local.register_function(slugify)

    async with xcl.aio.Config(registries=[local], state_path=".xcl", on_event=on_event) as cfg:
        await cfg.apply("./infra")
        web = await cfg.find(App, "app.web")
        print(web.image, web.meta.id)


async def on_event(event):
    print(event.operation, event.phase, event.resource_id)


asyncio.run(main())
```

The engine is polled from a thread, so a web service keeps answering
requests during a long apply. State-store calls and functions run as asyncio
tasks, concurrently. Events reach `on_event` one at a time, in the order the
engine sent them, as they do with `xcl.Config` and in Go: a plain handler runs
in the default executor and an `async def` one on the loop, and the next event
waits until the handler has finished with the last, so
`on_event=xcl.prettylog.handler(sys.stderr)` and `xcl.logging_handler()` write
their lines in order. (Before this release, asyncio handlers ran concurrently
and could see events out of order.) Cancelling the task that awaits an operation cancels the engine's
work: no further provider call starts, the progress made is saved, and
`asyncio.CancelledError` is raised once the engine has stopped.

## Migrating from highlight=

`highlight=` has been removed from `encode_entity` and `encode_saved_entity`,
on `xcl.Config` and `xcl.aio.Config`; passing it raises `TypeError` as an
unexpected keyword argument. To print coloured configuration text, use
`cfg.print_entity(entity, formatter=xcl.highlight.TERMINAL)` (or
`cfg.print_saved_entity(record, ...)`), or `formatter=xcl.highlight.for_stream(sys.stdout)`
to colour only on a terminal. To get the text with its labels for your own
format, use `cfg.entity_tokens(entity)`. `encode_entity` and
`encode_saved_entity` return plain text, as they did without `highlight=`.

## Migrating from string event data levels

`event_data` takes only an `xcl.EventDataLevel` member, the Python form of
Go's `xcl.EventDataLevel`. A string is refused with a `TypeError`, even one
spelled exactly like a level, and so is any other value that is not a member,
including `None`. Code that passed a level's word passes the member of the same
name, upper-cased, instead: `xcl.EventDataLevel.NONE`, `xcl.EventDataLevel.RAW`
or `xcl.EventDataLevel.PROCESSED`. Code that left the option out is unaffected.
Type checkers such as mypy and pyright flag a string passed as the level
before the program runs.

## Migrating from xcl.Resource and @xcl.entity

`xcl.Resource` and `@xcl.entity(type, subtype)` have been removed: a block
type is now a plain dataclass, named when it is registered, as
`registry.Register[T](local, "database", "postgres")` names a Go type. A class
written as

```python
@xcl.entity("database", "postgres")
@dataclass
class Database(xcl.Resource):
    name: str
    port: int = 5432


local.register_type(Database)
```

becomes

```python
@dataclass
class Database:
    name: str
    port: int = 5432
    meta: xcl.Meta | None = None


local.register_type(Database, "database", "postgres")
```

Two edits are needed: drop the base class and the decorator, and pass the
type, and the subtype if there is one, to `register_type` on the
`xcl.LocalRegistry` or `xcl.GitHubRegistry` the class was registered on.

- Keep a `meta: xcl.Meta | None = None` field, or a label field, on every
  class whose blocks are written with a label: a class with neither is a
  singleton, written without labels. Code that read `obj.address` reads
  `obj.meta.id`.
- Code that read `obj.disabled` or `obj.depends_on` reads `obj.meta.disabled`
  or `obj.meta.depends_on`; a class declares no field by either name.
- `xcl.Resource` declared its `meta` field keyword-only, so it never clashed
  with a class's required fields. A class that declares it itself puts it
  after its required fields, as `meta` follows `name` above, or is declared
  `@dataclass(kw_only=True)`.

Code still using either name raises `xcl.RemovedNameError`, an `xcl.Error`
and an `ImportError`, whose message shows the new form.

## Errors

Every failure is an exception under `xcl.Error`, one class per kind of
error, carrying `message`, `details` and `causes`: `xcl.NotFoundError`,
`xcl.NotUniqueError`, `xcl.ConfigError` (whose `problems` list each problem
with its file, line and column, a `message` saying what is wrong and why, and,
from an engine that reports them, its `detail` on its own and the `entity` and
`field` it is in), `xcl.PluginVerificationError`,
`xcl.FunctionNameClashError`, `xcl.CancelledError` and so on. A plugin
release whose signature does not verify against the trusted keys is refused.
An error holding configuration problems also carries their report, shown on
tracebacks and logged exceptions and printed by `xcl.print_error`; see
[Printing errors](#printing-errors). `xcl.InvalidStyleError` and
`xcl.InvalidThemeError` report a theme that cannot be used.

Two errors concern the engine itself. `xcl.EngineNotFoundError` is raised on
first use when the installed package does not hold its engine, and names
where the engine program and the shared library were expected.
`xcl.EngineExitedError` is raised by every call waiting on the engine if it
exits unexpectedly, carrying its exit status, or the signal that ended it, in
`details` and `returncode`. Your program carries on: the next configuration
starts a new engine, and a configuration created before the exit raises
`xcl.EngineExitedError` again.

## Forking

A forked child creates its own configuration. `import xcl` starts nothing,
so forking before using the package is unaffected, and a child forked after
the parent used it simply creates a new `xcl.Config`, which starts the
child's own engine. Using a configuration created before the fork raises
`xcl.ForkedProcessError` in the child, since its engine belongs to the
parent. With that one rule, gunicorn's `preload_app`, celery's prefork pool
and `multiprocessing` with the `fork` start method all work.

## Development

The package is built against a checkout of xcl, `XCL_SRC` (by default
`../xcl`): `make protos` generates the message classes from its `proto/` with
protoc, `make engine` builds the engine program into `xcl/_bin` with Go and no
C compiler, `make plugins` builds the fixture plugins the integration tests
use, and `make test` runs the suite.

The tests find the xcl sources the same way: `XCL_SRC` when it is set, else a
sibling `../xcl` checkout. To run the suite against xcl checked out anywhere
else, point `XCL_SRC` at it, for example
`XCL_SRC=$HOME/src/xcl make plugins test`. With neither, the tests that need
the sources (the schema and parity tests, and building the fixture plugins)
skip with a message telling you to set `XCL_SRC`.

The end-to-end and GitHub registry tests need network access but no Docker.
They install the signed release of a plugin made only for testing,
[jumppad-labs/xcl-plugin-test](https://github.com/jumppad-labs/xcl-plugin-test),
pinned in `tests/plugins.toml`, from GitHub once per run, verified against the
jumppad-labs release key in `tests/keys`; set `GITHUB_TOKEN` if you run them
often, to stay inside GitHub's API rate limit. The Docker plugin in Getting
started remains the example to follow for your own configuration.

CI runs the suite with `XCL_TEST_STRICT=1`, which turns a skip for something
the run should have into a failure: the xcl sources, the fixture plugins, the
plugin release, and the engine for each route `XCL_TEST_ENGINES` lists
(`subprocess`, or `subprocess,inprocess`). Skips for a route the run did not
select, and for a platform without a feature such as `fork`, stay skips.

The engine can also be built as a shared library and loaded into the Python
process instead, which keeps the in-process route tested: `make libxcl`
builds it into `xcl/_lib` with Go and a C compiler, `pip install -e
'.[test,inprocess]'` adds cffi to load it (the standard library's ctypes is
used without it), and `XCL_TRANSPORT=inprocess` selects it. Without the
variable the engine program runs even when the library is present, and a
missing engine is reported, never replaced by the other form. With the
in-process route the forking rule is stricter, since the engine is a Go
runtime in the process: use the `spawn` start method, or create the
configuration after the fork, in gunicorn's `post_fork` hook or celery's
`worker_process_init` signal.
### Releases and the engine pin

Releases are automatic, and follow
[xcl's release process](https://github.com/jumppad-labs/xcl#releases). Every
pull request carries exactly one of the labels `patch`, `minor`, `major` or
`no-release`, and merging it tags and publishes the next version of this
package to PyPI, with a GitHub release listing the merged pull requests and
naming the bundled engine. The package's version line is its own: a fix here
releases Python alone, with no xcl release.

`xcl-ref.txt` pins the xcl release the package is tested against, built
against and bundles. When xcl releases, a pull request titled "Use xcl engine
<tag>" moves the pin to the new tag, labelled with the same size as the engine
release. It merges by itself once its checks pass, which releases the package
with the new engine. If its checks fail it stays open; fix the binding on its
branch and it merges once they pass.

A release stamps the pin into `xcl/_version.py` as `__engine_version__`. In a
checkout it holds the development value `v0.0.0-dev`, which `make engine` and
`make libxcl` also stamp on the engine they build, so a development engine
always passes the version check.

`PARITY.md` lists every Go operation and lookup with its Python equivalent. The distribution is published as `xcl-lang`, since the name `xcl` on PyPI belongs to another project; the import name is `xcl`.

## Licence

Apache-2.0, as xcl.
