# Parity with the Go API

Every operation and lookup of the Go API has an equivalent in the synchronous
API, `xcl.Config`, and the asyncio API, `xcl.aio.Config`. This list is
checked against the Go API of the xcl release the package bundles at each
release; the `tests/parity` suite checks that the two give the same results
on a shared set of fixtures.

## Operations

| Go (`*xcl.Config`) | `xcl.Config` | `xcl.aio.Config` |
|---|---|---|
| `Validate(paths...)` / `ValidateContext(ctx, paths...)` | `validate(*paths)` | `await validate(*paths)` |
| `Apply(paths...)` / `ApplyContext(ctx, paths...)` | `apply(*paths)` | `await apply(*paths)` |
| `Diff(paths, options...)` / `DiffContext(ctx, paths, options...)` | `diff(*paths, reveal_sensitive=False)` | `await diff(*paths, reveal_sensitive=False)` |
| `Destroy()` / `DestroyContext(ctx)` | `destroy()` | `await destroy()` |
| `Load()` / `LoadContext(ctx)` | `load()` | `await load()` |

The context forms are how the asyncio API cancels: cancelling the task that
awaits an operation cancels the engine's context. The synchronous API
cancels on `KeyboardInterrupt`.

## Lookups

| Go | `xcl.Config` | `xcl.aio.Config` |
|---|---|---|
| `Entities()` | `entities()` | `await entities()` |
| `EntityCount()` | `entity_count()` | `await entity_count()` |
| `FindResource(address)` / `Find[T](c, address)` | `find(cls, address)` | `await find(cls, address)` |
| `FindByType[T](c, path...)` / `FindEntitiesByType(path...)` | `find_by_type(cls, *path)` | `await find_by_type(cls, *path)` |
| `FindOne[T](c, path...)` / `FindOneEntity(path...)` | `find_one(cls, *path)` | `await find_one(cls, *path)` |
| `All[T](c)` | `all(cls)` | `await all(cls)` |
| `Outputs()` | `outputs()` | `await outputs()` |
| `EncodeEntity(value, options...)` | `encode_entity(entity, include_computed=False, include_empty=False, reveal_sensitive=False, show_references=False)` | `await encode_entity(entity, ...)` |
| `EncodeSavedEntity(data, options...)` | `encode_saved_entity(data, include_computed=False, include_empty=False, reveal_sensitive=False, show_references=False)` | `await encode_saved_entity(data, ...)` |
| `EntityTokens(value, options...)` | `entity_tokens(entity, include_computed=False, ...)` | `await entity_tokens(entity, ...)` |
| `PrintEntity(w, value, options...)` | `print_entity(entity, file=None, include_computed=False, ..., formatter=PLAIN, theme=DEFAULT_THEME)` | `await print_entity(entity, file=None, ...)` |
| `EncodeSavedEntity` has no print or tokens form in Go | `saved_entity_tokens(data, ...)` and `print_saved_entity(data, file=None, ...)` | `await saved_entity_tokens(data, ...)` and `await print_saved_entity(data, file=None, ...)` |

Each configuration hydrates into the classes registered on its own
registries. Passing `None` as the class returns the class registered on the
configuration for the entity's type, or `xcl.Entity` for a type it registered
no class for, which is how a Go plugin's entities are read. A class the
configuration did not register raises `xcl.NotRegisteredError`, as `All[T]`
with an unregistered `T` returns `ErrNotRegistered` in Go.

The encoding options are keywords, all off by default: `IncludeComputed()` is
`include_computed=True`, `IncludeEmpty()` is `include_empty=True`,
`RevealSensitive()` is `reveal_sensitive=True` and `ShowReferences()` is
`show_references=True`. The engine renders the text
through the same encoder Go uses, so it is identical to Go's for the same
entity and choices, which the parity suite checks for every fixture. A
looked-up entity holds only the sensitive marker, so with `reveal_sensitive`
the engine shows its own configured value. An entity taken from an event and
encoded after its operation is filled the same way, so it shows the engine's
current value, where Go's event data always shows the marker.

## Printing

The engine lays out reports, configuration text and change summaries as
labelled text, the same tokens Go's formatters receive, and Python's built-in
formats write the same bytes as Go's: the parity suite compares printed
reports, entities and change summaries for every fixture, and the formats are
held to the reference outputs in xcl's `highlight/testdata/reference`.

| Go | Python |
|---|---|
| `xcl.PrintError(w, err, options...)` | `xcl.print_error(err, file=None, formatter=PLAIN, theme=DEFAULT_THEME, width=80)`; `xcl.format_error(err, ...)` for a string |
| `xcl.PrintDiff(w, d, options...)` | `xcl.print_diff(diff, file=None, formatter=PLAIN, theme=DEFAULT_THEME)` |
| `xcl.WithFormatter(f)`, `xcl.WithTheme(t)`, `xcl.WithWidth(n)` | the `formatter=`, `theme=` and `width=` keywords |
| `xcl.ErrorTokens(err)` | `err.tokens` |
| `(*diff.Diff).Tokens()` | `diff.tokens`, on a diff `Config.diff` returned |
| `%+v` on a configuration error | the error's exception note, shown on tracebacks and logged exceptions |
| `highlight.Plain`, `Terminal`, `HTML`, `HTMLInline`, `SVG` | `xcl.highlight.PLAIN`, `TERMINAL`, `HTML`, `HTML_INLINE`, `SVG` |
| `highlight.Formatter`, `highlight.FormatterFunc` | the `xcl.highlight.Formatter` protocol: any object with `format(out, theme, tokens)` |
| `highlight.Kind`, `highlight.Token` | `xcl.highlight.Kind` (an `IntEnum`, the same numbers), `xcl.highlight.Token` |
| `Kind.Parent()`, `Kind.Class()` | `Kind.parent`, `Kind.css_class`; `parent_of(n)`, `css_class_of(n)` for any number |
| `highlight.Theme`, `highlight.DefaultTheme` | `xcl.highlight.Theme` (a mapping of kind to style string), `xcl.highlight.DEFAULT_THEME` |
| `DefaultTheme.With(overrides)` | `DEFAULT_THEME \| {...}` |
| `Theme.Style(kind)`, `highlight.ParseStyle(s)` | `xcl.highlight.style_for(theme, kind)`, `xcl.highlight.parse_style(s)` |
| `Theme.Validate()` and `errors.InvalidStyleError` | `xcl.highlight.validate(theme)`, raising one `xcl.InvalidStyleError` naming every unknown word |
| `highlight.WriteCSS(w, theme)` | `xcl.highlight.css(theme)` |
| `highlight.For(w)` | `xcl.highlight.for_stream(stream)` |
| `highlight.LoadVSCodeTheme(r)` and `errors.InvalidThemeError` | `xcl.highlight.load_vscode_theme(path_or_bytes)`, converted by the engine, and `xcl.InvalidThemeError` |

