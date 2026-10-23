"""Single-file customer chat and ops console (no build step, no extra dependencies)."""

CHAT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Northwind Support</title>
<style>
  :root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f8fafc;--brand:#0b3b6f;--accent:#c8a24a}
  *{box-sizing:border-box} body{margin:0;font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
  header{background:var(--brand);color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:center}
  header h1{font-size:16px;margin:0;letter-spacing:.02em} header a{color:#dbe7f5;font-size:13px;text-decoration:none}
  .wrap{max-width:860px;margin:0 auto;padding:20px}
  .card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
  label{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
  select,input,button{font:inherit}
  select,input{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:8px;margin:6px 0 10px}
  button{background:var(--brand);color:#fff;border:0;border-radius:8px;padding:10px 16px;cursor:pointer}
  button.ghost{background:#fff;color:var(--brand);border:1px solid var(--line)}
  button:disabled{opacity:.5;cursor:not-allowed}
  #log{min-height:320px;max-height:56vh;overflow:auto;display:flex;flex-direction:column;gap:12px;padding:4px}
  .msg{max-width:82%;padding:10px 13px;border-radius:12px;white-space:pre-wrap}
  .user{align-self:flex-end;background:var(--brand);color:#fff;border-bottom-right-radius:4px}
  .bot{align-self:flex-start;background:#f1f5f9;border:1px solid var(--line);border-bottom-left-radius:4px}
  .meta{font-size:11px;color:var(--muted);margin-top:6px;display:flex;gap:10px;flex-wrap:wrap}
  .chip{background:#fff;border:1px solid var(--line);border-radius:99px;padding:2px 8px}
  .row{display:flex;gap:8px}.row input{margin:0}
  .hint{font-size:12px;color:var(--muted)}
  .orders{font-size:13px;color:var(--muted);margin-top:6px}
  .orders b{color:var(--ink)}
  .warn{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;padding:8px 10px;border-radius:8px;font-size:12px;margin-bottom:10px}
</style>
</head>
<body>
<header><h1>Northwind Outfitters — Support</h1><a href="/ops">Ops console →</a></header>
<div class="wrap">
  <div class="card">
    <label for="customer">Sign in as a demo customer</label>
    <div class="row">
      <select id="customer"></select>
      <button id="signin">Start chat</button>
    </div>
    <div class="orders" id="orders"></div>
  </div>

  <div class="card">
    <div class="warn">Demo mode: synthetic data only. The assistant cannot see another customer's orders; every refund is policy-checked server-side.</div>
    <div id="log"></div>
    <div class="row" style="margin-top:12px">
      <input id="input" placeholder="e.g. My headphones from ORD-1001 arrived damaged, I'd like a refund" disabled>
      <button id="send" disabled>Send</button>
    </div>
    <div class="hint" id="model"></div>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
let token = null, conversationId = null;

async function api(path, opts = {}) {
  const headers = {"Content-Type": "application/json", ...(opts.headers || {})};
  if (token) headers["X-Demo-Session"] = token;
  const res = await fetch(path, {...opts, headers});
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.statusText);
  return body;
}

function bubble(role, text, meta) {
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "user" : "bot");
  div.textContent = text;
  if (meta) {
    const m = document.createElement("div");
    m.className = "meta";
    meta.forEach(t => { const s = document.createElement("span"); s.className = "chip"; s.textContent = t; m.appendChild(s); });
    div.appendChild(m);
  }
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
}

async function loadCustomers() {
  const list = await api("/api/customers");
  $("customer").innerHTML = list.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
  const info = await api("/api/model-info");
  $("model").textContent = `Serving: ${info.model_id} · policy ${info.policy_version} · ${info.serving}`;
}

$("signin").onclick = async () => {
  try {
    const login = await api("/api/login", {method: "POST", body: JSON.stringify({customer_id: Number($("customer").value)})});
    token = login.token;
    const conv = await api("/api/conversations", {method: "POST", body: "{}"});
    conversationId = conv.conversation_id;
    $("log").innerHTML = "";
    bubble("bot", `Hi ${login.customer.name.split(" ")[0]} — I can help with orders, returns, refunds, replacements and product questions. What's up?`);
    $("input").disabled = false; $("send").disabled = false; $("input").focus();
    renderOrders();
  } catch (e) { alert(e.message); }
};

async function renderOrders() {
  const orders = await api("/api/orders");
  $("orders").innerHTML = orders.map(o =>
    `<div><b>${o.order_id}</b> — ${o.status} · $${(o.total_cents/100).toFixed(2)}</div>`).join("");
}

async function send() {
  const text = $("input").value.trim();
  if (!text || !conversationId) return;
  $("input").value = ""; bubble("user", text);
  const btn = $("send"); btn.disabled = true;
  try {
    const r = await api(`/api/conversations/${conversationId}/messages`, {method: "POST", body: JSON.stringify({message: text})});
    const meta = [`intent: ${r.intent}`, `decision: ${r.reason_code}`, `${r.latency_ms} ms`];
    if (r.action_taken) meta.push(`action: ${r.action_taken}`);
    bubble("bot", r.message, meta);
    if (r.escalated) bubble("bot", "A colleague has the case — reference in the message above.", ["escalated"]);
  } catch (e) {
    bubble("bot", "Something went wrong: " + e.message, ["error"]);
  } finally { btn.disabled = false; $("input").focus(); }
}

$("send").onclick = send;
$("input").addEventListener("keydown", e => { if (e.key === "Enter") send(); });
loadCustomers().catch(e => alert(e.message));
</script>
</body></html>
"""


OPS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Northwind — Ops</title>
<style>
  :root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f8fafc;--brand:#0b3b6f}
  *{box-sizing:border-box} body{margin:0;font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
  header{background:var(--brand);color:#fff;padding:14px 20px;display:flex;justify-content:space-between}
  header h1{font-size:16px;margin:0} header a{color:#dbe7f5;text-decoration:none;font-size:13px}
  .wrap{max-width:1120px;margin:0 auto;padding:20px}
  .cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
  .card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px}
  .card .n{font-size:24px;font-weight:600}.card .l{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
  h2{font-size:14px;margin:18px 0 8px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
  th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:top}
  th{background:#f8fafc;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
  tr:last-child td{border-bottom:0}
  button{font:inherit;background:var(--brand);color:#fff;border:0;border-radius:6px;padding:5px 10px;cursor:pointer;margin-right:4px}
  button.no{background:#fff;color:#b91c1c;border:1px solid #fecaca}
  .pill{padding:1px 7px;border-radius:99px;font-size:11px;background:#eef2f7}
  .pill.open,.pill.pending_approval,.pill.pending{background:#fff7ed;color:#9a3412}
  .pill.approved,.pill.processed{background:#ecfdf5;color:#047857}
  .pill.denied{background:#fef2f2;color:#b91c1c}
  .muted{color:var(--muted)}
</style>
</head>
<body>
<header><h1>Northwind — Support Operations</h1><a href="/">Customer chat →</a></header>
<div class="wrap">
  <div class="cards" id="stats"></div>
  <h2>Refund approvals (above auto-approval limit)</h2>
  <table><thead><tr><th>ID</th><th>Refund</th><th>Amount</th><th>Reason</th><th>Status</th><th>Action</th></tr></thead><tbody id="approvals"></tbody></table>
  <h2>Escalations</h2>
  <table><thead><tr><th>ID</th><th>Conversation</th><th>Reason</th><th>Summary</th><th>Status</th></tr></thead><tbody id="escalations"></tbody></table>
  <h2>Audit trail</h2>
  <table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Decision</th><th>Reason</th><th>Correlation</th></tr></thead><tbody id="audit"></tbody></table>
</div>
<script>
const $ = (id) => document.getElementById(id);
const money = (c) => "$" + (c/100).toFixed(2);
async function api(path, opts = {}) {
  const res = await fetch(path, {...opts, headers: {"Content-Type": "application/json", ...(opts.headers||{})}});
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.statusText);
  return body;
}
function pill(s) { return `<span class="pill ${s}">${s}</span>`; }

async function load() {
  const [stats, approvals, escalations, audit] = await Promise.all([
    api("/api/ops/stats"), api("/api/ops/approvals"), api("/api/ops/escalations"), api("/api/ops/audit")
  ]);
  $("stats").innerHTML = [
    ["Model", stats.model_id], ["Orders", stats.orders],
    ["Pending approvals", stats.pending_approvals], ["Open escalations", stats.escalations]
  ].map(([l, n]) => `<div class="card"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");

  $("approvals").innerHTML = approvals.map(a => `<tr>
    <td>${a.id}</td><td>#${a.refund_id ?? "-"}</td><td>${money(a.amount_cents)}</td>
    <td class="muted">${a.reason}</td><td>${pill(a.status)}</td>
    <td>${a.status === "pending"
      ? `<button onclick="decide(${a.id},'approve')">Approve</button><button class="no" onclick="decide(${a.id},'deny')">Deny</button>`
      : `<span class="muted">decided</span>`}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">No approvals yet.</td></tr>`;

  $("escalations").innerHTML = escalations.map(e => `<tr>
    <td>${e.id}</td><td>${e.conversation_id}</td><td>${e.reason}</td>
    <td class="muted">${e.summary}</td><td>${pill(e.status)}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">No escalations.</td></tr>`;

  $("audit").innerHTML = audit.map(a => `<tr>
    <td class="muted">${a.ts.replace("T"," ").slice(0,19)}</td><td>${a.actor}</td><td>${a.action}</td>
    <td>${a.target}</td><td>${pill(a.decision.toLowerCase())}</td><td>${a.reason_code}</td>
    <td class="muted">${a.correlation_id}</td></tr>`).join("");
}

async function decide(id, decision) {
  await api(`/api/ops/approvals/${id}`, {method:"POST", body: JSON.stringify({decision, note: "ops console"})});
  load();
}
load().catch(e => alert(e.message));
setInterval(load, 15000);
</script>
</body></html>
"""
