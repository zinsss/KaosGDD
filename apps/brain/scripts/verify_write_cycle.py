#!/usr/bin/env python3
import argparse
import json
import urllib.error
import urllib.request
import uuid


def request_json(base, host, method, path, payload=None, expected=(200,)):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
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
            status = response.status
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_body = exc.read()
    result = json.loads(response_body.decode("utf-8"))
    if status not in expected:
        raise RuntimeError(f"{method} {path} returned {status}: {result}")
    return result


def preferred_collection(bootstrap, component, host):
    preferred_owner = "wife" if host == "family.kaosgdd.net" else "zin"
    candidates = [
        collection
        for collection in bootstrap.get("collections", [])
        if component in collection.get("components", [])
    ]
    for collection in candidates:
        if collection.get("owner") == preferred_owner:
            return collection["id"]
    raise RuntimeError(f"no personal {component} collection for {host}")


def item_by_uid(bootstrap, section, uid):
    return next((item for item in bootstrap.get(section, []) if item.get("uid") == uid), None)


def main():
    parser = argparse.ArgumentParser(description="Create, update, verify, and delete temporary Brain records.")
    parser.add_argument("--brain", default="http://100.94.208.16:8092")
    parser.add_argument("--host", default="kaosgdd.net")
    args = parser.parse_args()
    marker = f"Brain parity {uuid.uuid4().hex[:10]}"
    cleanup = []

    try:
        bootstrap = request_json(args.brain, args.host, "GET", "/api/calendar/bootstrap")
        event_collection = preferred_collection(bootstrap, "VEVENT", args.host)
        task_collection = preferred_collection(bootstrap, "VTODO", args.host)

        task = request_json(
            args.brain,
            args.host,
            "POST",
            "/api/calendar/tasks",
            {
                "collectionId": task_collection,
                "title": marker,
                "memo": "Temporary Brain write-parity verification",
                "dueDate": "",
                "dueTime": "",
                "priority": "",
            },
            expected=(201,),
        )
        cleanup.append(("/api/calendar/tasks", task["uid"], task_collection))
        request_json(
            args.brain,
            args.host,
            "PUT",
            "/api/calendar/tasks",
            {
                "uid": task["uid"],
                "collectionId": task_collection,
                "title": f"{marker} updated",
                "memo": "Temporary Brain write-parity verification",
                "dueDate": "",
                "dueTime": "",
                "priority": "",
            },
        )

        event = request_json(
            args.brain,
            args.host,
            "POST",
            "/api/calendar/events",
            {
                "collectionId": event_collection,
                "title": marker,
                "memo": "Temporary Brain write-parity verification",
                "allDay": True,
                "startDate": "2099-12-30",
                "endDate": "2099-12-30",
                "repeat": "",
                "alarmTime": "",
            },
            expected=(201,),
        )
        cleanup.append(("/api/calendar/events", event["uid"], event_collection))
        request_json(
            args.brain,
            args.host,
            "PUT",
            "/api/calendar/events",
            {
                "uid": event["uid"],
                "collectionId": event_collection,
                "title": f"{marker} updated",
                "memo": "Temporary Brain write-parity verification",
                "allDay": True,
                "startDate": "2099-12-30",
                "endDate": "2099-12-30",
                "repeat": "",
                "alarmTime": "",
            },
        )

        bootstrap = request_json(args.brain, args.host, "GET", "/api/calendar/bootstrap")
        saved_task = item_by_uid(bootstrap, "tasks", task["uid"])
        saved_event = item_by_uid(bootstrap, "events", event["uid"])
        if not saved_task or saved_task.get("summary") != f"{marker} updated":
            raise RuntimeError("temporary task was not readable after update")
        if not saved_event or saved_event.get("summary") != f"{marker} updated":
            raise RuntimeError("temporary event was not readable after update")

        print(
            json.dumps(
                {
                    "ok": True,
                    "host": args.host,
                    "taskUid": task["uid"],
                    "eventUid": event["uid"],
                    "verified": ["create", "update", "read"],
                }
            )
        )
    finally:
        cleanup_errors = []
        for path, uid, collection_id in reversed(cleanup):
            try:
                request_json(
                    args.brain,
                    args.host,
                    "DELETE",
                    path,
                    {"uid": uid, "collectionId": collection_id},
                )
            except Exception as exc:
                cleanup_errors.append(f"{path} {uid}: {exc}")
        if cleanup_errors:
            raise RuntimeError(f"temporary record cleanup failed: {cleanup_errors}")

    bootstrap = request_json(args.brain, args.host, "GET", "/api/calendar/bootstrap")
    leftovers = [
        item.get("uid")
        for section in ("events", "tasks")
        for item in bootstrap.get(section, [])
        if item.get("summary", "").startswith(marker)
    ]
    if leftovers:
        raise RuntimeError(f"temporary records remain: {leftovers}")
    print(json.dumps({"ok": True, "host": args.host, "verified": ["delete"], "leftovers": []}))


if __name__ == "__main__":
    main()
