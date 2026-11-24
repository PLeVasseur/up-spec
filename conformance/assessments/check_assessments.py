import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
import re
import subprocess
import sys

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ANNOTATIONS = ("$schema", "$id", "title", "description")
ASSERTIONS = ("type", "properties", "required", "additionalProperties", "const", "enum",
              "pattern", "minLength", "items", "$ref", "$defs", "oneOf", "allOf", "not", "if",
              "then", "minimum", "minItems", "maxItems", "uniqueItems")
JSON_TYPES = ("null", "boolean", "object", "array", "number", "string", "integer")
SCHEMA_FILES = {1: "schema.json", 2: "schema.v2.json"}
HERE = os.path.dirname(os.path.abspath(__file__))

DELIMITERS = {"----": "listing", "....": "literal", "====": "example", "****": "sidebar",
              "____": "quote", "++++": "pass", "////": "comment", "|===": "table",
              "!===": "table", ",===": "table", ":===": "table"}
VERBATIM_BLOCKS = ("listing", "literal", "pass", "comment", "fenced")
VERBATIM_STYLES = ("source", "listing", "literal", "pass", "comment", "stem", "latexmath",
                   "asciimath", "verse")
LINE_COMMENT = re.compile(r"//(?:[^/]|$)")
ATTRIBUTE_LINE = re.compile(r"\[(?:|[\w.#%{,\"'].*|\[(?:|(?:[^\W\d]|:)[\w\-:.]*(?:, *.+)?)\])\]")
BLOCK_ANCHOR = re.compile(r"\[\[((?:[^\W\d]|:)[\w\-:.]*)(?:, *.+)?\]\]")
SHORTHAND_ANCHOR = re.compile(r"\[#((?:[^\W\d]|:)[\w\-:]*)\]")
OTHER_ID = re.compile(r"\[(?:[^\],\"']*#|\s*id\s*=|.*?,\s*id\s*=)")
BLOCK_TITLE = re.compile(r"\.\.?[^ \t.].*")
SECTION_TITLE = re.compile(r"(=={0,5}|#{1,6})[ \t]+(.+?)(?:[ \t]+\1)?")
ATTRIBUTE_ENTRY = re.compile(r":!?\w[^:]*:(?:[ \t]+.*)?")
DIRECTIVE = re.compile(r"\\?(?:ifdef|ifndef|ifeval|endif|include)::.*")
CONDITIONAL = re.compile(r"(\\)?(ifdef|ifndef|ifeval|endif)::(\S*?(?:[,+]\S*?)?)\[(.+)?\]")
BLOCK_MACRO = re.compile(r"(?:image|video|audio|toc)::\S*\[.*\]")
BREAK = re.compile(r"'{3,}|<{3,}| {0,3}([-*_])( *)\1\2\1")
LIST_ITEM = re.compile(r"(?:[ \t]*(?:-|\*+|\.+|•|\d+\.|[a-zA-Z]\.|[IVXivx]+\))[ \t]"
                       r"|(?!//[^/])[ \t]*[^ \t].*?(?::{2,4}|;;)(?:$|[ \t])|<(?:\d+|\.)>[ \t])")
CELL_SPEC = (r"(?:(?:\d+(?:\.\d*)?|(?:\d*\.)?\d+)[*+])?"
             r"(?:[<^>](?:\.[<^>]?)?|(?:[<^>]?\.)?[<^>])?([a-z])?")
CELL_SPEC_START = re.compile(r"[ \t]*" + CELL_SPEC)
CELL_SPEC_END = re.compile(r"[ \t]+" + CELL_SPEC + r"$")
COLUMN_SPEC = re.compile(r"(?:\d+\*)?(?:[<^>](?:\.[<^>]?)?|(?:[<^>]?\.)?[<^>])?(?:\d+%?|~)?([a-z])?")
SETEXT_TITLE = re.compile(r"(?!\.).*?[^\W_].*")
SERVICE_VERSION = re.compile(r"up-l3/([^/]+)/(v[0-9]+)/")
COMMIT = re.compile(r"[0-9a-f]{40}")
ZERO_PIN = "0" * 40
NUM_RE = re.compile(r"(-)?(0|[1-9][0-9]*)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?")
INERT_SOURCE_STYLE = re.compile(r"\[source(?:,[^\]\[=\"']*)?\]")
STRUCTURAL_NOTES = ("include_directive", "conditional_region", "single_line_conditional",
                    "unterminated_block", "setext_title", "heading_in_block", "unmatched_endif")
CELL_NOTES = ("cell_style_from_columns", "oft_sid_in_delimited_data_table", "text_before_first_cell")
DOUBTFUL_FLAGS = ("unreadable_attribute_list", "multiple_oft_sid", "single_quoted",
                  "attribute_reference", "attribute_line_in_list_item", "in_verbatim_paragraph",
                  "conditional", "head_detached_by_blank", "no_target", "target_is_comment")


class Unsupported(Exception):
    pass


class Undecided(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class JsonNumber:
    def __init__(self, raw):
        m = NUM_RE.fullmatch(raw)
        if not m:
            raise ValueError("invalid JSON number %r" % raw)
        self.raw = raw
        sign, ipart, fpart, epart = m.groups()
        digits = (ipart + (fpart or "")).lstrip("0")
        if not digits:
            self.mantissa = 0
            self.exp10 = 0
        else:
            nz = digits.rstrip("0")
            try:
                exp_val = int(epart) if epart else 0
                mant_val = int(nz)
            except ValueError as exc:
                raise Unsupported("a JSON number exceeds the host numeric conversion limit: %s" % exc)
            self.exp10 = exp_val - len(fpart or "") + (len(digits) - len(nz))
            self.mantissa = -mant_val if sign else mant_val


def num_parts(value):
    if isinstance(value, JsonNumber):
        return value.mantissa, value.exp10
    if isinstance(value, int) and not isinstance(value, bool):
        if value == 0:
            return 0, 0
        try:
            s = str(abs(value))
            nz = s.rstrip("0")
            m = int(nz)
        except ValueError as exc:
            raise Unsupported("a JSON number exceeds the host numeric conversion limit: %s" % exc)
        return (-m if value < 0 else m), len(s) - len(nz)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float")
        n = JsonNumber(str(Decimal(value)))
        return n.mantissa, n.exp10
    raise TypeError("not a number")


def exact_int(value):
    m, e = num_parts(value)
    if e < 0:
        raise ValueError("not an integer")
    if m == 0:
        return 0
    if e > 1000:
        raise Unsupported("an integer exponent outside the supported range")
    res = m * (10 ** e)
    try:
        str(res)
    except ValueError as exc:
        raise Unsupported("an integer exceeds the host numeric conversion limit: %s" % exc)
    return res


def schema_version_of(value):
    if not is_number(value):
        return None
    m, e = num_parts(value)
    if e == 0 and m in SCHEMA_FILES:
        return m
    return None


def num_cmp(a, b):
    ma, ea = num_parts(a)
    mb, eb = num_parts(b)
    if (ma, ea) == (mb, eb):
        return 0
    sa = 1 if ma > 0 else (-1 if ma < 0 else 0)
    sb = 1 if mb > 0 else (-1 if mb < 0 else 0)
    if sa != sb:
        return -1 if sa < sb else 1
    try:
        da = str(abs(ma))
        db = str(abs(mb))
    except ValueError as exc:
        raise Unsupported("a JSON number exceeds the host numeric conversion limit: %s" % exc)
    oa = len(da) + ea
    ob = len(db) + eb
    if oa != ob:
        mag = -1 if oa < ob else 1
    else:
        mag = -1 if da < db else 1
    return mag if sa > 0 else -mag


def dump_json(value, indent=None, level=0):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, JsonNumber):
        return value.raw
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        if not value:
            return "[]"
        if indent is None:
            return "[" + ",".join(dump_json(v) for v in value) + "]"
        pad = " " * (indent * (level + 1))
        end = " " * (indent * level)
        return "[\n" + ",\n".join(pad + dump_json(v, indent, level + 1) for v in value) + "\n" + end + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        keys = sorted(value)
        if indent is None:
            return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + dump_json(value[k]) for k in keys) + "}"
        pad = " " * (indent * (level + 1))
        end = " " * (indent * level)
        parts = [pad + json.dumps(k, ensure_ascii=False) + ": " + dump_json(value[k], indent, level + 1) for k in keys]
        return "{\n" + ",\n".join(parts) + "\n" + end + "}"
    raise TypeError("cannot encode %r" % type(value).__name__)


