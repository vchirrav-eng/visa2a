"""
A2A (Agent2Agent) client agent over HTTP using JSON-RPC 2.0.

Steps:
  1. GET the Agent Card            -> discover what the remote agent can do
  2. message/send "2 plus 3"       -> task completes in one turn
  3. message/send "add 10"         -> task stops at "input-required"
  4. message/send "and 5" (same taskId) -> same task continues and completes
  5. tasks/get                     -> fetch the finished task again by id

Run (after starting server.py):
    python client.py
"""

import json
import urllib.request
import uuid


BASE_URL = "http://127.0.0.1:8002"


def show(label: str, data):
    print(f"[client] {label}\n{json.dumps(data, indent=2)}\n")


def get_agent_card() -> dict:
    url = f"{BASE_URL}/.well-known/agent-card.json"
    print(f"[client] -> GET {url}")
    with urllib.request.urlopen(url) as resp:
        card = json.loads(resp.read().decode("utf-8"))
    show("<- Agent Card", card)
    return card


def rpc(endpoint: str, method: str, params: dict, req_id: int) -> dict:
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    show(f"-> POST {endpoint}", payload)

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        response = json.loads(resp.read().decode("utf-8"))
    show("<-", response)
    return response


def user_message(text: str, task_id: str | None = None, context_id: str | None = None) -> dict:
    message = {
        "kind": "message",
        "role": "user",
        "messageId": str(uuid.uuid4()),
        "parts": [{"kind": "text", "text": text}],
    }
    if task_id:
        message["taskId"] = task_id
    if context_id:
        message["contextId"] = context_id
    return message


def summarize(task: dict):
    state = task["status"]["state"]
    if state == "completed":
        answer = task["artifacts"][0]["parts"][0]["text"]
        print(f"[client] == task {task['id'][:8]} completed: {answer}\n")
    else:
        question = task["status"]["message"]["parts"][0]["text"]
        print(f"[client] == task {task['id'][:8]} is {state}: agent asks \"{question}\"\n")


def main():
    # 1. Discovery: read the Agent Card to find the endpoint and skills.
    card = get_agent_card()
    endpoint = card["url"]
    print(f"[client] == talking to '{card['name']}', skills: "
          f"{[s['id'] for s in card['skills']]}\n")

    # 2. Single-turn task.
    resp = rpc(endpoint, "message/send", {"message": user_message("What is 2 plus 3?")}, req_id=1)
    summarize(resp["result"])

    # 3. Multi-turn task: first message has only one number.
    resp = rpc(endpoint, "message/send", {"message": user_message("Please add 10")}, req_id=2)
    task = resp["result"]
    summarize(task)

    # 4. Reply on the SAME task by sending its taskId and contextId.
    resp = rpc(
        endpoint,
        "message/send",
        {"message": user_message("and 5", task_id=task["id"], context_id=task["contextId"])},
        req_id=3,
    )
    summarize(resp["result"])

    # 5. Look the task up again by id.
    resp = rpc(endpoint, "tasks/get", {"id": task["id"]}, req_id=4)
    summarize(resp["result"])


if __name__ == "__main__":
    main()
