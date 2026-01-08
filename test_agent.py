#!/usr/bin/env python3
"""
Test Agent Locally

Permite probar la lógica de los agentes sin WhatsApp.
Los cambios en la base de datos se hacen en PostgreSQL real.

Usage:
    python test_agent.py "cuántos productos tengo?"
    python test_agent.py "registrar venta: 2 pulseras rojas"
    python test_agent.py --phone +5491112345678 "mi mensaje"
"""

import sys
import argparse
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import graph
from graph import create_business_agent_graph

def test_agent(message: str, phone: str = "+5491112345678"):
    """
    Test agent with a message.

    Args:
        message: User message to process
        phone: Phone number (tenant)
    """
    print("=" * 60)
    print(f"Testing Agent")
    print("=" * 60)
    print(f"Phone: {phone}")
    print(f"Message: {message}")
    print("=" * 60)
    print()

    # Create graph
    graph = create_business_agent_graph()

    # Initial state (same format as WhatsApp server)
    initial_state = {
        "messages": [],
        "user_input": message,
        "phone": phone,
        "sender": phone,
        "normalized_entities": {},
        "metadata": {}
    }

    try:
        # Invoke graph
        print("[Processing...]")
        print()

        result = graph.invoke(initial_state)

        # Extract response
        if "messages" in result and len(result["messages"]) > 0:
            last_message = result["messages"][-1]

            # Handle different message formats
            if hasattr(last_message, 'content'):
                response = last_message.content
            elif isinstance(last_message, dict) and 'content' in last_message:
                response = last_message['content']
            elif isinstance(last_message, str):
                response = last_message
            else:
                response = str(last_message)

            print("[OK] Response:")
            print("-" * 60)
            # Remove emojis for Windows console compatibility
            response_clean = response.encode('ascii', 'ignore').decode('ascii')
            print(response_clean if response_clean.strip() else response)
            print("-" * 60)
        else:
            print("[WARNING] No response generated")

        # Show metadata if available
        if "metadata" in result and result["metadata"]:
            print()
            print("[Metadata]")
            for key, value in result["metadata"].items():
                print(f"  {key}: {value}")

        return result

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None


def interactive_mode(phone: str = "+5491112345678"):
    """Interactive REPL mode."""
    print("=" * 60)
    print("Interactive Agent Test Mode")
    print("=" * 60)
    print(f"Phone: {phone}")
    print()
    print("Commands:")
    print("  Type your message and press Enter")
    print("  Type 'exit' or 'quit' to exit")
    print("  Type 'change phone' to change phone number")
    print("=" * 60)
    print()

    while True:
        try:
            message = input(f"\n[{phone}] >>> ").strip()

            if not message:
                continue

            if message.lower() in ['exit', 'quit']:
                print("Bye!")
                break

            if message.lower() == 'change phone':
                phone = input("New phone number: ").strip()
                print(f"Phone changed to: {phone}")
                continue

            # Test agent
            test_agent(message, phone)

        except KeyboardInterrupt:
            print("\n\nBye!")
            break
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(description="Test Agent Locally")
    parser.add_argument(
        "message",
        nargs="?",
        help="Message to test (omit for interactive mode)"
    )
    parser.add_argument(
        "--phone",
        "-p",
        default="+5491112345678",
        help="Phone number (tenant)"
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode (REPL)"
    )

    args = parser.parse_args()

    # Interactive mode
    if args.interactive or not args.message:
        interactive_mode(args.phone)
    else:
        # Single message mode
        test_agent(args.message, args.phone)


if __name__ == "__main__":
    main()
