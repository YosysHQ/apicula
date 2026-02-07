#!/usr/bin/env python3
"""Generate C++ header files from Python dataclasses.

This script parses the chipdb.py dataclasses and generates C++ structs
with msgpack-c serialization support.

Usage:
    python -m apycula.generate_cpp > gowin_pack_cpp/src/chipdb_types.hpp
"""

from dataclasses import fields, is_dataclass
from typing import get_origin, get_args, Union, Any, List, Dict, Set, Tuple
import sys

# Import the dataclasses we want to convert
# We need to work around fuse_h4x requiring sys.argv[1]
sys.argv = ['generate_cpp', 'GW1N-1']

from apycula.chipdb import Bel, Tile, Device, Coord


# Type mappings from Python to C++
PRIMITIVE_TYPE_MAP = {
    int: "int64_t",
    str: "std::string",
    bool: "bool",
    float: "double",
    bytes: "std::vector<uint8_t>",
    bytearray: "std::vector<uint8_t>",
}

# C++ reserved keywords that need renaming
RESERVED_KEYWORDS = {
    'template': 'template_',
    'const': 'const_',
    'class': 'class_',
    'struct': 'struct_',
    'enum': 'enum_',
    'union': 'union_',
    'namespace': 'namespace_',
    'new': 'new_',
    'delete': 'delete_',
    'default': 'default_',
    'operator': 'operator_',
    'private': 'private_',
    'protected': 'protected_',
    'public': 'public_',
}


def get_hash_type(cpp_type: str) -> str:
    """Get the hash type for a given C++ type."""
    if cpp_type == "std::string":
        return "std::hash<std::string>"
    if cpp_type == "int64_t":
        return "std::hash<int64_t>"
    if cpp_type == "Coord":
        return "PairHash"  # Coord is std::pair<int64_t, int64_t>
    if cpp_type.startswith("std::pair<"):
        return "PairHash"
    if cpp_type.startswith("std::array<"):
        return "ArrayHash"
    if cpp_type.startswith("std::tuple<"):
        return "TupleHash"
    return f"std::hash<{cpp_type}>"


def map_type(py_type, depth: int = 0) -> str:
    """Convert a Python type annotation to a C++ type string."""
    # Handle None type
    if py_type is type(None):
        return "std::nullptr_t"

    # Handle primitive types
    if py_type in PRIMITIVE_TYPE_MAP:
        return PRIMITIVE_TYPE_MAP[py_type]

    # Handle type aliases
    if py_type is Coord:
        return "Coord"  # We define this as std::pair<int64_t, int64_t>

    # Get the origin and args for generic types
    origin = get_origin(py_type)
    args = get_args(py_type)

    # Handle Union types (including Optional)
    if origin is Union:
        # Check if it's Optional (Union with None)
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            # Optional[T] -> std::optional<T>
            inner = map_type(non_none_args[0], depth + 1)
            return f"std::optional<{inner}>"
        # Union[int, str] -> std::variant<int, str>
        inner_types = ", ".join(map_type(a, depth + 1) for a in args)
        return f"std::variant<{inner_types}>"

    # Handle List
    if origin is list:
        if not args:
            return "std::vector<msgpack::object>"
        inner = map_type(args[0], depth + 1)
        return f"std::vector<{inner}>"

    # Handle Dict
    if origin is dict:
        if len(args) < 2:
            return "std::unordered_map<msgpack::object, msgpack::object>"
        key_type = map_type(args[0], depth + 1)
        val_type = map_type(args[1], depth + 1)
        hash_type = get_hash_type(key_type)
        return f"std::unordered_map<{key_type}, {val_type}, {hash_type}>"

    # Handle Set
    if origin is set:
        if not args:
            return "std::unordered_set<msgpack::object>"
        inner = map_type(args[0], depth + 1)
        hash_type = get_hash_type(inner)
        return f"std::unordered_set<{inner}, {hash_type}>"

    # Handle Tuple
    if origin is tuple:
        if not args:
            return "std::tuple<>"
        # Check if all args are the same type (fixed-size array)
        if len(set(args)) == 1 and len(args) > 2:
            inner = map_type(args[0], depth + 1)
            return f"std::array<{inner}, {len(args)}>"
        # Two-element tuple -> std::pair
        if len(args) == 2:
            first = map_type(args[0], depth + 1)
            second = map_type(args[1], depth + 1)
            return f"std::pair<{first}, {second}>"
        # General tuple
        inner_types = ", ".join(map_type(a, depth + 1) for a in args)
        return f"std::tuple<{inner_types}>"

    # Handle Any type
    if py_type is Any:
        return "msgpack::object"

    # Handle dataclass references
    if is_dataclass(py_type):
        return py_type.__name__

    # Fallback for unknown types
    return "msgpack::object"


