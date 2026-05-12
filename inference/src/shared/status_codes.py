from __future__ import annotations

# Mirror backend/api/shared/status_codes.py numeric convention, but inference-specific.

GRAPH_NODE_RUNNING = 2001
GRAPH_NODE_COMPLETE = 2002
GRAPH_NODE_FAILED = 2003

RETRIEVAL_LOOP_TRIGGERED = 2101
RETRIEVAL_LOOP_CAPPED = 2102  # loop_count hit LOOP_MAX

COVERAGE_PASSED = 2201
COVERAGE_FAILED = 2202

ASSERTION_PASSED = 2301
ASSERTION_RETRY = 2302
ASSERTION_FAILED = 2303  # degraded path — stream continues with warning

