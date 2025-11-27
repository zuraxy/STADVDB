# ...existing code...
import subprocess
import sys
import os
import shutil

def run_backend():
    backend_dir = os.path.join(os.getcwd(), "backend")

    if not os.path.isdir(backend_dir):
        print(f"Backend directory not found: {backend_dir}. Skipping backend start.")
        return

    pkg_json = os.path.join(backend_dir, "package.json")
    # run npm install if package.json exists and npm is available
    npm_path = shutil.which("npm")
    if os.path.exists(pkg_json):
        if npm_path is None:
            print("npm not found on PATH. Install Node.js/npm or add npm to PATH to run `npm install`.")
        else:
            try:
                print("Running npm install in backend...")
                subprocess.run([npm_path, "install"], cwd=backend_dir, check=True)
            except subprocess.CalledProcessError as e:
                print(f"npm install failed: {e}")
                return
            except FileNotFoundError:
                print("Failed to execute npm. Ensure npm is installed and on PATH.")
                return
    else:
        print("No package.json found in backend; skipping npm install.")

    node_path = shutil.which("node")
    server_file = os.path.join(backend_dir, "src", "server.js")
    if not os.path.exists(server_file):
        print(f"Backend server file not found: {server_file}. Skipping backend start.")
        return
    if node_path is None:
        print("node executable not found on PATH. Install Node.js or add node to PATH to start the backend.")
        return

    try:
        subprocess.Popen([node_path, "src/server.js"], cwd=backend_dir)
        print("Backend started.")
    except FileNotFoundError:
        print("Failed to start backend: node not found or invalid command.")
        return
# ...existing code...
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
# ...existing code...