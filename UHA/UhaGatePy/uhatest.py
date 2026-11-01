#!/usr/bin/env python3
"""UhaGate6 test helpers.

  uhatest.py compare V5.json V6.json   structure (keys, order, types) and values of two outputs
  uhatest.py reader SECONDS FILE...    parse the files 20x per second, count read/parse errors
                                       (checks that the web never sees a half-written file)
"""
import json
import sys
import time


def load(path):
    dups = []

    def pairs(items):
        keys = [k for k, _ in items]
        dups.extend(k for k in set(keys) if keys.count(k) > 1)
        return dict(items)

    with open(path) as f:
        return json.load(f, object_pairs_hook=pairs), dups


def flatten(node, prefix=""):
    """Ordered list of (path, value) for all leaves."""
    if isinstance(node, dict):
        out = []
        for k, v in node.items():
            out.extend(flatten(v, f"{prefix}.{k}" if prefix else k))
        return out
    if isinstance(node, list):
        out = []
        for i, v in enumerate(node):
            out.extend(flatten(v, f"{prefix}[{i}]"))
        return out
    return [(prefix, node)]


def compare(a_path, b_path):
    a, a_dups = load(a_path)
    b, b_dups = load(b_path)
    fa, fb = flatten(a), flatten(b)
    ka, kb = [k for k, _ in fa], [k for k, _ in fb]
    va, vb = dict(fa), dict(fb)

    missing = [k for k in ka if k not in vb]
    extra = [k for k in kb if k not in va]
    common = [k for k in ka if k in vb]
    types = [k for k in common if type(va[k]) is not type(vb[k]) and not (
        isinstance(va[k], (int, float)) and isinstance(vb[k], (int, float)))]
    diffs = [k for k in common if va[k] != vb[k] and not k.endswith("UnixTime")]
    same_order = [k for k in ka if k in vb] == [k for k in kb if k in va]

    print(f"{a_path} vs {b_path}")
    print(f"  keys: {len(ka)} / {len(kb)}, missing in 2nd: {len(missing)}, extra in 2nd: {len(extra)}, "
          f"same order: {same_order}, type mismatches: {len(types)}, duplicate keys: {a_dups or b_dups or 0}")
    print(f"  values equal: {len(common) - len(diffs)}, different: {len(diffs)} (UnixTime ignored)")
    for k in missing[:20]:
        print(f"  missing: {k}")
    for k in extra[:20]:
        print(f"  extra:   {k}")
    for k in types[:20]:
        print(f"  type:    {k}: {va[k]!r} vs {vb[k]!r}")
    for k in diffs[:30]:
        print(f"  value:   {k}: {va[k]} -> {vb[k]}")
    return 0 if not (missing or extra or types or not same_order) else 1


def reader(seconds, paths):
    ok = errors = 0
    end = time.monotonic() + float(seconds)
    while time.monotonic() < end:
        for p in paths:
            try:
                with open(p) as f:
                    json.loads(f.read())
                ok += 1
            except (OSError, ValueError) as e:
                errors += 1
                print(f"  {time.strftime('%H:%M:%S')} {p}: {e}")
        time.sleep(0.05)
    print(f"reader: {ok} good reads, {errors} errors")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2], sys.argv[3]))
    if len(sys.argv) >= 4 and sys.argv[1] == "reader":
        sys.exit(reader(sys.argv[2], sys.argv[3:]))
    print(__doc__)
    sys.exit(2)