## Logging

| Go | Python |
|---|---|
| `events.SlogHandler(logger)` | `xcl.logging_handler(logger=None)`: the same levels, messages and attribute names, on standard `logging` records, plus `xcl_event` |
| a slog handler printing an error's report | `xcl.highlight.LogFormatter(..., formatter=, theme=, width=)` |

Go's pretty logger is an example (`example/prettylog`) that only its
examples import; Python's is part of the package. The parity suite compares
what the two write for every fixture whose apply succeeds, apart from
timestamps and durations.

| Go (`example/prettylog`) | Python (`xcl.prettylog`) |
|---|---|
| `prettylog.Handler(w, level)` | `xcl.prettylog.handler(file=None, level=logging.INFO, *, logger=None, formatter=None)`: the same lines, and also a configuration mistake's report beneath its error line at every level, and one line saying how to turn resource data on when it is off |
| `prettylog.LevelFromEnv()` | `xcl.prettylog.level_from_env()`, a `logging` level |
| `prettylog.LevelEnv` | `xcl.prettylog.LEVEL_ENV` (`"XCL_LOG_LEVEL"`) |
| `slog.Level` | a standard `logging` level `int` |

## Configuration options

| Go (`xcl.NewConfig` option) | `xcl.Config(...)` and `xcl.aio.Config(...)` |
|---|---|
| `WithRegistry(r)` | `registries=[...]` (`xcl.LocalRegistry`, `xcl.GitHubRegistry`) |
| `WithStatePath(dir)` | `state_path=dir` |
| `WithStateStore(store)` | `state_store=obj` |
| `WithStateMask(m)` | `state_mask=xcl.mask.aes256gcm(key)` |
| `WithVariables(vars)` | `variables={...}` |
| `WithEventHandler(h)` | `on_event=callable` |
| `WithEventData(level)`, `level` an `xcl.EventDataLevel` (`xcl.EventDataNone`, `xcl.EventDataRaw`, `xcl.EventDataProcessed`) | `event_data=xcl.EventDataLevel.NONE`, `.RAW` or `.PROCESSED` (an `xcl.EventDataLevel`; a string is refused) |
| `WithEventBufferSize(n)` | `event_buffer_size=n` |
| `WithEventMask(m)` | `event_mask=xcl.mask.hmac_sha256(key)` |
| `WithNoEventMask()` | `no_event_mask=True` |

## Registries

| Go | Python |
|---|---|
| `registry.NewLocal(registry.PluginPattern(p))` | `xcl.LocalRegistry(plugin_pattern=p)` |
| `registry.Register[T](local, type, subtype)`, `local.RegisterType(prototype, type, subtype)` | `local.register_type(cls, type, subtype)` |
| A label field, `xcl:"name,label"` | `xcl.field(label=True)` |
| A `Meta` field, `types.Meta` | a `meta` field, an `xcl.Meta \| None` |
| A plain struct with neither, a singleton | a dataclass with neither, a singleton |
| `local.RegisterFunction(name, fn)` | `local.register_function(fn, name=None)` |
| `local.RegisterExternalPlugin(path)` | `local.register_external_plugin(path)` |
| `local.RegisterPluginDirectory(dir)` | `local.register_plugin_directory(dir)` |
| `registry.NewGitHub(options...)` | `xcl.GitHubRegistry(cache_dir=, trusted_keys=, token=, api_url=)` |
| `github.RegisterPlugin(repo, version)` | `github.register_plugin(repo, version)` |
| `registry.Register[T](github, type, subtype)`, `github.RegisterType(prototype, type, subtype)` | `github.register_type(cls, type, subtype)` |

## Not applicable

| Go | Why there is no Python form |
|---|---|
| `Decode(entity, &target)` | A lookup already returns an instance of the registered class; there is no separate struct to fill. |
| `As[T](entity)` | A lookup takes the class to return; `find(cls, address)` is the conversion. |
| `GetResources()` / `ResourceCount()` | Deprecated in Go in favour of `Entities()` / `EntityCount()`. |
| `Event.Entity()` through a Go type | `xcl.Event.entity()` hydrates the class registered on the configuration that emitted the event, or `xcl.Entity`. |
| `highlight.Tokenize(text)` | Python never lexes configuration: labelled text comes from the engine, through `entity_tokens`, `err.tokens` and `diff.tokens`. |
| `Kind.Scope()` | Scopes are used only to convert a VS Code theme, which the engine does for `load_vscode_theme`. |
