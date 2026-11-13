import contextlib
import copy
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from extract import WwiseExtract
from mapper import Mapper
from tools.hsr_battle_map import embed_battle_names
from tools.hsr_map import merge_map


def empty_map():
    languages = bytearray([2])
    for name in ['Chinese(PRC)', 'Japanese']:
        raw = name.encode()
        languages.extend(bytes([len(raw)]) + bytes(b ^ (0x97 + len(raw)) for b in raw))
    chunks = [languages, b'', b'', b'', b'\x0c', b'']
    header = bytearray(b'ESFM\x00\x0032\x00\x00\x05hkrpg\x2f')
    offset = 0
    for chunk in chunks:
        header.extend(offset.to_bytes(3, 'big') + len(chunk).to_bytes(3, 'big'))
        offset += len(chunk)
    return bytes(header) + b''.join(chunks)


def mapping(raw):
    result = Mapper.__new__(Mapper)
    result.mode, result.data = 'MAP', raw
    with contextlib.redirect_stdout(io.StringIO()):
        result.process_map()
    return result


def manifest(size, language='Chinese(PRC)', embedded=False):
    location = {'kind': 'embedded' if embedded else 'sound', 'id': 123,
                'bytes': size, 'package': f'C:/game/{language}/VoBanks0.pck'}
    if embedded:
        location['embedded_bank_id'] = 456
    sound = {'media_id': 123, 'stream_type': 0 if embedded else 2,
             'generated_source': False, 'complete_location': location}
    return {'language': language, 'events': [
        {'event': label, 'character': 'asta', 'sounds': [copy.deepcopy(sound)]} for label in
        ['Ev_vo_avatar_skill_cast_asta', 'Ev_vo_avatar_ultra_skill_cast_asta']]}


def pcm():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\x00\x00' * 80)
    return stream.getvalue()


def package(media):
    # Minimal real AKPK stream index, read through wavescan and WwiseExtract.
    langs = struct.pack('<I', 0)
    banks = struct.pack('<I', 0)
    sounds_size = 4 + 20
    offset = 28 + len(langs) + len(banks) + sounds_size
    sounds = struct.pack('<I5I', 1, 123, 1, len(media), offset, 0)
    return struct.pack('<4s6I', b'AKPK', offset - 8, 1, len(langs), len(banks), len(sounds), 0) + langs + banks + sounds + media


