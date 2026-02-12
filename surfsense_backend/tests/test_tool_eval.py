#!/usr/bin/env python3
"""
Simple test script to validate tool_eval_service logic without external dependencies.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_parse_eval_suite():
    """Test parsing of evaluation suite from JSON."""
    test_data = {
        "name": "Test Suite",
        "description": "Test description",
        "config": {
            "tool_retrieval": {
                "limit": 2,
                "use_reranker": True,
            },
            "scoring": {
                "route_correct_weight": 0.15,
            },
            "test_routing": True,
            "test_agents": True,
        },
        "categories": [
            {
                "category_id": "test_cat",
                "category_name": "Test Category",
                "test_cases": [
                    {
                        "id": "test_001",
                        "query": "Test query",
                        "expected_route": "action",
                        "expected_tools": ["tool1", "tool2"],
                        "tags": ["test"],
                        "difficulty": "easy",
                    }
                ],
            }
        ],
    }
    
    try:
        from app.services.tool_eval_service import parse_eval_suite
        suite = parse_eval_suite(test_data)
        
        assert suite.name == "Test Suite"
        assert len(suite.categories) == 1
        assert suite.categories[0].category_id == "test_cat"
        assert len(suite.categories[0].test_cases) == 1
        assert suite.categories[0].test_cases[0].id == "test_001"
        
        print("✓ parse_eval_suite test passed")
        return True
    except ImportError as e:
        print(f"⚠ Skipping test due to missing dependencies: {e}")
        return None
    except Exception as e:
        print(f"✗ parse_eval_suite test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_route_evaluation():
    """Test route classification regex patterns."""
    try:
        from app.services.tool_eval_service import _eval_route
        
        test_cases = [
            ("Finns det några trafikstörningar?", "action"),
            ("Hej!", "smalltalk"),
            ("Sök efter information om AI", "knowledge"),
            ("Befolkningsstatistik Sverige", "statistics"),
            ("/compare GPT-4 vs Claude", "compare"),
        ]
        
        for query, expected in test_cases:
            result = _eval_route(query)
            if result == expected:
                print(f"✓ Route test passed: '{query}' -> {result}")
            else:
                print(f"✗ Route test failed: '{query}' -> {result} (expected {expected})")
                return False
        
        print("✓ All route evaluation tests passed")
        return True
    except ImportError as e:
        print(f"⚠ Skipping test due to missing dependencies: {e}")
        return None
    except Exception as e:
        print(f"✗ Route evaluation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_json_suite_loading():
    """Test loading the actual test suite file."""
    suite_path = Path(__file__).parent.parent / "eval_suites" / "full_pipeline_eval_v1.json"
    
    if not suite_path.exists():
        print(f"✗ Test suite file not found: {suite_path}")
        return False
    
    try:
        with open(suite_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate structure
        assert "name" in data
        assert "categories" in data
        assert len(data["categories"]) == 4  # trafikverket, bolagsverket, general_tools, adversarial
        
        total_cases = sum(len(cat["test_cases"]) for cat in data["categories"])
        assert total_cases == 80  # As specified in requirements
        
        print(f"✓ Test suite loaded successfully: {total_cases} test cases across {len(data['categories'])} categories")
        return True
    except Exception as e:
        print(f"✗ JSON suite loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Tool Evaluation Service - Basic Tests")
    print("=" * 60)
    
    results = []
    
    print("\n[1/3] Testing parse_eval_suite...")
    results.append(test_parse_eval_suite())
    
    print("\n[2/3] Testing route evaluation...")
    results.append(test_route_evaluation())
    
    print("\n[3/3] Testing JSON suite loading...")
    results.append(test_json_suite_loading())
    
    print("\n" + "=" * 60)
    
    # Count results (None means skipped due to missing deps)
    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)
    skipped = sum(1 for r in results if r is None)
    
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)
    
    # Return 0 if all tests passed or were skipped, 1 if any failed
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
