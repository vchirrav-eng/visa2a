"""
A2A (Agent2Agent) server agent over HTTP using JSON-RPC 2.0.

Transport: HTTP
  GET  /.well-known/agent-card.json  -> Agent Card (discovery)
  POST /a2a                          -> JSON-RPC 2.0 (message/send, tasks/get)
Encoding:  JSON text

The agent is a "Calculator Agent". It reads a plain-English message,
finds the numbers in it, and adds them up. If it finds fewer than two
numbers it asks the caller for more (task state "input-required").

Run:
    python server.py
"""

import datetime
import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST, PORT = "127.0.0.1", 8002


# ---- Agent Card: the agent's public "business card" ------------------------
AGENT_CARD = {
    "protocolVersion": "0.3.0",
    "name": "Calculator Agent",
    "description": "Adds up the numbers found in a plain-English message.",
    "url": f"http://{HOST}:{PORT}/a2a",
    "preferredTransport": "JSONRPC",
    "version": "1.0.0",
    "capabilities": {"streaming": False, "pushNotifications": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "add",
            "name": "Add numbers",
            "description": "Adds every number mentioned in the message.",
            "tags": ["math", "calculator"],
            "examples": ["What is 2 plus 3?", "Add 10, 20 and 30"],
        }
    ],
}


# ---- Task store (in memory) ------------------------------------------------
TASKS = {}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def text_of(message: dict) -> str:
    return " ".join(p["text"] for p in message.get("parts", []) if p.get("kind") == "text")


def agent_message(text: str, task_id: str, context_id: str) -> dict:
    return {
        "kind": "message",
        "role": "agent",
        "messageId": str(uuid.uuid4()),
        "taskId": task_id,
        "contextId": context_id,
        "parts": [{"kind": "text", "text": text}],
    }


# ---- The agent's "brain" ---------------------------------------------------
def run_agent(task: dict):
    """Look at every user message in the task so far and decide what to do."""
    user_text = " ".join(text_of(m) for m in task["history"] if m["role"] == "user")
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", user_text)]

    if len(numbers) < 2:
        reply = "I need at least two numbers to add. What else should I add?"
        task["status"] = {
            "state": "input-required",
            "message": agent_message(reply, task["id"], task["contextId"]),
            "timestamp": now(),
        }
        return

    total = sum(numbers)
    answer = f"{' + '.join(f'{n:g}' for n in numbers)} = {total:g}"
    task["artifacts"] = [
        {
            "artifactId": str(uuid.uuid4()),
            "name": "sum",
            "parts": [{"kind": "text", "text": answer}],
        }
    ]
    task["status"] = {"state": "completed", "timestamp": now()}


# ---- JSON-RPC 2.0 dispatch -------------------------------------------------
def rpc_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def rpc_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def message_send(req_id, params: dict) -> dict:
    message = params.get("message")
    if not message or message.get("role") != "user":
        return rpc_error(req_id, -32602, "Invalid params: 'message' with role 'user' is required")

    task_id = message.get("taskId")
    if task_id:
        # Follow-up message for an existing task (multi-turn).
        task = TASKS.get(task_id)
        if task is None:
            return rpc_error(req_id, -32001, f"Task not found: {task_id}")
        if task["status"]["state"] != "input-required":
            return rpc_error(req_id, -32602, f"Invalid params: task {task_id} is not waiting for input")
    else:
        # First message: start a new task.
        task_id = str(uuid.uuid4())
        task = {
            "kind": "task",
            "id": task_id,
            "contextId": message.get("contextId") or str(uuid.uuid4()),
            "status": {"state": "submitted", "timestamp": now()},
            "history": [],
            "artifacts": [],
        }
        TASKS[task_id] = task

    message["taskId"] = task_id
    message["contextId"] = task["contextId"]
    task["history"].append(message)
    task["status"] = {"state": "working", "timestamp": now()}

    run_agent(task)

    if task["status"].get("message"):
        task["history"].append(task["status"]["message"])
    return rpc_result(req_id, task)


def tasks_get(req_id, params: dict) -> dict:
    task = TASKS.get(params.get("id"))
    if task is None:
        return rpc_error(req_id, -32001, f"Task not found: {params.get('id')}")
    return rpc_result(req_id, task)


METHODS = {
    "message/send": message_send,
    "tasks/get": tasks_get,
}


def handle_rpc(request: dict) -> dict:
    req_id = request.get("id")
    if request.get("jsonrpc") != "2.0":
        return rpc_error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = METHODS.get(request.get("method"))
    if method is None:
        return rpc_error(req_id, -32601, f"Method not found: {request.get('method')}")
    return method(req_id, request.get("params") or {})


# ---- HTTP layer ------------------------------------------------------------
class A2AHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/.well-known/agent-card.json":
            self.send_error(404, "Not Found")
            return
        print(f"[server] <- GET {self.path}")
        self._send_json(200, json.dumps(AGENT_CARD).encode("utf-8"))
        print("[server] -> Agent Card")

    def do_POST(self):
        if self.path != "/a2a":
            self.send_error(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            body = json.dumps(rpc_error(None, -32700, "Parse error")).encode()
            self._send_json(400, body)
            return

        print(f"[server] <- {raw}")
        response = handle_rpc(request)
        body = json.dumps(response).encode("utf-8")
        print(f"[server] -> {body.decode()}")
        self._send_json(200, body)

    def _send_json(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), A2AHandler)
    print(f"[server] A2A Calculator Agent on http://{HOST}:{PORT}")
    print(f"[server] Agent Card: http://{HOST}:{PORT}/.well-known/agent-card.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
