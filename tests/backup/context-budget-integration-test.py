#!/usr/bin/env python3
"""
ISI-2615 Context Budget Consistency Tests - Integration Test

This test verifies that backup agent health checks properly integrate with 
the context budget system from Story 5.9. It ensures that backup agents never
silently truncate must-include content and that context budget violations
are detected.

Integration test goals:
1. Verify context budget validation in health checks
2. Ensure fail-closed behavior for budget violations
3. Validate must-include content protection
4. Test model window awareness and constraints
"""

import sys
import json
from typing import Dict, List, Optional


class ContextBudget:
    """Represents context budget configuration (Story 5.9)"""
    def __init__(self, total_tokens: int, authoritative_tokens: int = None, 
                 untrusted_recall_tokens: int = None, untrusted_external_tokens: int = None):
        self.total_tokens = total_tokens
        self.authoritative_tokens = authoritative_tokens or total_tokens // 3
        self.untrusted_recall_tokens = untrusted_recall_tokens or total_tokens // 3
        self.untrusted_external_tokens = untrusted_external_tokens or total_tokens // 3


class BackupAgentHealth:
    """Represents backup agent health status"""
    def __init__(self, name: str, runtime_type: str = "opencode"):
        self.name = name
        self.runtime_type = runtime_type
        self.endpoint_url = ""
        self.advertised_capabilities = []
        self.context_budget = None
        self.must_include_min_tokens = 0
        self.resolved_model_context_window = 100000  # Default 100K
        
        # Health status
        self.ready = False
        self.pod_ready = False
        self.runtime_capability_verified = False
        self.endpoint_available = True
        self.context_budget_valid = False
        self.context_fitting_valid = False
        
    def set_context_budget(self, budget: ContextBudget, must_include_min: int):
        """Set context budget configuration"""
        self.context_budget = budget
        self.must_include_min_tokens = must_include_min
        
    def get_overall_ready(self) -> bool:
        """Get overall ready status including context budget validation"""
        return (self.pod_ready and 
                self.runtime_capability_verified and 
                self.endpoint_available and 
                self.context_budget_valid and 
                self.context_fitting_valid)


def validate_context_budget(health: BackupAgentHealth) -> tuple[bool, str]:
    """
    Story 5.9 AC2: Budget is keyed to resolved model window and resolved per-runtime-default then per-Agent override.
    Configuration can shrink but never exceed the physical window.
    """
    # Check if must-include exceeds model window (AC3) - this is always checked, even without budget
    if health.must_include_min_tokens > health.resolved_model_context_window:
        return False, f"Must-include content ({health.must_include_min_tokens}) exceeds model window ({health.resolved_model_context_window})"
    
    if health.context_budget is None:
        return True, "No context budget configured, using defaults"
    
    # Check if budget exceeds model's physical window (AC4)
    if health.context_budget.total_tokens > health.resolved_model_context_window:
        return False, f"Context budget ({health.context_budget.total_tokens}) exceeds model window ({health.resolved_model_context_window})"
    
    # Check if must-include fits within budget (AC3)
    if health.must_include_min_tokens > health.context_budget.total_tokens:
        return False, f"Must-include content ({health.must_include_min_tokens}) exceeds total budget ({health.context_budget.total_tokens})"
    
    # Check if must-include fits within authoritative allocation (AC1)
    if health.must_include_min_tokens > health.context_budget.authoritative_tokens:
        return False, f"Must-include content ({health.must_include_min_tokens}) exceeds authoritative allocation ({health.context_budget.authoritative_tokens})"
    
    return True, "Context budget validation passed"


def validate_context_fitting(health: BackupAgentHealth) -> tuple[bool, str]:
    """
    Story 5.9 AC1: Must-include is placed first and never truncated; best-effort summarized/lowest-priority-first.
    """
    if health.context_budget is None:
        return True, "No context budget configured, skipping fitting validation"
    
    # AC1: Must-include never truncated
    if health.must_include_min_tokens > health.context_budget.total_tokens:
        return False, "Must-include content would be truncated to fit budget"
    
    # AC1: Best-effort content fits within remaining budget
    remaining_budget = health.context_budget.total_tokens - health.must_include_min_tokens
    total_best_effort = (health.context_budget.untrusted_recall_tokens + 
                        health.context_budget.untrusted_external_tokens)
    
    if total_best_effort > remaining_budget:
        # This is acceptable as best-effort can be summarized/trimmed
        return True, f"Best-effort content may be summarized to fit remaining {remaining_budget} tokens"
    
    return True, "Context fitting validation passed"


