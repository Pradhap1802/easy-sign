# Check if HTTP server is running and print homepage
import requests

try:
    resp = requests.get("http://127.0.0.1:8069", timeout=5)
    print("Status code:", resp.status_code)
    print("Server header:", resp.headers.get("Server"))
    print("Content preview:", resp.text[:200])
except Exception as e:
    print("Error:", e)
