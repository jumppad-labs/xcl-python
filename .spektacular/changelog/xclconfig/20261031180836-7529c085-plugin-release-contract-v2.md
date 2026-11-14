---
created_date: "2026-11-02"
document_status: draft
project: xclconfig
spec: 20261031180836-7529c085-plugin-release-contract-v2
plan: 20261031180836-7529c085-plugin-release-contract-v2
---

# Engine v0.13.1: plugin releases in the v2 layout, and local plugins as commands

The package moves to xcl engine v0.13.1. Plugins installed from GitHub use the new release layout, a signed index plus a zip per platform, so pin plugin releases published in it, such as `jumppad-labs/xcl-plugin-docker` v0.4.1. `LocalRegistry.register_external_plugin` now also takes a list holding a program and its arguments, such as `["python3", "plugin.py"]`, so a plugin can run from source.

> Derived from project xcl (jumppad-labs/xcl), spec/plan 20261031180836-7529c085-plugin-release-contract-v2. See the project-level record for the full feature.

## What changed

- **Engine:** `xcl-ref.txt` pins v0.13.1, and the protocol stubs are regenerated. The local registry's `external_plugins` field became `external_plugin_commands`.
- **`register_external_plugin(command)`:**
  - Takes a plugin's path, or a list or tuple holding a program and its arguments. Any item may be a `pathlib.Path`.
  - An empty list raises `xcl.SchemaError`.
  - The asyncio API shares the registry.
- **Tests:**
  - The integration tests install the test plugin v0.3.1.
  - The tamper tests tamper with the index (refused by the signature check, before the zip is fetched) and with the zip (refused by its checksum in the index).
  - The unsigned-install test checks the index and zip are cached without a signature.
  - New unit tests cover every accepted form. New integration tests start a plugin through a Python launcher command in the sync and asyncio APIs.
- **Docs:**
  - The README pins Docker v0.4.1, says the signature covers the release's index, and gains a "Local plugins" section.
  - `PARITY.md` maps Go's command form.

## Why

The engine retired the field this package used to register external plugins, and installs only plugin releases in the new layout. Both changes have to land with the engine bump. Registering a plugin as a command is the first step towards plugins written in Python and other languages.

## Upgrading

- Pin plugin releases published in the new layout. Old-layout releases, with tarballs and a checksums file, no longer install.
- Code passing `register_external_plugin(path=...)` by keyword uses `command=...`.
