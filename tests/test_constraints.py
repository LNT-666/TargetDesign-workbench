import tempfile
import unittest
from pathlib import Path

from tools.check_constraints import ROOT, check_repository


CPU = "requirements/constraints-linux-cpu.txt"
CUDA = "requirements/constraints-linux-cuda.txt"


def write_minimal_tree(root: Path) -> None:
    files = {
        "requirements.txt": "numpy>=1\n",
        "requirements-models-linux.txt": "torch>=2\ntensorflow>=2\n",
        "requirements-crispai.txt": "setuptools<81\n",
        "requirements/requirements-linux-cpu.txt": "-r ../requirements-linux.txt\ntorch==2.10.*\n",
        "requirements/requirements-linux-cuda.txt": "-r ../requirements-linux.txt\ntorch==2.10.*\ntensorflow[and-cuda]==2.20.*\n",
        CPU: (
            "# Generated: test\n# Environment: test\n# Validation: test\n"
            "numpy==1\ntorch==2.10.0+cpu\nsetuptools==80.9.0\n"
        ),
        CUDA: (
            "# Generated: test\n# Environment: test\n# Validation: test\n"
            "numpy==1\ntorch==2.10.0\ntensorflow==2.20.0\n"
            "nvidia-nccl-cu12==2.27.5\nsetuptools==80.9.0\n"
        ),
        "Dockerfile": "RUN python -m pip install -c requirements/constraints-linux-cpu.txt -r requirements.txt\n",
        ".github/workflows/portability.yml": "run: python -m pip install -c requirements/constraints-linux-cpu.txt -r requirements.txt\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class ConstraintSnapshotTests(unittest.TestCase):
    def test_repository_snapshots_are_complete(self):
        self.assertEqual(check_repository(ROOT), [])

    def test_missing_direct_pin_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_tree(root)
            cpu = root / CPU
            cpu.write_text(
                cpu.read_text(encoding="utf-8").replace("numpy==1\n", ""),
                encoding="utf-8",
            )
            errors = check_repository(root)
            self.assertTrue(any("missing pins for: numpy" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
