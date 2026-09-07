import io
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout, redirect_stderr
from unittest import TestCase
from unittest.mock import patch
from sentiment.run_progress import logged_run, stage_progress
from scripts import update_index


class ProgressTests(TestCase):
    def test_console_log_and_heartbeat_stop(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "run.log"
            console = io.StringIO()
            with redirect_stdout(console), redirect_stderr(console), logged_run(path):
                with stage_progress("测试步骤", interval=.01):
                    time.sleep(.035)
                count = console.getvalue().count("仍在运行")
                time.sleep(.03)
                self.assertEqual(console.getvalue().count("仍在运行"), count)
            self.assertGreater(count, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), console.getvalue())

    def test_failure_announced_immediately_and_other_steps_continue(self):
        calls = []
        def market(root):
            calls.append("market")
            raise ValueError("模拟来源不可用")
        def community(root):
            calls.append("community")
            return {"meta": {"tradeDate": "2026-09-07"}}
        def report(root):
            calls.append("report")
            return {"meta": {"tradeDate": "2026-09-07"}}
        out = io.StringIO()
        with patch.object(update_index, "build_market_snapshot", market), patch.object(update_index, "build_snapshot", community), patch.object(update_index, "build_report", report), redirect_stdout(out), redirect_stderr(out):
            self.assertEqual(update_index.run_steps(), 1)
            self.assertEqual(calls, ["market", "community", "report"])
            self.assertLess(out.getvalue().index("步骤失败"), out.getvalue().index("开始：2/3"))
            self.assertIn("运行结束：成功 2/3", out.getvalue())
            calls.clear()
            self.assertEqual(update_index.run_steps("community"), 0)
            self.assertEqual(calls, ["community"])