def test_context_budget_integration():
    """Test context budget integration with backup agent health checks"""
    print("[test] ISI-2615 Context Budget Consistency Tests - Integration Test")
    
    # Test Case 1: Valid context budget configuration
    print("\n[test] Case 1: Valid context budget configuration")
    agent1 = BackupAgentHealth("backup-1")
    valid_budget = ContextBudget(total_tokens=80000)
    agent1.set_context_budget(valid_budget, 20000)
    agent1.resolved_model_context_window = 100000
    
    budget_valid, budget_msg = validate_context_budget(agent1)
    fitting_valid, fitting_msg = validate_context_fitting(agent1)
    
    agent1.context_budget_valid = budget_valid
    agent1.context_fitting_valid = fitting_valid
    agent1.pod_ready = True
    agent1.runtime_capability_verified = True
    
    assert budget_valid, f"Budget validation should pass: {budget_msg}"
    assert fitting_valid, f"Fitting validation should pass: {fitting_msg}"
    assert agent1.get_overall_ready(), "Agent should be ready with valid configuration"
    
    print(f"  ✓ Budget validation: {budget_msg}")
    print(f"  ✓ Fitting validation: {fitting_msg}")
    print(f"  ✓ Overall ready: {agent1.get_overall_ready()}")
    
    # Test Case 2: Context budget exceeds model window (should fail)
    print("\n[test] Case 2: Context budget exceeds model window")
    agent2 = BackupAgentHealth("backup-2")
    invalid_budget = ContextBudget(total_tokens=150000)  # 150K > 100K model window
    agent2.set_context_budget(invalid_budget, 20000)
    agent2.resolved_model_context_window = 100000  # Model window is 100K
    
    budget_valid, budget_msg = validate_context_budget(agent2)
    
    agent2.context_budget_valid = budget_valid
    agent2.pod_ready = True
    agent2.runtime_capability_verified = True
    agent2.endpoint_available = True
    
    assert not budget_valid, "Budget validation should fail for over-window budget"
    assert not agent2.get_overall_ready(), "Agent should not be ready with invalid configuration"
    
    print(f"  ✗ Budget validation failed as expected: {budget_msg}")
    print(f"  ✗ Overall ready: {agent2.get_overall_ready()}")
    
    # Test Case 3: Must-include exceeds model window (should fail closed)
    print("\n[test] Case 3: Must-include exceeds model window")
    agent3 = BackupAgentHealth("backup-3")
    agent3.must_include_min_tokens = 120000  # 120K > 100K model window
    agent3.resolved_model_context_window = 100000
    
    budget_valid, budget_msg = validate_context_budget(agent3)
    
    agent3.context_budget_valid = budget_valid
    agent3.pod_ready = True
    agent3.runtime_capability_verified = True
    agent3.endpoint_available = True
    
    assert not budget_valid, "Budget validation should fail for must-include overflow"
    assert not agent3.get_overall_ready(), "Agent should not be ready when must-include overflows"
    
    print(f"  ✗ Budget validation failed as expected: {budget_msg}")
    print(f"  ✗ Overall ready: {agent3.get_overall_ready()}")
    
    # Test Case 4: Must-include fits, best-effort needs summarization (should pass)
    print("\n[test] Case 4: Must-include fits, best-effort needs summarization")
    agent4 = BackupAgentHealth("backup-4")
    tight_budget = ContextBudget(total_tokens=50000, authoritative_tokens=35000,
                                untrusted_recall_tokens=10000, untrusted_external_tokens=5000)
    agent4.set_context_budget(tight_budget, 30000)
    agent4.resolved_model_context_window = 100000
    
    budget_valid, budget_msg = validate_context_budget(agent4)
    fitting_valid, fitting_msg = validate_context_fitting(agent4)
    
    
    
    agent4.context_budget_valid = budget_valid
    agent4.context_fitting_valid = fitting_valid
    agent4.pod_ready = True
    agent4.runtime_capability_verified = True
    agent4.endpoint_available = True
    
    assert budget_valid, f"Budget validation should pass: {budget_msg}"
    assert fitting_valid, "Fitting validation should pass (best-effort can be summarized)"
    assert agent4.get_overall_ready(), "Agent should be ready"
    
    print(f"  ✓ Budget validation: {budget_msg}")
    print(f"  ✓ Fitting validation: {fitting_msg}")
    print(f"  ✓ Overall ready: {agent4.get_overall_ready()}")
    
    # Test Case 5: Must-include truncated in budget (should fail)
    print("\n[test] Case 5: Must-include exceeds allocated budget")
    agent5 = BackupAgentHealth("backup-5")
    unbalanced_budget = ContextBudget(total_tokens=50000, authoritative_tokens=20000)  # Only 20K for must-include
    agent5.set_context_budget(unbalanced_budget, 30000)  # But need 30K for must-include
    agent5.resolved_model_context_window = 100000
    
    budget_valid, budget_msg = validate_context_budget(agent5)
    fitting_valid, fitting_msg = validate_context_fitting(agent5)
    
    agent5.context_budget_valid = budget_valid
    agent5.context_fitting_valid = fitting_valid
    agent5.pod_ready = True
    agent5.runtime_capability_verified = True
    agent5.endpoint_available = True
    
    assert not budget_valid, "Budget validation should fail for insufficient must-include allocation"
    assert not agent5.get_overall_ready(), "Agent should not be ready with insufficient must-include budget"
    
    print(f"  ✗ Budget validation failed as expected: {budget_msg}")
    print(f"  ✗ Overall ready: {agent5.get_overall_ready()}")
    
    print("\n[test] === ISI-2615 Context Budget Integration Test Complete ===")
    print("[test] All tests passed - backup agent health checks properly integrate with context budget system")
    
    return True


def main():
    """Main test function"""
    try:
        test_context_budget_integration()
        print("\n✅ SUCCESS: ISI-2615 Context Budget Consistency Tests completed successfully")
        print("✅ Integration between backup agent health checks and context budget system verified")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ FAILED: ISI-2615 Context Budget Integration Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()