import time
import uuid
import requests
import json
import sys

# Configuration
NODE_URL = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

def print_step(msg):
    print(f"\n[TEST] ➤ {msg}")

def check_health():
    print_step("Checking Node Health...")
    try:
        resp = requests.get(f"{NODE_URL}/recovery/health")
        if resp.status_code == 200:
            print(f"✅ Node is UP. State: {resp.json().get('state')}")
            return True
        else:
            print(f"❌ Node returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Could not connect to node: {e}")
        return False

def trigger_recovery():
    print_step("Triggering Leader Recovery...")
    payload = {"mode": "leader"}
    try:
        resp = requests.post(f"{NODE_URL}/recovery/start", json=payload, headers=HEADERS)
        if resp.status_code == 200:
            job_data = resp.json()
            job_id = job_data.get("job_id")
            print(f"✅ Recovery Job Started. Job ID: {job_id}")
            return job_id
        else:
            print(f"❌ Failed to start recovery: {resp.text}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Exception starting recovery: {e}")
        sys.exit(1)

def poll_status(job_id):
    print_step(f"Polling Status for Job {job_id}...")
    
    while True:
        resp = requests.get(f"{NODE_URL}/recovery/status/{job_id}")
        if resp.status_code != 200:
            print("❌ Failed to get status")
            break
            
        data = resp.json()
        progress = data.get("progress", {})
        state = progress.get("state")
        ops_remaining = progress.get("ops_remaining", 0)
        
        print(f"   ⟳ State: {state.upper()} | Ops Remaining: {ops_remaining} | Fetched: {progress.get('ops_fetched')}")
        
        if state == "ready":
            print("\n✅ Recovery COMPLETE! Node is READY.")
            break
        elif state == "failed":
            print(f"\n❌ Recovery FAILED. Error: {progress.get('last_error')}")
            sys.exit(1)
            
        time.sleep(1)

def main():
    print("=== STARTING RECOVERY INTEGRATION TEST ===")
    
    # 1. Check if node is running
    if not check_health():
        print("Please start your FastAPI server first: uvicorn main:app --reload")
        sys.exit(1)

    # 2. Start Recovery
    job_id = trigger_recovery()
    
    # 3. Monitor until done
    poll_status(job_id)
    
    # 4. Final Verification
    print_step("Final Health Check...")
    final_health = requests.get(f"{NODE_URL}/recovery/health").json()
    if final_health.get("is_ready") is True:
        print("✅ SUCCESS: Node reports it is READY and authoritative.")
    else:
        print("❌ FAILURE: Node is not marked as ready.")

if __name__ == "__main__":
    main()