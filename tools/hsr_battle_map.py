"""Embed verified battle-media names in an HSR map, preserving its legacy sectors.

python tools/hsr_battle_map.py --map maps/hkrpg.map --manifest path/manifest.json --output maps/hkrpg.map
Only complete media locations from the manifest are named; no game files are changed.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mapper import Mapper
from tools.hsr_battle import collect_events


def character_events(directory):
    """Use avatar configuration ownership rather than splitting event suffixes."""
    owners = defaultdict(set)
    characters = set()
    for path in sorted(directory.glob('*.json')):
        match = re.fullmatch(r'Avatar_(.+?)_\d{2}(?:_[A-Za-z]+)?_Audio_AnimEvent\.json', path.name)
        if not match:
            continue
        character = match[1].lower()
        characters.add(character)
        for event in collect_events(path).values():
            owners[event].add(character)
    conflicts = {event: sorted(chars) for event, chars in owners.items() if len(chars) != 1}
    if conflicts:
        raise ValueError(f'Ambiguous avatar configuration ownership: {conflicts}')
    return {event: next(iter(chars)) for event, chars in owners.items()}, characters


def embed_battle_names(mapping, manifests):
    names = defaultdict(set)
    character_sources = {}
    for report in manifests:
        language = report['language']
        if language not in mapping.languages:
            raise ValueError(f'Unknown map language: {language}')
        source = report.get('event_names_source')
        if source not in character_sources:
            character_sources[source] = character_events(Path(source)) if source else ({}, set())
        owners, characters = character_sources[source]
        for event in report['events']:
            label = event['event']
            if not re.fullmatch(r'Ev_vo_avatar_[A-Za-z0-9_]+', label, re.IGNORECASE):
                raise ValueError(f'Invalid avatar event name: {label}')
            character = event.get('character') or owners.get(label)
            if not character:
                # Mission events can reference avatars outside their own files.
                matches = [name for name in characters if
                           re.search(rf'(?:^|_){re.escape(name)}(?:_|$)', label, re.IGNORECASE)]
                character = matches[0] if len(matches) == 1 else None
            if not character or not re.fullmatch(r'[a-z0-9_]+', character):
                raise ValueError(f'No unambiguous character for {label}; provide its configuration or character')
            for sound in event['sounds']:
                location = sound['complete_location']
                if not location or sound.get('generated_source'):
                    continue
                ident = str(sound['media_id'])
                if location['kind'] == 'embedded':
                    if sound['stream_type'] != 0:
                        raise ValueError('Streaming prefetch is not complete media')
                    ident = f"{location['embedded_bank_id']}_{ident}"
                elif location['kind'] != 'sound' or sound['stream_type'] not in (1, 2):
                    raise ValueError('Unsupported complete media location')
                if location['bytes'] <= 0 or location['id'] != sound['media_id']:
                    raise ValueError('Invalid complete media location')
                package = location['package'].replace('\\', '/').rsplit('/', 1)[-1]
                path = f"voice\\battle\\{character}\\{label}_{sound['media_id']}"
                names[(language, package, ident, location['bytes'])].add(path)
    records = [list(key) + [sorted(paths)] for key, paths in sorted(names.items())]
    payload = json.dumps(records, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return mapping.data[:mapping.map_end] + b'ESFB' + struct.pack('<I', len(payload)) + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    mapping = Mapper(args.map)
    reports = [json.loads(path.read_text(encoding='utf-8')) for path in args.manifest]
    raw = embed_battle_names(mapping, reports)
    args.output.write_bytes(raw)
    print(f'Wrote {args.output}; legacy map sectors unchanged')


if __name__ == '__main__':
    main()
