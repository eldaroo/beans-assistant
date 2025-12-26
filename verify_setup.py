"""
Verification script to test that the multi-agent system is properly set up.
Run this after installation to check all components.
"""
import sys


def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        import langchain
        print("  ✓ langchain")
    except ImportError as e:
        print(f"  ✗ langchain: {e}")
        return False

    try:
        import langgraph
        print("  ✓ langgraph")
    except ImportError as e:
        print(f"  ✗ langgraph: {e}")
        return False

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        print("  ✓ langchain_google_genai")
    except ImportError as e:
        print(f"  ✗ langchain_google_genai: {e}")
        return False

    try:
        from langchain_community.utilities import SQLDatabase
        print("  ✓ langchain_community")
    except ImportError as e:
        print(f"  ✗ langchain_community: {e}")
        return False

    try:
        import sqlite3
        print("  ✓ sqlite3")
    except ImportError as e:
        print(f"  ✗ sqlite3: {e}")
        return False

    return True


def test_project_structure():
    """Test that all required files exist."""
    print("\nTesting project structure...")

    import os

    required_files = [
        "agents/__init__.py",
        "agents/state.py",
        "agents/router.py",
        "agents/read_agent.py",
        "agents/write_agent.py",
        "agents/resolver.py",
        "graph.py",
        "database.py",
        "llm.py",
        "beansco.db",
    ]

    all_exist = True
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} (missing)")
            all_exist = False

    return all_exist


def test_database():
    """Test database connection and basic queries."""
    print("\nTesting database...")

    try:
        import sqlite3

        conn = sqlite3.connect("beansco.db")
        cursor = conn.cursor()

        # Test tables exist
        tables = ["products", "sales", "stock_movements", "expenses"]
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  ✓ {table} table exists ({count} rows)")

        # Test views exist
        views = ["stock_current", "profit_summary"]
        for view in views:
            try:
                cursor.execute(f"SELECT * FROM {view} LIMIT 1")
                print(f"  ✓ {view} view exists")
            except sqlite3.OperationalError:
                print(f"  ✗ {view} view missing (run apply_views.py)")

        conn.close()
        return True

    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return False


def test_env_config():
    """Test environment configuration."""
    print("\nTesting environment configuration...")

    import os
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        print(f"  ✓ API key configured (length: {len(api_key)})")
    else:
        print("  ✗ No API key found in .env")
        print("    Set GOOGLE_API_KEY in your .env file")
        return False

    model = os.getenv("GEMINI_MODEL") or "gemini-2.0-flash-exp"
    print(f"  ✓ Model: {model}")

    return True


def test_agents():
    """Test that agents can be instantiated."""
    print("\nTesting agent instantiation...")

    try:
        from agents import (
            create_router_agent,
            create_read_agent,
            create_write_agent,
            create_resolver_agent,
        )
        from llm import get_llm

        llm = get_llm()
        print("  ✓ LLM initialized")

        router = create_router_agent(llm)
        print("  ✓ Router agent created")

        read_agent = create_read_agent(llm)
        print("  ✓ Read agent created")

        write_agent = create_write_agent()
        print("  ✓ Write agent created")

        resolver = create_resolver_agent()
        print("  ✓ Resolver agent created")

        return True

    except Exception as e:
        print(f"  ✗ Error creating agents: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_graph():
    """Test that the graph can be compiled."""
    print("\nTesting graph compilation...")

    try:
        from graph import create_business_agent_graph

        graph = create_business_agent_graph()
        print("  ✓ Graph compiled successfully")

        return True

    except Exception as e:
        print(f"  ✗ Error compiling graph: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification tests."""
    print("="*70)
    print("  Beans&Co Multi-Agent System - Setup Verification")
    print("="*70 + "\n")

    tests = [
        ("Imports", test_imports),
        ("Project Structure", test_project_structure),
        ("Database", test_database),
        ("Environment Config", test_env_config),
        ("Agents", test_agents),
        ("Graph", test_graph),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n✗ {name} test failed with exception: {e}")
            results[name] = False

    # Summary
    print("\n" + "="*70)
    print("  SUMMARY")
    print("="*70)

    all_passed = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("="*70 + "\n")

    if all_passed:
        print("✓ All tests passed! The system is ready to use.")
        print("\nQuick start:")
        print("  python graph.py                    # Interactive mode")
        print("  python graph.py -q 'your question' # Single query")
        print("  python example_usage.py            # Run examples")
        return 0
    else:
        print("✗ Some tests failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("  pip install -r requirements.txt    # Install dependencies")
        print("  python init_db.py                  # Initialize database")
        print("  python apply_views.py              # Create views")
        print("  cp .env.example .env               # Set up environment")
        return 1


if __name__ == "__main__":
    sys.exit(main())
