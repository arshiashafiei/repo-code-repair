import ast, pathlib


def lines(path):
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="ignore")
    return text, text.splitlines()


def func_signature(node: ast.FunctionDef | ast.AsyncFunctionDef):
    a = node.args
    def fmt_args(args): return [arg.arg for arg in args]
    parts = []
    parts += fmt_args(a.posonlyargs) + fmt_args(a.args)
    if a.vararg: parts.append("*" + a.vararg.arg)
    if a.kwonlyargs: parts += [kw.arg + ("=..." if d is not None else "")
                               for kw, d in zip(a.kwonlyargs, a.kw_defaults)]
    if a.kwarg: parts.append("**" + a.kwarg.arg)
    return f"{node.name}(" + ", ".join(parts) + ")"


def first_last_five(src_lines, start, end):
    # start/end are 1-based inclusive; clamp and skip empties sparingly
    block = src_lines[start-1:end]
    head = "\n".join(block[:5])
    tail = "\n".join(block[-5:]) if len(block) > 5 else ""
    return (head + ("\n...\n" if tail else "") + tail).strip()


def build_python_skeleton(path):
    text, src_lines = lines(path)
    mod = ast.parse(text)
    skeleton = {
        "file_path": str(path),
        "module_docstring": ast.get_docstring(mod) or "",
        "classes": [],
        "functions": [],
    }
    for node in mod.body:
        if isinstance(node, ast.ClassDef):
            methods = []
            for b in node.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(func_signature(b))
            skeleton["classes"].append({
                "name": node.name + "(" + ",".join([ast.unparse(base) if hasattr(ast, "unparse") else "..." for base in node.bases]) + ")",
                "docstring": ast.get_docstring(node) or "",
                "methods": methods
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = getattr(node, "lineno", 1), getattr(node, "end_lineno", node.lineno)
            skeleton["functions"].append({
                "name": func_signature(node),
                "content": first_last_five(src_lines, start, end)
            })
    return skeleton
