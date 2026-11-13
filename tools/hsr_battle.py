"""Recover HSR battle-event labels through parsed Wwise object references.

Requires a local checkout of https://github.com/bnnm/wwiser; use --help for options.
Game files are opened read-only. Outputs are separate from the 64-bit story map.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import wave


def u32(data, offset=0):
    return struct.unpack_from('<I', data, offset)[0]


def hash32(name):
    value = 2166136261
    for byte in name.lower().encode('utf-8'):
        value = ((value * 16777619) & 0xffffffff) ^ byte
    return value


def package_index(path):
    """Read only AKPK index bytes; bank/media data stays on disk."""
    with path.open('rb') as stream:
        header = stream.read(28)
        if header[:4] != b'AKPK':
            raise ValueError(f'Invalid AKPK: {path}')
        _, flag, langs, banks, sounds, externals = struct.unpack_from('<6I', header, 4)
        if flag != 1:
            raise ValueError('Only little-endian AKPK supported')
        stream.seek(28 + langs)
        data = stream.read(banks + sounds + externals)
    position = 0
    for kind, size in [('bank', banks), ('sound', sounds), ('external', externals)]:
        if not size:
            continue
        count = u32(data, position)
        step = (size - 4) // count if count else 0
        if count and step not in (20, 24):
            raise ValueError(f'Unknown AKPK entry length {step}')
        for index in range(count):
            cursor = position + 4 + index * step
            if kind == 'external':
                continue
            ident, block, length, offset, lang = struct.unpack_from(
                '<IIQII' if step == 24 else '<5I', data, cursor)
            yield {'kind': kind, 'id': ident, 'offset': offset * block if block else offset,
                   'bytes': length, 'language_id': lang, 'package': str(path)}
        position += size


def read_entry(entry):
    with open(entry['package'], 'rb') as stream:
        stream.seek(entry['offset'])
        data = stream.read(entry['bytes'])
    if len(data) != entry['bytes']:
        raise ValueError('Truncated package entry')
    return data


def chunks(data):
    position = 0
    while position + 8 <= len(data):
        tag, size = struct.unpack_from('<4sI', data, position)
        if position + 8 + size > len(data):
            raise ValueError('Truncated BNK chunk')
        yield tag, position + 8, size
        position += 8 + size


def raw_event_ids(data):
    for tag, start, size in chunks(data):
        if tag != b'HIRC':
            continue
        cursor = start + 4
        for _ in range(u32(data, start)):
            kind, length, ident = struct.unpack_from('<BII', data, cursor)
            if cursor + 5 + length > start + size:
                raise ValueError('Truncated HIRC object')
            if kind == 4:
                yield ident
            cursor += 5 + length


def values(node, name):
    return [field.get_attr('value') for field in node.finds(name=name)]


def value(node, name):
    found = values(node, name)
    if len(found) != 1:
        raise ValueError(f'Expected one {name}, got {len(found)}')
    return found[0]


def parse_bank(entry, cache, parser_class):
    data = read_entry(entry)
    path = cache / f"{entry['id']}-{hashlib.sha256(data).hexdigest()[:16]}.bnk"
    path.write_bytes(data)
    parser = parser_class()
    if not parser.parse_bank(str(path)):
        raise ValueError(f'wwiser could not parse {path.name}')
    bank = parser.get_banks()[0]
    if bank.get_error_count():
        raise ValueError(f'wwiser found {bank.get_error_count()} parse errors')
    loaded = bank.find(name='listLoadedItem')
    # State objects use ulStateID and are not playable child objects.
    objects = {value(obj, 'ulID'): obj for obj in loaded.get_children() or []
               if values(obj, 'ulID')} if loaded else {}
    return bank, objects


def collect_events(directory):
    names = defaultdict(set)
    for path in ([directory] if directory.is_file() else sorted(directory.rglob('*.json'))):
        def walk(obj):
            if isinstance(obj, dict):
                name = obj.get('SoundName', '')
                if isinstance(name, str) and name.lower().startswith('ev_vo_avatar_'):
                    names[hash32(name)].add(name)
                for child in obj.values():
                    walk(child)
            elif isinstance(obj, list):
                for child in obj:
                    walk(child)
        walk(json.loads(path.read_text(encoding='utf-8')))
    collisions = {str(key): sorted(val) for key, val in names.items() if len(val) != 1}
    if collisions:
        raise ValueError(f'Event hash collisions: {collisions}')
    return {key: next(iter(val)) for key, val in names.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-data', type=Path, required=True, help='StarRail_Data directory')
    parser.add_argument('--events', type=Path, required=True, help='ConfigAnimEvents/Avatar/Audio')
    parser.add_argument('--events-version', required=True, help='Version/commit of event-name config')
    parser.add_argument('--wwiser', type=Path, required=True, help='wwiser repository root')
    parser.add_argument('--wwiser-revision', default='unspecified', help='Pinned wwiser commit for provenance')
    parser.add_argument('--language', default='Chinese(PRC)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--export-limit', type=int, default=20, help='Unique media WAV exports; 0 means all')
    parser.add_argument('--vgmstream', type=Path, default=Path(__file__).resolve().parent / 'vgmstream/vgmstream-cli.exe')
    args = parser.parse_args()
    sys.path.insert(0, str(args.wwiser.resolve()))
    from wwiser.parser.wparser import Parser

    output = args.output.resolve()
    cache = output / 'banks'
    cache.mkdir(parents=True, exist_ok=True)
    names = collect_events(args.events)
    if not names:
        raise ValueError('No battle event names found')
    game = args.game_data.resolve()
    banks = defaultdict(list)
    media = defaultdict(list)
    public = []
    package_paths = sorted({*game.glob('StreamingAssets/Audio/AudioPackage/Windows/Banks*.pck'),
                            *game.glob('Persistent/Audio/AudioPackage/Windows/Banks*.pck')})
    voice_paths = sorted((game / 'Persistent/Audio/AudioPackage/Windows' / args.language).glob('VoBanks*.pck'))
    for path in package_paths + voice_paths:
        for entry in package_index(path):
            if entry['kind'] == 'sound' and path in voice_paths:
                media[entry['id']].append(entry)
            elif entry['kind'] == 'bank':
                banks[entry['id']].append(entry)
                if path in package_paths:
                    public.append(entry)
                # Embedded media are fallback only, often merely prefetch fragments.
                if path in voice_paths:
                    data = read_entry(entry)
                    sections = {tag: (start, size) for tag, start, size in chunks(data)}
                    if b'DIDX' in sections and b'DATA' in sections:
                        start, size = sections[b'DIDX']
                        for cursor in range(start, start + size, 12):
                            ident, offset, length = struct.unpack_from('<III', data, cursor)
                            media[ident].append({**entry, 'id': ident, 'kind': 'embedded',
                                                 'offset': entry['offset'] + sections[b'DATA'][0] + offset,
                                                 'bytes': length, 'embedded_bank_id': entry['id']})
    report = {'event_names_source': str(args.events.resolve()), 'event_names_version': args.events_version,
              'wwiser_revision': args.wwiser_revision,
              'wwiser_parser_sha256': hashlib.sha256((args.wwiser / 'wwiser/parser/wparser.py').read_bytes()).hexdigest(),
              'language': args.language, 'game_data': str(game), 'known_event_names': len(names),
              'voice_packages': len(voice_paths), 'public_packages': len(package_paths),
              'labels_are_original_filenames': False, 'events': [], 'skipped': [], 'exports': []}
    parsed = {}
    def get_bank(entry):
        key = (entry['package'], entry['offset'])
        if key not in parsed:
            parsed[key] = parse_bank(entry, cache, Parser)
        return parsed[key]
    supported = {'CAkRanSeqCntr', 'CAkSwitchCntr', 'CAkActorMixer', 'CAkLayerCntr'}
    for entry in public:
        matches = set(raw_event_ids(read_entry(entry))) & names.keys()
        if not matches:
            continue
        _, objects = get_bank(entry)
        for event_id in sorted(matches):
            event = {'event': names[event_id], 'event_id': event_id, 'event_bank_id': entry['id'],
                     'event_package': entry['package'], 'sounds': []}
            report['events'].append(event)
            for action_id in values(objects[event_id], 'ulActionID'):
                try:
                    action = objects[action_id]
                    if action.get_name() != 'CAkActionPlay':
                        raise ValueError(f'Unsupported action {action.get_name()}')
                    target, bank_id = value(action, 'idExt'), value(action, 'bankID')
                    candidates = [x for x in banks[bank_id] if Path(x['package']) in voice_paths]
                    if len(candidates) != 1:
                        raise ValueError(f'Expected one localized bank {bank_id}, got {len(candidates)}')
                    voice_entry = candidates[0]
                    voice_bank, voice_objects = get_bank(voice_entry)
                    if voice_bank.get_version() < 112:
                        raise ValueError('Source stream modes before Wwise bank version 112 are unsupported')
                    def visit(ident, chain):
                        if ident in chain:
                            raise ValueError('Object reference cycle')
                        obj = voice_objects[ident]
                        chain = chain + [ident]
                        if obj.get_name() == 'CAkSound':
                            source = value(obj, 'sourceID')
                            mode = value(obj, 'StreamType')
                            locations = sorted(media[source], key=lambda x: (x['kind'] != 'sound', -x['bytes'], x['package']))
                            # Wwise shares media across banks by sourceID. A Data/bnk
                            # source may reside in a different localized bank.
                            complete = [loc for loc in locations if
                                        (mode == 0 and loc['kind'] == 'embedded') or
                                        (mode in (1, 2) and loc['kind'] == 'sound')]
                            event['sounds'].append({'action_id': action_id, 'voice_bank_id': bank_id,
                                                    'voice_bank_package': voice_entry['package'],
                                                    'object_chain': chain, 'media_id': source,
                                                    'stream_type': mode, 'plugin_id': value(obj, 'ulPluginID'),
                                                    'generated_source': (value(obj, 'ulPluginID') & 0xf) == 2,
                                                    'complete_location': complete[0] if complete else None,
                                                    'locations': locations})
                        elif obj.get_name() in supported:
                            children = obj.find(name='Children')
                            if children is None:
                                raise ValueError(f'No explicit Children in {obj.get_name()}')
                            for child in values(children, 'ulChildID'):
                                if value(voice_objects[child], 'DirectParentID') != ident:
                                    raise ValueError(f'Child {child} parent does not match {ident}')
                                visit(child, chain)
                        else:
                            raise ValueError(f'Unsupported object {obj.get_name()}')
                    visit(target, [])
                except (KeyError, ValueError) as error:
                    report['skipped'].append({'event': event['event'], 'action_id': action_id, 'reason': str(error)})
            print(event['event'], len(event['sounds']), flush=True)
    # Keep all aliases in manifest; export each unique complete media once.
    unique = {}
    for event in report['events']:
        for sound in event['sounds']:
            if sound['complete_location']:
                unique.setdefault(sound['media_id'], (event['event'], sound['complete_location']))
    for ident, (event_name, location) in list(unique.items())[:args.export_limit or None]:
        folder = output / 'audio' / event_name
        folder.mkdir(parents=True, exist_ok=True)
        wem, wav = folder / f'{ident}.wem', folder / f'{ident}.wav'
        raw = read_entry(location)
        if raw[:4] not in (b'RIFF', b'RIFX'):
            raise ValueError(f'Invalid media {ident}')
        wem.write_bytes(raw)
        subprocess.run([str(args.vgmstream.resolve()), '-o', str(wav), str(wem)],
                       check=True, stdout=subprocess.DEVNULL)
        with wave.open(str(wav)) as audio:
            record = {'media_id': ident, 'event': event_name, 'wem': str(wem.relative_to(output)),
                      'wav': str(wav.relative_to(output)), 'sample_rate': audio.getframerate(),
                      'channels': audio.getnchannels(), 'frames': audio.getnframes(),
                      'seconds': audio.getnframes() / audio.getframerate(),
                      'wem_sha256': hashlib.sha256(raw).hexdigest()}
            if not record['frames']:
                raise ValueError('Empty decoded WAV')
            report['exports'].append(record)
    report['summary'] = {'matched_events': len(report['events']),
                         'events_with_sound_sources': sum(bool(x['sounds']) for x in report['events']),
                         'event_media_relations': sum(len(x['sounds']) for x in report['events']),
                         'unique_complete_media': len(unique), 'wav_exports': len(report['exports']),
                         'relations_without_complete_media': sum(s['complete_location'] is None for e in report['events'] for s in e['sounds']),
                         'generated_source_relations': sum(s['generated_source'] for e in report['events'] for s in e['sounds']),
                         'skipped_actions': len(report['skipped'])}
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # Many event aliases can reference one media: retain every association.
    with (output / 'event-media.tsv').open('w', encoding='utf-8', newline='') as stream:
        stream.write('event\tmedia_id\tvoice_bank_id\tobject_chain\tcomplete_media\n')
        for event in report['events']:
            for sound in event['sounds']:
                complete = sound['complete_location'] is not None
                stream.write(f"{event['event']}\t{sound['media_id']}\t{sound['voice_bank_id']}\t"
                             f"{' -> '.join(map(str, sound['object_chain']))}\t{complete}\n")
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
