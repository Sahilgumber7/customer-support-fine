"""Customer chat, landing page, and ops console — rebuilt with SOP authority panel."""
import io as _io

# ---------------------------------------------------------------------------
# Landing / Chat page
# ---------------------------------------------------------------------------

CHAT_HTML = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Customer Support Fine — Policy-Gated AI Support</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --ink: #0f172a; --muted: #64748b; --line: #e2e8f0; --bg: #f8fafc;
    --brand: #1e3a5f; --brand2: #2563eb; --accent: #f59e0b;
    --green: #10b981; --red: #ef4444; --glass: rgba(255,255,255,0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font: 15px/1.6 'Inter', ui-sans-serif, system-ui, sans-serif; color: var(--ink); background: var(--bg); }

  /* ── HERO ── */
  .hero {
    background: linear-gradient(135deg, #0f2444 0%, #1e3a5f 45%, #1d4ed8 100%);
    color: #fff; padding: 0 20px;
  }
  .hero-inner { max-width: 1080px; margin: 0 auto; }
  nav { display: flex; justify-content: space-between; align-items: center; padding: 18px 0; }
  nav .logo { font-weight: 700; font-size: 18px; letter-spacing: -.02em; }
  nav .logo span { color: var(--accent); }
  nav a { color: rgba(255,255,255,.8); text-decoration: none; font-size: 13px; font-weight: 500;
           padding: 7px 14px; border: 1px solid rgba(255,255,255,.2); border-radius: 8px; transition: all .2s; }
  nav a:hover { background: rgba(255,255,255,.1); }
  .hero-body { display: grid; grid-template-columns: 1fr 1fr; gap: 48px; align-items: center; padding: 64px 0 72px; }
  .hero-body h1 { font-size: 42px; font-weight: 700; line-height: 1.15; letter-spacing: -.03em; margin-bottom: 18px; }
  .hero-body h1 em { font-style: normal; color: var(--accent); }
  .hero-body p { font-size: 17px; line-height: 1.7; color: rgba(255,255,255,.8); margin-bottom: 28px; }
  .badge-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 32px; }
  .badge { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.18);
           border-radius: 99px; padding: 4px 12px; font-size: 12px; font-weight: 500; }
  .badge.green { background: rgba(16,185,129,.2); border-color: rgba(16,185,129,.4); color: #6ee7b7; }
  .badge.amber { background: rgba(245,158,11,.2); border-color: rgba(245,158,11,.4); color: #fcd34d; }

  /* chat card preview */
  .hero-card { background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.12);
               backdrop-filter: blur(16px); border-radius: 20px; padding: 20px; min-height: 340px;
               display: flex; flex-direction: column; gap: 12px; }
  .hc-header { display: flex; align-items: center; gap: 10px; padding-bottom: 14px;
               border-bottom: 1px solid rgba(255,255,255,.1); }
  .hc-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--accent);
               display: flex; align-items: center; justify-content: center; font-size: 16px; }
  .hc-name { font-weight: 600; font-size: 14px; }
  .hc-status { font-size: 11px; color: var(--green); }
  .hc-msg { max-width: 85%; padding: 10px 14px; border-radius: 16px; font-size: 13px; line-height: 1.5; }
  .hc-msg.bot { background: rgba(255,255,255,.1); border-bottom-left-radius: 4px; }
  .hc-msg.user { align-self: flex-end; background: var(--brand2); border-bottom-right-radius: 4px; }
  .hc-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 2px; }
  .hc-chip { background: rgba(16,185,129,.2); border: 1px solid rgba(16,185,129,.3);
             border-radius: 99px; padding: 2px 8px; font-size: 11px; color: #6ee7b7; }
  .hc-chip.orange { background: rgba(245,158,11,.2); border-color: rgba(245,158,11,.3); color: #fcd34d; }

  /* ── FEATURES ── */
  .features { max-width: 1080px; margin: 0 auto; padding: 64px 20px; }
  .section-label { font-size: 12px; font-weight: 600; text-transform: uppercase;
                   letter-spacing: .1em; color: var(--brand2); margin-bottom: 10px; }
  .section-title { font-size: 30px; font-weight: 700; letter-spacing: -.02em; margin-bottom: 14px; }
  .section-sub { font-size: 16px; color: var(--muted); max-width: 540px; margin-bottom: 48px; }
  .feat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
  .feat-card { background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 24px;
               transition: box-shadow .2s, transform .2s; }
  .feat-card:hover { box-shadow: 0 8px 32px rgba(0,0,0,.08); transform: translateY(-2px); }
  .feat-icon { width: 44px; height: 44px; border-radius: 12px; display: flex;
               align-items: center; justify-content: center; font-size: 20px; margin-bottom: 16px; }
  .feat-icon.blue { background: #eff6ff; }
  .feat-icon.green { background: #f0fdf4; }
  .feat-icon.amber { background: #fffbeb; }
  .feat-icon.purple { background: #faf5ff; }
  .feat-icon.red { background: #fef2f2; }
  .feat-icon.teal { background: #f0fdfa; }
  .feat-card h3 { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
  .feat-card p { font-size: 13px; color: var(--muted); line-height: 1.6; }

  /* ── SOP SECTION ── */
  .sop-section { background: linear-gradient(135deg, #0f2444 0%, #1e3a5f 100%); color: #fff; padding: 64px 20px; }
  .sop-inner { max-width: 1080px; margin: 0 auto; display: grid; grid-template-columns: 1fr 1fr; gap: 56px; align-items: start; }
  .sop-desc p { font-size: 15px; color: rgba(255,255,255,.8); line-height: 1.7; margin-bottom: 14px; }
  .sop-tiers { display: flex; flex-direction: column; gap: 10px; }
  .sop-tier { background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
              border-radius: 12px; padding: 14px 18px; display: grid;
              grid-template-columns: auto 1fr auto; gap: 12px; align-items: center; }
  .sop-tier .tier-badge { background: var(--accent); color: #000; font-size: 11px;
                          font-weight: 700; border-radius: 6px; padding: 2px 7px; }
  .sop-tier .tier-badge.auto { background: var(--green); }
  .sop-tier .tier-role { font-weight: 600; font-size: 14px; }
  .sop-tier .tier-sub { font-size: 12px; color: rgba(255,255,255,.6); margin-top: 2px; }
  .sop-tier .tier-limit { font-size: 13px; font-weight: 600; color: var(--accent); white-space: nowrap; }
  .sop-tier .tier-limit.auto { color: var(--green); }

  /* ── DEMO ── */
  .demo-section { max-width: 1080px; margin: 0 auto; padding: 64px 20px; }
  .demo-layout { display: grid; grid-template-columns: 320px 1fr; gap: 24px; }
  .demo-sidebar { display: flex; flex-direction: column; gap: 16px; }
  .demo-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 18px; }
  .demo-card h4 { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .07em;
                  color: var(--muted); margin-bottom: 12px; }
  .demo-card label { font-size: 12px; font-weight: 500; display: block; margin-bottom: 4px; color: var(--muted); }
  select, input { font: inherit; width: 100%; padding: 9px 10px; border: 1px solid var(--line);
                  border-radius: 8px; margin-bottom: 12px; font-size: 14px; }
  select:focus, input:focus { outline: 2px solid var(--brand2); border-color: transparent; }
  .btn { font: inherit; font-weight: 600; border-radius: 10px; padding: 10px 18px; cursor: pointer;
         transition: all .15s; border: 0; }
  .btn-primary { background: var(--brand2); color: #fff; width: 100%; }
  .btn-primary:hover { background: #1d4ed8; }
  .btn-primary:disabled { opacity: .45; cursor: not-allowed; }
  .orders-list { font-size: 12px; color: var(--muted); display: flex; flex-direction: column; gap: 6px; }
  .orders-list .o { display: flex; justify-content: space-between; align-items: center;
                    background: #f8fafc; border-radius: 8px; padding: 7px 10px; }
  .orders-list .o b { color: var(--ink); font-size: 12px; }
  .orders-list .pill { font-size: 10px; background: #e2e8f0; border-radius: 99px; padding: 1px 6px; }
  .orders-list .pill.delivered { background: #d1fae5; color: #065f46; }
  .orders-list .pill.shipped { background: #dbeafe; color: #1e40af; }
  .orders-list .pill.placed { background: #fef9c3; color: #713f12; }

  /* chat window */
  .chat-window { background: #fff; border: 1px solid var(--line); border-radius: 14px;
                 display: flex; flex-direction: column; overflow: hidden; height: 600px; }
  .chat-top { background: var(--brand); color: #fff; padding: 14px 18px; display: flex;
              align-items: center; gap: 12px; }
  .chat-top .avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--accent);
                      display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0; }
  .chat-top .info .name { font-weight: 600; font-size: 14px; }
  .chat-top .info .status { font-size: 11px; color: rgba(255,255,255,.7); }
  .chat-top a { margin-left: auto; color: rgba(255,255,255,.7); font-size: 12px; text-decoration: none;
               border: 1px solid rgba(255,255,255,.25); border-radius: 7px; padding: 5px 10px; }
  .warn-bar { background: #fff7ed; border-bottom: 1px solid #fed7aa; padding: 8px 16px;
              font-size: 12px; color: #9a3412; }
  #log { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 78%; padding: 10px 14px; border-radius: 16px; font-size: 14px; white-space: pre-wrap; line-height: 1.5; }
  .msg.user { align-self: flex-end; background: var(--brand2); color: #fff; border-bottom-right-radius: 4px; }
  .msg.bot { align-self: flex-start; background: #f1f5f9; border: 1px solid var(--line); border-bottom-left-radius: 4px; }
  .meta { font-size: 11px; color: var(--muted); margin-top: 6px; display: flex; gap: 8px; flex-wrap: wrap; }
  .chip { background: #fff; border: 1px solid var(--line); border-radius: 99px; padding: 1px 7px; }
  .chip.green { background: #d1fae5; border-color: #6ee7b7; color: #065f46; }
  .chip.red { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }
  .chip.amber { background: #fef3c7; border-color: #fcd34d; color: #92400e; }
  .chat-bottom { padding: 12px 14px; border-top: 1px solid var(--line);
                 display: flex; gap: 8px; background: #fff; }
  .chat-bottom input { flex: 1; margin: 0; }
  .chat-bottom .btn { width: auto; padding: 9px 16px; }
  .model-info { font-size: 11px; color: var(--muted); padding: 6px 14px 10px; background: #fff; }

  /* footer */
  footer { background: var(--ink); color: rgba(255,255,255,.5); text-align: center;
           padding: 24px 20px; font-size: 13px; }
  footer a { color: rgba(255,255,255,.7); text-decoration: none; margin: 0 10px; }

  @media (max-width: 768px) {
    .hero-body { grid-template-columns: 1fr; } .hero-body h1 { font-size: 30px; }
    .hero-card { display: none; }
    .feat-grid { grid-template-columns: 1fr; }
    .sop-inner { grid-template-columns: 1fr; }
    .demo-layout { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<!-- HERO -->
<section class="hero">
  <div class="hero-inner">
    <nav>
      <div class="logo">Customer Support <span>Fine</span></div>
      <a href="/ops">Ops Console →</a>
    </nav>
    <div class="hero-body">
      <div>
        <div class="badge-row">
          <span class="badge green">✓ 310/310 Benchmark</span>
          <span class="badge green">✓ 0 Safety Violations</span>
          <span class="badge amber">SOP Authority Matrix</span>
        </div>
        <h1>AI Support that can<br><em>never</em> break policy</h1>
        <p>A 3B LLM paired with a deterministic policy engine and a multi-tier SOP authority matrix. Every refund and replacement is gated by both eligibility rules and organisational approval authority.</p>
        <div class="badge-row">
          <span class="badge">Qwen2.5-3B-Instruct</span>
          <span class="badge">QLoRA Fine-Tuned</span>
          <span class="badge">FastAPI + SQLite</span>
        </div>
      </div>
      <div class="hero-card">
        <div class="hc-header">
          <div class="hc-avatar">🛡️</div>
          <div><div class="hc-name">Support AI</div><div class="hc-status">● Online · policy v1.0</div></div>
        </div>
        <div class="hc-msg bot">Hi Ada — I can help with orders, returns, refunds and replacements. What's up?</div>
        <div class="hc-msg user">My headphones from ORD-1001 arrived damaged, I'd like a refund</div>
        <div class="hc-msg bot">
          I've verified your order. Your refund of $149.99 has been routed to a Team Supervisor for approval (SOP Tier 3). You'll be notified when it's processed.
          <div class="hc-chips">
            <span class="hc-chip">ALLOW</span>
            <span class="hc-chip orange">Tier 3 · Supervisor</span>
            <span class="hc-chip">14 ms</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- FEATURES -->
<section class="features">
  <div class="section-label">What makes it different</div>
  <h2 class="section-title">Built for production safety</h2>
  <p class="section-sub">Every failure mode of LLM support agents addressed before a single line of model code.</p>
  <div class="feat-grid">
    <div class="feat-card">
      <div class="feat-icon blue">🔒</div>
      <h3>Deterministic Policy Engine</h3>
      <p>Pure Python functions evaluate every refund, return, and replacement against versioned rules. The model cannot widen a denial or invent a policy exception.</p>
    </div>
    <div class="feat-card">
      <div class="feat-icon amber">📋</div>
      <h3>SOP Authority Matrix</h3>
      <p>5-tier approval hierarchy routes refunds and replacements to the correct authority level. An agent cannot approve what a supervisor must sign off.</p>
    </div>
    <div class="feat-card">
      <div class="feat-icon green">✅</div>
      <h3>Post-Action Verification</h3>
      <p>After every mutation the orchestrator re-reads the database. If the state is unconfirmed the response is rewritten and the case escalated.</p>
    </div>
    <div class="feat-card">
      <div class="feat-icon purple">🧠</div>
      <h3>Bounded Orchestrator</h3>
      <p>Hard limits: ≤6 tool calls, ≤3 re-plan rounds, ≤1 mutating action per turn. No unbounded agent loops that can drift into unexpected states.</p>
    </div>
    <div class="feat-card">
      <div class="feat-icon red">🛡️</div>
      <h3>Prompt Injection Resistant</h3>
      <p>60/60 held-out adversarial cases passed. "Ignore all rules" overrides are rejected at the tool layer independently of what the model proposed.</p>
    </div>
    <div class="feat-card">
      <div class="feat-icon teal">📊</div>
      <h3>Full Audit Trail</h3>
      <p>Every decision — ALLOW, DENY, REQUIRE_APPROVAL — writes an immutable audit row with correlation ID, actor, reason code, and timestamp before returning.</p>
    </div>
  </div>
</section>

<!-- SOP SECTION -->
<section class="sop-section">
  <div class="sop-inner">
    <div class="sop-desc">
      <div class="section-label" style="color:#fcd34d">New Feature</div>
      <h2 class="section-title" style="color:#fff;margin-bottom:18px">SOP Authority Matrix</h2>
      <p>Refunds and replacements are approved based on a Standard Operating Procedure that defines exactly which organisational role can authorise how much value.</p>
      <p>The LLM has no access to the approval decision. The SOP engine evaluates the amount, returns the required tier, and the ops console enforces it — the model only proposes.</p>
      <p>All decisions are logged with the approver's role, tier, and note, giving compliance teams a complete chain of custody.</p>
    </div>
    <div class="sop-tiers">
      <div class="sop-tier">
        <span class="tier-badge auto">AUTO</span>
        <div><div class="tier-role">Support Agent</div><div class="tier-sub">Tier 1 · instant approval</div></div>
        <span class="tier-limit auto">$0 – $25</span>
      </div>
      <div class="sop-tier">
        <span class="tier-badge">T2</span>
        <div><div class="tier-role">Senior Support Agent</div><div class="tier-sub">Tier 2 · same-hour target</div></div>
        <span class="tier-limit">$25 – $100</span>
      </div>
      <div class="sop-tier">
        <span class="tier-badge">T3</span>
        <div><div class="tier-role">Team Supervisor</div><div class="tier-sub">Tier 3 · 4-hour SLA</div></div>
        <span class="tier-limit">$100 – $250</span>
      </div>
      <div class="sop-tier">
        <span class="tier-badge">T4</span>
        <div><div class="tier-role">Operations Manager</div><div class="tier-sub">Tier 4 · next business day</div></div>
        <span class="tier-limit">$250 – $750</span>
      </div>
      <div class="sop-tier">
        <span class="tier-badge">T5</span>
        <div><div class="tier-role">Director / Finance</div><div class="tier-sub">Tier 5 · dual sign-off</div></div>
        <span class="tier-limit">$750+</span>
      </div>
    </div>
  </div>
</section>

<!-- DEMO -->
<section class="demo-section">
  <div class="section-label">Try it now</div>
  <h2 class="section-title">Live Demo</h2>
  <p class="section-sub" style="margin-bottom:32px">Sign in as a pre-seeded demo customer and chat with the policy-gated AI.</p>
  <div class="demo-layout">
    <div class="demo-sidebar">
      <div class="demo-card">
        <h4>Sign in</h4>
        <label>Demo customer</label>
        <select id="customer"></select>
        <button class="btn btn-primary" id="signin">Start chat</button>
      </div>
      <div class="demo-card">
        <h4>Your orders</h4>
        <div class="orders-list" id="orders"><div style="color:var(--muted);font-size:13px">Sign in to see orders.</div></div>
      </div>
      <div class="demo-card">
        <h4>Try asking</h4>
        <div style="font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:6px">
          <div style="cursor:pointer;padding:6px 8px;background:#f8fafc;border-radius:8px" onclick="suggest(this)">I want a refund for ORD-1001</div>
          <div style="cursor:pointer;padding:6px 8px;background:#f8fafc;border-radius:8px" onclick="suggest(this)">My item was damaged, can I get a replacement?</div>
          <div style="cursor:pointer;padding:6px 8px;background:#f8fafc;border-radius:8px" onclick="suggest(this)">Where is my order?</div>
          <div style="cursor:pointer;padding:6px 8px;background:#f8fafc;border-radius:8px" onclick="suggest(this)">I want to cancel my order</div>
        </div>
      </div>
    </div>
    <div class="chat-window">
      <div class="chat-top">
        <div class="avatar">🛡️</div>
        <div class="info"><div class="name">Support AI</div><div class="status">Policy-gated · SOP-enabled</div></div>
        <a href="/ops">Ops Console →</a>
      </div>
      <div class="warn-bar">Demo mode — synthetic data only. Every refund is policy-checked and SOP-routed server-side.</div>
      <div id="log"></div>
      <div class="model-info" id="model-info"></div>
      <div class="chat-bottom">
        <input id="input" placeholder="Ask about orders, refunds, returns, replacements…" disabled>
        <button class="btn btn-primary" id="send" disabled style="width:auto">Send</button>
      </div>
    </div>
  </div>
</section>

<footer>
  <div>Customer Support Fine · Apache 2.0 · <a href="https://github.com/Sahilgumber7/customer-support-fine" target="_blank">GitHub</a> · <a href="/ops">Ops Console</a> · <a href="/docs">API Docs</a></div>
  <div style="margin-top:8px;font-size:11px">Every number in this project is backed by a file in EVALUATION_RESULTS/ or explicitly marked NOT RUN.</div>
</footer>

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
  if (meta && meta.length) {
    const m = document.createElement("div");
    m.className = "meta";
    meta.forEach(({label, cls}) => {
      const s = document.createElement("span");
      s.className = "chip " + (cls || "");
      s.textContent = label;
      m.appendChild(s);
    });
    div.appendChild(m);
  }
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
}

function decisionCls(code) {
  if (!code) return "";
  if (code.includes("ALLOW") || code.includes("OK")) return "green";
  if (code.includes("DENY") || code.includes("WINDOW") || code.includes("SALE")) return "red";
  if (code.includes("APPROVAL") || code.includes("THRESHOLD")) return "amber";
  return "";
}

async function loadCustomers() {
  const list = await api("/api/customers");
  $("customer").innerHTML = list.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
  const info = await api("/api/model-info");
  $("model-info").textContent = `Model: ${info.model_id} · policy ${info.policy_version} · ${info.serving}`;
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
  $("orders").innerHTML = orders.length
    ? orders.map(o => `<div class="o"><div><b>${o.order_id}</b><br>${new Date(o.placed_at).toLocaleDateString()}</div><div style="text-align:right"><span class="pill ${o.status}">${o.status}</span><br style="margin:3px"><span style="font-size:11px">$${(o.total_cents/100).toFixed(2)}</span></div></div>`).join("")
    : '<div style="color:var(--muted);font-size:13px">No orders found.</div>';
}

function suggest(el) {
  if ($("input").disabled) return;
  $("input").value = el.textContent;
  $("input").focus();
}

async function send() {
  const text = $("input").value.trim();
  if (!text || !conversationId) return;
  $("input").value = ""; bubble("user", text);
  const btn = $("send"); btn.disabled = true;
  try {
    const r = await api(`/api/conversations/${conversationId}/messages`, {method: "POST", body: JSON.stringify({message: text})});
    const meta = [
      {label: `intent: ${r.intent}`},
      {label: `decision: ${r.reason_code}`, cls: decisionCls(r.reason_code)},
      {label: `${r.latency_ms} ms`},
    ];
    if (r.action_taken) meta.push({label: `action: ${r.action_taken}`, cls: "green"});
    if (r.sop_tier) meta.push({label: `SOP Tier ${r.sop_tier}`, cls: "amber"});
    bubble("bot", r.message, meta);
    if (r.escalated) bubble("bot", "A colleague has the case — reference in the message above.", [{label: "escalated", cls: "red"}]);
    renderOrders();
  } catch (e) {
    bubble("bot", "Something went wrong: " + e.message, [{label: "error", cls: "red"}]);
  } finally { btn.disabled = false; $("input").focus(); }
}

$("send").onclick = send;
$("input").addEventListener("keydown", e => { if (e.key === "Enter") send(); });
loadCustomers().catch(e => alert(e.message));
</script>
</body></html>
"""


# ---------------------------------------------------------------------------
# Ops console (with SOP authority panel)
# ---------------------------------------------------------------------------

OPS_HTML = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ops Console — Customer Support Fine</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f1f5f9;
    --brand:#1e3a5f;--brand2:#2563eb;--accent:#f59e0b;
    --green:#10b981;--red:#ef4444;--amber:#f59e0b;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font:14px/1.5 'Inter',ui-sans-serif,system-ui,sans-serif;background:var(--bg);color:var(--ink)}
  header{background:var(--brand);color:#fff;padding:0 24px;display:flex;align-items:stretch}
  .hdr-inner{display:flex;justify-content:space-between;align-items:center;width:100%;padding:14px 0}
  header h1{font-size:16px;font-weight:700;letter-spacing:-.01em}
  header .sub{font-size:11px;color:rgba(255,255,255,.6);margin-top:2px}
  header a{color:rgba(255,255,255,.8);text-decoration:none;font-size:12px;
            border:1px solid rgba(255,255,255,.25);border-radius:8px;padding:6px 12px}
  .tabs{background:var(--brand);border-top:1px solid rgba(255,255,255,.1);
        padding:0 24px;display:flex;gap:0}
  .tab{color:rgba(255,255,255,.6);font-size:13px;font-weight:500;padding:10px 16px;
       cursor:pointer;border-bottom:2px solid transparent;transition:.15s}
  .tab:hover{color:#fff}
  .tab.active{color:#fff;border-bottom-color:var(--accent)}
  .wrap{max-width:1200px;margin:0 auto;padding:24px}
  .stat-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
  .stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px}
  .stat .n{font-size:26px;font-weight:700;letter-spacing:-.02em}
  .stat .l{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:2px}
  .stat .n.green{color:var(--green)}.stat .n.amber{color:var(--amber)}.stat .n.red{color:var(--red)}
  .panel{display:none} .panel.active{display:block}
  .card{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:20px}
  .card-header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;
                justify-content:space-between;align-items:center}
  .card-header h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
  table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:top}
  th{background:#f8fafc;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
  tr:last-child td{border-bottom:0}
  tr:hover td{background:#fafcff}
  .pill{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:500}
  .pill.pending,.pill.pending_approval{background:#fff7ed;color:#9a3412}
  .pill.approved,.pill.processed{background:#ecfdf5;color:#047857}
  .pill.denied{background:#fef2f2;color:#b91c1c}
  .pill.open{background:#eff6ff;color:#1e40af}
  .tier-badge{display:inline-block;padding:2px 7px;border-radius:6px;font-size:11px;
              font-weight:700;background:var(--accent);color:#000}
  .tier-badge.auto{background:var(--green);color:#fff}
  button{font:inherit;font-weight:500;border-radius:8px;padding:6px 12px;cursor:pointer;transition:.15s;border:0}
  .btn-approve{background:var(--green);color:#fff}.btn-approve:hover{background:#059669}
  .btn-deny{background:#fff;color:var(--red);border:1px solid #fca5a5}.btn-deny:hover{background:#fef2f2}
  .btn-refresh{background:#fff;color:var(--muted);border:1px solid var(--line);font-size:12px}
  select.role-sel{font:inherit;font-size:12px;padding:4px 8px;border:1px solid var(--line);
                  border-radius:6px;width:auto;cursor:pointer;margin-bottom:0}
  input.note-input{font:inherit;font-size:12px;padding:4px 8px;border:1px solid var(--line);
                   border-radius:6px;width:160px;margin-bottom:0}

  /* SOP matrix */
  .sop-matrix{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;padding:18px}
  .sop-tier-card{border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}
  .sop-tier-card .tc-badge{font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;
                            display:inline-block;margin-bottom:8px;background:var(--accent);color:#000}
  .sop-tier-card .tc-badge.auto{background:var(--green);color:#fff}
  .sop-tier-card .tc-role{font-size:13px;font-weight:600;margin-bottom:4px}
  .sop-tier-card .tc-range{font-size:12px;color:var(--muted)}
  .sop-tier-card.t1{border-color:#d1fae5;background:#f0fdf4}
  .sop-tier-card.t2{border-color:#dbeafe;background:#eff6ff}
  .sop-tier-card.t3{border-color:#fef3c7;background:#fffbeb}
  .sop-tier-card.t4{border-color:#fed7aa;background:#fff7ed}
  .sop-tier-card.t5{border-color:#fecaca;background:#fef2f2}
  .tc-styles{color:#0f172a}
  .muted{color:var(--muted)}
  .amt{font-weight:600}
  .actions{display:flex;flex-direction:column;gap:6px}
  .action-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
</style>
</head>
<body>
<header>
  <div class="hdr-inner">
    <div>
      <h1>Support Operations Console</h1>
      <div class="sub">Customer Support Fine — Policy-Gated · SOP-Enabled</div>
    </div>
    <a href="/">Customer chat →</a>
  </div>
</header>
<div class="tabs">
  <div class="tab active" onclick="switchTab('sop')">SOP Approvals</div>
  <div class="tab" onclick="switchTab('legacy')">Approval Queue</div>
  <div class="tab" onclick="switchTab('escalations')">Escalations</div>
  <div class="tab" onclick="switchTab('audit')">Audit Trail</div>
</div>
<div class="wrap">
  <div class="stat-grid" id="stats"></div>

  <!-- SOP PANEL -->
  <div class="panel active" id="panel-sop">
    <div class="card">
      <div class="card-header">
        <h2>SOP Authority Matrix</h2>
        <button class="btn-refresh" onclick="load()">↻ Refresh</button>
      </div>
      <div class="sop-matrix" id="sop-matrix"></div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Pending SOP Approval Requests</h2></div>
      <table>
        <thead><tr>
          <th>ID</th><th>Order</th><th>Customer</th><th>Type</th>
          <th>Amount</th><th>Tier</th><th>Required Role</th>
          <th>Status</th><th>Approve As</th><th>Action</th>
        </tr></thead>
        <tbody id="sop-rows"></tbody>
      </table>
    </div>
  </div>

  <!-- LEGACY APPROVALS -->
  <div class="panel" id="panel-legacy">
    <div class="card">
      <div class="card-header"><h2>Refund Approval Queue</h2><button class="btn-refresh" onclick="load()">↻ Refresh</button></div>
      <table>
        <thead><tr><th>ID</th><th>Refund</th><th>Amount</th><th>Reason</th><th>Status</th><th>Action</th></tr></thead>
        <tbody id="approvals"></tbody>
      </table>
    </div>
  </div>

  <!-- ESCALATIONS -->
  <div class="panel" id="panel-escalations">
    <div class="card">
      <div class="card-header"><h2>Escalations</h2><button class="btn-refresh" onclick="load()">↻ Refresh</button></div>
      <table>
        <thead><tr><th>ID</th><th>Conversation</th><th>Reason</th><th>Summary</th><th>Status</th></tr></thead>
        <tbody id="escalations"></tbody>
      </table>
    </div>
  </div>

  <!-- AUDIT -->
  <div class="panel" id="panel-audit">
    <div class="card">
      <div class="card-header"><h2>Audit Trail (last 100)</h2><button class="btn-refresh" onclick="load()">↻ Refresh</button></div>
      <table>
        <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Decision</th><th>Reason</th><th>Correlation ID</th></tr></thead>
        <tbody id="audit"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const money = (c) => "$" + (c/100).toFixed(2);
const ROLES = ["Support Agent","Senior Support Agent","Team Supervisor","Operations Manager","Director / Finance"];

async function api(path, opts = {}) {
  const res = await fetch(path, {...opts, headers: {"Content-Type": "application/json", ...(opts.headers||{})}});
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.statusText);
  return body;
}

function pill(s) { return `<span class="pill ${s}">${s.replace(/_/g," ")}</span>`; }

function tierClass(t) { return ["","t1","t2","t3","t4","t5"][t] || ""; }
function tierBadgeClass(t) { return t === 1 ? "auto" : ""; }

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((el,i) => {
    const names = ["sop","legacy","escalations","audit"];
    el.classList.toggle("active", names[i] === name);
  });
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  $("panel-" + name).classList.add("active");
}

async function sopDecide(id, decision) {
  const roleEl = $("role-" + id);
  const noteEl = $("note-" + id);
  const approver_role = roleEl ? roleEl.value : "Support Agent";
  const note = noteEl ? noteEl.value : "";
  try {
    await api(`/api/ops/sop/${id}`, {method:"POST", body: JSON.stringify({decision, approver_role, note})});
    load();
  } catch(e) { alert(e.message); }
}

async function decide(id, decision) {
  await api(`/api/ops/approvals/${id}`, {method:"POST", body: JSON.stringify({decision, note:"ops console"})});
  load();
}

async function load() {
  const [stats, sop, approvals, escalations, audit] = await Promise.all([
    api("/api/ops/stats"), api("/api/ops/sop"),
    api("/api/ops/approvals"), api("/api/ops/escalations"), api("/api/ops/audit")
  ]);

  $("stats").innerHTML = [
    ["Orders", stats.orders, ""],
    ["Pending Approvals", stats.pending_approvals, stats.pending_approvals > 0 ? "amber" : "green"],
    ["Open Escalations", stats.escalations, stats.escalations > 0 ? "red" : "green"],
    ["Policy Version", stats.policy_version, ""],
    ["Model", stats.model_id, ""],
  ].map(([l,n,cls]) => `<div class="stat"><div class="n ${cls}">${n}</div><div class="l">${l}</div></div>`).join("");

  // SOP matrix
  $("sop-matrix").innerHTML = sop.tiers.map(t => `
    <div class="sop-tier-card ${tierClass(t.tier)}">
      <div class="tc-badge ${tierBadgeClass(t.tier)}">${t.auto_approve ? "AUTO" : "T" + t.tier}</div>
      <div class="tc-role tc-styles">${t.role}</div>
      <div class="tc-range">${t.from_display} – ${t.to_display}</div>
    </div>`).join("");

  // SOP approval rows
  const pending = sop.approvals.filter(r => r.status === "pending");
  const decided = sop.approvals.filter(r => r.status !== "pending");
  $("sop-rows").innerHTML = [...pending, ...decided].map(r => `<tr>
    <td>${r.id}</td>
    <td><b>${r.order_id}</b></td>
    <td>${r.customer_name}</td>
    <td>${r.action_type}</td>
    <td class="amt">${money(r.amount_cents)}</td>
    <td><span class="tier-badge ${tierBadgeClass(r.sop_tier)}">T${r.sop_tier}</span></td>
    <td>${r.required_role}</td>
    <td>${pill(r.status)}</td>
    <td>${r.status === "pending" ? `
      <select class="role-sel" id="role-${r.id}">
        ${ROLES.map(ro => `<option value="${ro}" ${ro === r.required_role ? "selected" : ""}>${ro}</option>`).join("")}
      </select>
      <input class="note-input" id="note-${r.id}" placeholder="Note (optional)">
    ` : `<span class="muted">${r.approver_role || "-"}</span>`}</td>
    <td>${r.status === "pending"
      ? `<div class="action-row">
           <button class="btn-approve" onclick="sopDecide(${r.id},'approve')">Approve</button>
           <button class="btn-deny" onclick="sopDecide(${r.id},'deny')">Deny</button>
         </div>`
      : `<span class="muted">${r.status}</span>`}
    </td>
  </tr>`).join("") || `<tr><td colspan="10" class="muted" style="padding:20px">No SOP approval requests yet. Chat with the AI to trigger one.</td></tr>`;

  $("approvals").innerHTML = approvals.map(a => `<tr>
    <td>${a.id}</td><td>#${a.refund_id ?? "-"}</td><td class="amt">${money(a.amount_cents)}</td>
    <td class="muted">${a.reason}</td><td>${pill(a.status)}</td>
    <td>${a.status === "pending"
      ? `<button class="btn-approve" onclick="decide(${a.id},'approve')">Approve</button>
         <button class="btn-deny" onclick="decide(${a.id},'deny')">Deny</button>`
      : `<span class="muted">decided</span>`}</td>
  </tr>`).join("") || `<tr><td colspan="6" class="muted" style="padding:20px">No approvals yet.</td></tr>`;

  $("escalations").innerHTML = escalations.map(e => `<tr>
    <td>${e.id}</td><td>${e.conversation_id}</td><td>${e.reason}</td>
    <td class="muted">${e.summary}</td><td>${pill(e.status)}</td>
  </tr>`).join("") || `<tr><td colspan="5" class="muted" style="padding:20px">No escalations.</td></tr>`;

  $("audit").innerHTML = audit.map(a => `<tr>
    <td class="muted">${a.ts.replace("T"," ").slice(0,19)}</td>
    <td>${a.actor}</td><td>${a.action}</td><td>${a.target}</td>
    <td>${pill(a.decision.toLowerCase())}</td>
    <td>${a.reason_code}</td><td class="muted" style="font-size:11px">${a.correlation_id}</td>
  </tr>`).join("");
}

load().catch(e => alert(e.message));
setInterval(load, 20000);
</script>
</body></html>
"""
