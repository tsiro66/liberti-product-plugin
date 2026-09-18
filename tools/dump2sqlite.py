#!/usr/bin/env python3
"""Convert the phpMyAdmin MariaDB dump to a SQLite copy for local analysis/testing.

Usage:  python3 tools/dump2sqlite.py [output_path]
Default output: local/vm_analysis.db (git-ignored).

Handles: backtick identifiers, ON UPDATE CURRENT_TIMESTAMP, COMMENT clauses,
KEY/CONSTRAINT lines, MySQL escapes in string literals, multi-row INSERTs,
enum()/set() types, CURRENT_TIMESTAMP() defaults.

NOTE: PRIMARY KEY / UNIQUE constraints are NOT carried over (join tables get a
rowid); tests that exercise AUTO_INCREMENT-style ids rebuild the relevant
tables with INTEGER PRIMARY KEY (see tests/conftest.py pattern).
"""
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP = ROOT / "support_antima_.sql"
DEFAULT_OUT = ROOT / "local" / "vm_analysis.db"


def tokenize_values(s):
    vals, i, n = [], 0, len(s)
    while i < n:
        while i < n and s[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        c = s[i]
        if c == "'":
            i += 1
            buf = []
            while i < n:
                ch = s[i]
                if ch == "\\" and i + 1 < n:
                    nxt = s[i + 1]
                    i += 2
                    esc = {"n": "\n", "r": "\r", "t": "\t", "0": "\x00", "\\": "\\",
                           "'": "'", '"': '"', "%": "%", "_": "_", "Z": "\x1a"}
                    buf.append(esc.get(nxt, nxt))
                elif ch == "'":
                    if i + 1 < n and s[i + 1] == "'":
                        buf.append("'")
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    buf.append(ch)
                    i += 1
            vals.append("".join(buf))
        else:
            j = i
            while j < n and s[j] not in ",":
                j += 1
            tok = s[i:j].strip()
            i = j
            if tok.upper() == "NULL":
                vals.append(None)
            else:
                vals.append(tok)
    return vals


def parse_insert_payload(payload):
    rows, buf, depth, in_str = [], [], 0, False
    esc = False
    for ch in payload:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "'":
                in_str = False
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            if depth == 1:
                buf = []
            else:
                buf.append(ch)
        elif ch == ")":
            depth -= 1
            if depth == 0:
                rows.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        else:
            if depth >= 1:
                buf.append(ch)
    return [tokenize_values(r) for r in rows if r.strip()]


def conv_col(line):
    line = line.strip().rstrip(",")
    line = re.sub(r"\s*ON UPDATE CURRENT_TIMESTAMP(\(\))?", "", line, flags=re.I)
    line = re.sub(r"\s*COMMENT\s+'(?:[^'\\]|\\.)*'", "", line, flags=re.I)
    line = re.sub(r"current_timestamp\(\)", "CURRENT_TIMESTAMP", line, flags=re.I)
    line = re.sub(r"(?:enum|set)\s*\([^)]*\)", "TEXT", line, flags=re.I)
    line = re.sub(r"\s*(CHARACTER SET|CHARSET)\s+\w+", "", line, flags=re.I)
    line = re.sub(r"\s*COLLATE\s+\w+", "", line, flags=re.I)
    line = re.sub(r"\)\s*unsigned", ")", line, flags=re.I)
    return line


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    src = DUMP.read_text(encoding="utf-8", errors="replace")

    con = sqlite3.connect(out)
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=OFF")
    cur.execute("PRAGMA synchronous=OFF")

    n_tables = 0
    for m in re.finditer(r"CREATE TABLE `([^`]+)` \((.*?)\n\) ENGINE=[^;]*;", src, re.S):
        tbl, body = m.group(1), m.group(2)
        cols = []
        for line in body.split("\n"):
            ls = line.strip()
            if not ls:
                continue
            if re.match(r"^(PRIMARY|UNIQUE|KEY|CONSTRAINT|INDEX|FULLTEXT|SPATIAL|FOREIGN)\b", ls, re.I):
                continue
            mm = re.match(r"`([^`]+)`\s+(.*)", ls)
            if mm:
                cols.append((mm.group(1), conv_col(mm.group(2))))
        defs = [f'"{col}" {extra}' for col, extra in cols]
        try:
            cur.execute(f'CREATE TABLE IF NOT EXISTS "{tbl}" (\n' + ",\n".join(defs) + "\n)")
            n_tables += 1
        except Exception as e:
            print(f"CREATE FAIL {tbl}: {e}", file=sys.stderr)
    con.commit()

    n_rows = 0
    for m in re.finditer(r"INSERT INTO `([^`]+)` \(([^)]*)\) VALUES\n(.*?);\n", src, re.S):
        tbl, collist, payload = m.group(1), m.group(2), m.group(3)
        cols = re.findall(r"`([^`]+)`", collist)
        rows = parse_insert_payload(payload)
        if not rows:
            continue
        ph = ",".join("?" * len(cols))
        try:
            cur.executemany(
                f'INSERT INTO "{tbl}" ({",".join(chr(34)+c+chr(34) for c in cols)}) VALUES ({ph})',
                rows,
            )
            n_rows += len(rows)
        except Exception as e:
            print(f"INSERT FAIL {tbl}: {e}", file=sys.stderr)
    con.commit()
    con.close()
    print(f"converted {n_tables} tables, {n_rows} rows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
