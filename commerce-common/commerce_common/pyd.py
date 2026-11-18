# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""One import point for the pydantic names this repository uses.

With pydantic 2 these are pydantic's own. With pydantic 1.10 (a pure-Python install, for
platforms where ``pydantic-core`` has no wheel, such as Android) a small layer gives
pydantic 1 the v2 surface the code relies on: ``model_dump``, ``model_validate``,
``ConfigDict``/``model_config``, ``field_validator``, ``model_validator``, ``TypeAdapter``
and the v2 spelling of ``Field`` length limits on lists. Nothing here changes behavior on
pydantic 2.
"""

from __future__ import annotations

import pydantic

PYDANTIC_V1 = pydantic.VERSION.startswith("1.")

if not PYDANTIC_V1:
    from pydantic import (  # noqa: F401
        BaseModel,
        ConfigDict,
        Field,
        TypeAdapter,
        ValidationError,
        ValidationInfo,
        field_validator,
        model_validator,
    )
else:
    import inspect
    import re
    from types import SimpleNamespace
    from typing import Any

    from pydantic import BaseModel as _V1BaseModel
    from pydantic import (
        Extra,
        ValidationError,  # noqa: F401
        parse_obj_as,
        root_validator,
        validator,
    )
    from pydantic.fields import FieldInfo
    from pydantic.main import ModelMetaclass

    ValidationInfo = Any  # annotation only; validators receive a SimpleNamespace

    def ConfigDict(**kwargs: Any) -> dict[str, Any]:  # noqa: N802
        return dict(kwargs)

    _LIST_LIKE = re.compile(r"\b(list|set|frozenset|tuple|List|Set|Sequence)\b\s*\[")

    def Field(*args: Any, **kwargs: Any) -> Any:  # noqa: N802
        if "pattern" in kwargs:
            kwargs["regex"] = kwargs.pop("pattern")
        return pydantic.Field(*args, **kwargs)

    class _Meta(ModelMetaclass):
        @property
        def model_fields(cls) -> dict[str, Any]:
            return cls._model_fields()

        def __new__(mcs, name, bases, namespace, **kwargs):  # noqa: N804
            annotations = namespace.get("__annotations__", {})
            for key, value in list(namespace.items()):
                if isinstance(value, FieldInfo):
                    annotation = annotations.get(key)
                    if annotation is not None and _LIST_LIKE.search(str(annotation)):
                        if value.min_length is not None:
                            value.min_items, value.min_length = value.min_length, None
                        if value.max_length is not None:
                            value.max_items, value.max_length = value.max_length, None
            config = namespace.pop("model_config", None)
            if config:
                body: dict[str, Any] = {}
                if "extra" in config:
                    body["extra"] = Extra(config["extra"])
                if config.get("frozen"):
                    body["allow_mutation"] = False
                if "populate_by_name" in config:
                    body["allow_population_by_field_name"] = config["populate_by_name"]
                if "str_strip_whitespace" in config:
                    body["anystr_strip_whitespace"] = config["str_strip_whitespace"]
                if "arbitrary_types_allowed" in config:
                    body["arbitrary_types_allowed"] = config["arbitrary_types_allowed"]
                namespace["Config"] = type("Config", (), body)
            return super().__new__(mcs, name, bases, namespace, **kwargs)

    class _FieldView:
        def __init__(self, field: Any) -> None:
            self.annotation = field.outer_type_ if not field.allow_none else field.annotation
            self.default = field.default
            self.required = field.required

    class BaseModel(_V1BaseModel, metaclass=_Meta):
        @classmethod
        def _model_fields(cls) -> dict[str, Any]:
            return {name: _FieldView(f) for name, f in cls.__fields__.items()}

        def model_dump(
            self,
            *,
            mode: str = "python",
            include: Any = None,
            exclude: Any = None,
            by_alias: bool = False,
            exclude_none: bool = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
        ) -> dict[str, Any]:
            data = self.dict(
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_none=exclude_none,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
            )
            if mode == "json":
                import json

                return json.loads(json.dumps(data, default=self.__json_encoder__))
            return data

        def model_dump_json(self, **kwargs: Any) -> str:
            return self.json(**kwargs)

        @classmethod
        def model_validate(cls, obj: Any) -> Any:
            return cls.parse_obj(obj)

        @classmethod
        def model_validate_json(cls, data: Any) -> Any:
            return cls.parse_raw(data)

        @classmethod
        def model_json_schema(cls, **kwargs: Any) -> dict[str, Any]:
            return cls.schema(**kwargs)

        @classmethod
        def model_construct(cls, **values: Any) -> Any:
            return cls.construct(**values)

        def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Any:
            return self.copy(update=update, deep=deep)

    def _wants_info(function: Any) -> bool:
        target = (
            function.__func__ if isinstance(function, (classmethod, staticmethod)) else function
        )
        return len(inspect.signature(target).parameters) >= 3

    def field_validator(*fields: str, mode: str = "after", **_: Any):  # noqa: ANN201
        def decorate(function: Any) -> Any:
            raw = function.__func__ if isinstance(function, classmethod) else function
            wants_info = _wants_info(function)

            def wrapper(cls: Any, value: Any, values: dict[str, Any], field: Any) -> Any:
                if wants_info:
                    info = SimpleNamespace(data=values, field_name=field.name)
                    return raw(cls, value, info)
                return raw(cls, value)

            wrapper.__name__ = raw.__name__
            return validator(*fields, pre=(mode == "before"), allow_reuse=True)(wrapper)

        return decorate

    def model_validator(*, mode: str = "after", **_: Any):  # noqa: ANN201
        def decorate(function: Any) -> Any:
            if mode == "before":

                def before(cls: Any, values: dict[str, Any]) -> Any:
                    return (
                        function.__func__(cls, values)
                        if isinstance(function, classmethod)
                        else function(cls, values)
                    )

                before.__name__ = function.__name__
                return root_validator(pre=True, allow_reuse=True)(before)

            def after(cls: Any, values: dict[str, Any]) -> dict[str, Any]:
                instance = cls.construct(**values)
                result = function(instance)
                return dict(result.__dict__) if result is not None else values

            after.__name__ = function.__name__
            return root_validator(skip_on_failure=True, allow_reuse=True)(after)

        return decorate

    class TypeAdapter:
        def __init__(self, type_: Any) -> None:
            self._type = type_

        def validate_python(self, value: Any) -> Any:
            return parse_obj_as(self._type, value)

        def json_schema(self) -> dict[str, Any]:

            wrapper = type("_Wrapper", (BaseModel,), {"__annotations__": {"v": self._type}})
            props = wrapper.schema().get("properties", {}).get("v", {})
            props.pop("title", None)
            return props
