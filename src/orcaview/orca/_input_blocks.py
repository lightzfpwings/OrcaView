"""Merge validated overrides into the input writer's own ORCA block templates."""


def _native_value(value):
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)


def _merge_body(body, additions, indent="  "):
    # Indentation is part of our templates. It distinguishes a field at this
    # level from an identically named field in a nested CI or MRCI section.
    for key, value in additions.items():
        index = None
        for i, line in enumerate(body):
            if line.startswith(indent) and line[len(indent):].partition(" ")[0].casefold() == key.casefold():
                index = i
                break
        if isinstance(value, dict):
            if index is None:
                body.extend([indent + key, *_merge_body([], value, indent + "  "), indent + "end"])
                continue
            if body[index].strip().casefold() == key.casefold():
                end = body.index(indent + "end", index + 1)
                body[index + 1:end] = _merge_body(body[index + 1:end], value, indent + "  ")
                continue
        if index is not None:
            raise ValueError(f"参数 {key} 已由所选计算模板设置")
        body.append(f"{indent}{key} {_native_value(value)}")
    return body


def merge_block_lines(template, values):
    if not values:
        return template
    additions = {}
    for (path, key), value in values.items():
        section = additions
        for name in path.split("."):
            section = section.setdefault(name, {})
        section[key] = value

    # Every top-level header in these generated lines starts at column zero;
    # nested 'end' lines and 'end' inside an MRCI refs expression stay intact.
    blocks = {}
    for line in template:
        if line.startswith("%"):
            name = line[1:]
            if name in blocks:
                raise ValueError(f"计算模板中出现重复的 %{name} 块")
            blocks[name] = []
        else:
            blocks[name].append(line)
    result = []
    for name in dict.fromkeys((*blocks, *additions)):
        original = blocks.get(name, ["end"])
        body = _merge_body(original[:-1], additions.get(name, {}))
        result.extend(("%" + name, *body, "end"))
    return tuple(result)
