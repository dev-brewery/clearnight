import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from clearnight.cache import Cache


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Cache(Path(self.tmp.name))

    def test_put_get_roundtrip(self):
        self.cache.put("data.bin", b"hello sky")
        self.assertEqual(self.cache.get("data.bin", 3600), b"hello sky")

    def test_fresh_within_age(self):
        self.cache.put("k", b"x")
        self.assertTrue(self.cache.fresh("k", 60))
        self.assertFalse(self.cache.fresh("k", 0))

    def test_fresh_false_after_age(self):
        self.cache.put("k", b"x")
        p = self.cache.path("k")
        old = time.time() - 7200
        os.utime(p, (old, old))
        self.assertFalse(self.cache.fresh("k", 3600))
        self.assertIsNone(self.cache.get("k", 3600))

    def test_get_missing(self):
        self.assertIsNone(self.cache.get("nope", 60))

    def test_max_age_none_never_expires(self):
        self.cache.put("k", b"x")
        ancient = time.time() - 10**9
        os.utime(self.cache.path("k"), (ancient, ancient))
        self.assertEqual(self.cache.get("k", None), b"x")

    def test_age(self):
        self.assertIsNone(self.cache.age("nope"))
        self.cache.put("k", b"x")
        a = self.cache.age("k")
        self.assertIsNotNone(a)
        self.assertLess(a, 60)

    def test_traversal_rejected(self):
        for bad in ("../evil", "a/b", "", "..", "a\\b"):
            with self.assertRaises(ValueError):
                self.cache.path(bad)

    def test_init_creates_root(self):
        with TemporaryDirectory() as d:
            root = Path(d) / "nested" / "cache"
            Cache(root)
            self.assertTrue(root.is_dir())


if __name__ == "__main__":
    unittest.main()
