import tempfile
import unittest
from pathlib import Path

from tools.check_constraints import ROOT, check_repository


CPU = "requirements/constraints-linux-cpu.txt"
CUDA = "requirements/constraints-linux-cuda.txt"


def write_minimal_tree(root: Path) -> None:
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.12,<3.14"\n',
        "requirements.txt": "numpy>=1\n",
        "requirements-models-linux.txt": "torch>=2\ntensorflow>=2\n",
        "requirements-crispai.txt": "setuptools<81\n",
        "requirements/requirements-linux-cpu.txt": "-r ../requirements-linux.txt\ntorch==2.10.*\n",
        "requirements/requirements-linux-cuda.txt": "-r ../requirements-linux.txt\ntorch==2.10.*\ntensorflow[and-cuda]==2.20.*\n",
        CPU: (
            "# Generated: test\n# Environment: test\n# Validation: test\n"
            "# Install: pip install -c requirements/constraints-linux-cpu.txt "
            "-r requirements/requirements-linux-cpu.txt\n"
            "numpy==1\ntorch==2.10.0+cpu\nsetuptools==80.9.0\n"
        ),
        CUDA: (
            "# Generated: test\n# Environment: test\n# Validation: test\n"
            "# Install: pip install -c requirements/constraints-linux-cuda.txt "
            "-r requirements/requirements-linux-cuda.txt\n"
            "numpy==1\ntorch==2.10.0\ntensorflow==2.20.0\n"
            "nvidia-nccl-cu12==2.27.5\nsetuptools==80.9.0\n"
        ),
        "README.md": """# README

Python >=3.12,<3.14 is supported; recommended version: Python 3.12.
The commands below use compatible dependency ranges, not pinned versions.

```powershell
py -3.12 -m venv .venv
pip install -r requirements-windows.txt
```

```bash
python3.12 -m venv .venv
pip install -r requirements.txt
```

Formal CPU/CUDA snapshots are documented in docs/ENVIRONMENT.md using
requirements/constraints-linux-cpu.txt with requirements/requirements-linux-cpu.txt,
and requirements/constraints-linux-cuda.txt with requirements/requirements-linux-cuda.txt.
""",
        "docs/ENVIRONMENT.md": """# Environment

Python >=3.12,<3.14 is supported; recommended version: Python 3.12.

```bash
python -m pip install -c requirements/constraints-linux-cpu.txt \
  -r requirements/requirements-linux-cpu.txt
```

```bash
python -m pip install -c requirements/constraints-linux-cuda.txt \
  -r requirements/requirements-linux-cuda.txt
```
""",
        "docs/help_en/index.md": """# English help

The source tree supports Python >=3.12,<3.14 and recommends Python 3.12.
The requirements files below define compatible dependency ranges; they are not pinned.

```powershell
py -3.12 -m venv .venv
pip install -r requirements-windows.txt
```

```bash
python3.12 -m venv .venv
pip install -r requirements.txt
```

Formal CPU/CUDA snapshots are documented in ../ENVIRONMENT.md using
requirements/constraints-linux-cpu.txt with requirements/requirements-linux-cpu.txt,
and requirements/constraints-linux-cuda.txt with requirements/requirements-linux-cuda.txt.
""",
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

    def test_constraint_headers_must_reference_formal_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_tree(root)
            cpu = root / CPU
            cpu.write_text(
                cpu.read_text(encoding="utf-8").replace(
                    "-r requirements/requirements-linux-cpu.txt",
                    "-r requirements-linux.txt",
                ),
                encoding="utf-8",
            )
            cuda = root / CUDA
            cuda.write_text(
                cuda.read_text(encoding="utf-8").replace(
                    "-r requirements/requirements-linux-cuda.txt",
                    "-r requirements-linux.txt",
                ),
                encoding="utf-8",
            )

            errors = check_repository(root)
            self.assertTrue(any(CPU in error and "install header must pair" in error
                                for error in errors), errors)
            self.assertTrue(any(CUDA in error and "install header must pair" in error
                                for error in errors), errors)

    def test_environment_command_must_pair_constraint_and_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_tree(root)
            environment = root / "docs/ENVIRONMENT.md"
            environment.write_text(
                environment.read_text(encoding="utf-8").replace(
                    "-r requirements/requirements-linux-cpu.txt",
                    "-r requirements-linux.txt",
                ),
                encoding="utf-8",
            )

            errors = check_repository(root)
            self.assertTrue(any(
                "docs/ENVIRONMENT.md: CPU install command must pair" in error
                for error in errors
            ), errors)

    def test_english_help_rejects_python_313_and_pinned_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_tree(root)
            help_page = root / "docs/help_en/index.md"
            help_page.write_text(
                help_page.read_text(encoding="utf-8")
                .replace("Python >=3.12,<3.14", "Python 3.13")
                .replace(
                    "compatible dependency ranges; they are not pinned",
                    "pinned requirements",
                ),
                encoding="utf-8",
            )

            errors = check_repository(root)
            self.assertTrue(any(
                "docs/help_en/index.md: must declare Python >=3.12,<3.14" in error
                for error in errors
            ), errors)
            self.assertTrue(any("pinned requirements" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
