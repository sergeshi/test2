import unittest

from runtime_bridge import normalize_snapshot


class NormalizeSnapshotTests(unittest.TestCase):
    def test_position_and_size(self):
        result = normalize_snapshot({
            "name": "Room",
            "units": "cm",
            "objects": [{"name": "Floor", "position": [0, 0, -5], "size": [10, 20, 2]}],
        })
        self.assertEqual(result["name"], "Room")
        self.assertEqual(result["objects"][0]["position"], [0.0, 0.0, -5.0])
        self.assertEqual(result["objects"][0]["size"], [10.0, 20.0, 2.0])

    def test_bounds_convert_to_center_and_size(self):
        result = normalize_snapshot({
            "objects": [{"name": "Wall", "bounds": [[-5, -10, 0], [5, 10, 30]]}],
        })
        item = result["objects"][0]
        self.assertEqual(item["position"], [0.0, 0.0, 15.0])
        self.assertEqual(item["size"], [10.0, 20.0, 30.0])

    def test_invalid_object_is_skipped(self):
        result = normalize_snapshot({"objects": [{"position": ["bad", 0, 0]}]})
        self.assertEqual(result["objects"], [])

    def test_non_object_root_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_snapshot([])


if __name__ == "__main__":
    unittest.main()
