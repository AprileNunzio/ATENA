import inspect
import types
import typing

from features.agent import registry

JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object", list: "array"}


def kind(annotation) -> str:
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        options = [a for a in typing.get_args(annotation) if a is not type(None)]
        return kind(options[0]) if options else "string"
    origin = typing.get_origin(annotation) or annotation
    return JSON_TYPES.get(origin, "string")


def input_schema(name: str) -> dict:
    row = registry.TOOLS[name]
    properties, required = {}, []
    for key, param in inspect.signature(row["fn"]).parameters.items():
        spec = {"type": kind(param.annotation) if param.annotation is not inspect.Parameter.empty else "string"}
        if key in row["args"]:
            spec["description"] = str(row["args"][key])
        properties[key] = spec
        if param.default is inspect.Parameter.empty:
            required.append(key)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def definition(name: str) -> dict:
    return {"name": name, "description": registry.TOOLS[name]["description"], "inputSchema": input_schema(name)}


def openai(name: str) -> dict:
    d = definition(name)
    return {"type": "function", "function": {"name": name, "description": d["description"], "parameters": d["inputSchema"]}}


def anthropic(name: str) -> dict:
    d = definition(name)
    return {"name": name, "description": d["description"], "input_schema": d["inputSchema"]}
