import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
from datetime import datetime


def parse_test_results(file_path: str) -> Dict[str, Any]:
    """Parse junit-style XML test results.

    Returns:
        Dict with keys: exists, total, passed, failed, skipped, time, timestamp, failed_names
        If file doesn't exist or is invalid: {"exists": False}
    """
    if not os.path.exists(file_path):
        return {"exists": False}

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Handle both <testsuites> wrapper and direct <testsuite>
        testsuite = root
        if root.tag == "testsuites":
            testsuite = root.find("testsuite")
            if testsuite is None:
                return {"exists": False}

        if testsuite.tag != "testsuite":
            return {"exists": False}

        # Extract attributes from testsuite
        total = int(testsuite.get("tests", 0))
        failures = int(testsuite.get("failures", 0))
        errors = int(testsuite.get("errors", 0))
        skipped = int(testsuite.get("skipped", 0))
        failed = failures + errors
        passed = total - failed - skipped

        time_str = testsuite.get("time", "0")
        try:
            time = float(time_str)
        except ValueError:
            time = 0.0

        timestamp_str = testsuite.get("timestamp", "")
        timestamp = None
        if timestamp_str:
            try:
                # Try to parse ISO format timestamp
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                # Fallback for other timestamp formats
                timestamp = None

        # Find failed test names
        failed_names = []
        for testcase in testsuite.findall("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")
            if failure is not None or error is not None:
                classname = testcase.get("classname", "")
                name = testcase.get("name", "")
                full_name = f"{classname}.{name}" if classname else name
                failed_names.append(full_name)

        return {
            "exists": True,
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "time": time,
            "timestamp": timestamp,
            "failed_names": failed_names
        }

    except (ET.ParseError, ValueError, AttributeError) as e:
        # XML is invalid or doesn't match expected structure
        return {"exists": False}