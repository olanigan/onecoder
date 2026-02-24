import unittest
from click.testing import CliRunner
from onecoder.commands.agent import agent as agent_command


class TestAgentCommand(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_agent_help(self):
        """Verify the agent command group is reachable."""
        result = self.runner.invoke(agent_command, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Universal Agent Orchestration", result.output)

    def test_agent_start_help(self):
        """Verify the start command help is reachable."""
        result = self.runner.invoke(agent_command, ["start", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--cmd", result.output)


if __name__ == "__main__":
    unittest.main()
