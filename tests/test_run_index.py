import datetime
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from utils import run_index  # noqa: E402

DAY = datetime.datetime(2026, 10, 6, 9, 30, 0)
OTHER_DAY = datetime.datetime(2026, 10, 7, 9, 30, 0)


class AllocateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_first_four_ids_of_a_day_are_reserved(self):
        ids = [
            run_index.allocate_run(self.tmp, when=DAY).run_id for _ in range(4)
        ]
        self.assertEqual(ids, ["0114", "0514", "1919", "0810"])

    def test_later_ids_continue_from_0005(self):
        ids = [
            run_index.allocate_run(self.tmp, when=DAY).run_id for _ in range(7)
        ]
        self.assertEqual(
            ids,
            ["0114", "0514", "1919", "0810", "0005", "0006", "0007"],
        )

    def test_same_id_can_repeat_on_another_day(self):
        first = run_index.allocate_run(self.tmp, when=DAY)
        second = run_index.allocate_run(self.tmp, when=OTHER_DAY)
        self.assertEqual(first.run_id, second.run_id)
        self.assertNotEqual(first.path, second.path)
        self.assertTrue(first.path.endswith("20261006-0114"))
        self.assertTrue(second.path.endswith("20261007-0114"))

    def test_existing_reserved_id_is_skipped(self):
        os.makedirs(os.path.join(self.tmp, "20261006-0114"))
        index = run_index.allocate_run(self.tmp, when=DAY)
        self.assertEqual(index.run_id, "0514")

    def test_reserved_numbers_are_skipped_by_the_counter(self):
        for run_id in ("0114", "0514", "1919", "0810"):
            os.makedirs(os.path.join(self.tmp, "20261006-" + run_id))
        for number in range(5, 114):
            os.makedirs(os.path.join(self.tmp, "20261006-%04d" % number))
        index = run_index.allocate_run(self.tmp, when=DAY)
        self.assertEqual(index.run_id, "0115")

    def test_next_run_id_exhaustion(self):
        taken = {"%04d" % number for number in range(10000)}
        with self.assertRaises(RuntimeError):
            run_index.next_run_id(taken)


class FindTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.today = run_index.allocate_run(self.tmp, when=DAY)
        self.next_day = run_index.allocate_run(self.tmp, when=OTHER_DAY)

    def test_find_by_id_prefers_newest_day(self):
        found = run_index.find_run(self.tmp, "0114")
        self.assertIsNotNone(found)
        self.assertEqual(found.day, "20261007")

    def test_find_by_day_id(self):
        found = run_index.find_run(self.tmp, "20261006-0114")
        self.assertEqual(found.path, self.today.path)
        found = run_index.find_run(self.tmp, "20261006/0114")
        self.assertEqual(found.path, self.today.path)

    def test_find_missing_returns_none(self):
        self.assertIsNone(run_index.find_run(self.tmp, "9999"))

    def test_parse_run_ref_rejects_bad_values(self):
        for bad in ("", "114", "abcdef", "20261006", "20261006-114"):
            with self.assertRaises(ValueError):
                run_index.parse_run_ref(bad)

    def test_list_runs_newest_day_first(self):
        runs = run_index.list_runs(self.tmp)
        self.assertEqual([run.day for run in runs], ["20261007", "20261006"])
        self.assertEqual([run.run_id for run in runs], ["0114", "0114"])
        self.assertEqual(len(run_index.list_runs(self.tmp, limit=1)), 1)
        self.assertEqual(
            len(run_index.list_runs(self.tmp, day="20261006")), 1
        )


class MetaTests(unittest.TestCase):
    def test_write_and_read_meta(self):
        tmp = tempfile.mkdtemp()
        index = run_index.allocate_run(tmp, when=DAY)
        run_index.write_meta(
            index.path, {"run_id": index.run_id, "batch_label": "demo"}
        )
        meta = run_index.read_meta(index.path)
        self.assertEqual(meta["run_id"], "0114")
        self.assertEqual(meta["batch_label"], "demo")
        self.assertEqual(run_index.read_meta(os.path.join(tmp, "nope")), {})


if __name__ == "__main__":
    unittest.main()
