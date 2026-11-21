#!/usr/bin/env python3
"""UI dictionary (spreadsheet) -> WS/i18n/texts.json, the single text source of the web pages.

    python UHA/tools/dict_to_texts.py [WS/i18n/uha_ui_dict.xlsx] [WS/i18n/texts.json]

Reads the xlsx with the standard library only (an xlsx is a zip of XML files; no openpyxl needed) and finds the
columns by their header names, not by letters, so columns may be moved or added. Sheets:
    UI texty         Klíč | CZ | EN                                  -> "ui":    {key: {cz, en}}
    Proměnné YAML    Klíč (YAML) | CZ | EN | CZ krátce | EN krátce   -> "vars":  {NAME: {cz, en, cz_short, en_short}}
    Příkazy YAML     Klíč (YAML) | CZ | EN                           -> "cmds":  {NAME: {cz, en}}
    Enumy YAML       Enum | Hodnota | Aktuálně | CZ | EN             -> "enums": {Enum: {value: {name, cz, en}}}
                                                                        (name = the item name in the YAML; uha2.json
                                                                         sends only that, the page looks it up)
An empty cell falls back to the other language, then to the key (short names fall back to the full names).
Rows without a key are skipped. Output keys keep the sheet order.

"var_enums": {VARIABLE: Enum} comes from uha_vars.yaml (UHA_FW repo, default ../UHA_FW/UHA_COMMON/VarDefs/, or the
env UHA_VARS_YAML; needs PyYAML): the same item name can mean different things in two enums ("None"), so the page
needs to know which enum a variable uses. Without the YAML the previous var_enums of texts.json are kept.

Texts the pages need but the dictionary does not have yet live in texts_pending.json next to the output (same
layout, usually only "ui"). They are merged in, the dictionary wins; the script lists the pending keys that are now
in the dictionary (delete them from texts_pending.json) and the ones still missing there.
"""
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN = os.path.join(HERE, "..", "..", "WS", "i18n", "uha_ui_dict.xlsx")
DEFAULT_OUT = os.path.join(HERE, "..", "..", "WS", "i18n", "texts.json")
DEFAULT_YAML = os.path.join(HERE, "..", "..", "..", "UHA_FW", "UHA_COMMON", "VarDefs", "uha_vars.yaml")


