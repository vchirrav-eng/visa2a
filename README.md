# A2A (Agent2Agent) + JSON-RPC 2.0: Teaching Guide

A minimal demo of the **A2A protocol**. A **client agent** talks to a **server agent**
(the "Calculator Agent") using **JSON-RPC 2.0 over HTTP**. It uses only the Python
standard library, so nothing needs installing.

```
 ┌──────────────┐   1. GET  /.well-known/agent-card.json   ┌──────────────────┐
 │ Client agent │ ───────────────────────────────────────▶ │  Server agent    │
 │ (client.py)  │ ◀─────────────── Agent Card ──────────── │ "Calculator      │
 │              │                                          │  Agent"          │
 │              │   2. POST /a2a   JSON-RPC: message/send  │  (server.py)     │
 │              │ ───────────────────────────────────────▶ │                  │
 │              │ ◀──────────── JSON-RPC result: Task ──── │  127.0.0.1:8002  │
 └──────────────┘                                          └──────────────────┘
```

| File | What it is |
|---|---|
| `server.py` | The remote agent. It serves the Agent Card and handles `message/send` and `tasks/get`. |
| `client.py` | The calling agent. It runs the whole conversation and prints every request and response. |

---

## 1. Key vocabulary (introduce before the demo)

| Term | Meaning |
|---|---|
| **Agent Card** | A JSON "business card" at a well-known URL. It gives the agent's name, endpoint URL, capabilities and skills. |
| **Skill** | Something the agent can do (here: `add`). Skills are described in plain English for other agents to read. |
| **Message** | One turn of conversation. It has a `role` (`user` = the caller, `agent` = the remote agent) and a list of **Parts**. |
| **Part** | A piece of content inside a message. This demo uses only `{"kind": "text"}`; A2A also has `file` and `data` parts. |
| **Task** | The unit of work the server creates for a request. It has an `id`, a `status.state`, a `history` and `artifacts`. |
| **Task state** | The lifecycle: `submitted` → `working` → `completed` (or `input-required`, `failed`, `canceled`, ...). |
| **Artifact** | The output the agent produces (here: the text `"2 + 3 = 5"`). |
| **contextId** | Groups related tasks and messages into one conversation. |
| **JSON-RPC 2.0** | The envelope around every call: `{"jsonrpc":"2.0","id":..,"method":..,"params":..}`. The reply contains either `result` or `error`. |

---

## 2. Setup

Open **two terminals** in this folder (`C:\vasu\code\visa2a`).

**Terminal 1: start the server agent**
```
uv run python server.py
```
Expected:
```
[server] A2A Calculator Agent on http://127.0.0.1:8002
[server] Agent Card: http://127.0.0.1:8002/.well-known/agent-card.json
```

**Terminal 2: run the client agent**
```
uv run python client.py
```

(Without uv, `python server.py` / `python client.py` work too, with Python 3.10 or newer.)

> Teaching tip: put the two terminals side by side. Every `[client] ->` request in
> Terminal 2 has a matching `[server] <-` line in Terminal 1.

---

## 3. Lesson walkthrough: the five exchanges

The client runs five steps in order. The payloads below come from a real run; the UUIDs are
shortened and some fields are trimmed with `...`.

### Step 1: Discovery (plain HTTP GET, not JSON-RPC yet)

Before calling an agent, you need to find out what it can do. A2A agents publish an
**Agent Card** at a fixed, well-known path.

```
GET http://127.0.0.1:8002/.well-known/agent-card.json
```
```json
{
  "protocolVersion": "0.3.0",
  "name": "Calculator Agent",
  "description": "Adds up the numbers found in a plain-English message.",
  "url": "http://127.0.0.1:8002/a2a",
  "preferredTransport": "JSONRPC",
  "capabilities": { "streaming": false, "pushNotifications": false },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    { "id": "add", "name": "Add numbers",
      "description": "Adds every number mentioned in the message.",
      "examples": ["What is 2 plus 3?", "Add 10, 20 and 30"] }
  ]
}
```

**Point out to students:**
- The client does **not** hard-code the RPC endpoint. It reads `url` from the card.
- `preferredTransport: "JSONRPC"` tells the caller how to talk to this agent.
- Skills are described in **natural language** with examples. That is written for another
  agent (often an LLM) to read, not for a compiler.

### Step 2: `message/send`, single turn → `completed`

The client sends a natural-language **Message** wrapped in a JSON-RPC request.

