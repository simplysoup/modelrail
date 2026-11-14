"""Permission-gating tests for the ModelRail MCP server.

Run with: python -m pytest mcp/tests/ -q
or:       python -m unittest discover -s mcp/tests -v
Uses only the standard library and the fake backend.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server as mcp_server  # noqa: E402


def make_request(method, params=None, req_id=1):
    req = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        req["params"] = params
    return req


class GatingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        mcp_server.AUDIT_LOG = os.path.join(self.tmp.name, "audit.log")
        self.backend = mcp_server.FakeBackend()

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, tool, args):
        req = make_request("tools/call", {"name": tool, "arguments": args})
        return mcp_server.handle_request(req, self.backend)

    def audit_lines(self):
        if not os.path.exists(mcp_server.AUDIT_LOG):
            return []
        with open(mcp_server.AUDIT_LOG, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_write_without_approval_is_rejected(self):
        resp = self.call("promote_model", {"model": "mobilenetv3-cifar10", "version": "3", "alias": "champion"})
        self.assertIn("error", resp)
        self.assertIn("approval", resp["error"]["message"])
        self.assertEqual(self.audit_lines(), [])

    def test_write_with_approval_false_is_rejected(self):
        resp = self.call("rollback", {"approval": False, "reason": "bad model"})
        self.assertIn("error", resp)
        self.assertEqual(self.audit_lines(), [])

    def test_write_with_approval_but_no_reason_is_rejected(self):
        resp = self.call("rollback", {"approval": True})
        self.assertIn("error", resp)
        self.assertIn("reason", resp["error"]["message"])
        self.assertEqual(self.audit_lines(), [])

    def test_write_with_approval_and_reason_succeeds_and_audits(self):
        resp = self.call("promote_model", {
            "model": "mobilenetv3-cifar10", "version": "3",
            "alias": "champion", "approval": True, "reason": "gate passed",
        })
        self.assertNotIn("error", resp)
        lines = self.audit_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["tool"], "promote_model")
        self.assertEqual(lines[0]["args"]["reason"], "gate passed")
        self.assertIn("timestamp", lines[0])

    def test_rollback_with_approval_succeeds_and_audits(self):
        resp = self.call("rollback", {"approval": True, "reason": "canary error rate high"})
        self.assertNotIn("error", resp)
        self.assertEqual(len(self.audit_lines()), 1)
        self.assertEqual(self.audit_lines()[0]["tool"], "rollback")

    def test_read_tools_need_no_approval(self):
        for tool in ["list_models", "get_deploy_status", "get_slo_status"]:
            resp = self.call(tool, {})
            self.assertNotIn("error", resp, tool)
        resp = self.call("compare_runs", {"run_ids": ["run-a", "run-b"]})
        self.assertNotIn("error", resp)
        self.assertEqual(self.audit_lines(), [])

    def test_no_delete_tools_listed(self):
        req = make_request("tools/list")
        resp = mcp_server.handle_request(req, self.backend)
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertNotIn("delete_model", names)
        self.assertNotIn("delete_run", names)
        self.assertTrue(all("delete" not in n for n in names))
        self.assertEqual(sorted(names), sorted(mcp_server.ALL_TOOLS))

    def test_unknown_tool_is_rejected(self):
        resp = self.call("delete_model", {"approval": True, "reason": "x"})
        self.assertIn("error", resp)
        self.assertEqual(self.audit_lines(), [])

    def test_promote_to_invalid_alias_is_rejected(self):
        resp = self.call("promote_model", {
            "model": "mobilenetv3-cifar10", "version": "3",
            "alias": "production", "approval": True, "reason": "test",
        })
        self.assertIn("error", resp)


if __name__ == "__main__":
    unittest.main()
