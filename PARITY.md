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
| `EncodeSavedEntity(data, options...)` | `encode_saved_entity(data, highlight=False)` | `await encode_saved_entity(data, highlight=False)` |

Passing `None` as the class returns the registered class for the entity's
type, or `xcl.Entity` for a type no class was registered for, which is how a
Go plugin's entities are read.

## Configuration options

| Go (`xcl.NewConfig` option) | `xcl.Config(...)` and `xcl.aio.Config(...)` |
|---|---|
| `WithRegistry(r)` | `registries=[...]` (`xcl.LocalRegistry`, `xcl.GitHubRegistry`) |
| `WithStatePath(dir)` | `state_path=dir` |
| `WithStateStore(store)` | `state_store=obj` |
| `WithStateMask(m)` | `state_mask=xcl.mask.aes256gcm(key)` |
| `WithVariables(vars)` | `variables={...}` |
| `WithEventHandler(h)` | `on_event=callable` |
| `WithEventData(level)` | `event_data="none" \| "raw" \| "processed"` |
| `WithEventBufferSize(n)` | `event_buffer_size=n` |
| `WithEventMask(m)` | `event_mask=xcl.mask.hmac_sha256(key)` |
| `WithNoEventMask()` | `no_event_mask=True` |

## Registries

| Go | Python |
|---|---|
| `registry.NewLocal(registry.PluginPattern(p))` | `xcl.LocalRegistry(plugin_pattern=p)` |
| `local.RegisterType(prototype, name...)` | `local.register_type(cls)` with `@xcl.entity(type, subtype)` |
| `local.RegisterFunction(name, fn)` | `local.register_function(fn, name=None)` |
| `local.RegisterExternalPlugin(path)` | `local.register_external_plugin(path)` |
| `local.RegisterPluginDirectory(dir)` | `local.register_plugin_directory(dir)` |
| `registry.NewGitHub(options...)` | `xcl.GitHubRegistry(cache_dir=, trusted_keys=, token=, api_url=)` |
| `github.RegisterPlugin(repo, version)` | `github.register_plugin(repo, version)` |
| `github.RegisterType(prototype, name...)` | `github.register_type(cls)` |

## Not applicable

| Go | Why there is no Python form |
|---|---|
| `Decode(entity, &target)` | A lookup already returns an instance of the registered class; there is no separate struct to fill. |
| `As[T](entity)` | A lookup takes the class to return; `find(cls, address)` is the conversion. |
| `EncodeEntity(value, options...)` | It renders a Go value; Python renders a saved record with `encode_saved_entity`. |
| `GetResources()` / `ResourceCount()` | Deprecated in Go in favour of `Entities()` / `EntityCount()`. |
| `Event.Entity()` through a Go type | `xcl.Event.entity()` hydrates the registered class or `xcl.Entity`. |
