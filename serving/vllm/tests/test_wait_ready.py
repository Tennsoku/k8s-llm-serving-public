from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


VLLM_DIR = Path(__file__).resolve().parents[1]
WAIT_READY = VLLM_DIR / "wait-ready.sh"


class WaitReadyTests(unittest.TestCase):
    def test_exited_container_ends_readiness_wait(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "server"
            fake_bin = root / "bin"
            output.mkdir()
            fake_bin.mkdir()

            (output / "server-start-ns.txt").write_text(
                f"{time.time_ns()}\n", encoding="utf-8"
            )
            (output / "container-id.txt").write_text(
                "test-container-id\n", encoding="utf-8"
            )
            (output / "base-url.txt").write_text(
                "http://127.0.0.1:8042\n", encoding="utf-8"
            )

            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                "#!/bin/sh\nprintf '000'\nexit 7\n", encoding="utf-8"
            )
            fake_curl.chmod(0o755)
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                "#!/bin/sh\nfor last; do :; done\n"
                "[ \"${last}\" = test-container-id ] || exit 2\n"
                "printf 'exited false 1\\n'\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            process = subprocess.run(
                [
                    str(WAIT_READY),
                    "--output-dir",
                    str(output),
                    "--timeout",
                    "30",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                env=environment,
            )

            self.assertEqual(process.returncode, 1, process.stderr)
            result = dict(
                line.split("=", 1)
                for line in (output / "ready-result.env")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            self.assertEqual(result["ready"], "false")
            self.assertEqual(result["attempts"], "1")
            self.assertEqual(result["failure_reason"], "container_exited")
            self.assertEqual(result["container_status"], "exited")
            self.assertEqual(result["container_running"], "false")
            self.assertEqual(result["container_exit_code"], "1")
            self.assertLess(float(result["server_ready_seconds"]), 5.0)
            attempts = (output / "readiness-attempts.tsv").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(attempts), 2)
            self.assertEqual(
                (output / "health.txt").read_text(encoding="utf-8"), "000\n"
            )


if __name__ == "__main__":
    unittest.main()
