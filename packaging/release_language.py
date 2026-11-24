"""Keep the English desktop release independent of optional language extensions."""

import ast
import json
import re


_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f\U00030000-\U000323af]")


def check_release_text(text, path):
    if _HAN.search(text):
        raise ValueError(f"Move Chinese text out of the desktop package and into a language extension: {path}")


def check_release_sources(root):
    source = root / "src/orcaview"
    for path in source.rglob("*"):
        if "__pycache__" in path.parts or not path.is_file():
            continue
        name = path.relative_to(source).as_posix()
        check_release_text(name, name)
        if path.suffix == ".qm" or name.startswith("languages/"):
            raise ValueError(f"An interface language pack must be distributed separately: {name}")
        if path.suffix == ".py":
            tree = ast.parse(path.read_bytes(), filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    check_release_text(node.value, f"{name}:{node.lineno}")
        elif path.suffix == ".json":
            # Decode escaped Unicode in the same way as the running application.
            check_release_text(json.dumps(json.loads(path.read_bytes()), ensure_ascii=False), name)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "packaging/desktop/SOURCES.txt",
                 "packaging/macos/DEPENDENCY_LICENSES.txt"):
        check_release_text((root / name).read_text(encoding="utf-8"), name)
