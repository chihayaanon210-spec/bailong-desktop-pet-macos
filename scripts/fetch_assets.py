#!/usr/bin/env python3
"""Extract only required artwork from the author's Windows ZIP over HTTP Range.

Does not execute or extract the Windows runtime. Every extracted entry is checked
against its ZIP central-directory size and CRC-32 before being written.
"""
import argparse
import concurrent.futures
import io
import json
import pathlib
import struct
import time
import urllib.request
import zipfile
import zlib

URL = 'https://github.com/jingh12312-rgb/bailong-desktop-pet/releases/download/v0.4.1/bailong-desktop-pet-v0.4.1-windows-x64.zip'
SIZE = 741624526
HERE = pathlib.Path(__file__).resolve().parents[1]
DEST = HERE


class RemoteZip(io.RawIOBase):
    def __init__(self, url=URL, size=SIZE):
        self.url = url
        self.size = size
        self.pos = 0
        self.cache = {}
        self.downloaded = 0

    def fetch(self, start, end):
        end = min(end, self.size - 1)
        request = urllib.request.Request(self.url, headers={
            'Range': f'bytes={start}-{end}', 'User-Agent': 'Bailong-local-mac-port',
            'Accept-Encoding': 'identity',
        })
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    if response.status != 206:
                        raise RuntimeError(f'HTTP Range unsupported (status {response.status}); full ZIP fallback needed')
                    content_range = response.headers.get('Content-Range', '')
                    if not content_range.startswith(f'bytes {start}-{end}/'):
                        raise RuntimeError(f'Wrong range returned: {content_range}')
                    data = response.read()
                    if len(data) != end - start + 1:
                        raise RuntimeError('Truncated HTTP Range response')
                self.downloaded += len(data)
                return data
            except Exception as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        raise last_error

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def read(self, count=-1):
        if count < 0:
            count = self.size - self.pos
        count = min(count, self.size - self.pos)
        if count <= 0:
            return b''
        key = (self.pos, count)
        if key not in self.cache:
            self.cache[key] = self.fetch(self.pos, self.pos + count - 1)
        self.pos += count
        return self.cache[key]


def entry_bytes(info):
    remote = RemoteZip()
    header = remote.fetch(info.header_offset, info.header_offset + min(4096, 30 + len(info.filename.encode('utf-8')) + len(info.extra) + info.compress_size) - 1)
    if header[:4] != b'PK\x03\x04':
        raise RuntimeError(f'Invalid local ZIP header: {info.filename}')
    name_length, extra_length = struct.unpack_from('<HH', header, 26)
    payload_start = 30 + name_length + extra_length
    needed_end = payload_start + info.compress_size
    if len(header) < needed_end:
        header += remote.fetch(info.header_offset + len(header), info.header_offset + needed_end - 1)
    payload = header[payload_start:needed_end]
    if info.compress_type == zipfile.ZIP_STORED:
        data = payload
    elif info.compress_type == zipfile.ZIP_DEFLATED:
        data = zlib.decompress(payload, -15)
    else:
        raise RuntimeError(f'Unsupported compression {info.compress_type}: {info.filename}')
    if len(data) != info.file_size or zlib.crc32(data) & 0xffffffff != info.CRC:
        raise RuntimeError(f'ZIP integrity mismatch: {info.filename}')
    return data, remote.downloaded


def output_relative(name):
    parts = pathlib.PurePosixPath(name).parts
    if 'outputs' not in parts:
        return None
    relative = pathlib.Path(*parts[parts.index('outputs'):])
    if '..' in relative.parts or relative.is_absolute():
        raise RuntimeError(f'Unsafe archive member: {name}')
    return relative


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    remote = RemoteZip()
    with zipfile.ZipFile(remote) as archive:
        infos = archive.infolist()
    listing = [{'name': i.filename, 'bytes': i.file_size, 'compressed': i.compress_size, 'crc32': f'{i.CRC:08x}'} for i in infos]
    (HERE / 'asset-entry-list.json').write_text(json.dumps(listing, ensure_ascii=False, indent=2))
    output_infos = {str(output_relative(i.filename)): i for i in infos if not i.is_dir() and output_relative(i.filename)}
    print(json.dumps({'total_entries': len(infos), 'output_entries': len(output_infos), 'output_files': list(output_infos)}, ensure_ascii=False), flush=True)
    if args.list:
        return
    manifest_keys = [k for k in output_infos if pathlib.Path(k).name == '素材清单.json']
    if len(manifest_keys) != 1:
        raise RuntimeError(f'Expected one artwork manifest: {manifest_keys}')
    manifest_key = manifest_keys[0]
    manifest_data, transferred = entry_bytes(output_infos[manifest_key])
    manifest = json.loads(manifest_data)
    artwork_root = pathlib.Path(manifest_key).parent
    filenames = set()
    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get('file'), str):
                filenames.add(value.get('playbackFile') or value['file'].replace('.webm', '.webp'))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(manifest)
    wanted = {manifest_key} | {str(artwork_root / filename) for filename in filenames}
    missing = sorted(wanted - set(output_infos))
    if missing:
        raise RuntimeError(f'Manifest playback assets missing from archive: {missing}')
    selected = [(pathlib.Path(k), output_infos[k]) for k in sorted(wanted)]
    # Preserve original bundled artwork/third-party notices when available.
    for info in infos:
        parts = pathlib.PurePosixPath(info.filename).parts
        if 'licenses' in parts and not info.is_dir() and info.file_size <= 5_000_000:
            relative = pathlib.Path(*parts[parts.index('licenses'):])
            if '..' not in relative.parts:
                selected.append((relative, info))
    print(json.dumps({'selected_entries': len(selected), 'playback_assets': len(filenames), 'compressed_bytes': sum(i.compress_size for _, i in selected)}, ensure_ascii=False), flush=True)
    results = []
    def extract(pair):
        relative, info = pair
        target = (DEST / relative).resolve()
        if not target.is_relative_to(DEST.resolve()):
            raise RuntimeError(f'Unsafe extraction target: {relative}')
        if target.exists() and target.stat().st_size == info.file_size:
            current = target.read_bytes()
            if zlib.crc32(current) & 0xffffffff == info.CRC:
                return {'path': str(relative), 'bytes': info.file_size, 'downloaded': 0, 'crc32': f'{info.CRC:08x}'}
        data, downloaded = (manifest_data, 0) if str(relative) == manifest_key else entry_bytes(info)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f'Extracted {relative} ({len(data):,} bytes; CRC OK)', flush=True)
        return {'path': str(relative), 'bytes': len(data), 'downloaded': downloaded, 'crc32': f'{info.CRC:08x}'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for result in executor.map(extract, selected):
            results.append(result)
    summary = {'source_url': URL, 'source_archive_bytes': SIZE, 'selected_files': len(results), 'playback_assets': len(filenames), 'transferred_bytes': remote.downloaded + transferred + sum(r['downloaded'] for r in results), 'extracted_bytes': sum(r['bytes'] for r in results), 'files': results}
    (HERE / 'asset-extraction-report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != 'files'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