**Request**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "role": "user",
      "messageId": "f519baa7-...",
      "parts": [ { "kind": "text", "text": "What is 2 plus 3?" } ]
    }
  }
}
```

**Response**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "kind": "task",
    "id": "690b610d-...",
    "contextId": "ffc2b540-...",
    "status": { "state": "completed", "timestamp": "..." },
    "history": [ { "role": "user", "parts": [ { "kind": "text", "text": "What is 2 plus 3?" } ], "...": "..." } ],
    "artifacts": [
      { "artifactId": "7b522911-...", "name": "sum",
        "parts": [ { "kind": "text", "text": "2 + 3 = 5" } ] }
    ]
  }
}
```

**Point out to students:**
- The **JSON-RPC layer**: `jsonrpc`, `id`, `method`, `params` → `result`. The response `id`
  (1) matches the request `id` (1). That is how a caller pairs replies with requests.
- The **A2A layer** sits inside `params` and `result`: a Message goes in and a **Task** comes back.
- The server created the task `id` and `contextId`; the client did not send them.
- The answer is in **`artifacts`**, not in a bare return value.

### Step 3: `message/send`, multi-turn → `input-required`

The client sends a message with only one number. The agent can't finish, so it **pauses the
task and asks a question**.

**Request** (only the message is shown)
```json
{ "role": "user", "parts": [ { "kind": "text", "text": "Please add 10" } ] }
```

**Response** (trimmed)
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "kind": "task",
    "id": "da65689b-...",
    "contextId": "0309c8d0-...",
    "status": {
      "state": "input-required",
      "message": {
        "role": "agent",
        "parts": [ { "kind": "text",
                     "text": "I need at least two numbers to add. What else should I add?" } ]
      }
    },
    "artifacts": []
  }
}
```

**Point out to students:**
- This is still a **successful** JSON-RPC response (`result`, not `error`). The *task*
  needs more input; the *RPC call* did not fail.
- The agent's question comes back as a Message with `role: "agent"`.
- `artifacts` is empty because there's no answer yet.

### Step 4: `message/send` again, continuing the same task → `completed`

The client answers the question. It sends the **same `taskId` and `contextId`** so the server
knows this message belongs to the paused task.

**Request** (message only)
```json
{
  "role": "user",
  "parts": [ { "kind": "text", "text": "and 5" } ],
  "taskId": "da65689b-...",
  "contextId": "0309c8d0-..."
}
```

**Response** (trimmed)
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "id": "da65689b-...",
    "status": { "state": "completed" },
    "history": [
      { "role": "user",  "parts": [ { "text": "Please add 10" } ] },
      { "role": "agent", "parts": [ { "text": "I need at least two numbers to add. What else should I add?" } ] },
      { "role": "user",  "parts": [ { "text": "and 5" } ] }
    ],
    "artifacts": [ { "name": "sum", "parts": [ { "kind": "text", "text": "10 + 5 = 15" } ] } ]
  }
}
```

**Point out to students:**
- The **task id is the same** as in Step 3. One task, two turns.
- The server is **stateful**: it remembered "10" from the earlier turn. Look at `history`.
- Compare this with MCP, where each `tools/call` is independent and stateless.

### Step 5: `tasks/get`, looking up a task by id

```json
{ "jsonrpc": "2.0", "id": 4, "method": "tasks/get", "params": { "id": "da65689b-..." } }
```
The response is the same completed Task as in Step 4.

**Point out to students:** a different JSON-RPC `method` is called on the same endpoint
(`/a2a`). In real systems, `tasks/get` lets a caller **poll** a long-running task.

---

## 4. Showing JSON-RPC errors

Send these by hand (see section 5) to show the `error` side of JSON-RPC.

