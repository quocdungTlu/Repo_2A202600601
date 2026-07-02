#!/usr/bin/env python3
"""
Verification script for Weather Agent setup
Checks if all components are configured correctly
"""
import os
import sys
from pathlib import Path

def check_environment():
    """Check if .env file exists and is configured"""
    print("🔍 Checking environment configuration...")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found")
        print("   Run: echo 'GOOGLE_API_KEY=your_key' > .env")
        return False
    
    # Check if GOOGLE_API_KEY is set
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your_google_api_key_here":
        print("❌ GOOGLE_API_KEY not configured in .env")
        print("   Get key from: https://aistudio.google.com/apikey")
        return False
    
    print(f"✅ GOOGLE_API_KEY configured ({api_key[:10]}...)")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    print("\n🔍 Checking dependencies...")
    
    required_packages = [
        ("google.adk", "Google ADK"),
        ("google.generativeai", "Google Generative AI"),
        ("mcp", "MCP"),
        ("fastmcp", "FastMCP"),
        ("dotenv", "python-dotenv"),
        ("httpx", "httpx"),
    ]
    
    all_installed = True
    for package, name in required_packages:
        try:
            __import__(package)
            print(f"✅ {name}")
        except ImportError:
            print(f"❌ {name} not installed")
            all_installed = False
    
    if not all_installed:
        print("\n   Install with: uv sync")
        print("   Or: pip install google-adk google-generativeai mcp fastmcp python-dotenv httpx")
    
    return all_installed

def check_agent_structure():
    """Check if agent directory structure is correct"""
    print("\n🔍 Checking agent structure...")
    
    required_files = [
        "weather_agent/agent.py",
        "weather_agent/__init__.py",
    ]
    
    all_exist = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} not found")
            all_exist = False
    
    return all_exist

def check_mcp_server():
    """Check if the local MCP server is accessible"""
    print("\n🔍 Checking MCP server connectivity...")

    # Local server started via `uv run python weather.py` in ../mcp-server
    # (agent.py connects to this same URL). Override with MCP_SERVER_URL if needed.
    server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8085/mcp")

    try:
        import httpx
        import asyncio

        async def test_connection():
            async with httpx.AsyncClient() as client:
                response = await client.get(server_url, timeout=10.0)
                return response.status_code

        status_code = asyncio.run(test_connection())

        # Any HTTP response means the server is up. A GET on the MCP endpoint
        # typically returns 400/404/406 since MCP expects POST — that's fine.
        if status_code < 500:
            print(f"✅ MCP server reachable at {server_url} (status {status_code})")
            return True
        else:
            print(f"⚠️  MCP server returned status {status_code}")
            return False

    except Exception as e:
        print(f"❌ Cannot reach MCP server at {server_url}: {e}")
        print("   Start it first: cd ../mcp-server && uv run python weather.py")
        return False

def check_agent_import():
    """Try to import the agent"""
    print("\n🔍 Checking agent import...")
    
    try:
        # Suppress warnings during import
        import warnings
        warnings.filterwarnings("ignore")
        
        from weather_agent import root_agent
        print(f"✅ Agent imported successfully: {root_agent.name}")
        print(f"   Model: {root_agent.model}")
        return True
    except Exception as e:
        print(f"❌ Failed to import agent: {e}")
        return False

def main():
    """Run all verification checks"""
    print("=" * 60)
    print("Weather Agent Setup Verification")
    print("=" * 60)
    print()
    
    checks = [
        check_environment(),
        check_dependencies(),
        check_agent_structure(),
        check_mcp_server(),
        check_agent_import(),
    ]
    
    print("\n" + "=" * 60)
    if all(checks):
        print("✅ All checks passed!")
        print("\n🚀 Ready to start!")
        print("   Run: uv run adk web")
        print("\n📍 Then open: http://localhost:8000")
        return 0
    else:
        print("❌ Some checks failed")
        print("\n⚠️  Fix the issues above and run this script again")
        return 1

if __name__ == "__main__":
    sys.exit(main())

