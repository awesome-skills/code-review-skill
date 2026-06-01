#!/usr/bin/env python3
"""Tests for pr-analyzer.py diff parsing (stdlib unittest, no extra deps)."""

import importlib.util
import os
import unittest

# The script has a hyphen in its name, so load it by path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'pr_analyzer', os.path.join(_HERE, 'pr-analyzer.py')
)
pr_analyzer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr_analyzer)


class ParseDiffFilenameTest(unittest.TestCase):
    def test_lib_prefixed_path(self):
        # "lib/" embeds a literal "b/" that the old regex swallowed.
        diff = (
            "diff --git a/lib/foo.py b/lib/foo.py\n"
            "index 1234567..89abcde 100644\n"
            "--- a/lib/foo.py\n"
            "+++ b/lib/foo.py\n"
            "@@ -1,2 +1,3 @@\n"
            " unchanged\n"
            "+added line\n"
            "-removed line\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].filename, 'lib/foo.py')
        self.assertEqual(files[0].additions, 1)
        self.assertEqual(files[0].deletions, 1)

    def test_normal_path(self):
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "index 1111111..2222222 100644\n"
            "--- a/src/main.py\n"
            "+++ b/src/main.py\n"
            "@@ -0,0 +1 @@\n"
            "+print('hi')\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].filename, 'src/main.py')

    def test_other_embedded_b_slash_prefixes(self):
        # web/ and db/ also contain a literal "b/".
        diff = (
            "diff --git a/web/x.js b/web/x.js\n"
            "+++ b/web/x.js\n"
            "+console.log(1)\n"
            "diff --git a/db/y.sql b/db/y.sql\n"
            "+++ b/db/y.sql\n"
            "+SELECT 1;\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual([f.filename for f in files], ['web/x.js', 'db/y.sql'])

    def test_rename_falls_back_to_b_side(self):
        diff = (
            "diff --git a/old/name.py b/new/name.py\n"
            "similarity index 100%\n"
            "rename from old/name.py\n"
            "rename to new/name.py\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].filename, 'new/name.py')


if __name__ == '__main__':
    unittest.main()