| Send this | Response `error.code` | Why |
|---|---|---|
| `tasks/get` with `"id": "nope"` | `-32001` | **A2A-specific** error: TaskNotFound |
| `"method": "tasks/cancel"` | `-32601` | Standard JSON-RPC: method not found (this demo doesn't implement cancel) |
| `message/send` with no `message` | `-32602` | Standard JSON-RPC: invalid params |
| `"jsonrpc": "1.0"` | `-32600` | Standard JSON-RPC: invalid request |
| A body that isn't valid JSON | `-32700` | Standard JSON-RPC: parse error |

Example response:
```json
{"jsonrpc": "2.0", "id": 9, "error": {"code": -32001, "message": "Task not found: nope"}}
```

**Point out to students:** a response contains `result` **or** `error`, never both.
JSON-RPC reserves codes -32700 to -32600 for its own errors. A2A defines its own codes in the
range -32001 and below.

---

## 5. Sending requests by hand (live in class)

With the server running, students can act as the client agent themselves.

**Bash / macOS / Linux / Git Bash**
```bash
# Discovery
curl http://127.0.0.1:8002/.well-known/agent-card.json

# Send a message
curl -X POST http://127.0.0.1:8002/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"text","text":"add 4 and 6"}]}}}'

# Error: unknown task
curl -X POST http://127.0.0.1:8002/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tasks/get","params":{"id":"nope"}}'
```

**Windows PowerShell** (in PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`, so use `Invoke-RestMethod`)
```powershell
# Discovery
Invoke-RestMethod http://127.0.0.1:8002/.well-known/agent-card.json

# Send a message
$body = '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"text","text":"add 4 and 6"}]}}}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8002/a2a -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 10
```

To continue an `input-required` task by hand, copy `result.id` and `result.contextId` from the
response into `taskId` / `contextId` inside the next `message`.

---

## 6. Seeing it on the wire (Wireshark)

1. Start Wireshark and capture on the **loopback** interface
   (on Windows: "Adapter for loopback traffic capture", which needs Npcap).
2. Display filter: `tcp.port == 8002`. To show only the HTTP messages: `http && tcp.port == 8002`.
3. Run `client.py`.
4. Right-click an HTTP POST → **Follow → HTTP Stream**.

**Point out to students:**
- You will see 1 GET (the Agent Card) and 4 POSTs (the JSON-RPC calls).
- Everything is **plain, human-readable JSON** in an HTTP/1.1 body. JSON-RPC itself has
  no framing beyond that.
- Every POST goes to the **same URL** (`/a2a`). The operation is chosen by the `method`
  field inside the body, not by the URL path (unlike REST).

---

## 7. Comparing with MCP (`..\vismcp\http_jsonrpc`)

Run both demos and put their output side by side. Both use **JSON-RPC 2.0 over HTTP**, but
they solve different problems.

| | MCP (`vismcp/http_jsonrpc`, port 8001) | A2A (this folder, port 8002) |
|---|---|---|
| Who talks | app / LLM → **tool** | **agent → agent** |
| Discovery | `tools/list` RPC call | Agent Card at a well-known URL (plain GET) |
| Request | `tools/call` with structured arguments `{"a": 2, "b": 3}` | `message/send` with a natural-language **Message** made of **Parts** |
| Response | a value: `{"content": 5}` | a **Task** with a lifecycle and **artifacts** |
| State | stateless, one call = one answer | stateful: `taskId` + `contextId` link several turns |
| Can ask back? | no | yes: `input-required` |

A useful one-liner for class: **MCP gives an agent tools; A2A lets agents talk to other agents.**
In practice the two are used together. An A2A agent like the Calculator Agent could call MCP tools
internally to do its work.

---

## 8. Exercises for students

1. **Read the card.** Using only `curl`, find the endpoint URL and the skill examples. Then
   send one of the example sentences.
2. **Multi-turn by hand.** Send `"add 7"`, read the `input-required` response, then send a
   follow-up with the right `taskId` and `contextId` so the task completes.
3. **Break it.** Trigger each error code in section 4. Which errors are JSON-RPC errors and
   which are A2A errors?
4. **Add a skill.** Extend `server.py` with a `multiply` skill: add it to the Agent Card and
   choose between add and multiply based on the words in the message.
5. **Add `tasks/cancel`.** Add a method that sets a task's state to `canceled`. Return error
   `-32002` (TaskNotCancelable) if the task is already `completed`.
6. **Agent chain.** Write a third agent that receives a message, forwards it to the Calculator
   Agent with `message/send`, and returns the answer. Now an agent is a client **and** a server.

---

## 9. Scope and spec notes

- Method and field names follow **A2A spec v0.3** (`message/send`, `tasks/get`, `kind`).
- To keep the demo short it leaves out streaming (`message/stream` over Server-Sent Events),
  push notifications, authentication, and file/data parts.
- Tasks are stored in memory, so restarting the server forgets them.
- The "agent" is a regex that adds numbers, not an LLM. The protocol is the same either way;
  only the code inside `run_agent()` would change.
