import tempfile
import unittest
from pathlib import Path

from gitgraph import discover_repos, parse_graph, first_commit_index


class ParseGraphTests(unittest.TestCase):
    def test_commit_and_connector_lines(self):
        sample = (
            "* \t@@\taaa111\t@@\t111aaaa\t@@\t2026-09-12\t@@\tPack the exe\t@@\tHEAD -> main\n"
            "|\\\n"
            "| * \t@@\tbbb222\t@@\t222bbbb\t@@\t2026-09-11\t@@\tEarlier work\t@@\t\n"
        )
        lines = parse_graph(sample)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0].short_hash, "111aaaa")
        self.assertEqual(lines[0].subject, "Pack the exe")
        self.assertEqual(lines[0].refs, "HEAD -> main")
        self.assertIsNone(lines[1].full_hash)
        self.assertIn("|\\", lines[1].display)
        self.assertEqual(lines[2].short_hash, "222bbbb")
        self.assertEqual(first_commit_index(lines), 0)

    def test_connector_first_skips_to_commit(self):
        sample = "|\n* \t@@\taaa\t@@\taaa\t@@\t2026-01-01\t@@\thi\t@@\t\n"
        lines = parse_graph(sample)
        self.assertEqual(first_commit_index(lines), 1)


class DiscoverTests(unittest.TestCase):
    def test_finds_nested_git_and_skips_node_modules(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "app" / ".git").mkdir(parents=True)
            junk = root / "node_modules" / "pkg"
            junk.mkdir(parents=True)
            (junk / ".git").mkdir()
            repos = discover_repos(root)
            paths = [repo.path for repo in repos]
            self.assertEqual(paths, [root / "app"])

    def test_root_repo_counts(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".git").mkdir()
            repos = discover_repos(root)
            self.assertEqual(len(repos), 1)
            self.assertEqual(repos[0].path, root.resolve())


if __name__ == "__main__":
    unittest.main()