def cpp_field_name(name: str) -> str:
    """Convert a Python field name to a valid C++ identifier."""
    return RESERVED_KEYWORDS.get(name, name)


def generate_struct(cls) -> str:
    """Generate a C++ struct definition for a dataclass."""
    lines = [f"struct {cls.__name__} {{"]

    field_names = []
    for f in fields(cls):
        cpp_type = map_type(f.type)
        cpp_name = cpp_field_name(f.name)
        lines.append(f"    {cpp_type} {cpp_name};")
        field_names.append(cpp_name)

    # Add MSGPACK_DEFINE macro
    if field_names:
        fields_str = ", ".join(field_names)
        lines.append(f"    MSGPACK_DEFINE({fields_str});")

    lines.append("};")
    return "\n".join(lines)


def generate_header() -> str:
    """Generate the complete C++ header file."""
    lines = [
        "// chipdb_types.hpp - Auto-generated from apycula/chipdb.py",
        "// DO NOT EDIT - Regenerate with: python -m apycula.generate_cpp",
        "#pragma once",
        "",
        "#include <msgpack.hpp>",
        "#include <string>",
        "#include <vector>",
        "#include <array>",
        "#include <unordered_map>",
        "#include <unordered_set>",
        "#include <optional>",
        "#include <variant>",
        "#include <cstdint>",
        "",
        "namespace apycula {",
        "",
        "// Type alias for coordinate tuples",
        "using Coord = std::pair<int64_t, int64_t>;",
        "",
        "// Hash function for Coord (pair of int64_t)",
        "struct PairHash {",
        "    template<typename T1, typename T2>",
        "    size_t operator()(const std::pair<T1, T2>& p) const {",
        "        auto h1 = std::hash<T1>{}(p.first);",
        "        auto h2 = std::hash<T2>{}(p.second);",
        "        return h1 ^ (h2 << 16);",
        "    }",
        "};",
        "",
        "// Hash function for std::array",
        "struct ArrayHash {",
        "    template<typename T, size_t N>",
        "    size_t operator()(const std::array<T, N>& arr) const {",
        "        size_t h = 0;",
        "        for (const auto& elem : arr) {",
        "            h ^= std::hash<T>{}(elem) + 0x9e3779b9 + (h << 6) + (h >> 2);",
        "        }",
        "        return h;",
        "    }",
        "};",
        "",
        "// Hash function for std::tuple",
        "struct TupleHash {",
        "    template<typename... Args>",
        "    size_t operator()(const std::tuple<Args...>& t) const {",
        "        return hash_tuple(t, std::index_sequence_for<Args...>{});",
        "    }",
        "private:",
        "    template<typename Tuple, size_t... Is>",
        "    size_t hash_tuple(const Tuple& t, std::index_sequence<Is...>) const {",
        "        size_t h = 0;",
        "        ((h ^= std::hash<std::tuple_element_t<Is, Tuple>>{}(std::get<Is>(t)) + 0x9e3779b9 + (h << 6) + (h >> 2)), ...);",
        "        return h;",
        "    }",
        "};",
        "",
    ]

    # Generate structs in dependency order: Bel, Tile, Device
    for cls in [Bel, Tile, Device]:
        lines.append(generate_struct(cls))
        lines.append("")

    lines.append("} // namespace apycula")
    lines.append("")

    return "\n".join(lines)


def main():
    print(generate_header())


if __name__ == "__main__":
    main()