class BattleMappingTests(unittest.TestCase):
    def test_character_folders_follow_configuration_ownership_and_mission_references(self):
        report = manifest(100)
        sound = report['events'][0]['sounds'][0]
        labels = [('Dr_Ratio', 'Ev_vo_avatar_skill_cast_drratio_01'),
                  ('Mar_7th', 'Ev_vo_avatar_skill_cast_march7th_02'),
                  ('Cyrene', 'Ev_vo_avatar_skill_cast_cyrene')]
        with tempfile.TemporaryDirectory() as directory:
            for character, label in labels:
                path = Path(directory) / f'Avatar_{character}_10_Audio_AnimEvent.json'
                path.write_text(json.dumps({'SoundName': label}), encoding='utf-8')
            report['event_names_source'] = directory
            report['events'] = [{'event': label, 'sounds': [sound]} for _, label in labels]
            report['events'].append({'event': 'Ev_vo_avatar_battleevent02_cyrene_week', 'sounds': [sound]})
            after = mapping(embed_battle_names(mapping(empty_map()), [report]))
        paths = after.get_bank_keys('123', 'Chinese(PRC)/VoBanks0.pck', 100)
        self.assertEqual(set(paths), {
            'voice\\battle\\dr_ratio\\Ev_vo_avatar_skill_cast_drratio_01_123',
            'voice\\battle\\mar_7th\\Ev_vo_avatar_skill_cast_march7th_02_123',
            'voice\\battle\\cyrene\\Ev_vo_avatar_skill_cast_cyrene_123',
            'voice\\battle\\cyrene\\Ev_vo_avatar_battleevent02_cyrene_week_123'})

    def test_legacy_sectors_and_external_lookups_are_unchanged(self):
        before = mapping(empty_map())
        raw = embed_battle_names(before, [manifest(100)])
        self.assertEqual(raw[:before.map_end], before.data)
        after = mapping(raw)
        self.assertIsNone(after.get_key('123'))
        self.assertEqual(after.keys, before.keys)
        self.assertEqual(after.music_keys, before.music_keys)
        merged = mapping(merge_map(after, {}, '4.7'))
        self.assertEqual(merged.bank_keys, after.bank_keys)
        self.assertEqual(mapping(before.data).bank_keys, {})

    def test_bank_names_require_matching_language_package_media_and_size(self):
        chinese, japanese = manifest(100), manifest(120, 'Japanese')
        after = mapping(embed_battle_names(mapping(empty_map()), [chinese, japanese]))
        names = after.get_bank_keys('123', 'C:/game/Chinese(PRC)/VoBanks0.pck', 100)
        self.assertEqual(names, [
            'voice\\battle\\asta\\Ev_vo_avatar_skill_cast_asta_123',
            'voice\\battle\\asta\\Ev_vo_avatar_ultra_skill_cast_asta_123'])
        self.assertEqual(after.get_bank_keys('123', 'Japanese/VoBanks0.pck', 100), [])
        self.assertEqual(len(after.get_bank_keys('123', 'Japanese/VoBanks0.pck', 120)), 2)
        self.assertEqual(after.get_bank_keys('123', 'Chinese(PRC)/VoBanks1.pck', 100), [])
        self.assertEqual(after.get_bank_keys('456_123', 'Chinese(PRC)/VoBanks0.pck', 100), [])
        self.assertEqual(after.get_bank_keys('123', 'VoBanks0.pck', 100), names)
        japanese = manifest(100, 'Japanese')
        ambiguous = mapping(embed_battle_names(mapping(empty_map()), [chinese, japanese]))
        self.assertEqual(ambiguous.get_bank_keys('123', 'VoBanks0.pck', 100), [])
        self.assertEqual(ambiguous.get_bank_keys('123', 'Chinese(PRC)/VoBanks0.pck', 100), names)

    def test_embedded_media_is_named_but_prefetch_and_silence_are_not(self):
        report = manifest(100, embedded=True)
        report['events'][0]['sounds'].append({'complete_location': None})
        silence = copy.deepcopy(report['events'][0]['sounds'][0])
        silence['media_id'] = silence['complete_location']['id'] = 999
        silence['generated_source'] = True
        report['events'][0]['sounds'].append(silence)
        after = mapping(embed_battle_names(mapping(empty_map()), [report]))
        self.assertEqual(len(after.get_bank_keys('456_123', 'Chinese(PRC)/VoBanks0.pck', 100)), 2)
        self.assertEqual(after.get_bank_keys('123', 'Chinese(PRC)/VoBanks0.pck', 100), [])
        self.assertEqual(after.get_bank_keys('456_999', 'Chinese(PRC)/VoBanks0.pck', 100), [])
        report['events'][0]['sounds'][0]['stream_type'] = 2
        with self.assertRaisesRegex(ValueError, 'prefetch'):
            embed_battle_names(mapping(empty_map()), [report])

    def test_truncated_extension_is_rejected(self):
        raw = embed_battle_names(mapping(empty_map()), [manifest(100)])
        with self.assertRaisesRegex(ValueError, 'length'):
            mapping(raw[:-1])

    def test_normal_package_loading_and_export_use_readable_filenames(self):
        media = pcm()
        raw = embed_battle_names(mapping(empty_map()), [manifest(len(media))])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / 'Chinese(PRC)'
            voice.mkdir()
            source = voice / 'VoBanks0.pck'
            source.write_bytes(package(media))
            extractor = WwiseExtract()
            extractor.maps['battle-test'] = mapping(raw)
            with contextlib.redirect_stdout(io.StringIO()):
                tree = extractor.load_folder('battle-test.map', [str(source)], '', str(voice), lambda _: None)
            files = tree['folders']['voice']['folders']['battle']['folders']['asta']['files']
            self.assertEqual(len(files), 2)
            self.assertTrue(all('skill' in name and 'asta' in name for name, _ in files))
            self.assertTrue(all(meta['original_name'] == '123.wem' for _, meta in files))
            selected = [dict(meta, name=name, path=['voice', 'battle', 'asta']) for name, meta in files]
            with contextlib.redirect_stdout(io.StringIO()):
                extractor.extract_files(str(voice), selected, str(root / 'export'), 'wem', progress=lambda _: None)
            for name, _ in files:
                self.assertEqual((root / 'export/voice/battle/asta' / name).read_bytes(), media)


if __name__ == '__main__':
    unittest.main()
