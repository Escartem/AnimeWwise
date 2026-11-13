import contextlib
import io
from pathlib import Path
import unittest

from mapper import Mapper
from tools.hsr_map import fnv, load, merge_map


ROOT = Path(__file__).resolve().parents[1]


class HsrMapMergeTests(unittest.TestCase):
    def test_shipped_47_map_restores_new_ambient_voice_and_gui_selection(self):
        import json
        index = json.loads((ROOT / 'version.json').read_text(encoding='utf-8'))
        entry = next(e for e in index['maps'] if e['game'] == 'Honkai: Star Rail')
        self.assertEqual(entry['version'], '4.7')
        mapping = load(ROOT / 'maps' / entry['name'])
        self.assertEqual(mapping.get_key('025e88528e2a3e1d', True),
                         ['voice\\vo\\ambient\\w5\\v470\\review\\player\\vo_ambient_w5_v470_review_player_104_m',
                          'Chinese(PRC)'])
        self.assertEqual(mapping.get_key('7700812c09a1b665', True),
                         ['voice\\chapter5\\73\\player\\chapter5_73_player_132_m', 'Chinese(PRC)'])
        self.assertEqual(mapping.get_key('654e53650240ba8a', True),
                         ['voice\\chapter5\\73\\player\\chapter5_73_player_132_f', 'Chinese(PRC)'])
        self.assertEqual(mapping.get_key('bcb0285fdfccd548', True),
                         ['voice\\chapter5\\75\\pangbai\\chapter5_75_pangbai_107', 'Chinese(PRC)'])

    def test_merge_retains_old_keys_and_decimal_names_in_two_languages(self):
        before = load(ROOT / 'maps/hkrpg.map')
        name = 'chapter_test_64.5_merge_regression_001'
        path = 'voice\\chapter_test\\64.5\\' + name
        additions = {fnv(f'{lang}/voice/{name}.wem'): (path, lang)
                     for lang in ['Chinese(PRC)', 'Japanese']}
        self.assertFalse(additions.keys() & before.keys.keys())
        raw = merge_map(before, additions, '4.7')
        after = Mapper.__new__(Mapper)
        after.mode = 'MAP'
        after.data = raw
        with contextlib.redirect_stdout(io.StringIO()):
            after.process_map()
        self.assertEqual(after.keys.keys(), before.keys.keys() | additions.keys())
        self.assertTrue(all(after.keys[k] == value for k, value in before.keys.items()))
        self.assertEqual(after.music_keys, before.music_keys)
        self.assertEqual(after.languages, before.languages)
        self.assertTrue(after.strings.startswith(before.strings))
        self.assertTrue(after.words.startswith(before.words))
        self.assertTrue(after.files.startswith(before.files))
        for key, expected in additions.items():
            self.assertEqual(after.get_key(key, True), list(expected))
        self.assertEqual(raw[11 + raw[10]], 47)

    def test_hash_is_fnv1_with_lowercase_language_and_basename(self):
        self.assertEqual(fnv('Chinese(PRC)/voice/chapter4_64.5_danfeng_101.wem'),
                         '23ee2e30638cb6b7')


if __name__ == '__main__':
    unittest.main()
