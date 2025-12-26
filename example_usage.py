"""
Example usage of the Beans&Co Multi-Agent System.

This script demonstrates various use cases:
1. Analytical queries (READ_ANALYTICS)
2. Business operations (WRITE_OPERATION)
3. Mixed operations (write + read)
4. Ambiguous requests
"""
from graph import run_agent


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")


def test_read_analytics():
    """Test analytical queries (READ_ANALYTICS intent)."""
    print_section("TEST 1: ANALYTICAL QUERIES (READ_ANALYTICS)")

    queries = [
        "¿cuántas pulseras tengo de cada tipo?",
        "what's my total revenue?",
        "show me current profit",
        "cuánto stock tengo en total",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 80)
        try:
            answer = run_agent(query, verbose=False)
            print(f"Answer: {answer}")
        except Exception as e:
            print(f"Error: {str(e)}")


def test_write_operations():
    """Test business operations (WRITE_OPERATION intent)."""
    print_section("TEST 2: BUSINESS OPERATIONS (WRITE_OPERATION)")

    operations = [
        "registrame una venta de 2 pulseras negras",
        "I sold 3 black bracelets",
        # Note: These require proper products in DB
    ]

    for operation in operations:
        print(f"\nOperation: {operation}")
        print("-" * 80)
        try:
            answer = run_agent(operation, verbose=False)
            print(f"Result: {answer}")
        except Exception as e:
            print(f"Error: {str(e)}")


def test_mixed_operations():
    """Test mixed operations (write then read)."""
    print_section("TEST 3: MIXED OPERATIONS (WRITE + READ)")

    mixed_queries = [
        "vendí 2 pulseras black, ¿cómo queda el stock?",
        "register a sale of 1 bracelet and show me the new revenue",
    ]

    for query in mixed_queries:
        print(f"\nQuery: {query}")
        print("-" * 80)
        try:
            answer = run_agent(query, verbose=False)
            print(f"Answer: {answer}")
        except Exception as e:
            print(f"Error: {str(e)}")


def test_ambiguous_requests():
    """Test ambiguous requests."""
    print_section("TEST 4: AMBIGUOUS REQUESTS")

    ambiguous = [
        "registrar algo",
        "cuánto tengo",
        "help",
    ]

    for query in ambiguous:
        print(f"\nQuery: {query}")
        print("-" * 80)
        try:
            answer = run_agent(query, verbose=False)
            print(f"Answer: {answer}")
        except Exception as e:
            print(f"Error: {str(e)}")


def test_full_flow():
    """Test a complete end-to-end flow with verbose output."""
    print_section("TEST 5: COMPLETE END-TO-END FLOW (VERBOSE)")

    test_query = "registrame una venta de 2 pulseras negras"

    print(f"Query: {test_query}\n")
    print("This will show the complete agent flow:\n")

    try:
        answer = run_agent(test_query, verbose=True)
        print(f"\n\nFINAL ANSWER:\n{answer}")
    except Exception as e:
        print(f"\nError: {str(e)}")


if __name__ == "__main__":
    import sys

    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║              Beans&Co Multi-Agent System - Example Usage                 ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

This script demonstrates the multi-agent system with various test cases.
Each test shows how different intents are routed to specialized agents.

""")

    if len(sys.argv) > 1:
        # Run specific test
        test_name = sys.argv[1]
        if test_name == "read":
            test_read_analytics()
        elif test_name == "write":
            test_write_operations()
        elif test_name == "mixed":
            test_mixed_operations()
        elif test_name == "ambiguous":
            test_ambiguous_requests()
        elif test_name == "full":
            test_full_flow()
        else:
            print(f"Unknown test: {test_name}")
            print("Available tests: read, write, mixed, ambiguous, full")
    else:
        # Run all tests
        print("Running all tests...\n")
        test_read_analytics()
        test_write_operations()
        test_mixed_operations()
        test_ambiguous_requests()
        test_full_flow()

    print("\n\n" + "="*80)
    print("  Tests completed!")
    print("="*80 + "\n")
