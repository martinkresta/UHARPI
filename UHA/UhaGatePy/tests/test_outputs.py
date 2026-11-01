import json
import os
import tempfile
import unittest

from uhagatepy import outputs, tunnel, vars_def
from uhagatepy.legacy_table import NAME_TO_ID, UHA_JSON_ITEMS
from uhagatepy.store import Store

from .helpers import float_packet, mini_defs, tunnel_packet


def zero_raw():
    return {name: 0 for name in NAME_TO_ID}


class UhaJsonTest(unittest.TestCase):
    def test_keys_and_order_follow_the_table(self):
        data = json.loads(outputs.build_uha_json(zero_raw(), 123))
        self.assertEqual(list(data), [key for key, _, _ in UHA_JSON_ITEMS] + ["UnixTime"])
        self.assertEqual(len(data), 256)
        self.assertEqual(data["UnixTime"], 123)

    def test_computed_key(self):
        raw = zero_raw()
        raw["VAR_CONS_TODAY_10WH"] = 123
        data = json.loads(outputs.build_uha_json(raw, 1))
        self.assertEqual(data["VAR_CONS_TODAY_WH"], 1230)
        self.assertNotIn("VAR_CONS_TODAY_10WH", data)               # only the computed key is published

    def test_whole_numbers_are_printed_as_integers(self):
        text = outputs.build_uha_json(zero_raw(), 1)
        self.assertIn('"VAR_BAT_SOC": 0,', text)
        self.assertNotIn("0.0", text)


class BmsJsonTest(unittest.TestCase):
    def test_structure_and_missing_keys(self):
        data = json.loads(outputs.build_bms_json(zero_raw(), 5))
        self.assertEqual(list(data), ["BatteryPackInfo", "LiveData", "Cells"])
        self.assertEqual(list(data["LiveData"]), [
            "SunPowerW", "TotalVoltageV", "ChargingA", "DischargingA", "TodayChargingKwh", "TodayDischargingKwh",
            "AvailableEnergyKwh", "SocPct", "TemperatureC", "SunPowerPct", "BattCurrentA", "LoadCurrentA",
            "LoadPowerW", "LoadPowerPct", "TodayDiffKwh", "UnixTime"])
        for never_present in ("TotalChargingKwh", "TotalDischargingKwh"):
            self.assertNotIn(never_present, data["LiveData"])
        self.assertEqual(len(data["Cells"]), 16)

    def test_values_and_quirks(self):
        raw = zero_raw()
        raw.update({"VAR_SOLAR_POWER_W": 5000, "VAR_LOAD_W": -8001, "VAR_LOAD_A100": 250,
                    "VAR_BAT_VOLTAGE_V10": 532, "VAR_BMS1_CELL1_MV": 3305, "VAR_BMS1_CELL1_C": 21,
                    "VAR_SOLAR_ENERGY_TODAY_10WH": 300, "VAR_CONS_TODAY_10WH": 120,
                    "VAR_AXPERT_BAT_CHARGING_A": 2, "VAR_MPPT_BAT_CURRENT_A10": 35})
        data = json.loads(outputs.build_bms_json(raw, 5))
        live = data["LiveData"]
        self.assertEqual(live["SunPowerPct"], 0)                     # integer division quirk: 5000 // 11200 = 0
        self.assertEqual(live["LoadPowerPct"], -100)                 # C truncates towards zero: -8001 / 8000 = -1
        self.assertEqual(live["DischargingA"], 2.5)
        self.assertEqual(live["TotalVoltageV"], 53.2)
        self.assertEqual(live["ChargingA"], 5.5)
        self.assertEqual(live["TodayDiffKwh"], 1800)                 # in Wh although the key says Kwh
        self.assertEqual(data["Cells"][0], {"VoltageV": 3.305, "TemperatureC": 21})


class Uha2JsonTest(unittest.TestCase):
    def test_sources_and_enum(self):
        defs = mini_defs()
        store = Store(defs, 2.0)
        store.set_old(10, 64, True, 1.0, 1)
        store.set_v2(tunnel.decode(float_packet(4, 11, 53.2), defs), 1.0, 1)
        store.set_v2(tunnel.decode(tunnel_packet(3, 80, (2).to_bytes(4, "little")), defs), 1.0, 1)
        data = json.loads(outputs.build_uha2_json(store, defs, 1.5, 99))
        self.assertEqual(data["YamlVersion"], 7)
        v = data["Vars"]
        self.assertEqual((v["BAT_SOC"]["source"], v["BAT_SOC"]["value"]), ("old", 64))
        self.assertEqual((v["BAT_VOLTAGE_V"]["source"], v["BAT_VOLTAGE_V"]["value"], v["BAT_VOLTAGE_V"]["unit"]),
                         ("vars2", 53.2, "V"))
        self.assertEqual(v["BAT_VOLTAGE_V"]["producer"], "ELECON")
        self.assertEqual((v["EL_HEATER_STATUS"]["value"], v["EL_HEATER_STATUS"]["enum_name"]), (2, "NoFreePower"))
        self.assertEqual((v["SOLAR_POWER_W"]["source"], v["SOLAR_POWER_W"]["value"], v["SOLAR_POWER_W"]["valid"]),
                         ("none", None, False))
        self.assertIn("BMS1_CELL_V_16", v)


class WriteAtomicTest(unittest.TestCase):
    def test_replaces_file_and_leaves_no_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "a.json")
            outputs.write_atomic(path, "one")
            outputs.write_atomic(path, "two")
            with open(path) as f:
                self.assertEqual(f.read(), "two")
            self.assertEqual(os.listdir(folder), ["a.json"])

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "needs symlinks")
    def test_symlink_is_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "ram", "a.json")
            os.mkdir(os.path.dirname(target))
            link = os.path.join(folder, "a.json")
            os.symlink(target, link)                                 # dangling at first, like after a reboot
            outputs.write_atomic(link, "x")
            self.assertTrue(os.path.islink(link))
            with open(target) as f:
                self.assertEqual(f.read(), "x")


class RealYamlTest(unittest.TestCase):
    """The real definition file from the UHA_FW repo, if it is available."""

    def test_loads_and_covers_uha_json(self):
        from .helpers import REAL_YAML
        if not os.path.exists(REAL_YAML):
            self.skipTest("uha_vars.yaml not found (set UHA_VARS_YAML)")
        defs = vars_def.load(REAL_YAML)
        self.assertGreater(len(defs.by_id), 250)
        legacy = {d.legacy for d in defs.by_id.values()}
        covered = [key for key, name, _ in UHA_JSON_ITEMS if name in legacy]
        self.assertGreaterEqual(len(covered), 250)                   # 252 of 256 keys map to a YAML variable


if __name__ == "__main__":
    unittest.main()
