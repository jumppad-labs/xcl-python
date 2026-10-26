"""Every public name of the package has a docstring.

The check walks the package's public objects, not the repository's files:
``xcl.__all__``, every public attribute of ``xcl.aio``, ``xcl.mask`` and
``xcl.highlight``, and the public methods of every public class.
"""

from __future__ import annotations

import inspect

import xcl
import xcl.aio
import xcl.highlight
import xcl.mask


def _missing_docstrings():
    missing = []

    def check(name, obj):
        if not (inspect.getdoc(obj) or "").strip():
            missing.append(name)

    for name in xcl.__all__:
        obj = getattr(xcl, name)
        if name == "__version__" or not (inspect.isclass(obj) or inspect.isfunction(obj) or inspect.ismodule(obj)):
            continue
        check(f"xcl.{name}", obj)
        if inspect.isclass(obj):
            for attr, member in vars(obj).items():
                if attr.startswith("_") and attr not in ("__init__",):
                    continue
                if attr == "__init__":
                    continue
                if inspect.isfunction(member) or isinstance(member, (property, classmethod, staticmethod)):
                    target = member.fget if isinstance(member, property) else member
                    target = target.__func__ if isinstance(target, (classmethod, staticmethod)) else target
                    check(f"xcl.{name}.{attr}", target)

    for module in (xcl.aio, xcl.mask, xcl.highlight):
        check(module.__name__, module)
        for attr in getattr(module, "__all__", []):
            obj = getattr(module, attr)
            # a constant, such as xcl.highlight.DEFAULT_THEME, cannot carry
            # a docstring of its own, as in the xcl.__all__ walk above
            if not (inspect.isclass(obj) or inspect.isfunction(obj) or inspect.ismodule(obj)):
                continue
            check(f"{module.__name__}.{attr}", obj)
            if inspect.isclass(obj):
                for member_name, member in vars(obj).items():
                    if member_name.startswith("_"):
                        continue
                    if inspect.isfunction(member) or isinstance(member, property):
                        target = member.fget if isinstance(member, property) else member
                        check(f"{module.__name__}.{attr}.{member_name}", target)

    return missing


def test_every_public_name_has_docstring():
    assert _missing_docstrings() == []


def test_package_and_submodules_have_docstrings():
    assert (xcl.__doc__ or "").strip()
    assert (xcl.aio.__doc__ or "").strip()
    assert (xcl.mask.__doc__ or "").strip()
    assert (xcl.highlight.__doc__ or "").strip()
