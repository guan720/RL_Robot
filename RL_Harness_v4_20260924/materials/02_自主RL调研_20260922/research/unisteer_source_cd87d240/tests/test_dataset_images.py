from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from src.dataset.dataset import load_traj_image_frame_chw_uint8
from src.tool.prepare_data import prepare_data


class DatasetImageLayoutTest(unittest.TestCase):
    def test_loads_tchw_and_thwc_as_chw(self) -> None:
        expected = np.arange(3 * 4 * 5, dtype=np.uint8).reshape(3, 4, 5)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tchw_dir = root / "tchw"
            thwc_dir = root / "thwc"
            tchw_dir.mkdir()
            thwc_dir.mkdir()
            np.save(tchw_dir / "primary.npy", expected[None])
            np.save(thwc_dir / "primary.npy", np.transpose(expected, (1, 2, 0))[None])

            tchw = load_traj_image_frame_chw_uint8(tchw_dir, "primary_image_crop", 0)
            thwc = load_traj_image_frame_chw_uint8(thwc_dir, "primary_image_crop", 0)

        self.assertEqual(tchw.shape, (3, 4, 5))
        self.assertTrue(tchw.flags.c_contiguous)
        np.testing.assert_array_equal(tchw, expected)
        np.testing.assert_array_equal(thwc, expected)

    def test_prepares_frame_directories_as_tchw_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            trajectory = root / "trajectory_000"
            trajectory.mkdir()
            np.save(trajectory / "action.npy", np.zeros((2, 7), dtype=np.float32))
            for camera_name in ("primary_image_crop", "wrist_image_crop"):
                frame_dir = trajectory / "images" / camera_name
                frame_dir.mkdir(parents=True)
                Image.fromarray(np.full((4, 5, 3), 11, dtype=np.uint8)).save(frame_dir / "2.jpg")
                Image.fromarray(np.full((4, 5, 3), 23, dtype=np.uint8)).save(frame_dir / "10.jpg")

            first_result = prepare_data(root)
            second_result = prepare_data(root)
            primary = np.load(trajectory / "primary.npy")
            wrist = np.load(trajectory / "wrist.npy")

        self.assertEqual(
            first_result, {"trajectories": 1, "converted_arrays": 2, "reused_arrays": 0}
        )
        self.assertEqual(
            second_result, {"trajectories": 1, "converted_arrays": 0, "reused_arrays": 2}
        )
        self.assertEqual(primary.shape, (2, 3, 4, 5))
        self.assertEqual(wrist.shape, (2, 3, 4, 5))
        self.assertTrue(primary.flags.c_contiguous)
        np.testing.assert_allclose(primary[:, 0, 0, 0], [11, 23], atol=1)
        np.testing.assert_allclose(wrist[:, 0, 0, 0], [11, 23], atol=1)

    def test_removes_partial_array_after_frame_shape_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            trajectory = Path(tmp_dir) / "trajectory_000"
            frame_dir = trajectory / "images" / "primary_image_crop"
            frame_dir.mkdir(parents=True)
            np.save(trajectory / "action.npy", np.zeros((2, 7), dtype=np.float32))
            Image.fromarray(np.zeros((4, 5, 3), dtype=np.uint8)).save(frame_dir / "0.jpg")
            Image.fromarray(np.zeros((5, 5, 3), dtype=np.uint8)).save(frame_dir / "1.jpg")

            with self.assertRaisesRegex(ValueError, "Inconsistent image shape"):
                prepare_data(trajectory)

            self.assertFalse((trajectory / "primary.npy").exists())
            self.assertFalse((trajectory / ".primary.npy.tmp").exists())


if __name__ == "__main__":
    unittest.main()
