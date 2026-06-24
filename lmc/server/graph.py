"""Polygloter CPG-Extractor auf Basis von tree-sitter.

Baut einen echten, in-memory Code Property Graph (Methoden + Call-Kanten)
fuer alle unterstuetzten Sprachen. Kein Joern/Scala noetig.

ponytail: Namensbasierte Call-Aufloesung, keine dynamische Dispatch-Analyse,
kein Data-Flow. Deckt Call-Graph-Fragen (callers/callees/impact) real ab;
fuer Data-Flow/taint muesste Joern angebunden werden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tree_sitter_language_pack import get_parser

#Unsere Sprachen -> tree-sitter-Sprachname.
TS_LANG = {
    "php": "php", "python": "python", "javascript": "javascript",
    "typescript": "typescript", "java": "java", "c": "c", "cpp": "cpp",
    "csharp": "csharp", "go": "go", "kotlin": "kotlin", "ruby": "ruby",
    "swift": "swift", "scala": "scala",
}

DEF_KINDS = {
    "function_definition", "function_declaration", "method_definition",
    "method_declaration", "method", "constructor_declaration",
    "destructor_declaration", "getter_declaration", "setter_declaration",
}
CALL_KINDS = {
    "call", "call_expression", "function_call_expression",
    "member_call_expression", "scoped_call_expression", "method_invocation",
    "invocation_expression", "generic_function_invocation",
}
CLASS_KINDS = {
    "class_declaration", "class_definition", "class", "trait",
    "interface_declaration", "interface", "object_declaration",
    "struct_declaration", "struct", "enum_declaration", "enum",
    "record_declaration", "impl_item",
}
IDENT_KINDS = {
    "identifier", "simple_identifier", "property_identifier",
    "namespace_identifier", "type_identifier", "field_identifier",
}
SELF_OBJECTS = {"this", "self", "$this", "super", "it", "me"}


def _text(node, src: str) -> str:
    if node is None:
        return ""
    return src[node.start_byte():node.end_byte()]


def _first_ident(node) -> Optional[object]:
    """Erster identifier-aehniger Named-Child (rekursiv, flach zuerst)."""
    for i in range(node.named_child_count()):
        c = node.named_child(i)
        if c.kind() in IDENT_KINDS:
            return c
    for i in range(node.named_child_count()):
        c = node.named_child(i)
        r = _first_ident(c)
        if r:
            return r
    return None


def def_name(node, src: str) -> str:
    n = node.child_by_field_name("name")
    if n:
        return _text(n, src)
    d = node.child_by_field_name("declarator")
    if d:
        nn = d.child_by_field_name("name")
        if nn:
            return _text(nn, src)
        dd = d.child_by_field_name("declarator")
        if dd:
            ident = _first_ident(dd) or _first_ident(d)
            if ident:
                return _text(ident, src)
        ident = _first_ident(d)
        if ident:
            return _text(ident, src)
    ident = _first_ident(node)
    return _text(ident, src) if ident else ""


def class_of(node, src: str) -> Optional[str]:
    parent = node.parent()
    while parent is not None:
        if parent.kind() in CLASS_KINDS:
            cn = parent.child_by_field_name("name")
            if not cn:
                cn = _first_ident(parent)
            return _text(cn, src) if cn else None
        parent = parent.parent()
    return None


def callee_of(call_node, src: str, caller_class: Optional[str]) -> Tuple[str, Optional[str]]:
    """Liefert (callee_name, callee_class_hint)."""
    n = call_node.child_by_field_name("name")
    if n:
        obj = call_node.child_by_field_name("object") or call_node.child_by_field_name("receiver")
        obj_t = _text(obj, src) if obj else None
        return _text(n, src), _resolve_class(obj_t, caller_class)
    f = call_node.child_by_field_name("function")
    if f is None:
        f = call_node.named_child(0) if call_node.named_child_count() else None
    if f is None:
        return "", None
    fk = f.kind()
    if fk in IDENT_KINDS:
        return _text(f, src), None
    # member_expression / field_access / scoped_identifier / qualified_identifier
    prop = (f.child_by_field_name("property") or f.child_by_field_name("name")
            or f.child_by_field_name("field") or f.child_by_field_name("method")
            or f.child_by_field_name("attribute"))
    obj = f.child_by_field_name("object") or f.child_by_field_name("receiver")
    if prop:
        return _text(prop, src), _resolve_class(_text(obj, src) if obj else None, caller_class)
    ident = _first_ident(f)
    return (_text(ident, src) if ident else "", None)


def _resolve_class(obj_text: Optional[str], caller_class: Optional[str]) -> Optional[str]:
    if not obj_text:
        return None
    if obj_text in SELF_OBJECTS:
        return caller_class
    return obj_text  # Klassenname (statisch) oder Variablenname (unbekannt)


@dataclass
class Method:
    name: str
    cls: Optional[str]
    file: str
    line: int
    kind: str
    start_byte: int
    end_byte: int

    @property
    def signature(self) -> str:
        return f"{self.cls}.{self.name}" if self.cls else self.name

    @property
    def class_last(self) -> Optional[str]:
        if not self.cls:
            return None
        return re.split(r"[\\/.]+", self.cls)[-1]


@dataclass
class Edge:
    caller: Method
    callee_name: str
    callee_class: Optional[str]


@dataclass
class Index:
    codebase_hash: str
    language: str
    methods: List[Method] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    files: Dict[str, str] = field(default_factory=dict)
    _by_sig: Dict[str, List[Method]] = field(default_factory=dict)

    def finalize(self):
        self._by_sig.clear()
        for m in self.methods:
            self._by_sig.setdefault(m.signature, []).append(m)
            self._by_sig.setdefault(m.name, []).append(m)

    # --- Query-API ---

    def resolve(self, spec: str) -> List[Method]:
        """Loest 'Class.method' oder 'method' auf Methoden auf."""
        if "." in spec:
            cls_part, method = spec.rsplit(".", 1)
            cls_last = re.split(r"[\\/.]+", cls_part)[-1]
            return [m for m in self.methods
                    if m.name == method and m.class_last == cls_last]
        return [m for m in self.methods if m.name == spec]

    def find(self, pattern: str) -> List[Method]:
        rx = re.compile(pattern)
        return [m for m in self.methods if rx.search(m.signature)]

    def callers(self, spec: str) -> List[Method]:
        targets = {id(m) for m in self.resolve(spec)}
        out: List[Method] = []
        seen = set()
        for e in self.edges:
            if id(e.caller) in seen:
                continue
            resolved = self._resolve_target(e)
            if any(id(t) in targets for t in resolved):
                seen.add(id(e.caller))
                out.append(e.caller)
        return out

    def callees(self, spec: str) -> List[Method]:
        out: List[Method] = []
        seen = set()
        for e in self.edges:
            if any(m.signature == e.caller.signature for m in self.resolve(spec)):
                for t in self._resolve_target(e):
                    if id(t) not in seen:
                        seen.add(id(t))
                        out.append(t)
        return out

    def _resolve_target(self, e: Edge) -> List[Method]:
        if e.callee_class:
            cls_last = re.split(r"[\\/.]+", e.callee_class)[-1]
            hits = [m for m in self.methods
                    if m.name == e.callee_name and m.class_last == cls_last]
            if hits:
                return hits
        return [m for m in self.methods if m.name == e.callee_name]

    def impact(self, spec: str, depth: int) -> Dict[int, List[str]]:
        """BFS ueber Caller (incoming) bis depth Ebenen."""
        affected: Dict[int, List[str]] = {}
        current = self.resolve(spec)
        visited = {id(m) for m in current}
        for d in range(1, depth + 1):
            next_level: List[Method] = []
            for m in current:
                for caller in self._direct_callers(m):
                    if id(caller) not in visited:
                        visited.add(id(caller))
                        next_level.append(caller)
            if not next_level:
                break
            affected[d] = sorted({c.signature for c in next_level})
            current = next_level
        return affected

    def _direct_callers(self, target: Method) -> List[Method]:
        out = []
        for e in self.edges:
            resolved = self._resolve_target(e)
            if any(t.signature == target.signature for t in resolved):
                out.append(e.caller)
        return out

    def source(self, spec: str) -> Optional[dict]:
        ms = self.resolve(spec)
        if not ms:
            return None
        m = ms[0]
        content = self.files.get(m.file, "")
        return {
            "file": m.file, "line": m.line,
            "signature": m.signature,
            "source": content[m.start_byte:m.end_byte],
        }

    def methods_of(self, class_name: str) -> List[Method]:
        """Alle Methoden einer Klasse (Match ueber letzten Segment)."""
        last = class_name.replace(chr(92), "/").split("/")[-1]
        return [m for m in self.methods if m.class_last == last]

    def callees_of_class(self, class_name: str) -> List[str]:
        """Alle von einer Klasse aufgerufenen Methoden-Signaturen (vereinigt)."""
        out, seen = [], set()
        for m in self.methods_of(class_name):
            for c in self.callees(m.signature):
                if c.signature not in seen:
                    seen.add(c.signature)
                    out.append(c.signature)
        return out


def build_index(codebase_hash: str, language: str, root_path) -> Index:
    """Parsed einen Worktree und baut den Index."""
    ts_lang = TS_LANG.get(language)
    if not ts_lang:
        raise ValueError(f"Sprache nicht unterstuetzt: {language}")
    parser = get_parser(ts_lang)
    root = Path(root_path).resolve()
    idx = Index(codebase_hash=codebase_hash, language=language)
    exts = _exts_for(language)

    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        if any(part in _IGNORE for part in p.relative_to(root).parts[:-1]):
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        idx.files[str(p)] = src
        try:
            tree = parser.parse(src)
        except Exception:
            continue
        _walk(tree.root_node(), src, str(p), idx, def_stack=[])
    idx.finalize()
    return idx


def _walk(node, src, file, idx, def_stack):
    k = node.kind()
    if k in DEF_KINDS and def_name(node, src):
        m = Method(
            name=def_name(node, src), cls=class_of(node, src),
            file=file, line=node.start_position().row + 1, kind=k,
            start_byte=node.start_byte(), end_byte=node.end_byte(),
        )
        idx.methods.append(m)
        def_stack = def_stack + [m]
    elif k in CALL_KINDS and def_stack:
        caller = def_stack[-1]
        cname, ccls = callee_of(node, src, caller.cls)
        if cname:
            idx.edges.append(Edge(caller=caller, callee_name=cname, callee_class=ccls))
    for i in range(node.child_count()):
        c = node.child(i)
        if c.is_named():
            _walk(c, src, file, idx, def_stack)


_IGNORE = {
    ".git", "node_modules", "vendor", ".venv", "venv", "dist", "build",
    "__pycache__", ".idea", ".vscode", "target", "bower_components",
    "storage", "var", "cache", "__pycache__",
}

_LANG_EXTS = {
    "php": {".php", ".phtml", ".php5"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx", ".mts", ".cts"},
    "python": {".py", ".pyi"},
    "java": {".java"},
    "c": {".c", ".h"},
    "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"},
    "csharp": {".cs"},
    "go": {".go"},
    "kotlin": {".kt", ".kts"},
    "ruby": {".rb"},
    "swift": {".swift"},
    "scala": {".scala", ".sc"},
}


def _exts_for(language: str) -> set:
    return _LANG_EXTS.get(language, set())


if __name__ == "__main__":
    # ponytail: self-check mit PHP + Python Quellen.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.php").write_text(
            '<?php\nclass Order {\n    public function store() { $this->save(); }\n'
            '    public function save() { Logger::log(); }\n}\nfunction helper() { order(); }\n')
        (Path(d) / "b.py").write_text(
            'def foo():\n    bar()\ndef bar():\n    pass\n')
        idx = build_index("h", "php", d)
        sigs = sorted(m.signature for m in idx.methods)
        assert "Order.store" in sigs and "Order.save" in sigs, sigs
        assert "helper" in sigs, sigs
        callers_store = [m.signature for m in idx.callers("Order.store")]
        callees_store = [m.signature for m in idx.callees("Order.store")]
        assert callees_store == ["Order.save"], callees_store
        idx2 = build_index("h2", "python", d)
        assert sorted(m.signature for m in idx2.methods) == ["bar", "foo"]
        assert [m.signature for m in idx2.callers("bar")] == ["foo"]
    print("graph.py self-check OK; php methods:", sigs)