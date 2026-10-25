"""Offline checks for Mac's bounded animation cache and original artwork."""
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image, ImageDraw
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from animation_frames import AnimationFrameStore, LazyAnimationFrames


APP = QApplication.instance() or QApplication([])
ARTWORK = Path(__file__).resolve().parents[1] / 'outputs' / '白龙桌宠素材'


def pixmap_bytes(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return bytes(image.constBits())


def pillow_reference(path, index, size):
    # Normalize through the same Qt pixel format so its premultiplied-alpha
    # roundoff is not mistaken for an animation decoder error.
    with Image.open(path) as image:
        image.seek(index)
        image = image.convert('RGBA')
        if image.size != (size, size):
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        raw = image.tobytes()
    return QPixmap.fromImage(QImage(raw, size, size, size * 4,
                                   QImage.Format.Format_RGBA8888).copy())


class AnimationCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.paths = []
        for variant in range(3):
            frames = []
            for index in range(6):
                image = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                color = [(255, 0, 0, 255), (0, 255, 0, 128),
                         (0, 0, 255, 64)][(index + variant) % 3]
                draw.rectangle((index, 2, index + 7, 12), fill=color)
                draw.point((15, 15), fill=(255, 255, 255, 255))
                frames.append(image)
            path = Path(self.directory.name) / f'animation-{variant}.webp'
            frames[0].save(path, format='WEBP', save_all=True,
                           append_images=frames[1:], lossless=True, exact=True,
                           duration=40, loop=0)
            self.paths.append(path)
        self.stores = []

    def tearDown(self):
        for store in self.stores:
            store.close()
        self.directory.cleanup()

    def store(self, **kwargs):
        store = AnimationFrameStore(**kwargs)
        self.stores.append(store)
        return store

    def test_forward_backward_random_seek_and_alpha(self):
        store = self.store(max_bytes=16 * 16 * 4 * 2)
        animation = LazyAnimationFrames(store, self.paths[0], 16)
        self.assertEqual(len(animation), 6)
        for index in (0, 1, 5, 2, 4, 0, 3, 5, -1, -6):
            expected = pillow_reference(self.paths[0], index % 6, 16)
            self.assertEqual(pixmap_bytes(animation[index]), pixmap_bytes(expected))
            self.assertLessEqual(store.cached_bytes, store.max_bytes)
        alpha = pixmap_bytes(animation[1])[3::4]
        self.assertIn(0, alpha)
        self.assertIn(128, alpha)
        self.assertIn(255, alpha)

    def test_lru_hits_and_eviction_enforce_byte_budget(self):
        cost = 16 * 16 * 4
        store = self.store(max_bytes=2 * cost)
        first = store.frame(self.paths[0], 16, 0)
        store.frame(self.paths[0], 16, 1)
        self.assertEqual(first.cacheKey(), store.frame(self.paths[0], 16, 0).cacheKey())
        store.frame(self.paths[0], 16, 2)
        self.assertEqual(list(store.frames), [(str(self.paths[0]), 16, 0),
                                              (str(self.paths[0]), 16, 2)])
        self.assertEqual(store.cached_bytes, 2 * cost)
        self.assertEqual(sum(cost for _, cost in store.frames.values()), store.cached_bytes)

    def test_oversized_frame_is_returned_but_never_cached(self):
        store = self.store(max_bytes=1023)
        result = store.frame(self.paths[0], 16, 0)
        self.assertEqual((result.width(), result.height()), (16, 16))
        self.assertEqual(store.cached_bytes, 0)
        self.assertFalse(store.frames)

    def test_decoder_eviction_closes_old_image_and_can_reopen(self):
        store = self.store(max_bytes=0, max_decoders=2)
        store.frame(self.paths[0], 16, 0)
        first_decoder = store.decoders[str(self.paths[0])]
        store.frame(self.paths[1], 16, 1)
        store.frame(self.paths[2], 16, 2)
        self.assertNotIn(str(self.paths[0]), store.decoders)
        self.assertEqual(len(store.decoders), 2)
        with self.assertRaises(ValueError):
            first_decoder.getpixel((0, 0))
        reopened = store.frame(self.paths[0], 16, 5)
        self.assertEqual(pixmap_bytes(reopened),
                         pixmap_bytes(pillow_reference(self.paths[0], 5, 16)))
        self.assertEqual(len(store.decoders), 2)

    def test_indices_close_and_reuse(self):
        store = self.store()
        animation = LazyAnimationFrames(store, self.paths[0], 16)
        for index in (-7, 6):
            with self.assertRaises(IndexError):
                animation[index]
        animation[0]
        store.close()
        store.close()
        self.assertEqual(store.cached_bytes, 0)
        self.assertFalse(store.frames)
        self.assertFalse(store.decoders)
        self.assertFalse(animation[1].isNull())


@unittest.skipUnless((ARTWORK / '素材清单.json').is_file(), 'Original artwork not installed')
class OriginalArtworkTests(unittest.TestCase):
    def test_all_manifest_animations_have_expected_alpha_frames(self):
        manifest = json.loads((ARTWORK / '素材清单.json').read_text(encoding='utf-8'))
        items = [manifest['idle']] + manifest.get('additionalIdleAnimations', [])
        items += manifest['variants']
        items += [value for value in manifest.get('workAnimations', []) if value]
        items += [manifest[key] for key in ('dragAnimation', 'landingAnimation', 'quotaAnimation')]
        self.assertEqual(len(items), 25)
        for item in items:
            path = ARTWORK / (item.get('playbackFile') or item['file'].replace('.webm', '.webp'))
            with self.subTest(animation=item['id']), Image.open(path) as image:
                self.assertEqual(image.format, 'WEBP')
                self.assertEqual(image.size, (720, 720))
                self.assertEqual(image.mode, 'RGBA')
                self.assertEqual(image.n_frames, round(item['durationMs'] * 24 / 1000))
                self.assertEqual(image.convert('RGBA').getchannel('A').getextrema(), (0, 255))

    def test_real_artwork_seek_resize_and_alpha_match_pillow(self):
        manifest = json.loads((ARTWORK / '素材清单.json').read_text(encoding='utf-8'))
        path = ARTWORK / manifest['idle']['playbackFile']
        store = AnimationFrameStore(max_bytes=3 * 64 * 64 * 4)
        try:
            animation = LazyAnimationFrames(store, path, 64)
            for index in (0, 1, 47, 95, 4, 0):
                expected = pillow_reference(path, index, 64)
                self.assertEqual(pixmap_bytes(animation[index]), pixmap_bytes(expected))
                self.assertLessEqual(store.cached_bytes, store.max_bytes)
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
