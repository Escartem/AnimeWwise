"""Build a package-verified HSR map with WwiseMapper, retaining existing records.

Run from the repository root; use --help for options. Game files are read only.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mapper import Mapper


def load(path):
    with contextlib.redirect_stdout(io.StringIO()):
        return Mapper(path)


def fnv(text):
    value = 14695981039346656037
    for byte in text.lower().encode():
        value = ((value * 1099511628211) & 0xffffffffffffffff) ^ byte
    return f'{value:016x}'


def sectors(raw):
    pos = 12 + raw[10]
    prefix = raw[:pos]
    def read():
        nonlocal pos
        value = int.from_bytes(raw[pos:pos+3], 'big'); pos += 3
        if value == 0xffffff:
            value = int.from_bytes(raw[pos:pos+4], 'big'); pos += 4
        return value
    entries = [(read(), read()) for _ in range(6)]
    base = pos if entries[0][0] == 0 else 0
    return prefix, [bytearray(raw[base+offset:base+offset+size]) for offset, size in entries]


def merge_map(before, additions, version):
    """Append verified keys using the existing ESFM32 sector encoding."""
    assert before.map_version == b'32'
    prefix, chunks = sectors(before.data)
    prefix = prefix[:-1] + bytes([int(version.replace('.', ''))])
    strings, words, files = chunks[1:4]
    def string_at(offset):
        size = strings[offset]
        if size > 128:
            return str(int.from_bytes(strings[offset+1:offset+1+size-128], 'big'))
        return bytes(b ^ (0x97+size) for b in strings[offset+1:offset+1+size]).decode()
    si, wi, pi = {}, {}, {}
    i = 0
    while i < len(strings):
        si.setdefault(string_at(i), i)
        size = strings[i]; i += 1 + (size-128 if size > 128 else size)
    i = 0
    while i < len(words):
        count = words[i]
        word = '_'.join(string_at(int.from_bytes(words[i+1+j*2:i+3+j*2], 'big')) for j in range(count))
        wi.setdefault(word, i); i += 1+count*2
    for key, (offset, _) in before.keys.items():
        if offset not in pi:
            pi[offset] = before.get_key(key)[0]
    paths = {p: offset for offset, p in pi.items()}
    def intern_string(text):
        if text not in si:
            raw = text.encode()
            assert len(raw) <= 104 and len(strings) < 65536
            si[text] = len(strings)
            strings.extend(bytes([len(raw)]) + bytes(b ^ (0x97+len(raw)) for b in raw))
        return si[text]
    def intern_word(text):
        if text not in wi:
            parts = text.split('_')
            assert len(parts) < 256 and len(words) < 0xffffff
            wi[text] = len(words); words.append(len(parts))
            for part in parts:
                words.extend(intern_string(part).to_bytes(2, 'big'))
        return wi[text]
    for key, (path, language) in sorted(additions.items()):
        assert key not in before.keys
        if path not in paths:
            parts = path.split('\\')
            assert len(parts) < 256 and len(files) < 0xffffff
            paths[path] = len(files); files.append(len(parts))
            for part in parts:
                files.extend(intern_word(part).to_bytes(3, 'big'))
        chunks[4].extend(paths[path].to_bytes(3, 'big') + bytes([before.languages.index(language)]) + bytes.fromhex(key))
    def i24(value):
        return value.to_bytes(3, 'big') if value < 0xffffff else b'\xff'*3 + value.to_bytes(4, 'big')
    header = bytearray(prefix); offset = 0
    for chunk in chunks:
        header.extend(i24(offset) + i24(len(chunk))); offset += len(chunk)
    return bytes(header) + b''.join(chunks)


def scan(game):
    """Read only AKPK external indexes and WAVE headers, not full packages."""
    found, packages = {}, []
    for parent in ['Persistent', 'StreamingAssets']:
        for package in sorted((game/'StarRail_Data'/parent/'Audio/AudioPackage/Windows').rglob('*.pck')):
            package_size = package.stat().st_size
            with package.open('rb') as stream:
                head = stream.read(28)
                assert head[:4] == b'AKPK', package
                endian = '<' if head[8:12] == b'\x01\x00\x00\x00' else '>'
                header, flag, langs, banks, sounds, ext = struct.unpack(endian+'6I', head[4:])
                assert flag == 1
                if langs+banks+sounds+16 >= header:
                    ext = 0
                stream.seek(28+langs+banks+sounds)
                data = stream.read(ext)
                count = struct.unpack_from(endian+'I', data)[0] if ext else 0
                assert not count or ext == 4+count*24, package
                for index in range(count):
                    ident, block, size, offset, lang = struct.unpack_from(endian+'Q4I', data, 4+index*24)
                    offset *= block or 1
                    assert size > 0 and offset+size <= package_size
                    key = f'{ident:016x}'
                    location = {'package': str(package), 'offset': offset, 'size': size}
                    found.setdefault(key, []).append(location)
                packages.append({'path': str(package), 'external_entries': count})
    return found, packages


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game', type=Path, required=True)
    ap.add_argument('--wwisemap', type=Path, required=True)
    ap.add_argument('--data', type=Path, required=True, help='WwiseMapper seed data directory (copied)')
    ap.add_argument('--commit', required=True, help='pinned DimbreathBot/TurnBasedGameData commit')
    ap.add_argument('--version', default='4.7')
    ap.add_argument('--baseline', type=Path, default=ROOT/'maps/hkrpg.map')
    ap.add_argument('--work', type=Path, default=ROOT/'temp/hsr-4.7')
    ap.add_argument('--output', type=Path, default=ROOT/'maps/hkrpg.map')
    ap.add_argument('--direct-network', action='store_true')
    ap.add_argument('--extract-samples', action='store_true')
    ap.add_argument('--extra-paths', type=Path, help='Additional candidate paths for WwiseMapper append; still verified against installed packages')
    args = ap.parse_args()
    if not re.fullmatch(r'[0-9]\.[0-9]', args.version):
        ap.error('ESFM version header requires a single-digit X.Y version')
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        ap.error('--commit must be a full 40-character commit hash')
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    raw = work/'raw'/args.commit; raw.mkdir(parents=True, exist_ok=True)
    import requests
    def download(name):
        path = raw/(name+'.json')
        url = f'https://raw.githubusercontent.com/DimbreathBot/TurnBasedGameData/{args.commit}/ExcelOutput/{name}.json'
        if not path.exists():
            session = requests.Session(); session.trust_env = not args.direct_network
            response = session.get(url, timeout=90); response.raise_for_status()
            json.loads(response.content)
            path.write_bytes(response.content)
        return {'name': name, 'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'rows': len(json.loads(path.read_bytes()))}
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources = list(pool.map(download, ['VoiceConfig', 'ResourceDeletionVPList', 'SFXConfig']))
    print('Fetched', sources, flush=True)
    data = work/'data'; data.mkdir(exist_ok=True)
    seed = args.data/'hkrpg.v1'
    shutil.copy2(seed, data/'hkrpg.v1')
    commands = []
    def run(*params):
        command = [str(args.wwisemap.resolve()), *map(str, params)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        commands.append({'argv': command, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        (work/'commands.json').write_text(json.dumps(commands, indent=2), encoding='utf-8')
        if result.returncode:
            raise RuntimeError(result.stderr)
    paths = work/'paths.json'; built = work/'candidates.map'
    run('parse', '-g', 'hkrpg', '-i', raw, '-o', paths)
    run('append', '-g', 'hkrpg', '-v', args.version, '-d', 'v1', '--data', data, '-p', paths)
    if args.extra_paths:
        run('append', '-g', 'hkrpg', '-v', args.version, '-d', 'v1', '--data', data, '-p', args.extra_paths.resolve())
    run('build', '-g', 'hkrpg', '-v', args.version, '--data', data, '-o', built)
    before, candidate = load(args.baseline), load(built)
    print('Scanning installed package indexes', flush=True)
    locations, packages = scan(args.game)
    additions, evidence, absent = {}, {}, 0
    for key in candidate.keys.keys()-before.keys.keys():
        if key not in locations:
            absent += 1; continue
        path, language = candidate.get_key(key, True)
        basename = path.rsplit('\\', 1)[-1]
        hashed = f'{language}/voice/{basename}.wem' if language != 'SFX' else f'sfx/{basename}.wem'
        assert fnv(hashed) == key, (key, hashed)
        for loc in locations[key]:
            package = Path(loc['package'])
            if language != 'SFX':
                assert package.parent.name == language, (key, language, package)
            with package.open('rb') as stream:
                stream.seek(loc['offset']); head = stream.read(12)
            assert head[:4] in [b'RIFF', b'RIFX'] and head[8:] == b'WAVE'
            endian = '<' if head[:4] == b'RIFF' else '>'
            assert struct.unpack(endian+'I', head[4:8])[0]+8 == loc['size']
        additions[key] = (path, language)
        evidence[key] = {'path': path, 'language': language, 'hash_input': hashed.lower(), 'locations': locations[key]}
    result = merge_map(before, additions, args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    after = load(args.output)
    assert after.keys.keys() == before.keys.keys() | additions.keys()
    assert all(after.get_key(key, True) == list(value) for key, value in additions.items())
    assert all(after.keys[key] == value for key, value in before.keys.items())
    assert after.music_keys == before.music_keys and after.languages == before.languages
    samples = []
    if args.extract_samples:
        out = ROOT/'output'/f'hsr-{args.version}'/'samples'
        for language in sorted({e['language'] for e in evidence.values()}):
            options = [(key, e) for key, e in sorted(evidence.items()) if e['language'] == language]
            options.sort(key=lambda item: ('v470' not in item[1]['path'], item[0]))
            for key, e in options[:2]:
                loc = e['locations'][0]
                folder = out/language; folder.mkdir(parents=True, exist_ok=True)
                dest = folder/(e['path'].rsplit('\\', 1)[-1]+'.wem')
                with Path(loc['package']).open('rb') as stream:
                    stream.seek(loc['offset']); payload = stream.read(loc['size'])
                dest.write_bytes(payload)
                wav = dest.with_suffix('.wav')
                proc = subprocess.run([str(ROOT/'tools/vgmstream/vgmstream-cli.exe'), '-o', str(wav), str(dest)], capture_output=True, text=True)
                assert proc.returncode == 0, proc.stderr
                samples.append({'hash': key, 'wem': str(dest), 'wav': str(wav), 'wem_sha256': hashlib.sha256(payload).hexdigest()})
    report = {'version': args.version, 'commit': args.commit, 'sources': sources,
              'wwisemap_exe': str(args.wwisemap.resolve()), 'wwisemap_sha256': hashlib.sha256(args.wwisemap.read_bytes()).hexdigest(),
              'seed_db_sha256': hashlib.sha256(seed.read_bytes()).hexdigest(),
              'baseline_sha256': hashlib.sha256(before.data).hexdigest(), 'baseline_keys': len(before.keys),
              'candidate_keys': len(candidate.keys), 'new_verified_keys': len(additions), 'new_languages': dict(Counter(e['language'] for e in evidence.values())),
              'uninstalled_candidate_keys_excluded': absent, 'final_keys': len(after.keys),
              'packages_scanned': len(packages), 'external_identifiers': len(locations),
              'coverage_before': len(locations.keys() & before.keys.keys()), 'coverage_after': len(locations.keys() & after.keys.keys()),
              'unresolved_external_identifiers': len(locations.keys()-after.keys.keys()),
              'baseline_records_unchanged': True, 'all_additions_roundtrip_verified': True,
              'output_sha256': hashlib.sha256(result).hexdigest(), 'output_bytes': len(result), 'samples': samples}
    if args.extra_paths:
        report['extra_paths'] = {'file': str(args.extra_paths), 'sha256': hashlib.sha256(args.extra_paths.read_bytes()).hexdigest()}
    for name, obj in [('report', report), ('evidence', evidence), ('packages', packages)]:
        (work/(name+'.json')).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
