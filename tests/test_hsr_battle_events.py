import json
from pathlib import Path
import tempfile
import unittest

from tools.hsr_battle import collect_events, collect_runtime_events, hash32


class RuntimeEventTests(unittest.TestCase):
    def test_variants_aliases_and_unmatched_candidates_preserve_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Avatar_Dr_Ratio_10_Audio_AnimEvent.json').write_text(
                json.dumps({'SoundName': 'Ev_vo_avatar_skill_cast_drratio'}), encoding='utf-8')
            config = root / 'AudioConfig.json'
            config.write_text(json.dumps({
                'CharacterVOEventMap': {'Healing': 'Ev_vo_avatar_healing_{0}'},
                'AdventureCharacterVOEventMap': {'Chest': 'Ev_vo_avatar_open_chest_{0}'}}), encoding='utf-8')
            candidates = collect_runtime_events(root, config)
            self.assertEqual({e['event'] for e in candidates.values()}, {
                'Ev_vo_avatar_healing_dr_ratio', 'Ev_vo_avatar_healing_drratio'})
            event = candidates[hash32('Ev_vo_avatar_healing_drratio')]
            self.assertEqual(event['character'], 'dr_ratio')
            self.assertEqual(event['category'], 'Healing')
            self.assertEqual(event['source'], str(config.resolve()))
            self.assertIn(hash32('Ev_vo_avatar_skill_cast_drratio'), collect_events(root))


if __name__ == '__main__':
    unittest.main()
