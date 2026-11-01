"""Golden test: uha.json and bms.json must have the same keys, key order and values as UhaGate6.

A small C++ tool is built from the real UhaGate6 sources (UHA/UHA6/src/outputs.cpp + cJSON) and fed
with random values; the Python builders get the same values. Skipped if no C++ compiler is found.
"""
import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest

from uhagatepy import outputs
from uhagatepy.legacy_table import NAME_TO_ID

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UHA6_SRC = os.path.join(os.path.dirname(APP_DIR), "UHA6", "src")


class GoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++")
        if compiler is None or not os.path.isdir(UHA6_SRC):
            raise unittest.SkipTest("g++ or UHA/UHA6/src not available")
        cls.folder = tempfile.mkdtemp()
        cls.tool = os.path.join(cls.folder, "golden_dump" + (".exe" if os.name == "nt" else ""))
        c_object = os.path.join(cls.folder, "cJSON.o")
        subprocess.run([shutil.which("gcc") or "gcc", "-c", "-O1", "-w", os.path.join(UHA6_SRC, "cJSON.c"),
                        "-o", c_object], check=True)
        subprocess.run([compiler, "-std=c++17", "-O1", "-w", "-I", UHA6_SRC,
                        os.path.join(APP_DIR, "tools", "golden_dump.cpp"), os.path.join(UHA6_SRC, "outputs.cpp"),
                        c_object, "-o", cls.tool], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def run_case(self, values):
        values_file = os.path.join(self.folder, "values.txt")
        with open(values_file, "w") as f:
            f.writelines(f"{name} {value}\n" for name, value in values.items())
        uha_file, bms_file = os.path.join(self.folder, "uha.json"), os.path.join(self.folder, "bms.json")
        subprocess.run([self.tool, values_file, "1700000000", uha_file, bms_file], check=True)
        raw = {name: values.get(name, 0) for name in NAME_TO_ID}
        for produced, expected_file in ((outputs.build_uha_json(raw, 1700000000), uha_file),
                                        (outputs.build_bms_json(raw, 1700000000), bms_file)):
            with open(expected_file) as f:
                expected = json.load(f, object_pairs_hook=lambda pairs: pairs)   # keeps the key order
            self.assertEqual(json.loads(produced, object_pairs_hook=lambda pairs: pairs), expected)

    def test_all_zero(self):
        self.run_case({})

    def test_random_values(self):
        generator = random.Random(2026)
        names = list(NAME_TO_ID)
        for _ in range(40):
            self.run_case({name: generator.randint(-32768, 32767) for name in names})


if __name__ == "__main__":
    unittest.main()
