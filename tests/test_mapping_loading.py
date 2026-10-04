import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from mapper import Mapper


ROOT = Path(__file__).resolve().parents[1]


class MappingLoadingTests(unittest.TestCase):
    def load(self, filename):
        with contextlib.redirect_stdout(io.StringIO()):
            return Mapper(filename)

    def test_mislabeled_12_byte_records_restore_paths_and_languages(self):
        data = bytearray((ROOT / "maps" / "hkrpg.map").read_bytes())
        self.assertEqual(data[6:8], b"32")
        data[6:8] = b"31"
        with tempfile.TemporaryDirectory() as directory:
            mapping = Path(directory) / "mislabeled.map"
            mapping.write_bytes(data)
            mapper = self.load(mapping)
        self.assertEqual(
            mapper.get_key("58da61c5e0668d3d", addLang=True),
            ["voice\\chapter4\\64\\hysilens\\chapter4_64_hysilens_113_m", "Chinese(PRC)"],
        )
        self.assertEqual(
            mapper.get_key("33e5629c8eefca5f", addLang=True),
            ["voice\\sideX\\sys2\\herta\\sideX_sys2_herta_133_m", "Chinese(PRC)"],
        )


if __name__ == "__main__":
    unittest.main()