def _col(ref: str) -> int:
    """'C12' -> 2 (zero based column)."""
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path: str) -> dict:
    """{sheet name: [[cell text, ...], ...]} with every cell as a stripped string ('' when empty)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(M + "si"):
                shared.append("".join(t.text or "" for t in si.iter(M + "t")))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).find(M + "sheets"):
            target = rels[sheet.get(R + "id")].lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            rows = []
            for row in ET.fromstring(z.read(target)).find(M + "sheetData").findall(M + "row"):
                cells = {}
                for c in row.findall(M + "c"):
                    kind, v = c.get("t"), c.find(M + "v")
                    if kind == "s" and v is not None:
                        text = shared[int(v.text)]
                    elif kind == "inlineStr":
                        text = "".join(t.text or "" for t in c.iter(M + "t"))
                    elif v is not None and v.text is not None:
                        text = v.text
                        if re.fullmatch(r"-?\d+\.0", text):        # whole numbers stored as floats
                            text = text[:-2]
                    else:
                        text = ""
                    cells[_col(c.get("r"))] = text.strip()
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
            sheets[sheet.get("name")] = rows
        return sheets


def table(rows: list, sheet: str) -> list:
    """Rows as dicts keyed by the header names of the first row."""
    if not rows:
        raise SystemExit(f"sheet '{sheet}' is empty")
    head = rows[0]
    return [{h: (r[i] if i < len(r) else "") for i, h in enumerate(head) if h} for r in rows[1:]]


def need(sheets: dict, name: str, columns: list) -> list:
    if name not in sheets:
        raise SystemExit(f"sheet '{name}' not found (sheets: {', '.join(sheets)})")
    rows = table(sheets[name], name)
    head = set(sheets[name][0])
    missing = [c for c in columns if c not in head]
    if missing:
        raise SystemExit(f"sheet '{name}': missing column(s) {', '.join(missing)}")
    return rows


def pair(cz: str, en: str, key: str) -> dict:
    return {"cz": cz or en or key, "en": en or cz or key}


def convert(sheets: dict) -> dict:
    out = {"ui": {}, "vars": {}, "cmds": {}, "enums": {}}
    for r in need(sheets, "UI texty", ["Klíč", "CZ", "EN"]):
        if r["Klíč"]:
            out["ui"][r["Klíč"]] = pair(r["CZ"], r["EN"], r["Klíč"])
    for r in need(sheets, "Proměnné YAML", ["Klíč (YAML)", "CZ", "EN", "CZ krátce", "EN krátce"]):
        key = r["Klíč (YAML)"]
        if key:
            full = pair(r["CZ"], r["EN"], key)
            out["vars"][key] = {**full, "cz_short": r["CZ krátce"] or r["EN krátce"] or full["cz"],
                                "en_short": r["EN krátce"] or r["CZ krátce"] or full["en"]}
    for r in need(sheets, "Příkazy YAML", ["Klíč (YAML)", "CZ", "EN"]):
        if r["Klíč (YAML)"]:
            out["cmds"][r["Klíč (YAML)"]] = pair(r["CZ"], r["EN"], r["Klíč (YAML)"])
    for r in need(sheets, "Enumy YAML", ["Enum", "Hodnota", "Aktuálně", "CZ", "EN"]):
        if r["Enum"] and r["Hodnota"] != "":
            name = r["Aktuálně"] or r["Hodnota"]
            out["enums"].setdefault(r["Enum"], {})[r["Hodnota"]] = {"name": name, **pair(r["CZ"], r["EN"], name)}
    return out


def merge_pending(texts: dict, path: str) -> None:
    """Add the keys of texts_pending.json that the dictionary does not have (the dictionary wins)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        pending = json.load(f)
    done, waiting = [], []
    for section, entries in pending.items():
        if section.startswith("_"):
            continue
        for key, value in entries.items():
            if key in texts.setdefault(section, {}):
                done.append(key)
            else:
                texts[section][key] = value
                waiting.append(key)
    if done:
        print(f"now in the dictionary, delete from {os.path.basename(path)}: {', '.join(done)}")
    if waiting:
        print(f"{len(waiting)} texts only in {os.path.basename(path)} (add them to the dictionary): {', '.join(waiting)}")


def var_enums(path: str) -> dict:
    """{variable name: enum name} for every enum variable of uha_vars.yaml (searched at any depth)."""
    import yaml                                   # PyYAML, only needed here
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    found = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "enum" and isinstance(node.get("name"), str) and node.get("enum"):
                found[node["name"]] = str(node["enum"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data.get("groups"))
    return found


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN
    dst = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    texts = convert(read_xlsx(src))
    merge_pending(texts, os.path.join(os.path.dirname(os.path.abspath(dst)), "texts_pending.json"))
    yaml_path = os.environ.get("UHA_VARS_YAML", DEFAULT_YAML)
    if os.path.exists(yaml_path):
        texts["var_enums"] = var_enums(yaml_path)
        unknown = sorted(set(texts["var_enums"].values()) - set(texts["enums"]))
        if unknown:
            print(f"enums used in the YAML but not in the dictionary: {', '.join(unknown)}")
    else:
        print(f"uha_vars.yaml not found ({yaml_path}): var_enums kept from the old texts.json")
        try:
            with open(dst, encoding="utf-8") as f:
                texts["var_enums"] = json.load(f).get("var_enums", {})
        except (OSError, ValueError):
            texts["var_enums"] = {}
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        json.dump(texts, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{dst}: {len(texts['ui'])} UI texts, {len(texts['vars'])} variables, {len(texts['cmds'])} commands, "
          f"{sum(len(v) for v in texts['enums'].values())} enum items")


if __name__ == "__main__":
    main()
