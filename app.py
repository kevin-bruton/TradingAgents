#!/usr/bin/env python3
"""
TradingAgents Web Application Launcher

This script starts the TradingAgents webapp using uvicorn.
It provides a convenient entry point to run the FastAPI application.
"""

import uvicorn
import os
import sys
from pathlib import Path

def main():
    """Start the TradingAgents webapp with uvicorn."""
    
    # Get the project root directory
    project_root = Path(__file__).parent.absolute()
    
    # Add the project root to Python path so imports work correctly
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # Change to the project directory to ensure relative paths work
    os.chdir(project_root)
    
    # Configuration for uvicorn
    config = {
        "app": "webapp.main:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": True,  # Enable auto-reload for development
        "reload_dirs": [str(project_root)],  # Watch for changes in project directory
        "log_level": "info",
        "access_log": True,
    }
    
    print("🚀 Starting TradingAgents WebApp...")
    print(f"📁 Project root: {project_root}")
    print(f"🌐 Server will be available at: http://localhost:{config['port']}")
    print("🔄 Auto-reload is enabled for development")
    print("⚠️  Make sure you have set up your .env file with required API keys")
    print("-" * 60)
    
    try:
        # Start the uvicorn server
        uvicorn.run(**config)
    except KeyboardInterrupt:
        print("\n👋 Shutting down TradingAgents WebApp...")
    except Exception as e:
        print(f"❌ Error starting the application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()