def finite_and_encodable(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return True
    if isinstance(value, list):
        return all(finite_and_encodable(v) for v in value)
    if isinstance(value, dict):
        return all(finite_and_encodable(k) and finite_and_encodable(v) for k, v in value.items())
    return True


def strict_json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate object member %r" % key)
            out[key] = value
        return out

    def constant(name):
        raise ValueError("%s is not JSON" % name)

    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant,
                       parse_float=JsonNumber, parse_int=JsonNumber)
    if not finite_and_encodable(value):
        raise ValueError("a number that is not finite, or a string that is not Unicode text")
    return value


def canonical(value):
    return dump_json(value, indent=None).encode("utf-8")


def is_number(value):
    return isinstance(value, (int, float, JsonNumber)) and not isinstance(value, bool)


def type_ok(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "number":
        return is_number(value)
    return is_number(value) and num_parts(value)[1] >= 0


def json_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if is_number(a) and is_number(b):
        return num_parts(a) == num_parts(b)
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return False


def pointer(name):
    return name.replace("~", "~0").replace("/", "~1")


def translate_pattern(pattern):
    out = []
    depth = 0
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "\\":
            if i + 1 >= n:
                raise Unsupported("a pattern that ends in a backslash")
            e = pattern[i + 1]
            if e == "d":
                out.append("[0-9]")
            elif e in "\\/.^$|?*+()[]{}-":
                out.append(re.escape(e))
            else:
                raise Unsupported("the pattern escape \\%s" % e)
            i += 2
        elif c == "[":
            j = i + 1
            part = ["["]
            if j < n and pattern[j] == "^":
                part.append("^")
                j += 1
            if j < n and pattern[j] == "]":
                raise Unsupported("an empty or ]-led character class")
            while True:
                if j >= n:
                    raise Unsupported("an unclosed character class")
                d = pattern[j]
                if d == "]":
                    break
                if d == "\\":
                    if j + 1 >= n:
                        raise Unsupported("a character class that ends in a backslash")
                    e = pattern[j + 1]
                    if e == "d":
                        part.append("0-9")
                    elif e in "\\]-^[":
                        part.append("\\" + e)
                    else:
                        raise Unsupported("the class escape \\%s" % e)
                    j += 2
                elif d.isascii() and (d.isalnum() or d in "-_:/ "):
                    part.append(d)
                    j += 1
                else:
                    raise Unsupported("the class character %r" % d)
            part.append("]")
            out.append("".join(part))
            i = j + 1
        elif c == "(":
            if pattern[i + 1:i + 2] == "?":
                raise Unsupported("group syntax (?")
            depth += 1
            out.append("(")
            i += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                raise Unsupported("an unbalanced )")
            out.append(")")
            i += 1
        elif c == "|":
            out.append("|")
            i += 1
        elif c in "?*+":
            if pattern[i + 1:i + 2] in ("?", "+"):
                raise Unsupported("a lazy or possessive quantifier")
            out.append(c)
            i += 1
        elif c == "{":
            m = re.match(r"\{(\d+)(,(\d*))?\}", pattern[i:])
            if not m:
                raise Unsupported("a { that is not a quantifier")
            out.append(m.group(0))
            i += len(m.group(0))
        elif c == "^":
            out.append("^")
            i += 1
        elif c == "$":
            out.append(r"\Z")
            i += 1
        elif c == ".":
            raise Unsupported("the pattern wildcard '.', whose meaning differs between dialects")
        elif c in "]}":
            raise Unsupported("an unbalanced %s" % c)
        else:
            out.append(re.escape(c))
            i += 1
    if depth:
        raise Unsupported("an unbalanced (")
    return re.compile("".join(out))


class Schema:
    def __init__(self, name, raw):
        self.name = name
        self.sha256 = sha256(raw)
        try:
            self.root = strict_json(raw)
        except ValueError as exc:
            raise Unsupported("%s: not a JSON document: %s" % (name, exc))
        self.compiled = {}
        self.keywords = set()
        if not isinstance(self.root, dict):
            raise Unsupported("%s: the schema is not an object" % name)
        if self.root.get("$schema") != DIALECT:
            raise Unsupported("%s: $schema is not %s" % (name, DIALECT))
        self.audit(self.root, "#", True)
        self.check_ref_cycles()

    def collect_refs(self, schema, out):
        if "$ref" in schema:
            out.append(schema["$ref"][8:])
        for sub in schema.get("properties", {}).values():
            self.collect_refs(sub, out)
        for key in ("items", "not", "if", "then"):
            if key in schema:
                self.collect_refs(schema[key], out)
        for key in ("oneOf", "allOf"):
            for sub in schema.get(key, []):
                self.collect_refs(sub, out)

    def check_ref_cycles(self):
        defs = self.root.get("$defs", {})
        edges = {}
        for name, sub in defs.items():
            refs = []
            self.collect_refs(sub, refs)
            edges[name] = refs
        state = {}
        path = []

        def visit(name):
            state[name] = 1
            path.append(name)
            for target in edges.get(name, []):
                st = state.get(target, 0)
                if st == 1:
                    idx = path.index(target)
                    cycle = " -> ".join(path[idx:] + [target])
                    self.fail("#/$defs/" + pointer(target), "a cyclic $ref (%s)" % cycle)
                if st == 0:
                    visit(target)
            path.pop()
            state[name] = 2

        for name in sorted(defs):
            if state.get(name, 0) == 0:
                visit(name)

    def fail(self, where, what):
        raise Unsupported("%s: %s at %s" % (self.name, what, where))

    def audit(self, schema, where, root=False):
        if not isinstance(schema, dict):
            self.fail(where, "a subschema that is not an object")
        for key, value in schema.items():
            here = where + "/" + pointer(key)
            if key not in ANNOTATIONS and key not in ASSERTIONS:
                self.fail(here, "the unsupported keyword %r" % key)
            self.keywords.add(key)
            if key in ("$schema", "$id"):
                if not root or not isinstance(value, str):
                    self.fail(here, "%s other than a string at the root" % key)
            elif key in ("title", "description"):
                if not isinstance(value, str):
                    self.fail(here, "a %s that is not a string" % key)
            elif key in ("$defs", "properties"):
                if key == "$defs" and not root:
                    self.fail(here, "$defs below the root")
                if not isinstance(value, dict):
                    self.fail(here, "%s that is not an object" % key)
                for name, sub in value.items():
                    self.audit(sub, here + "/" + pointer(name))
            elif key in ("items", "not", "if", "then"):
                self.audit(value, here)
            elif key in ("oneOf", "allOf"):
                if not isinstance(value, list) or not value:
                    self.fail(here, "%s that is not a non-empty array" % key)
                for k, sub in enumerate(value):
                    self.audit(sub, "%s/%d" % (here, k))
            elif key == "type":
                names = value if isinstance(value, list) else [value]
                if not names or len(set(map(str, names))) != len(names) or any(n not in JSON_TYPES for n in names):
                    self.fail(here, "a type other than the JSON type names")
            elif key == "required":
                if not isinstance(value, list) or any(not isinstance(v, str) for v in value) or len(set(value)) != len(value):
                    self.fail(here, "required that is not an array of unique strings")
            elif key == "additionalProperties":
                if not isinstance(value, bool):
                    self.fail(here, "additionalProperties other than true or false")
            elif key == "enum":
                if not isinstance(value, list) or not value:
                    self.fail(here, "enum that is not a non-empty array")
            elif key == "pattern":
                if not isinstance(value, str):
                    self.fail(here, "a pattern that is not a string")
                try:
                    self.compiled[value] = translate_pattern(value)
                except Unsupported as exc:
                    self.fail(here, str(exc))
            elif key in ("minLength", "minItems", "maxItems"):
                if not (is_number(value) and num_parts(value)[1] >= 0 and num_cmp(value, 0) >= 0):
                    self.fail(here, "%s that is not a non-negative integer" % key)
                exact_int(value)
            elif key == "minimum":
                if not is_number(value):
                    self.fail(here, "minimum that is not a number")
            elif key == "uniqueItems":
                if not isinstance(value, bool):
                    self.fail(here, "uniqueItems that is not a boolean")
            elif key == "$ref":
                if not isinstance(value, str) or not re.fullmatch(r"#/\$defs/[^/~]+", value):
                    self.fail(here, "a $ref other than #/$defs/<name>")
                if value[8:] not in self.root.get("$defs", {}):
                    self.fail(here, "a $ref to a missing definition")

    def validate(self, value):
        errors = []
        self.check(value, self.root, "", errors)
        return errors

    def errors_of(self, value, schema, at):
        errors = []
        self.check(value, schema, at, errors)
        return errors

    def check(self, value, schema, at, errors):
        where = at or "/"
        if "$ref" in schema:
            self.check(value, self.root["$defs"][schema["$ref"][8:]], at, errors)
        if "type" in schema:
            names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(type_ok(value, n) for n in names):
                errors.append("%s: the type is not %s" % (where, " or ".join(names)))
        if "const" in schema and not json_equal(value, schema["const"]):
            errors.append("%s: not the constant %s" % (where, dump_json(schema["const"])))
        if "enum" in schema and not any(json_equal(value, e) for e in schema["enum"]):
            errors.append("%s: not one of the enumerated values" % where)
        if isinstance(value, str):
            if "minLength" in schema and len(value) < exact_int(schema["minLength"]):
                errors.append("%s: shorter than %d characters" % (where, exact_int(schema["minLength"])))
            if "pattern" in schema and not self.compiled[schema["pattern"]].search(value):
                errors.append("%s: does not match the pattern %s" % (where, schema["pattern"]))
        if is_number(value) and "minimum" in schema and num_cmp(value, schema["minimum"]) < 0:
            errors.append("%s: less than %s" % (where, dump_json(schema["minimum"])))
        if isinstance(value, list):
            if "minItems" in schema and len(value) < exact_int(schema["minItems"]):
                errors.append("%s: fewer than %d items" % (where, exact_int(schema["minItems"])))
            if "maxItems" in schema and len(value) > exact_int(schema["maxItems"]):
                errors.append("%s: more than %d items" % (where, exact_int(schema["maxItems"])))
            if schema.get("uniqueItems") and any(json_equal(value[a], value[b]) for a in range(len(value)) for b in range(a)):
                errors.append("%s: two items are equal" % where)
            if "items" in schema:
                for k, item in enumerate(value):
                    self.check(item, schema["items"], "%s/%d" % (at, k), errors)
        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    errors.append("%s: the required member %s is missing" % (where, name))
            properties = schema.get("properties", {})
            for name, sub in properties.items():
                if name in value:
                    self.check(value[name], sub, at + "/" + pointer(name), errors)
            if schema.get("additionalProperties") is False:
                for name in value:
                    if name not in properties:
                        errors.append("%s: the member %s is not allowed" % (where, name))
        for sub in schema.get("allOf", []):
            self.check(value, sub, at, errors)
        if "oneOf" in schema:
            valid = sum(1 for sub in schema["oneOf"] if not self.errors_of(value, sub, at))
            if valid != 1:
                errors.append("%s: %d branches of oneOf hold, not exactly 1" % (where, valid))
        if "not" in schema and not self.errors_of(value, schema["not"], at):
            errors.append("%s: holds the schema under not" % where)
        if "if" in schema and "then" in schema and not self.errors_of(value, schema["if"], at):
            self.check(value, schema["then"], at, errors)


class Title:
    def __init__(self, line, level, text, above):
        self.line = line
        self.level = level
        self.text = text
        self.above = above


def delimiter(line):
    if line == "--":
        return "open"
    if line.startswith("```"):
        return "fenced"
    if len(line) >= 4 and line[:4] in DELIMITERS and line[4:] == line[3] * (len(line) - 4):
        return DELIMITERS[line[:4]]
    return None


def attribute_entries(inner):
    entries = []
    i = 0
    n = len(inner)
    named = re.compile(r"([\w][\w\-]*)[ \t]*=[ \t]*")
    while True:
        while i < n and inner[i] in " \t":
            i += 1
        name = None
        m = named.match(inner, i)
        if m:
            name = m.group(1)
            i = m.end()
        if i < n and inner[i] in "\"'":
            quote = inner[i]
            i += 1
            buf = []
            while i < n and inner[i] != quote:
                if inner[i] == "\\" and i + 1 < n and inner[i + 1] == quote:
                    buf.append(quote)
                    i += 2
                else:
                    buf.append(inner[i])
                    i += 1
            if i >= n:
                raise ValueError("an unterminated quoted value")
            i += 1
            while i < n and inner[i] in " \t":
                i += 1
            if i < n and inner[i] != ",":
                raise ValueError("text after a quoted value")
            entries.append((name, "".join(buf), quote))
        else:
            j = inner.find(",", i)
            if j < 0:
                j = n
            entries.append((name, inner[i:j].rstrip(" \t"), None))
            i = j
        if i >= n:
            return entries
        i += 1


def block_style(line):
    if line.startswith("[["):
        return None
    first = line[1:-1].split(",", 1)[0].strip()
    if not first or first[0] in ".#%\"'" or "=" in first:
        return None
    return re.split(r"[.#%]", first, maxsplit=1)[0]


def setext(line1, line2):
    if len(line2) < 2 or line2[0] not in "=-~^+" or line2 != line2[0] * len(line2):
        return False
    return bool(SETEXT_TITLE.fullmatch(line1)) and abs(len(line1) - len(line2)) < 2


def cell_lstrip(content):
    out = list(content)
    while out:
        no, text = out[0]
        text = text.lstrip(" \t\r\n\f\v\0")
        if text:
            out[0] = (no, text)
            break
        out.pop(0)
    return out


def column_styles(head):
    m = re.search(r"(?:^|[\[,])\s*cols\s*=\s*(\"[^\"]*\"|'[^']*'|[^,\]]*)", head)
    if not m:
        return False
    spec = m.group(1).strip("\"'")
    for part in re.split(r"[,;]", spec):
        c = COLUMN_SPEC.fullmatch(part.strip())
        if c is None or (c.group(1) and c.group(1) != "d"):
            return True
    return False


class Scan:
    def __init__(self, text):
        raw = text.split("\n")
        if raw and raw[-1] == "":
            raw.pop()
        self.lines = [line.rstrip(" \t\r\n\f\v\0") for line in raw]
        self.kinds = {}
        self.titles = []
        self.occurrences = []
        self.inert = []
        self.notes = []
        self.conditional = set()
        self.preprocess()
        self.parse([(k + 1, line) for k, line in enumerate(self.lines)], "top")
        self.occurrences.sort(key=lambda o: o["line"])
        self.titles.sort(key=lambda t: t.line)

    def preprocess(self):
        depth = []
        for k, line in enumerate(self.lines, 1):
            m = CONDITIONAL.fullmatch(line)
            if m and not m.group(1):
                if m.group(2) == "endif":
                    if depth:
                        depth.pop()
                    else:
                        self.notes.append((k, "unmatched_endif"))
                    continue
                if m.group(2) == "ifeval" or m.group(4) is None:
                    depth.append(k)
                    self.notes.append((k, "conditional_region"))
                    continue
                body = m.group(4)
                next_line = self.lines[k] if k < len(self.lines) else ""
                prev_line = self.lines[k - 2] if k >= 2 else ""
                if not (INERT_SOURCE_STYLE.fullmatch(body) and delimiter(next_line) == "listing" and "oft-sid" not in prev_line):
                    self.notes.append((k, "single_line_conditional"))
            elif line.startswith("include::"):
                self.notes.append((k, "include_directive"))
            if depth:
                self.conditional.add(k)

    def mark(self, no, ctx, kind):
        self.kinds[no] = (ctx, kind)

    def head_start(self, items, i):
        k = i
        while k > 0 and items[k - 1][0] == items[k][0] - 1 and self.kinds.get(items[k - 1][0], (None, None))[1] == "head":
            k -= 1
        return k

    def discrete(self, items, i):
        return any(block_style(text) in ("discrete", "float") for _, text in items[self.head_start(items, i):i])

    def head_text(self, items, i):
        return "".join(text for _, text in items[self.head_start(items, i):i])

    def parse(self, items, ctx):
        para = None
        style = None
        i = 0
        n = len(items)
        while i < n:
            no, line = items[i]
            if line == "":
                self.mark(no, ctx, "blank")
                para = None
                style = None
                i += 1
                continue
            if DIRECTIVE.fullmatch(line):
                self.mark(no, ctx, "directive")
                i += 1
                continue
            if LINE_COMMENT.match(line):
                self.mark(no, ctx, "comment")
                i += 1
                continue
            kind = delimiter(line)
            if kind:
                close = "```" if kind == "fenced" else line
                j = i + 1
                while j < n and items[j][1] != close:
                    j += 1
                if j >= n:
                    self.notes.append((no, "unterminated_block"))
                inner = items[i + 1:j]
                head = self.head_text(items, i)
                self.mark(no, ctx, "delimiter")
                if j < n:
                    self.mark(items[j][0], ctx, "delimiter")
                verbatim = (kind in VERBATIM_BLOCKS or (kind == "open" and style in VERBATIM_STYLES)
                            or (kind == "quote" and style == "verse"))
                if verbatim:
                    for no2, text in inner:
                        self.mark(no2, ctx, "verbatim")
                        if "oft-sid" in text:
                            self.inert.append((no2, "in_comment" if kind == "comment" or style == "comment" else "in_verbatim"))
                elif kind == "table":
                    self.table(inner, line, head, ctx)
                else:
                    for no2, _ in inner:
                        self.mark(no2, ctx, "nested")
                    self.parse(inner, "cell" if ctx == "cell" else "block")
                para = None
                style = None
                i = j + 1
                continue
            if ATTRIBUTE_LINE.fullmatch(line):
                before = para
                para = None
                self.mark(no, ctx, "head")
                if "oft-sid" in line:
                    self.item(items, i, ctx, before)
                s = block_style(line)
                if s is not None:
                    style = s
                i += 1
                continue
            if para is None:
                if BLOCK_TITLE.fullmatch(line):
                    self.mark(no, ctx, "head")
                    i += 1
                    continue
                m = SECTION_TITLE.fullmatch(line)
                if m and ctx == "top" and self.discrete(items, i):
                    self.mark(no, ctx, "discrete_heading")
                    style = None
                    i += 1
                    continue
                if m and ctx == "top":
                    above = items[i - 1][1] if i > 0 and items[i - 1][0] == no - 1 else None
                    self.titles.append(Title(no, len(m.group(1)) - 1, m.group(2), above))
                    self.mark(no, ctx, "title")
                    style = None
                    i += 1
                    continue
                if m:
                    self.notes.append((no, "heading_in_block"))
                if ATTRIBUTE_ENTRY.fullmatch(line):
                    self.mark(no, ctx, "attribute_entry")
                    i += 1
                    continue
                if BREAK.fullmatch(line):
                    self.mark(no, ctx, "break")
                    style = None
                    i += 1
                    continue
                if i + 1 < n and items[i + 1][0] == no + 1 and setext(line, items[i + 1][1]):
                    self.notes.append((no, "setext_title"))
            if line == "+":
                self.mark(no, ctx, "continuation")
                para = None
                style = None
                i += 1
                continue
            if "oft-sid" in line:
                self.inert.append((no, "in_list_item_text" if para == "list" else "mention"))
            if para is None:
                if style in VERBATIM_STYLES or (line[0] in " \t" and not LIST_ITEM.match(line)):
                    para = "verbatim"
                elif LIST_ITEM.match(line):
                    para = "list"
                elif BLOCK_MACRO.fullmatch(line):
                    self.mark(no, ctx, "macro")
                    style = None
                    i += 1
                    continue
                else:
                    para = "paragraph"
            self.mark(no, ctx, "text")
            style = None
            i += 1

    def table(self, inner, opener, head, ctx):
        for no, _ in inner:
            self.mark(no, ctx, "nested")
        if opener[0] in ",:":
            for no, text in inner:
                if "oft-sid" in text:
                    self.notes.append((no, "oft_sid_in_delimited_data_table"))
            return
        sep = opener[0]
        styled_columns = column_styles(head)
        cells = []
        current = None
        for no, text in inner:
            positions = [p for p, c in enumerate(text) if c == sep and (p == 0 or text[p - 1] != "\\")]
            if not positions:
                if current is not None:
                    current[1].append((no, text))
                elif "oft-sid" in text:
                    self.notes.append((no, "text_before_first_cell"))
                continue
            start = 0
            for p in positions:
                seg = text[start:p]
                style = None
                content = seg
                m = CELL_SPEC_START.fullmatch(seg) if start == 0 else None
                if m:
                    style = m.group(1)
                    content = ""
                else:
                    m = CELL_SPEC_END.search(seg)
                    if m:
                        style = m.group(1)
                        content = seg[:m.start()]
                if current is not None and (start > 0 or content != ""):
                    current[1].append((no, content))
                current = [style, [], no]
                cells.append(current)
                start = p + 1
            if text[start:] != "":
                current[1].append((no, text[start:]))
        for style, content, opened in cells:
            if style == "a":
                if content and content[0][0] == opened:
                    content = cell_lstrip(content)
                self.parse(content, "cell")
                continue
            for no, text in content:
                if "oft-sid" in text:
                    if style is None and styled_columns:
                        self.notes.append((no, "cell_style_from_columns"))
                    else:
                        self.inert.append((no, "in_plain_table_cell"))

    def item(self, items, i, ctx, before):
        no, line = items[i]
        n = len(items)
        flags = []
        try:
            entries = attribute_entries(line[1:-1])
        except ValueError:
            entries = None
            flags.append("unreadable_attribute_list")
        sids = [] if entries is None else [(v, q) for k, v, q in entries if k == "oft-sid"]
        if entries is not None and not sids:
            self.inert.append((no, "mention"))
            return
        if len(sids) > 1:
            flags.append("multiple_oft_sid")
        sid, quote = sids[0] if sids else (None, None)
        if quote == "'":
            flags.append("single_quoted")
        if sid is not None and "{" in sid:
            flags.append("attribute_reference")
        if before == "list":
            flags.append("attribute_line_in_list_item")
        if before == "verbatim":
            flags.append("in_verbatim_paragraph")
        if no in self.conditional:
            flags.append("conditional")
        k = self.head_start(items, i)
        t = i + 1
        while (t < n and items[t][0] == items[t - 1][0] + 1
               and (ATTRIBUTE_LINE.fullmatch(items[t][1]) or BLOCK_TITLE.fullmatch(items[t][1]))):
            t += 1
        head_style = None
        for _, hline in items[k:t]:
            if ATTRIBUTE_LINE.fullmatch(hline):
                hs = block_style(hline)
                if hs is not None:
                    head_style = hs
        target = None
        target_kind = None
        statement = None
        if t >= n or items[t][0] != items[t - 1][0] + 1:
            flags.append("no_target")
        else:
            target = items[t][0]
            text = items[t][1]
            kind = delimiter(text)
            if text == "":
                flags.append("head_detached_by_blank")
                target_kind = "blank"
            elif SECTION_TITLE.fullmatch(text) and ctx == "top":
                target_kind = "section"
            elif LINE_COMMENT.match(text):
                flags.append("target_is_comment")
                target_kind = "comment"
            elif kind:
                target_kind = "delimited:" + kind
                close = "```" if kind == "fenced" else text
                e = t + 1
                while e < n and items[e][1] != close:
                    e += 1
                statement = items[t + 1:e]
            else:
                target_kind = "paragraph"
                e = t
                while (e < n and items[e][1] not in ("", "+")
                       and (e == t or not (delimiter(items[e][1]) or ATTRIBUTE_LINE.fullmatch(items[e][1])))):
                    e += 1
                statement = items[t:e]
        if (entries is not None and before not in ("list", "verbatim")
                and (target_kind == "delimited:comment"
                     or (head_style == "comment" and target_kind in ("delimited:open", "paragraph")))):
            self.inert.append((no, "in_comment"))
            return
        above = items[i - 1][1] if i > 0 and items[i - 1][0] == no - 1 else None
        self.occurrences.append({
            "sid": sid, "line": no, "head_start": items[k][0], "target": target,
            "target_kind": target_kind, "context": ctx, "flags": flags, "above": above,
            "statement": None if statement is None else [text for _, text in statement],
            "statement_lines": None if not statement else [statement[0][0], statement[-1][0]],
        })


def anchor_value(line):
    if line is None:
        return None
    for rx in (BLOCK_ANCHOR, SHORTHAND_ANCHOR):
        m = rx.fullmatch(line)
        if m:
            return m.group(1)
    if DIRECTIVE.fullmatch(line):
        raise Undecided("a preprocessor directive stands where the derivation reads an anchor")
    if ATTRIBUTE_LINE.fullmatch(line):
        try:
            entries = attribute_entries(line[1:-1])
        except ValueError:
            if OTHER_ID.match(line):
                raise Undecided("an identifier is written in a form that the rules do not name: %s" % line)
            return None
        for idx, (name, val, quote) in enumerate(entries):
            if name == "id" or (idx == 0 and name is None and quote is None and "#" in val):
                raise Undecided("an identifier is written in a form that the rules do not name: %s" % line)
    return None


def scan_doubts(scan, sid):
    unsure = [o for o in scan.occurrences if o["sid"] is None or "{" in o["sid"]]
    relevant = unsure or any(sid in line for line in scan.lines)
    doubts = ["line %d: %s" % (no, code) for no, code in scan.notes
              if code == "single_line_conditional" or (code in STRUCTURAL_NOTES and relevant)]
    for o in scan.occurrences:
        if any(f in DOUBTFUL_FLAGS for f in o["flags"]):
            if o in unsure or o["sid"] == sid or sid in scan.lines[o["line"] - 1]:
                doubts.append("line %d: an occurrence with %s" % (o["line"], ",".join(o["flags"])))
    for no, code in scan.notes:
        if code in CELL_NOTES and sid in scan.lines[no - 1]:
            doubts.append("line %d: %s" % (no, code))
    return doubts


def derive_anchor(scan, occ):
    lines = scan.lines
    above = occ["above"]
    value = anchor_value(above)
    if value is not None:
        return value, "first"
    if occ["target_kind"] == "section" or occ["context"] != "top":
        return None, None
    titles = [t for t in scan.titles if t.line < occ["head_start"]]
    if not titles:
        return None, None
    title = titles[-1]
    if title.level == 0:
        return None, None
    value = anchor_value(title.above)
    if value is None:
        return None, None
    for no in range(title.line + 1, occ["head_start"]):
        ctx, kind = scan.kinds.get(no, (None, None))
        if kind == "directive":
            raise Undecided("a preprocessor directive stands between the section title and the item")
        if kind in ("blank", "comment", "attribute_entry"):
            continue
        if kind in ("delimiter", "verbatim") and comment_block_between(scan, no):
            continue
        return None, None
    later = [t for t in scan.titles if t.line > title.line]
    end = later[0].line if later else len(lines) + 1
    body = [o for o in scan.occurrences if title.line < o["line"] < end]
    if any(o is not occ and o["target_kind"] == "section" for o in body):
        raise Undecided("an item that heads a later section stands in this section's own body")
    if len(body) != 1:
        return None, None
    return value, "second"


def comment_block_between(scan, no):
    ctx, kind = scan.kinds.get(no, (None, None))
    if kind == "delimiter":
        return scan.lines[no - 1].startswith("////")
    k = no
    while k > 0 and scan.kinds.get(k, (None, None))[1] == "verbatim":
        k -= 1
    return k > 0 and scan.lines[k - 1].startswith("////")


def service_version_of(path):
    m = SERVICE_VERSION.match(path)
    return "%s/%s" % (m.group(1), m.group(2)) if m else None


def canonical_path(path):
    if path == "" or path.startswith("/"):
        return False
    return all(segment not in ("", ".", "..") for segment in path.split("/"))


def under_conformance(path):
    return path.split("/")[0] == "conformance"


def is_asciidoc_path(path):
    return path.endswith(".adoc")


def git_run(git_dir, *args):
    env = dict(os.environ)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(name, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    return subprocess.run(["git", "--git-dir=" + git_dir, "--no-replace-objects"] + list(args),
                          capture_output=True, env=env, stdin=subprocess.DEVNULL)


class Tree:
    def __init__(self, commit, source):
        self.commit = commit
        self.source = source
        self.scans = {}

    def scan(self, path):
        if path not in self.scans:
            try:
                text = self.data(path).decode("utf-8")
            except UnicodeDecodeError:
                raise Undecided("%s at %s is not UTF-8 text" % (path, self.commit))
            self.scans[path] = Scan(text)
        return self.scans[path]


class GitTree(Tree):
    def __init__(self, git_dir, commit, shown):
        Tree.__init__(self, commit, "git directory %s" % shown)
        self.git_dir = git_dir
        r = git_run(git_dir, "rev-parse", "--verify", "--quiet", commit + "^{commit}")
        if r.returncode != 0 or r.stdout.decode("ascii", "replace").strip() != commit:
            raise KeyError(commit)
        r = git_run(git_dir, "ls-tree", "-r", "-z", "--full-tree", commit)
        if r.returncode != 0:
            raise Unsupported("git ls-tree failed for %s" % commit)
        self.entries = {}
        for rec in r.stdout.split(b"\0"):
            if not rec:
                continue
            meta, path = rec.split(b"\t", 1)
            mode, kind, oid = meta.decode("ascii").split(" ")
            self.entries[path.decode("utf-8")] = (mode, kind, oid)

    def kind(self, path):
        e = self.entries.get(path)
        if e is None:
            return None
        if e[1] == "blob" and e[0] in ("100644", "100755"):
            return "file"
        return "link" if e[0] == "120000" else "other"

    def paths(self):
        return sorted(self.entries)

    def data(self, path):
        r = git_run(self.git_dir, "cat-file", "blob", self.entries[path][2])
        if r.returncode != 0:
            raise Unsupported("git cat-file failed for %s at %s" % (path, self.commit))
        return r.stdout


class DirTree(Tree):
    def __init__(self, root, commit, shown):
        Tree.__init__(self, commit, "checkout %s" % shown)
        self.root = root
        self.entries = {}
        for dirpath, dirnames, filenames in os.walk(root):
            rel = os.path.relpath(dirpath, root)
            prefix = "" if rel == "." else rel.replace(os.sep, "/") + "/"
            if prefix == "":
                dirnames[:] = [d for d in dirnames if d != ".git"]
            for d in list(dirnames):
                if os.path.islink(os.path.join(dirpath, d)):
                    self.entries[prefix + d] = "link"
                    dirnames.remove(d)
            for f in filenames:
                full = os.path.join(dirpath, f)
                self.entries[prefix + f] = "link" if os.path.islink(full) else ("file" if os.path.isfile(full) else "other")

    def kind(self, path):
        return self.entries.get(path)

    def paths(self):
        return sorted(self.entries)

    def data(self, path):
        with open(os.path.join(self.root, *path.split("/")), "rb") as fh:
            return fh.read()


class FixtureTree(Tree):
    def __init__(self, files, commit, where):
        Tree.__init__(self, commit, "fixture tree %s" % where)
        self.files = files

    def kind(self, path):
        return "file" if path in self.files else None

    def paths(self):
        return sorted(self.files)

    def data(self, path):
        return self.files[path].encode("utf-8")


class Pins:
    def __init__(self, git_dir, checkouts):
        self.git_dir = git_dir
        self.checkouts = checkouts
        self.cache = {}
        self.shown = {}

    def tree(self, commit, fixture_trees):
        if commit in fixture_trees:
            return fixture_trees[commit]
        if commit not in self.cache:
            tree = None
            if commit in self.checkouts:
                tree = DirTree(os.path.abspath(self.checkouts[commit]), commit, self.checkouts[commit])
            elif self.git_dir:
                try:
                    tree = GitTree(os.path.abspath(self.git_dir), commit, self.git_dir)
                except KeyError:
                    tree = None
            self.cache[commit] = tree
        return self.cache[commit]


def sid_of(subject):
    return "%s~%d" % (subject["requirement_id"], exact_int(subject["requirement_revision"]))


def resolve_v1(tree, subject):
    sid = sid_of(subject)
    found = []
    for path in tree.paths():
        if not is_asciidoc_path(path) or under_conformance(path) or tree.kind(path) != "file":
            continue
        scan = tree.scan(path)
        doubts = scan_doubts(scan, sid)
        if doubts:
            raise Undecided("%s at %s: %s" % (path, tree.commit, "; ".join(doubts)))
        for ordinal, occ in enumerate([o for o in scan.occurrences if o["sid"] == sid], 1):
            found.append((path, ordinal, occ))
    result = {"occurrences": [{"source_path": p, "ordinal": k, "line": o["line"]} for p, k, o in found]}
    if len(found) != 1:
        result.update(resolution="fail", reasons=["ambiguous" if found else "unresolvable"])
        return result
    path, ordinal, occ = found[0]
    anchor, form = derive_anchor(tree.scan(path), occ)
    result.update(resolution="pass", reasons=[], located_line=occ["line"], anchor_form=form, statement=occ["statement"],
                  derived_occurrence={"source_path": path, "ordinal": ordinal, "anchor": anchor,
                                      "service_version": service_version_of(path)})
    return result


def resolve_v2(tree, subject):
    sid = sid_of(subject)
    occ = subject["requirement_occurrence"]
    path = occ["source_path"]
    if not canonical_path(path):
        return {"resolution": "fail", "reasons": ["source_path_not_canonical"]}
    reasons = []
    result = {}
    if under_conformance(path):
        reasons.append("source_path_under_conformance")
    elif tree.kind(path) != "file":
        reasons.append("source_path_absent")
    elif not is_asciidoc_path(path):
        result["occurrences_in_file"] = 0
        reasons.append("ordinal_absent")
    else:
        scan = tree.scan(path)
        doubts = scan_doubts(scan, sid)
        if doubts:
            raise Undecided("%s at %s: %s" % (path, tree.commit, "; ".join(doubts)))
        same = [o for o in scan.occurrences if o["sid"] == sid]
        result["occurrences_in_file"] = len(same)
        if num_cmp(occ["ordinal"], len(same)) > 0:
            reasons.append("ordinal_absent")
        else:
            target = same[exact_int(occ["ordinal"]) - 1]
            anchor, form = derive_anchor(scan, target)
            result.update(located_line=target["line"], anchor_form=form, derived_anchor=anchor, statement=target["statement"])
            if not json_equal(occ["anchor"], anchor):
                reasons.append("anchor_mismatch")
    result["derived_service_version"] = service_version_of(path)
    if not json_equal(occ["service_version"], result["derived_service_version"]):
        reasons.append("service_version_mismatch")
    result.update(resolution="fail" if reasons else "pass", reasons=reasons)
    return result


def set_math_equal(a, b):
    if len(a) != len(b):
        return False
    used = set()
    for x in a:
        matched = None
        for k, y in enumerate(b):
            if k not in used and json_equal(x, y):
                matched = k
                break
        if matched is None:
            return False
        used.add(matched)
    return True


def math_equal_records(a, b):
    if a.keys() != b.keys():
        return False
    for k in a:
        if k == "subject":
            sa, sb = a[k], b[k]
            if sa.keys() != sb.keys():
                return False
            for sk in sa:
                if sk in ("component_identities", "selected_functions"):
                    if not set_math_equal(sa[sk], sb[sk]):
                        return False
                elif not json_equal(sa[sk], sb[sk]):
                    return False
        elif not json_equal(a[k], b[k]):
            return False
    return True


def comparison_form(record):
    subject = record["subject"]
    comps = subject["component_identities"]
    components = [canonical(c) for c in comps]
    raw_dup = len(set(components)) != len(components)
    math_dup = any(json_equal(comps[i], comps[j]) for i in range(len(comps)) for j in range(i))
    if math_dup and not raw_dup:
        raise Undecided("whether duplicate component_identities differing only in number spelling are equal is not decided by the rules (Q-3e-4)")
    if raw_dup:
        return None
    copy = dict(record)
    copy["subject"] = dict(subject)
    copy["subject"]["component_identities"] = sorted(comps, key=canonical)
    copy["subject"]["selected_functions"] = sorted(subject["selected_functions"], key=canonical)
    return canonical(copy)


def identity_of(record):
    a = record["assessment"]
    return [a["producer_authority"], a["assessment_id"], exact_int(a["assessment_revision"])]


def loose_identity(data):
    try:
        document = strict_json(data)
        return identity_of(document["records"][0])
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, Unsupported):
        return None


CASE_MEMBERS = {"case", "subject", "required_outcome", "decided_by", "pins", "note", "steps", "catalogue", "index",
                "reading", "contrast", "observation", "trees"}
STEP_MEMBERS = {"submission", "provenance", "expect", "occurrence_equals_derived_of_step"}
KEPT_RECORD = "version_2_record"
KEPT_DOCUMENT = "version_1_document_with_derived_occurrence"
KEPT_REASON = "refused_submission_with_reason"
KEPT_PROVENANCE = "refused_submission_with_provenance"
NOT_AGAIN = "not_again_no_op"
NOT_STATED = "not_stated_by_the_rules"


class Catalogue:
    def __init__(self):
        self.entries = []

    def submit(self, step, name, data, provenance, schemas, pins, fixture_trees):
        entry = {"step": step, "submission": name, "sha256": sha256(data), "provenance": provenance,
                 "schema": None, "shape": "not reached", "resolution": "not reached",
                 "identity": "not reached", "outcome": None, "reasons": [], "kept": None}
        earlier = list(self.entries)
        self.entries.append(entry)
        entry["bytes"] = data
        try:
            document = strict_json(data)
        except (ValueError, UnicodeDecodeError) as exc:
            entry.update(shape="fail", outcome="refused", reasons=["unparseable"], errors=[str(exc)], kept=NOT_STATED)
            return entry
        version = schema_version_of(document.get("schema_version") if isinstance(document, dict) else None)
        if version is None:
            entry.update(shape="fail", outcome="refused", reasons=["schema_version_unknown"], kept=NOT_STATED)
            return entry
        entry["schema_version"] = version
        entry["schema"] = SCHEMA_FILES[version]
        errors = schemas[version].validate(document)
        if errors:
            entry.update(shape="fail", outcome="refused", reasons=["shape_invalid"], errors=errors, kept=NOT_STATED)
            return entry
        entry["shape"] = "pass"
        if len(document["records"]) != 1:
            raise Undecided("the submission %s holds %d records; the fixtures and these rules are written for one "
                            "record per submission" % (name, len(document["records"])))
        record = document["records"][0]
        subject = record["subject"]
        entry["spec_commit"] = subject["spec_commit"]
        entry["requirement"] = sid_of(subject)
        if version == 2:
            entry["submitted_occurrence"] = subject["requirement_occurrence"]
        tree = pins.tree(subject["spec_commit"], fixture_trees)
        if tree is None:
            raise Unsupported("the pin %s of %s is not available: give --git-dir or --checkout" % (subject["spec_commit"], name))
        entry["pin_source"] = tree.source
        result = resolve_v1(tree, subject) if version == 1 else resolve_v2(tree, subject)
        entry.update(result)
        if result["resolution"] == "fail":
            entry.update(outcome="refused", kept=KEPT_REASON if version == 1 else NOT_STATED)
            return entry
        form = comparison_form(record)
        if form is None:
            entry.update(identity="duplicate", outcome="refused", reasons=["duplicate_component_identity"], kept=NOT_STATED)
            return entry
        entry["form"] = form
        entry["record"] = record
        entry["comparison_form_sha256"] = sha256(form)
        key = identity_of(record)
        entry["assessment_identity"] = key
        admitted = [e for e in earlier if e["outcome"] == "admitted" and e["assessment_identity"] == key]
        if admitted:
            first = admitted[0]
            if first["form"] == form:
                entry.update(identity="no-op", outcome="no-op", kept=NOT_AGAIN, same_as_step=first["step"])
            elif math_equal_records(first["record"], record):
                raise Undecided("the outcome for %s turns on how equal numbers are written in the comparison form (Q-3e-4)" % name)
            else:
                entry.update(identity="conflict", outcome="refused", reasons=["conflict"], kept=KEPT_PROVENANCE,
                             conflicts_with_step=first["step"])
            return entry
        for e in earlier:
            if (e.get("assessment_identity") or loose_identity(e["bytes"])) == key:
                raise Undecided("the submission %s has the identity of step %d, which was not admitted; the rules do "
                                "not say whether a refused submission holds its identity" % (name, e["step"]))
        entry.update(identity="new", outcome="admitted", kept=KEPT_RECORD if version == 2 else KEPT_DOCUMENT)
        return entry

    def finish(self, case_dir):
        for e in self.entries:
            with open(os.path.join(case_dir, e["submission"]), "rb") as fh:
                e["stored_bytes_unchanged"] = sha256(fh.read()) == e["sha256"] == sha256(e["bytes"])

    def view(self):
        out = {"version_2_records": [], "version_1_documents": [], "kept_refused_submissions": [], "no_ops": [],
               "refused_keeping_not_stated": []}
        for e in self.entries:
            if e["kept"] == KEPT_RECORD:
                out["version_2_records"].append(e["step"])
            elif e["kept"] == KEPT_DOCUMENT:
                out["version_1_documents"].append(e["step"])
            elif e["kept"] in (KEPT_REASON, KEPT_PROVENANCE):
                out["kept_refused_submissions"].append(e["step"])
            elif e["kept"] == NOT_AGAIN:
                out["no_ops"].append(e["step"])
            else:
                out["refused_keeping_not_stated"].append(e["step"])
        return out


def public(entry):
    return {k: v for k, v in entry.items() if k not in ("bytes", "form", "record")}


def inside(base, rel):
    full = os.path.realpath(os.path.join(base, rel))
    return full if full.startswith(os.path.realpath(base) + os.sep) else None


def read_inside(case_dir, rel):
    full = inside(case_dir, rel)
    if full is None:
        raise Unsupported("%s lies outside its case directory" % rel)
    with open(full, "rb") as fh:
        return fh.read()


def load_fixture_trees(case, case_dir):
    trees = {}
    for commit, rel in case.get("trees", {}).items():
        if commit != ZERO_PIN:
            raise Unsupported("a fixture tree is allowed only for the 40-zero synthetic pin, not %r" % commit)
        spec = strict_json(read_inside(case_dir, rel))
        files = spec.get("files") if isinstance(spec, dict) else None
        if not isinstance(files, dict) or not all(isinstance(v, str) and canonical_path(k) for k, v in files.items()):
            raise Unsupported("the fixture tree %s is not {\"files\": {path: text}}" % rel)
        trees[commit] = FixtureTree(files, commit, rel)
    return trees


def compare(expected, actual, where, differences):
    for key, value in expected.items():
        if key not in actual:
            differences.append("%s: %s is expected as %s but not reported" % (where, key, dump_json(value)))
        elif not json_equal(value, actual[key]):
            differences.append("%s: %s is %s, expected %s" % (where, key, dump_json(actual[key]), dump_json(value)))


def check_index(spec, context, differences):
    with open(os.path.join(context["assessments"], "index.json"), "rb") as fh:
        raw = fh.read()
    document = strict_json(raw)
    result = {"file": "index.json", "sha256": sha256(raw), "schema": None, "shape": "fail"}
    v_int = schema_version_of(document.get("schema_version") if isinstance(document, dict) else None)
    if v_int is not None:
        result["schema_version"] = v_int
        result["schema"] = SCHEMA_FILES[v_int]
        errors = context["schemas"][v_int].validate(document)
        result["shape"] = "fail" if errors else "pass"
        if errors:
            result["errors"] = errors
    records = document.get("records") if isinstance(document, dict) else None
    result["records"] = len(records) if isinstance(records, list) else None
    counts = document.get("historical_intake_provenance", {}).get("historical_counts", {})
    result["unassessed_slots"] = counts.get("unassessed_implementation_evidence_slots")
    result["schema_json_sha256"] = context["schemas"][1].sha256
    pin = spec.get("schema_json_pin")
    if pin:
        tree = context["pins"].tree(pin, {})
        if tree is None:
            raise Unsupported("the pin %s is not available for the comparison of schema.json" % pin)
        name = "conformance/assessments/schema.json"
        result["schema_json_pin"] = pin
        result["schema_json_equals_pin"] = tree.kind(name) == "file" and sha256(tree.data(name)) == context["schemas"][1].sha256
    compare(spec["expect"], result, "index", differences)
    return result


def check_reading(spec, case_dir, catalogue, differences):
    entry = catalogue.entries[exact_int(spec["step"]) - 1]
    raw = read_inside(case_dir, spec["configuration"])
    configuration = strict_json(raw)
    record = strict_json(entry["bytes"])["records"][0]
    statement = entry.get("statement")
    result = {"configuration_digest_matches": record["subject"]["configuration_digest"] == "sha256:" + sha256(raw),
              "configured_value": configuration.get(spec["member"]),
              "clause": None if statement is None else "\n".join(statement)}
    result["clause_as_expected"] = result["clause"] == spec["clause"]
    value = result["configured_value"]
    relation = spec["bound"]["relation"]
    bound = spec["bound"]["seconds"]
    if relation not in ("at_least", "exactly"):
        raise Unsupported("the reading relation %r" % relation)
    if not is_number(value) or not result["clause_as_expected"] or not result["configuration_digest_matches"]:
        result["reading"] = "not applicable"
    elif relation == "at_least":
        result["reading"] = "within" if num_cmp(value, bound) >= 0 else "violates"
    else:
        result["reading"] = "within" if json_equal(value, bound) else "violates"
    result["standing"] = ("a documentary reading of the resolved clause, not an assessment: a pass still needs "
                          "evidence, provenance and authority")
    compare(spec["expect"], result, "reading", differences)
    return result


def check_contrast(spec, report, results, differences):
    other = results[spec["case"]]
    a = other["steps"][0]
    b = report["steps"][0]
    result = {"with": spec["case"],
              "same_pin_and_occurrence": (a.get("spec_commit") == b.get("spec_commit")
                                          and json_equal(a.get("submitted_occurrence"), b.get("submitted_occurrence"))),
              "same_clause": a.get("statement") == b.get("statement"),
              "readings": [other.get("reading", {}).get("reading"), report.get("reading", {}).get("reading")]}
    result["conclusion_transfers"] = result["same_pin_and_occurrence"] and result["same_clause"]
    compare(spec["expect"], result, "contrast", differences)
    return result


def check_observation(spec, case_dir, results, differences):
    document = strict_json(read_inside(case_dir, spec["file"]))
    configured = document.get("configured_value") if isinstance(document, dict) else None
    result = {"configured_value": configured, "decided_by": [], "decides": {}}
    for name in spec["against"]:
        other = results[name]
        if "reading" not in other:
            raise Unsupported("the observation is read against %s, which has no reading" % name)
        result["decides"][name] = "nothing: no configured value is known" if configured is None else "a configured value is known"
    compare(spec["expect"], result, "observation", differences)
    return result


def run_case(case_dir, case, context):
    differences = []
    fixture_trees = load_fixture_trees(case, case_dir)
    catalogue = Catalogue()
    report = {"case": case["case"], "fixture": os.path.basename(case_dir), "subject": case.get("subject"),
              "required_outcome": case.get("required_outcome"), "decided_by": case.get("decided_by")}
    unknown = set(case) - CASE_MEMBERS
    if unknown:
        raise Unsupported("case.json of %s has the unknown members %s" % (case.get("case"), ", ".join(sorted(unknown))))
    steps = case.get("steps", [])
    for number, step in enumerate(steps, 1):
        unknown = set(step) - STEP_MEMBERS
        if unknown or "expect" not in step or "submission" not in step:
            raise Unsupported("step %d of %s has the members %s" % (number, case.get("case"), ", ".join(sorted(step))))
        data = read_inside(case_dir, step["submission"])
        entry = catalogue.submit(number, step["submission"], data, step.get("provenance"), context["schemas"],
                                 context["pins"], fixture_trees)
        if "occurrence_equals_derived_of_step" in step:
            other = catalogue.entries[exact_int(step["occurrence_equals_derived_of_step"]) - 1]
            entry["occurrence_equals_derived_of_step"] = json_equal(entry.get("submitted_occurrence"), other.get("derived_occurrence"))
    catalogue.finish(case_dir)
    for number, (step, entry) in enumerate(zip(steps, catalogue.entries), 1):
        compare(step["expect"], entry, "step %d" % number, differences)
        if not entry["stored_bytes_unchanged"]:
            differences.append("step %d: the stored bytes changed" % number)
    report["steps"] = [public(e) for e in catalogue.entries]
    report["catalogue"] = catalogue.view()
    if "catalogue" in case:
        compare(case["catalogue"], report["catalogue"], "catalogue", differences)
    if "index" in case:
        report["index"] = check_index(case["index"], context, differences)
    if "reading" in case:
        report["reading"] = check_reading(case["reading"], case_dir, catalogue, differences)
    if "contrast" in case:
        report["contrast"] = check_contrast(case["contrast"], report, context["results"], differences)
    if "observation" in case:
        report["observation"] = check_observation(case["observation"], case_dir, context["results"], differences)
    report["differences"] = differences
    report["status"] = "as stated" if not differences else "differs"
    return report


HELP = """
The three kinds of check (README.md, "Three kinds of check")
  shape        the JSON Schema that the document's schema_version selects: 1 selects schema.json,
               2 selects schema.v2.json, and any other value is refused (README.md, "Shape rules")
  resolution   the written resolution rules, against the specification files at the subject's own
               spec_commit (README.md, "Resolution rules")
  identity     the written import rules, against the submissions already kept in the same fixture
               (README.md, "Import rules")
  This checker runs shape, then resolution, then identity, with short-circuit: a refusal gives the
  reasons of the kind that refused it, and the later kinds are "not reached". That order is the
  checker's own; which reason or keeping rule governs a submission that fails more than one kind is
  open (Q-3e-1).

Pins
  A pin is a full 40-character commit ID. The files of a pin are read, for the 40-zero synthetic
  pin only, from the tree that the fixture carries for it (a fixture tree for any other pin is
  refused as unsupported), else from a --checkout given for it, else from --git-dir. A Git
  directory is read
  with git rev-parse, git ls-tree and git cat-file only, with GIT_NO_LAZY_FETCH=1 so a promisor
  remote triggers no network fetch. A --checkout COMMIT=DIR directory is trusted as labelled; the
  checker does not verify its contents against Git. A pin that none of them holds is reported as
  unsupported.

Fixtures (--fixtures; by default fixtures/ next to this file)
  One directory per case, AS01 to AS19, each with case.json and the files that it names. case.json
  has these members:
    case          the case's name in the plan's table, AS1 to AS19
    subject, required_outcome, decided_by
                  the case as stated, for the reader
    steps         the submissions in the order received. Each step names its submission (the
                  producer's bytes: a document of the index shape with one record) and its
                  provenance, and gives in expect the members of the step's result that the rules
                  decide
    catalogue     the kept set after the last step, as lists of step numbers: version_2_records,
                  version_1_documents, kept_refused_submissions, no_ops, refused_keeping_not_stated
    index         check index.json itself, and compare schema.json with its blob at a pin
    reading       a documentary reading of the resolved clause against a configuration file whose
                  SHA-256 is the record's configuration_digest; the clause text is compared exactly
    contrast      compare this case's pin, occurrence, clause and reading with another case's
    observation   an observation with no configured value, read against other cases' readings
    trees         {commit: file}: a synthetic tree, {"files": {path: text}}, for a pin that names no
                  commit (40 zeros), where no pin of the repository has the case's construct; it puts
                  no AsciiDoc file into the repository
  A step's result has: schema, shape, resolution, identity, outcome (admitted, no-op or refused),
  reasons, kept, sha256 (of the producer's bytes) and stored_bytes_unchanged; and, where they apply,
  occurrences, derived_occurrence (version 1), submitted_occurrence, occurrences_in_file,
  derived_anchor, derived_service_version (version 2), located_line, anchor_form (first, second or
  null), statement, assessment_identity, comparison_form_sha256, same_as_step, conflicts_with_step
  and errors.

Derived data
  The occurrence derived for an admitted version-1 record is reported beside the kept submission,
  as derived_occurrence of its step; it is never written into the submission. Kept submissions are
  the producer's bytes: each step gives their SHA-256, and every file is read again at the end to
  show that it is unchanged. Version-1 documents and version-2 records are listed apart in each
  case's catalogue. kept is one of version_2_record, version_1_document_with_derived_occurrence,
  refused_submission_with_reason (README.md, I4), refused_submission_with_provenance (I8),
  not_again_no_op (I8), and not_stated_by_the_rules for a refusal whose keeping the rules leave
  open. A submission whose identity is that of an earlier submission that was not admitted is
  reported as undecided. The comparison form does not normalize JSON number spellings: where an
  outcome (such as no-op versus conflict on 1 against 1.0) would turn on how equal numbers are
  written, the checker stops as undecided (Q-3e-4).

Reasons
  shape        unparseable, schema_version_unknown, shape_invalid
  resolution   ambiguous, unresolvable (version 1); source_path_not_canonical,
               source_path_under_conformance, source_path_absent, ordinal_absent, anchor_mismatch,
               service_version_mismatch (version 2)
  identity     duplicate_component_identity, conflict

Schema keywords
  Shape is checked by this file's own validator, for the subset of JSON Schema 2020-12 that
  schema.json and schema.v2.json use: type, properties, required, additionalProperties (true or
  false), const, enum, pattern, minLength, items (one schema), $ref (#/$defs/<name>) with $defs,
  oneOf, allOf, not, if with then, minimum, minItems, maxItems and uniqueItems; $schema, $id, title
  and description are annotations. Local #/$defs/<name> references must be acyclic; a schema with
  any other keyword, another form of these, or a cyclic $ref is refused as unsupported before any
  case runs. A pattern is ECMA-262 restricted to literals,
  character classes, \\d, groups, alternation, the quantifiers ? * + {n} {n,} {n,m} and the anchors
  ^ and $, and is searched for, not anchored; other pattern syntax is refused. Numbers are parsed
  as exact decimal values (no binary floating-point rounding): a number is an integer only when its
  exact fractional part is zero, equality is exact JSON equality, minLength counts code points, and
  a document with a duplicate object member is unparseable. Valid JSON numbers whose digit count or
  exact integer expansion exceeds the host numeric conversion limit (such as Python's
  int_max_str_digits) or the exact-integer exponent bound are reported as unsupported (exit 2), not
  as unparseable.

Occurrences and anchors
  An occurrence is a block attribute line of an AsciiDoc file (a name ending in .adoc) whose
  oft-sid attribute has exactly the value <requirement_id>~<requirement_revision>, outside
  verbatim, passthrough and comment blocks (including comment-styled open blocks and paragraphs
  headed by [comment] or [comment.specitem,...], and //// targets) and outside plain table cells.
  Block attribute lists accept ASCII spaces and horizontal tabs around commas, =, and entry
  boundaries. The checker reads the
  block structure itself: delimited blocks to their first closing line, AsciiDoc table cells,
  paragraphs that a block attribute line ends, line comments and atx section titles. The anchor
  derivation reads the line directly above the attribute line within the same block or AsciiDoc
  table cell (first form; never across a cell boundary), else the line directly above the section
  title (level 1 or deeper, ==..====== / ##..######; a level-0 document title is not a section
  title) whose own body holds the item (second form). Both version-1 and version-2 resolution use
  the same .adoc file test. Where a file has a construct that the checker does not read (an
  include, a conditional region, a single-line conditional other than [source,...] directly before
  a ---- listing delimiter, an unterminated block, an underlined section title, an oft-sid that is
  single-quoted, holds an attribute reference or stands in list item text, or an identifier written
  in a form that the anchor derivation does not name, such as [id=x], [id="x"] or [#id.role]), it
  reports the case as undecided instead of deciding it.

Exit status
  0 every case is as stated; 1 a case differs; 2 an unsupported schema, pin or construct, a case
  that the rules do not decide, or a usage error.
"""


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -I -B check_assessments.py",
        description="Apply schema dispatch, resolution and the identity rules of this directory's README to the\n"
                    "documentary fixtures AS1 to AS19, against the specification files at each fixture's pin,\n"
                    "and report each fixture's outcome as JSON on standard output. It opens no file for writing,\n"
                    "uses no network, imports no real assessment and qualifies nothing.",
        epilog=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--git-dir", metavar="DIR", help="a Git directory that holds the pins, read-only")
    parser.add_argument("--checkout", metavar="COMMIT=DIR", action="append", default=[],
                        help="an exported checkout of the full commit ID COMMIT (repeatable; trusted as labelled)")
    parser.add_argument("--fixtures", metavar="DIR", default=os.path.join(HERE, "fixtures"),
                        help="the fixture directory (default: fixtures/ next to this file)")
    parser.add_argument("--assessments", metavar="DIR", default=HERE,
                        help="the directory of schema.json, schema.v2.json and index.json (default: this file's)")
    parser.add_argument("--case", metavar="NAME", action="append", default=[],
                        help="run only this case, AS1 or AS01 (repeatable); the cases that it refers to run too")
    parser.add_argument("--text", action="store_true", help="print one line per case and step instead of JSON")
    args = parser.parse_args(argv)
    checkouts = {}
    for spec in args.checkout:
        commit, sep, directory = spec.partition("=")
        if not sep or not COMMIT.fullmatch(commit) or not os.path.isdir(directory):
            parser.error("--checkout needs COMMIT=DIR, with a full commit ID and a directory: %s" % spec)
        checkouts[commit] = directory
    report = {"checker": "check_assessments.py", "opens_for_writing": "nothing", "network": "none",
              "imports": "no real assessment", "qualifies": "nothing"}
    code = 2
    try:
        schemas = {}
        for version, name in SCHEMA_FILES.items():
            with open(os.path.join(args.assessments, name), "rb") as fh:
                schemas[version] = Schema(name, fh.read())
        if schemas[1].root.get("$id") == schemas[2].root.get("$id"):
            raise Unsupported("schema.json and schema.v2.json share one $id")
        report["schemas"] = {name: {"sha256": schemas[v].sha256, "$id": schemas[v].root.get("$id"),
                                    "keywords": sorted(schemas[v].keywords)} for v, name in SCHEMA_FILES.items()}
        cases = {}
        for d in sorted(os.listdir(args.fixtures)):
            path = os.path.join(args.fixtures, d, "case.json")
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    cases[d] = strict_json(fh.read())
        by_name = {case["case"]: d for d, case in cases.items()}
        wanted = set()
        for name in args.case or sorted(cases):
            d = name if name in cases else by_name.get(name)
            if d is None:
                parser.error("no such case: %s" % name)
            wanted.add(d)
        run = set(wanted)
        while True:
            more = set()
            for d in run:
                refs = [cases[d].get("contrast", {}).get("case")] + cases[d].get("observation", {}).get("against", [])
                for r in refs:
                    if r and r not in by_name:
                        raise Unsupported("%s refers to the case %s, which has no fixture" % (d, r))
                    if r:
                        more.add(by_name[r])
            if more <= run:
                break
            run |= more
        context = {"schemas": schemas, "pins": Pins(args.git_dir, checkouts),
                   "assessments": args.assessments, "results": {}}
        report["cases"] = []
        for d in sorted(run):
            result = run_case(os.path.join(args.fixtures, d), cases[d], context)
            context["results"][result["case"]] = result
            report["cases"].append(result)
        statuses = [r["status"] for r in report["cases"]]
        report["summary"] = {"cases": len(statuses), "as_stated": statuses.count("as stated"),
                             "differ": statuses.count("differs")}
        code = 0 if report["summary"]["differ"] == 0 else 1
    except (Unsupported, Undecided) as exc:
        report["stopped"] = "%s: %s" % ("undecided" if isinstance(exc, Undecided) else "unsupported", exc)
        print("check_assessments: %s" % report["stopped"], file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["stopped"] = "error: %s: %s" % (type(exc).__name__, exc)
        print("check_assessments: %s" % report["stopped"], file=sys.stderr)
    if args.text:
        for r in report.get("cases", []):
            print("%s (%s): %s" % (r["case"], r["fixture"], r["status"]))
            for e in r["steps"]:
                print("  step %d %s: shape %s, resolution %s, identity %s; %s %s; kept %s" % (
                    e["step"], e["submission"], e["shape"], e["resolution"], e["identity"], e["outcome"],
                    ",".join(e["reasons"]) or "-", e["kept"]))
            for d in r["differences"]:
                print("  differs: %s" % d)
        print(report.get("stopped") or "summary: %s" % json.dumps(report["summary"]))
    else:
        sys.stdout.write(dump_json(report, indent=1) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
