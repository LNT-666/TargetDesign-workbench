import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "container.yml"


class ContainerWorkflowTests(unittest.TestCase):
    def test_verification_run_builds_full_image_without_publishing(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Build the full image locally for verification", text)
        self.assertIn("Smoke test the full image", text)
        self.assertIn("load: true", text)
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && !inputs.publish && inputs.build_full",
            text,
        )

    def test_full_publish_requires_explicit_publish_input(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Publish the full image", text)
        self.assertIn(
            "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')",
            text,
        )
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && inputs.publish == true && inputs.build_full == true",
            text,
        )
        self.assertNotIn(
            "if: ${{ github.event_name == 'push' || inputs.build_full }}",
            text,
        )


if __name__ == "__main__":
    unittest.main()
