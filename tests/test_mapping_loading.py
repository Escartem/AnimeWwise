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

    def test_hsr_map_restores_verified_46_voice(self):
        mapper = self.load(ROOT / "maps" / "hkrpg.map")
        self.assertEqual(
            mapper.get_key("26fc35b1a76ad017", addLang=True),
            ["voice\\chapter4\\64\\hysilens\\chapter4_64_hysilens_134_f", "Chinese(PRC)"],
        )
        self.assertIsNone(mapper.get_key("missing"))

    def test_hsr_map_preserves_sfx_root_and_decimal_chapter(self):
        mapper = self.load(ROOT / "maps" / "hkrpg.map")
        self.assertEqual(
            mapper.get_key("0022aafcca492c02", addLang=True),
            ["sfx\\xianzhou\\cutscene\\sfx_xianzhou_cutscene_590_m", "SFX"],
        )
        self.assertEqual(
            mapper.get_key("23ee2e30638cb6b7")[0],
            "voice\\chapter4\\64.5\\danfeng\\chapter4_64.5_danfeng_101",
        )

    def test_hsr_expansion_preserves_master_only_records(self):
        mapper = self.load(ROOT / "maps" / "hkrpg.map")
        self.assertEqual(
            mapper.get_key("00754d8b6d33217a", addLang=True),
            ["voice\\chapter4\\7\\danheng\\chapter4_7_danheng_112", "English"],
        )
        self.assertEqual(
            mapper.get_key("01171784345bf654", addLang=True),
            ["voice\\chapter4\\4\\aglaea\\chapter4_4_aglaea_117", "Korean"],
        )

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
            ["voice\\SideX\\sys2\\herta\\SideX_sys2_herta_133_m", "Chinese(PRC)"],
        )


if __name__ == "__main__":
    unittest.main()
