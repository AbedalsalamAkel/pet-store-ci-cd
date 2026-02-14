import time
import requests

BASE1 = "http://localhost:5001"
BASE2 = "http://localhost:5002"

def wait_up(base):
    for _ in range(40):
        try:
            requests.get(base)
            return
        except:
            time.sleep(0.5)
    raise RuntimeError("Service not up")

def test_flow():
    wait_up(BASE1)
    wait_up(BASE2)

    r1 = requests.post(BASE1 + "/pet-types", json={"type":"Australian Shepherd"})
    assert r1.status_code == 201
    pid = r1.json()["id"]

    r2 = requests.get(f"{BASE1}/pet-types/{pid}")
    # assert r2.status_code == 200
    assert r2.status_code == 404
