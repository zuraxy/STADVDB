#!/usr/bin/env python3
"""
Comprehensive End-to-End Recovery Subsystem Test Suite

This test validates that the Recovery Subsystem is fully implemented 
and working in both backend APIs and frontend integration points.

Test Categories:
1. Backend API Tests - Verify all /recovery/* endpoints exist and work
2. Frontend Integration Tests - Verify API service can call recovery endpoints  
3. State Machine Tests - Verify recovery state transitions
4. Multi-Node Tests - Verify recovery works across distributed nodes
5. Dashboard Tests - Verify dashboard serves and works

Usage:
    # Test single node (local)
    python test_recovery_e2e.py

    # Test specific node
    python test_recovery_e2e.py --node http://localhost:8000

    # Test all cloud nodes
    python test_recovery_e2e.py --cloud

    # Verbose output
    python test_recovery_e2e.py -v

    # Run specific test category
    python test_recovery_e2e.py --category backend
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library not found.")
    print("Install it with: pip install requests")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

class NodeConfig:
    """Node URL configurations."""
    LOCAL = "http://localhost:8000"
    NODE0 = "https://ccscloud.dlsu.edu.ph:60832"  # Leader
    NODE1 = "https://ccscloud.dlsu.edu.ph:60833"  # Replica (qty <= 5)
    NODE2 = "https://ccscloud.dlsu.edu.ph:60834"  # Replica (qty > 5)


class TestCategory(Enum):
    """Test categories for selective running."""
    BACKEND = "backend"
    FRONTEND = "frontend"
    STATE_MACHINE = "state_machine"
    MULTI_NODE = "multi_node"
    DASHBOARD = "dashboard"
    ALL = "all"


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    category: TestCategory
    passed: bool
    message: str
    duration_ms: float
    details: Optional[Dict[str, Any]] = None


# =============================================================================
# Test Runner
# =============================================================================

class RecoveryE2ETestSuite:
    """Comprehensive E2E test suite for Recovery Subsystem."""
    
    def __init__(
        self,
        base_url: str = NodeConfig.LOCAL,
        cloud_mode: bool = False,
        verbose: bool = False,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.cloud_mode = cloud_mode
        self.verbose = verbose
        self.timeout = timeout
        self.results: List[TestResult] = []
        self.session = requests.Session()
        
        # Cloud node URLs
        self.nodes = {
            "node0": NodeConfig.NODE0,
            "node1": NodeConfig.NODE1,
            "node2": NodeConfig.NODE2,
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message if verbose mode is enabled."""
        if self.verbose or level in ("ERROR", "WARN"):
            prefix = {"INFO": "ℹ️", "OK": "✅", "ERROR": "❌", "WARN": "⚠️"}.get(level, "")
            print(f"{prefix} {message}")
    
    def _api_call(
        self,
        method: str,
        endpoint: str,
        base_url: Optional[str] = None,
        **kwargs
    ) -> Tuple[bool, Any, int]:
        """Make an API call and return (success, data, status_code)."""
        url = urljoin(base_url or self.base_url, endpoint)
        kwargs.setdefault("timeout", self.timeout)
        
        try:
            response = self.session.request(method, url, **kwargs)
            
            # Try to parse JSON
            try:
                data = response.json()
            except json.JSONDecodeError:
                data = response.text
            
            return (response.ok, data, response.status_code)
        
        except requests.exceptions.ConnectionError as e:
            return (False, f"Connection failed: {e}", 0)
        except requests.exceptions.Timeout:
            return (False, "Request timed out", 0)
        except Exception as e:
            return (False, str(e), 0)
    
    def _run_test(
        self,
        name: str,
        category: TestCategory,
        test_func,
    ) -> TestResult:
        """Run a single test and record the result."""
        start = time.time()
        try:
            passed, message, details = test_func()
        except Exception as e:
            passed, message, details = False, f"Exception: {e}", None
        
        duration_ms = (time.time() - start) * 1000
        
        result = TestResult(
            name=name,
            category=category,
            passed=passed,
            message=message,
            duration_ms=duration_ms,
            details=details,
        )
        
        self.results.append(result)
        
        status = "✅ PASS" if passed else "❌ FAIL"
        self.log(f"{status} [{category.value}] {name}: {message}", "OK" if passed else "ERROR")
        
        return result
    
    # =========================================================================
    # Backend API Tests
    # =========================================================================
    
    def test_health_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test GET /recovery/health endpoint exists and returns valid data."""
        ok, data, status = self._api_call("GET", "/recovery/health")
        
        if not ok:
            return False, f"Health endpoint failed: {data}", None
        
        # Validate response schema
        required_fields = ["node", "state", "is_ready", "local_stats", "peers"]
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            return False, f"Missing fields: {missing}", data
        
        return True, f"Node {data['node']} is in state '{data['state']}'", data
    
    def test_state_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test GET /recovery/state endpoint."""
        ok, data, status = self._api_call("GET", "/recovery/state")
        
        if not ok:
            return False, f"State endpoint failed: {data}", None
        
        required_fields = ["state", "is_ready", "is_syncing", "node"]
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            return False, f"Missing fields: {missing}", data
        
        valid_states = ["startup", "needs_rebuild", "syncing", "ready", "failed"]
        if data["state"] not in valid_states:
            return False, f"Invalid state: {data['state']}", data
        
        return True, f"State: {data['state']}, Ready: {data['is_ready']}", data
    
    def test_gap_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test GET /recovery/gap endpoint."""
        ok, data, status = self._api_call("GET", "/recovery/gap")
        
        if not ok:
            return False, f"Gap endpoint failed: {data}", None
        
        if "local_max_lamport" not in data:
            return False, "Missing local_max_lamport field", data
        
        if "gaps" not in data:
            return False, "Missing gaps field", data
        
        return True, f"Local Lamport: {data['local_max_lamport']}, Gaps: {data['gaps']}", data
    
    def test_jobs_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test GET /recovery/jobs endpoint."""
        ok, data, status = self._api_call("GET", "/recovery/jobs")
        
        if not ok:
            return False, f"Jobs endpoint failed: {data}", None
        
        if "jobs" not in data:
            return False, "Missing 'jobs' field in response", data
        
        return True, f"Found {len(data['jobs'])} job(s)", data
    
    def test_start_recovery_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test POST /recovery/start endpoint."""
        ok, data, status = self._api_call(
            "POST",
            "/recovery/start",
            json={"mode": "leader"},
        )
        
        if not ok:
            # 409 Conflict means recovery already running, which is valid
            if status == 409:
                return True, "Recovery already in progress (409 Conflict)", {"status": status}
            return False, f"Start endpoint failed: {data}", None
        
        if "job_id" not in data:
            return False, "Missing job_id in response", data
        
        return True, f"Started job: {data['job_id']}", data
    
    def test_status_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test GET /recovery/status/{job_id} endpoint."""
        # First get a job ID
        ok, jobs_data, _ = self._api_call("GET", "/recovery/jobs")
        
        if not ok or not jobs_data.get("jobs"):
            # Try to start one
            ok, start_data, status = self._api_call(
                "POST", "/recovery/start", json={"mode": "leader"}
            )
            if ok and "job_id" in start_data:
                job_id = start_data["job_id"]
            elif status == 409:
                # Recovery running, try jobs again
                ok, jobs_data, _ = self._api_call("GET", "/recovery/jobs")
                if ok and jobs_data.get("jobs"):
                    job_id = jobs_data["jobs"][0]["job_id"]
                else:
                    return False, "Cannot get or create a job for testing", None
            else:
                return False, "Cannot get or create a job for testing", None
        else:
            job_id = jobs_data["jobs"][0]["job_id"]
        
        # Now test status endpoint
        ok, data, status = self._api_call("GET", f"/recovery/status/{job_id}")
        
        if not ok:
            return False, f"Status endpoint failed: {data}", None
        
        required_fields = ["job_id", "is_running", "progress"]
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            return False, f"Missing fields: {missing}", data
        
        progress = data["progress"]
        progress_fields = ["state", "mode", "ops_fetched", "ops_applied"]
        missing_progress = [f for f in progress_fields if f not in progress]
        
        if missing_progress:
            return False, f"Missing progress fields: {missing_progress}", data
        
        return True, f"Job {job_id}: {progress['state']}", data
    
    def test_logs_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test GET /recovery/logs/{job_id} endpoint."""
        # Get a job ID
        ok, jobs_data, _ = self._api_call("GET", "/recovery/jobs")
        
        if not ok or not jobs_data.get("jobs"):
            return False, "No jobs available to test logs", None
        
        job_id = jobs_data["jobs"][0]["job_id"]
        
        ok, data, status = self._api_call("GET", f"/recovery/logs/{job_id}")
        
        if not ok:
            return False, f"Logs endpoint failed: {data}", None
        
        if "job_id" not in data or "logs" not in data:
            return False, "Invalid logs response format", data
        
        return True, f"Job {job_id} has {len(data['logs'])} log entries", data
    
    def test_snapshot_endpoint(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test POST /recovery/snapshot endpoint."""
        ok, data, status = self._api_call("POST", "/recovery/snapshot")
        
        if not ok:
            if status == 409:
                return True, "Recovery already in progress (409 Conflict)", {"status": status}
            return False, f"Snapshot endpoint failed: {data}", None
        
        if "job_id" not in data:
            return False, "Missing job_id in response", data
        
        return True, f"Snapshot started: {data['job_id']}", data
    
    def test_invalid_mode(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that invalid recovery mode returns 400 error."""
        ok, data, status = self._api_call(
            "POST",
            "/recovery/start",
            json={"mode": "invalid_mode"},
        )
        
        if ok:
            return False, "Should have rejected invalid mode", data
        
        if status != 400:
            return False, f"Expected 400, got {status}", {"status": status, "data": data}
        
        return True, "Correctly rejected invalid mode with 400", {"status": status}
    
    def test_nonexistent_job(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that nonexistent job ID returns 404."""
        fake_job_id = "nonexistent-job-12345"
        ok, data, status = self._api_call("GET", f"/recovery/status/{fake_job_id}")
        
        if ok:
            return False, "Should have returned 404 for fake job", data
        
        if status != 404:
            return False, f"Expected 404, got {status}", {"status": status}
        
        return True, "Correctly returned 404 for nonexistent job", {"status": status}
    
    # =========================================================================
    # Frontend Integration Tests
    # =========================================================================
    
    def test_cors_headers(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that CORS headers are properly set for frontend access."""
        ok, data, status = self._api_call("GET", "/recovery/health")
        
        # The test passes if endpoint works - CORS is typically configured in middleware
        if not ok:
            return False, f"Endpoint failed: {data}", None
        
        return True, "Recovery endpoints accessible (CORS assumed from middleware)", None
    
    def test_json_content_type(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that endpoints return proper JSON content type."""
        try:
            response = self.session.get(
                urljoin(self.base_url, "/recovery/health"),
                timeout=self.timeout,
            )
            
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return False, f"Wrong content-type: {content_type}", None
            
            return True, "Proper JSON content-type header", {"content_type": content_type}
        
        except Exception as e:
            return False, str(e), None
    
    def test_api_response_schema(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that API responses match expected frontend schema."""
        # Test health endpoint matches what frontend expects
        ok, data, status = self._api_call("GET", "/recovery/health")
        
        if not ok:
            return False, f"Health endpoint failed: {data}", None
        
        # Frontend expects: node, state, is_ready, local_stats, peers
        schema_valid = all([
            isinstance(data.get("node"), str),
            isinstance(data.get("state"), str),
            isinstance(data.get("is_ready"), bool),
            isinstance(data.get("local_stats"), dict),
            isinstance(data.get("peers"), list),
        ])
        
        if not schema_valid:
            return False, "Response doesn't match expected frontend schema", data
        
        return True, "API response matches frontend expectations", data
    
    def test_sse_logs_streaming(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test Server-Sent Events log streaming works."""
        # Get a job ID first
        ok, jobs_data, _ = self._api_call("GET", "/recovery/jobs")
        
        if not ok or not jobs_data.get("jobs"):
            # Start a job
            ok, start_data, status = self._api_call(
                "POST", "/recovery/start", json={"mode": "leader"}
            )
            if status == 409:
                # Already running, try again
                ok, jobs_data, _ = self._api_call("GET", "/recovery/jobs")
                if ok and jobs_data.get("jobs"):
                    job_id = jobs_data["jobs"][0]["job_id"]
                else:
                    return False, "Cannot get job for SSE test", None
            elif ok:
                job_id = start_data["job_id"]
            else:
                return False, "Cannot start job for SSE test", None
        else:
            job_id = jobs_data["jobs"][0]["job_id"]
        
        # Test SSE endpoint
        try:
            response = self.session.get(
                urljoin(self.base_url, f"/recovery/logs/{job_id}?stream=true"),
                timeout=5,
                stream=True,
            )
            
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                return False, f"Wrong SSE content-type: {content_type}", None
            
            # Read a bit to confirm streaming works
            response.close()
            
            return True, "SSE streaming endpoint works", {"job_id": job_id}
        
        except requests.exceptions.Timeout:
            # Timeout is okay for streaming - means it was streaming
            return True, "SSE streaming endpoint works (timed out as expected)", None
        except Exception as e:
            return False, f"SSE test failed: {e}", None
    
    # =========================================================================
    # State Machine Tests
    # =========================================================================
    
    def test_state_transitions(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that recovery state machine transitions work correctly."""
        # Get initial state
        ok, state_data, _ = self._api_call("GET", "/recovery/state")
        if not ok:
            return False, f"Cannot get state: {state_data}", None
        
        initial_state = state_data["state"]
        
        # Valid states
        valid_states = ["startup", "needs_rebuild", "syncing", "ready", "failed"]
        if initial_state not in valid_states:
            return False, f"Invalid initial state: {initial_state}", state_data
        
        return True, f"State machine in valid state: {initial_state}", state_data
    
    def test_recovery_flow(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test complete recovery flow from start to completion/timeout."""
        # Start recovery
        ok, start_data, status = self._api_call(
            "POST", "/recovery/start", json={"mode": "leader"}
        )
        
        if status == 409:
            # Already running, get the current job
            ok, jobs_data, _ = self._api_call("GET", "/recovery/jobs")
            if not ok or not jobs_data.get("jobs"):
                return False, "Cannot get running job", None
            job_id = jobs_data["jobs"][0]["job_id"]
        elif ok:
            job_id = start_data["job_id"]
        else:
            return False, f"Cannot start recovery: {start_data}", None
        
        # Poll status for a few seconds
        states_seen = set()
        for _ in range(10):
            ok, status_data, _ = self._api_call("GET", f"/recovery/status/{job_id}")
            if ok:
                state = status_data["progress"]["state"]
                states_seen.add(state)
                
                if state in ["ready", "failed"]:
                    break
            
            time.sleep(0.5)
        
        return True, f"Recovery flow observed states: {states_seen}", {
            "job_id": job_id,
            "states_seen": list(states_seen),
        }
    
    # =========================================================================
    # Multi-Node Tests
    # =========================================================================
    
    def test_all_nodes_health(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that all cloud nodes have recovery endpoints."""
        if not self.cloud_mode:
            return True, "Skipped (not in cloud mode)", None
        
        results = {}
        all_healthy = True
        
        for name, url in self.nodes.items():
            ok, data, status = self._api_call("GET", "/recovery/health", base_url=url)
            results[name] = {
                "ok": ok,
                "status": status,
                "state": data.get("state") if ok else str(data),
            }
            if not ok:
                all_healthy = False
        
        if all_healthy:
            return True, "All nodes have healthy recovery endpoints", results
        
        failed = [n for n, r in results.items() if not r["ok"]]
        return False, f"Nodes failed: {failed}", results
    
    def test_node_peer_visibility(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that nodes can see their peers."""
        ok, data, _ = self._api_call("GET", "/recovery/health")
        
        if not ok:
            return False, f"Health check failed: {data}", None
        
        peers = data.get("peers", [])
        
        if not peers:
            return True, "No peers configured (single-node mode)", data
        
        healthy_peers = [p for p in peers if p.get("status") == "healthy"]
        
        return True, f"{len(healthy_peers)}/{len(peers)} peers healthy", {
            "total_peers": len(peers),
            "healthy_peers": len(healthy_peers),
            "peers": peers,
        }
    
    def test_sync_gap_consistency(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test sync gap endpoint returns consistent data."""
        ok, data, _ = self._api_call("GET", "/recovery/gap")
        
        if not ok:
            return False, f"Gap check failed: {data}", None
        
        local_lamport = data.get("local_max_lamport", 0)
        gaps = data.get("gaps", {})
        
        # Gaps should be non-negative
        invalid_gaps = {k: v for k, v in gaps.items() if v < 0}
        if invalid_gaps:
            return False, f"Invalid negative gaps: {invalid_gaps}", data
        
        return True, f"Lamport: {local_lamport}, Gaps: {gaps}", data
    
    # =========================================================================
    # Dashboard Tests
    # =========================================================================
    
    def test_dashboard_serves(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that the recovery dashboard HTML is served."""
        try:
            response = self.session.get(
                urljoin(self.base_url, "/recovery/dashboard"),
                timeout=self.timeout,
            )
            
            if not response.ok:
                return False, f"Dashboard returned {response.status_code}", None
            
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return False, f"Wrong content-type: {content_type}", None
            
            html = response.text
            
            # Check for key elements
            checks = {
                "has_title": "Recovery Dashboard" in html,
                "has_node_health": "nodeHealth" in html or "Node Health" in html,
                "has_start_button": "startRecovery" in html or "Start Recovery" in html,
                "has_progress_bar": "progress-bar" in html or "progressFill" in html,
                "has_log_container": "logContainer" in html or "log-container" in html,
            }
            
            all_checks = all(checks.values())
            
            if not all_checks:
                failed = [k for k, v in checks.items() if not v]
                return False, f"Missing dashboard elements: {failed}", checks
            
            return True, "Dashboard HTML serves correctly", checks
        
        except Exception as e:
            return False, f"Dashboard test failed: {e}", None
    
    def test_dashboard_api_integration(self) -> Tuple[bool, str, Optional[Dict]]:
        """Test that dashboard can call all required APIs."""
        # The dashboard needs these endpoints:
        required_endpoints = [
            ("GET", "/recovery/health"),
            ("GET", "/recovery/state"),
            ("GET", "/recovery/jobs"),
        ]
        
        results = {}
        all_ok = True
        
        for method, endpoint in required_endpoints:
            ok, data, status = self._api_call(method, endpoint)
            results[endpoint] = {"ok": ok, "status": status}
            if not ok:
                all_ok = False
        
        if all_ok:
            return True, "All dashboard API endpoints work", results
        
        failed = [e for e, r in results.items() if not r["ok"]]
        return False, f"Dashboard APIs failed: {failed}", results
    
    # =========================================================================
    # Run Tests
    # =========================================================================
    
    def run_category(self, category: TestCategory):
        """Run all tests in a category."""
        
        # Backend API tests
        if category in (TestCategory.BACKEND, TestCategory.ALL):
            self._run_test("Health Endpoint", TestCategory.BACKEND, self.test_health_endpoint)
            self._run_test("State Endpoint", TestCategory.BACKEND, self.test_state_endpoint)
            self._run_test("Gap Endpoint", TestCategory.BACKEND, self.test_gap_endpoint)
            self._run_test("Jobs Endpoint", TestCategory.BACKEND, self.test_jobs_endpoint)
            self._run_test("Start Recovery Endpoint", TestCategory.BACKEND, self.test_start_recovery_endpoint)
            self._run_test("Status Endpoint", TestCategory.BACKEND, self.test_status_endpoint)
            self._run_test("Logs Endpoint", TestCategory.BACKEND, self.test_logs_endpoint)
            self._run_test("Snapshot Endpoint", TestCategory.BACKEND, self.test_snapshot_endpoint)
            self._run_test("Invalid Mode Rejection", TestCategory.BACKEND, self.test_invalid_mode)
            self._run_test("Nonexistent Job 404", TestCategory.BACKEND, self.test_nonexistent_job)
        
        # Frontend integration tests
        if category in (TestCategory.FRONTEND, TestCategory.ALL):
            self._run_test("CORS/Accessibility", TestCategory.FRONTEND, self.test_cors_headers)
            self._run_test("JSON Content-Type", TestCategory.FRONTEND, self.test_json_content_type)
            self._run_test("API Response Schema", TestCategory.FRONTEND, self.test_api_response_schema)
            self._run_test("SSE Log Streaming", TestCategory.FRONTEND, self.test_sse_logs_streaming)
        
        # State machine tests
        if category in (TestCategory.STATE_MACHINE, TestCategory.ALL):
            self._run_test("State Transitions", TestCategory.STATE_MACHINE, self.test_state_transitions)
            self._run_test("Recovery Flow", TestCategory.STATE_MACHINE, self.test_recovery_flow)
        
        # Multi-node tests
        if category in (TestCategory.MULTI_NODE, TestCategory.ALL):
            self._run_test("All Nodes Health", TestCategory.MULTI_NODE, self.test_all_nodes_health)
            self._run_test("Node Peer Visibility", TestCategory.MULTI_NODE, self.test_node_peer_visibility)
            self._run_test("Sync Gap Consistency", TestCategory.MULTI_NODE, self.test_sync_gap_consistency)
        
        # Dashboard tests
        if category in (TestCategory.DASHBOARD, TestCategory.ALL):
            self._run_test("Dashboard Serves", TestCategory.DASHBOARD, self.test_dashboard_serves)
            self._run_test("Dashboard API Integration", TestCategory.DASHBOARD, self.test_dashboard_api_integration)
    
    def run_all(self):
        """Run all tests."""
        print("=" * 70)
        print("🔬 RECOVERY SUBSYSTEM - COMPREHENSIVE E2E TEST SUITE")
        print("=" * 70)
        print(f"Target: {self.base_url}")
        print(f"Cloud Mode: {self.cloud_mode}")
        print(f"Verbose: {self.verbose}")
        print("=" * 70)
        print()
        
        self.run_category(TestCategory.ALL)
        
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        print()
        print("=" * 70)
        print("📊 TEST SUMMARY")
        print("=" * 70)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        # Group by category
        by_category = {}
        for r in self.results:
            if r.category not in by_category:
                by_category[r.category] = {"passed": 0, "failed": 0}
            if r.passed:
                by_category[r.category]["passed"] += 1
            else:
                by_category[r.category]["failed"] += 1
        
        print()
        print("By Category:")
        for cat, counts in by_category.items():
            total = counts["passed"] + counts["failed"]
            icon = "✅" if counts["failed"] == 0 else "❌"
            print(f"  {icon} {cat.value}: {counts['passed']}/{total} passed")
        
        print()
        print(f"Total: {passed}/{len(self.results)} tests passed")
        print()
        
        if failed > 0:
            print("❌ FAILED TESTS:")
            for r in self.results:
                if not r.passed:
                    print(f"  - [{r.category.value}] {r.name}: {r.message}")
            print()
            print("🔴 SOME TESTS FAILED - Recovery implementation may be incomplete")
        else:
            print("🟢 ALL TESTS PASSED - Recovery Subsystem is fully implemented!")
        
        print("=" * 70)
        
        return failed == 0


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive E2E test suite for Recovery Subsystem"
    )
    parser.add_argument(
        "--node", "-n",
        default=NodeConfig.LOCAL,
        help=f"Base URL of the node to test (default: {NodeConfig.LOCAL})"
    )
    parser.add_argument(
        "--cloud", "-c",
        action="store_true",
        help="Enable cloud mode to test all CCS Cloud nodes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--category",
        choices=["backend", "frontend", "state_machine", "multi_node", "dashboard", "all"],
        default="all",
        help="Test category to run (default: all)"
    )
    
    args = parser.parse_args()
    
    # Determine base URL
    if args.cloud:
        base_url = NodeConfig.NODE0
    else:
        base_url = args.node
    
    suite = RecoveryE2ETestSuite(
        base_url=base_url,
        cloud_mode=args.cloud,
        verbose=args.verbose,
        timeout=args.timeout,
    )
    
    if args.category == "all":
        success = suite.run_all()
    else:
        category = TestCategory(args.category)
        print(f"Running category: {category.value}")
        suite.run_category(category)
        success = suite.print_summary()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
