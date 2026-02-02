import json
import subprocess
import time
from pathlib import Path
import requests

BASE1="http://localhost:5001"
BASE2="http://localhost:5002"
ORDER="http://localhost:5003"

def sh(cmd):
    subprocess.run(cmd, shell=True, check=True)

def wait(url):
    for _ in range(50):
        try:
            requests.get(url)
            return
        except:
            time.sleep(0.5)
    raise RuntimeError("timeout")

def main():
    sh("docker network create assn4net || true")
    sh("docker rm -f mongo_order petstore1 petstore2 pet-order || true")

    sh("docker run -d --name mongo_order --network assn4net mongo:7")
    sh("docker run -d --name petstore1 --network assn4net -p 5001:5001 -e PORT=5001 petstore:assn4")
    sh("docker run -d --name petstore2 --network assn4net -p 5002:5001 -e PORT=5001 petstore:assn4")
    sh("docker run -d --name pet-order --network assn4net -p 5003:5001 -e PORT=5001 -e MONGO_URL=mongodb://mongo_order:27017 pet-order:assn4")

    wait(BASE1)
    wait(BASE2)
    wait(ORDER)

    q = Path("query.txt")
    if not q.exists():
        raise RuntimeError("query.txt missing")

    out=[]
    for line in q.read_text().splitlines():
        if line.startswith("query:"):
            rest=line.split("query:",1)[1].strip().rstrip(";")
            store,qs=rest.split(",",1)
            base=BASE1 if store=="1" else BASE2
            r=requests.get(base+"/pet-types?"+qs)
            out+= [str(r.status_code), json.dumps(r.json(),indent=2), ";"]
    Path("response.txt").write_text("\n".join(out))

if __name__=="__main__":
    main()
