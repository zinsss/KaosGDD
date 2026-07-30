#!/usr/bin/env python3
import argparse
import json
import urllib.error
import urllib.request


CASES = (
    ("POST", "/api/calendar/events"),
    ("PUT", "/api/calendar/events"),
    ("DELETE", "/api/calendar/events"),
    ("POST", "/api/calendar/tasks"),
    ("PUT", "/api/calendar/tasks"),
    ("DELETE", "/api/calendar/tasks"),
)


def request_json(base, host, method, path, payload):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Host": host,
            "X-Forwarded-Host": host,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main():
    parser = argparse.ArgumentParser(description="Compare non-mutating Brain write contracts with the live adapter.")
    parser.add_argument("--adapter", default="http://100.94.208.16:8091")
    parser.add_argument("--brain", default="http://100.94.208.16:8092")
    parser.add_argument("--host", action="append", default=[])
    args = parser.parse_args()
    hosts = args.host or ["kaosgdd.net", "family.kaosgdd.net"]
    failed = False

    for host in hosts:
        for method, path in CASES:
            adapter_status, adapter_payload = request_json(args.adapter, host, method, path, {})
            brain_status, brain_payload = request_json(args.brain, host, method, path, {})
            match = adapter_status == brain_status and canonical(adapter_payload) == canonical(brain_payload)
            failed = failed or not match
            print(
                json.dumps(
                    {
                        "host": host,
                        "method": method,
                        "path": path,
                        "match": match,
                        "adapterStatus": adapter_status,
                        "brainStatus": brain_status,
                        "adapterPayload": adapter_payload,
                        "brainPayload": brain_payload,
                    },
                    ensure_ascii=False,
                )
            )

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
