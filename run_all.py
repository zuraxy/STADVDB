import subprocess
import sys
import os

def run_backend():
    backend_dir = os.path.join(os.getcwd(), "backend")
    subprocess.Popen(
        ["node", "src/server.js"],
        cwd=backend_dir
    )

def run_frontend():
    frontend_dir = os.path.join(os.getcwd(), "frontend")
    subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=frontend_dir
    )

if __name__ == "__main__":
    run_backend()
    run_frontend()
    print("Backend and frontend started.")