"""Decode animation frames on demand within a shared, bounded pixel cache."""
from collections import OrderedDict
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QImage, QPixmap


class AnimationFrameStore:
    def __init__(self, max_bytes=128 * 1024 * 1024, max_decoders=2):
        self.max_bytes = max_bytes
        self.max_decoders = max_decoders
        self.frames = OrderedDict()
        self.decoders = OrderedDict()
        self.cached_bytes = 0

    def frame(self, path, size, index):
        key = (str(path), size, index)
        if key in self.frames:
            self.frames.move_to_end(key)
            return self.frames[key][0]
        name = str(path)
        if name not in self.decoders:
            self.decoders[name] = Image.open(path)
        self.decoders.move_to_end(name)
        while len(self.decoders) > self.max_decoders:
            _, old = self.decoders.popitem(last=False)
            old.close()
        source = self.decoders[name]
        source.seek(index)
        image = source.convert('RGBA')
        if image.size != (size, size):
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        raw = image.tobytes()
        pixmap = QPixmap.fromImage(QImage(raw, size, size, size * 4, QImage.Format.Format_RGBA8888).copy())
        cost = size * size * 4
        # Even an oversized individual frame must not violate the cache limit.
        if cost <= self.max_bytes:
            while self.frames and self.cached_bytes + cost > self.max_bytes:
                _, (_, old_cost) = self.frames.popitem(last=False)
                self.cached_bytes -= old_cost
            self.frames[key] = (pixmap, cost)
            self.cached_bytes += cost
        return pixmap

    def close(self):
        for decoder in self.decoders.values():
            decoder.close()
        self.decoders.clear()
        self.frames.clear()
        self.cached_bytes = 0

    def __del__(self):
        self.close()


class LazyAnimationFrames:
    def __init__(self, store, path, size):
        self.store, self.path, self.size = store, Path(path), size
        with Image.open(self.path) as source:
            self.count = getattr(source, 'n_frames', 1)
        if self.count < 1:
            raise ValueError('动画没有可播放帧：' + str(path))

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        return self.store.frame(self.path, self.size, index)
