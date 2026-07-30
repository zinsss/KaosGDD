#!/usr/bin/env python3
import argparse
import hashlib
import json
import urllib.request


def fetch(base, host, path):
    request = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={
            "Accept": "application/json",
            "Host": host,
            "X-Forwarded-Host": host,
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def canonical_digest(payload):
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Compare Brain shadow payloads with the live calendar adapter.")
    parser.add_argument("--adapter", default="http://100.94.208.16:8091")
    parser.add_argument("--brain", default="http://100.94.208.16:8092")
    parser.add_argument("--host", action="append", default=[])
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args()
    hosts = args.host or ["kaosgdd.net", "family.kaosgdd.net"]
    paths = args.path or ["/api/calendar/bootstrap"]
    failed = False

    for host in hosts:
        for path in paths:
            adapter_payload = fetch(args.adapter, host, path)
            brain_payload = fetch(args.brain, host, path)
            adapter_digest = canonical_digest(adapter_payload)
            brain_digest = canonical_digest(brain_payload)
            match = adapter_digest == brain_digest
            failed = failed or not match
            print(
                json.dumps(
                    {
                        "host": host,
                        "path": path,
                        "match": match,
                        "adapterSha256": adapter_digest,
                        "brainSha256": brain_digest,
                    },
                    ensure_ascii=False,
                )
            )

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
