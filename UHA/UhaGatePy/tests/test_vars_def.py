"""Loading uha_vars.yaml: the old flat layout and the new layout with subgroups give the same variables."""
import dataclasses
import os
import subprocess
import tempfile
import unittest

from uhagatepy import vars_def

from .helpers import FIXTURES, REAL_YAML

# The last flat uha_vars.yaml (before the subgroups), read with git from the UHA_FW repo if it is there (PC only).
UHA_COMMON = os.path.dirname(os.path.dirname(REAL_YAML))
OLD_YAML_COMMIT = "e28d6a8"


def load_text(text: str) -> vars_def.VarsFile:
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "vars.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return vars_def.load(path)


def without_sha(defs: vars_def.VarsFile) -> tuple:
    """Everything the gateway uses, except the file hash."""
    return defs.version, defs.nodes, defs.enums, defs.by_id, defs.warnings


class SubgroupLayoutTest(unittest.TestCase):
    def setUp(self):
        self.flat = vars_def.load(os.path.join(FIXTURES, "mini_vars.yaml"))
        self.nested = vars_def.load(os.path.join(FIXTURES, "mini_vars_subgroups.yaml"))

    def test_same_variables_as_the_flat_layout(self):
        self.assertEqual(len(self.nested.by_id), 22)
        self.assertEqual(without_sha(self.nested), without_sha(self.flat))

    def test_producer_inheritance(self):
        by_name = {d.name: d for d in self.nested.by_id.values()}
        self.assertEqual(by_name["SOLAR_POWER_W"].producer, "ELECON")         # from the container group
        self.assertEqual(by_name["EL_HEATER_STATUS"].producer, "TECHM")        # from the subgroup
        self.assertEqual(by_name["STRG1_BALANCED_TODAY"].producer, "ELECON_D")
        self.assertEqual(by_name["BMS1_CELL_V_16"].producer, "ELECON_D")       # plain group

    def test_subgroup_producer_wins_over_the_container(self):
        defs = load_text("""
nodes: {ELECON: 4, TECHM: 3}
groups:
  G:
    producer: ELECON
    subgroups:
      A: {producer: TECHM, vars: [{id: 80, name: EL_HEATER_STATUS, legacy: VAR_EL_HEATER_STATUS, period_ms: 1000}]}
      B: {vars: [{id: 10, name: BAT_SOC, legacy: VAR_BAT_SOC, period_ms: 1000}]}
""")
        self.assertEqual((defs.by_id[80].producer, defs.by_id[10].producer), ("TECHM", "ELECON"))

    def test_broken_groups_are_reported(self):
        for groups, reason in (("G: {producer: ELECON}", "neither 'vars' nor 'subgroups'"),
                               ("G: {producer: ELECON, subgroups: {S: {producer: ELECON}}}", "G.S has no 'vars'"),
                               ("G: {subgroups: {S: {vars: [{id: 10, name: BAT_SOC, legacy: VAR_BAT_SOC, "
                                "period_ms: 1000}]}}}", "(G.S): producer 'None'")):
            with self.assertRaises(vars_def.VarsDefError) as caught:
                load_text("nodes: {ELECON: 4}\ngroups:\n  " + groups + "\n")
            self.assertIn(reason, str(caught.exception))


class RealYamlTest(unittest.TestCase):
    def test_real_file_loads(self):
        if not os.path.exists(REAL_YAML):
            self.skipTest("uha_vars.yaml not found")
        defs = vars_def.load(REAL_YAML)
        self.assertGreaterEqual(len(defs.by_id), 257)

    def test_real_file_equals_the_last_flat_version(self):
        """Only the grouping changed: ids, names, producers, scales, periods ... must be the same."""
        try:
            old = subprocess.run(["git", "-C", UHA_COMMON, "show", f"{OLD_YAML_COMMIT}:VarDefs/uha_vars.yaml"],
                                 capture_output=True, text=True, encoding="utf-8", check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("UHA_FW git history not available (normal on the Pi)")
        old_defs, new_defs = load_text(old), vars_def.load(REAL_YAML)
        self.assertEqual(len(new_defs.by_id), 258)
        # since 0.3.0 the file also has log_s / agg (DB logging); everything else must be unchanged
        new_defs.by_id = {i: dataclasses.replace(d, log_s=0, agg="avg") for i, d in new_defs.by_id.items()}
        self.assertEqual(without_sha(new_defs), without_sha(old_defs))


if __name__ == "__main__":
    unittest.main()
