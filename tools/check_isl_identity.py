"""Check pinned ISL role mappings without importing application/Qt code.

Distributed from ergonomie/tools/check_identity.py by verify_adoption.py.
Only explicit adopted roles are checked; this is not a full visual audit.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def read_binding(tree, name):
    parts = name.split(".")
    scope = tree
    for part in parts[:-1]:
        functions = (n for n in scope.body if isinstance(n, ast.FunctionDef))
        scope = next(n for n in functions if n.name == part)
    found = []
    for node in scope.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        )
        if any(isinstance(t, ast.Name) and t.id == parts[-1] for t in targets):
            found.append(node.value)
    if len(found) != 1:
        raise ValueError(f"Expected one binding for {name}, got {len(found)}")
    return found[0]


def select(node, path):
    for key in path:
        if isinstance(node, ast.Call):
            node = next(k.value for k in node.keywords if k.arg == key)
        elif isinstance(node, ast.Dict):
            keys = [ast.literal_eval(k) for k in node.keys]
            node = node.values[keys.index(key)]
        elif isinstance(node, (ast.Tuple, ast.List)):
            node = node.elts[key]
        elif isinstance(node, ast.IfExp) and key in ("body", "orelse"):
            node = getattr(node, key)
        else:
            raise ValueError(f"Unsupported selector {key}")
    return ast.literal_eval(node)


def check(root, contract):
    trees, errors = {}, []
    for rule in contract["rules"]:
        file = rule["file"]
        try:
            if file not in trees:
                trees[file] = ast.parse((root / file).read_text(encoding="utf-8"))
            binding = read_binding(trees[file], rule["binding"])
            actual = select(binding, rule.get("path", []))
            expected = rule["expected"]
            if str(actual).casefold() != str(expected).casefold():
                errors.append(
                    f"{file}: {rule['binding']} {rule.get('path', [])}: "
                    f"{actual!r} != {expected!r} ({rule['source']})"
                )
        except (
            OSError,
            SyntaxError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            StopIteration,
        ) as error:
            errors.append(f"{file}: {rule['binding']}: cannot verify ({error})")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    path = args.contract or args.root / "docs/isl-identity-contract.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    errors = check(args.root, contract)
    for error in errors:
        print(error)
    print(
        f"ISL UX {contract['reference_version']}: {len(contract['rules'])} mappings, "
        f"{len(errors)} deviations. Scope: adopted roles only."
    )
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
