"use strict";
// Board page: vanilla JS, no build. The person drags cards, ticks the checklist, attaches files and
// leaves messages for the agent; every write is a POST that the server hands to store.py.
// Every visible string comes from i18n/<lang>.json through t(); values passed in are escaped by the caller.

const $ = (s, el = document) => el.querySelector(s);
const enc = encodeURIComponent;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
const S = { boards: [], board: null, data: null, rev: null, card: null, inbox: 0, showArchived: false, cfg: { lang: "en", home: "~/.devboard" } };
const T = {};
const t = (key, vars = {}) => String(T[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : ""));

const SVG = (d) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const I = {
  cols: SVG('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>'),
  hist: SVG('<path d="M12 8v4l2 2"/><path d="M3.05 11a9 9 0 1 1 .5 4M3 4v5h5"/>'),
  warn: SVG('<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'),
  msg: SVG('<path d="M8 9h8M8 13h6"/><path d="M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-5l-5 3v-3H6a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z"/>'),
  search: SVG('<circle cx="10" cy="10" r="7"/><path d="m21 21-6-6"/>'),
  target: SVG('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>'),
  clock: SVG('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>'),
  minus: SVG('<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>'),
  wait: SVG('<path d="M6 3h12M6 21h12M7 3c0 5 10 5 10 9s-10 4-10 9M17 3c0 5-10 5-10 9"/>'),
  left: SVG('<path d="M19 12H5M11 18l-6-6 6-6"/>'),
  folder: SVG('<path d="M4 6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>'),
  repeat: SVG('<path d="M4 12V9a3 3 0 0 1 3-3h13l-3-3M20 12v3a3 3 0 0 1-3 3H4l3 3"/>'),
  box: SVG('<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8M10 12h4"/>'),
  clip: SVG('<path d="m15 7-6.5 6.5a1.5 1.5 0 0 0 3 3L18 10a3 3 0 0 0-6-6l-6.5 6.5a4.5 4.5 0 0 0 9 9L21 13"/>'),
};
const DESC = (key) => (T[`desc.${key}`] ? t(`desc.${key}`) : "");

async function api(path, body, raw) {
  const opt = body === undefined ? {} : raw
    ? { method: "POST", headers: { "X-Board": "1", "X-Filename": enc(raw), "Content-Type": "application/octet-stream" }, body }
    : { method: "POST", headers: { "Content-Type": "application/json", "X-Board": "1" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.error || r.statusText), { status: r.status, body: j });
  return j;
}

function route() {
  let parts = [];
  try { parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent); } catch { parts = []; }
  const [board = "", view = "board", id = ""] = parts;
  return { board, view: view || "board", id };
}
const href = (...p) => "#/" + p.map(enc).join("/");
const cardUrl = (id) => `/api/b/${enc(S.board)}/cards/${enc(id)}`;

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("on"), 4500);
}

const fmtDate = (d) => {
  const [y, m, dd] = String(d || "").slice(0, 10).split("-");
  if (!dd) return esc(d);
  return S.cfg.lang === "pt-BR" ? `${esc(dd)}/${esc(m)}/${esc(y)}` : `${esc(y)}-${esc(m)}-${esc(dd)}`;
};
const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${num(n)} B`);
const label = (id) => (/^\d+$/.test(id) ? t("stage", { id: esc(id) }) : esc(id));
const pct = (c) => (c.progress == null ? "—" : `${num(c.progress)}%`);
const colName = (k) => esc((S.data.board.columns || {})[k] || k);

// --- markdown subset. Line rule and checklist numbering MUST match derive.checklist in Python. ---
const CHECK_RE = /^([ \t]*[-*][ \t]+)\[( |x|X)\]([ \t][^\n]*)?$/;
const FENCE_RE = /^[ \t]*```/;
const mdLines = (md) => String(md || "").replace(/^﻿/, "").split("\n").map((l) => l.replace(/\r$/, ""));

function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

function renderMd(md, readonly) {
  const out = [];
  let list = null, fence = null, n = 0;
  const close = () => { if (list) { out.push(`</${list === "check" ? "ul" : list}>`); list = null; } };
  const open = (kind) => {
    if (list === kind) return;
    close();
    out.push(kind === "check" ? '<ul class="check">' : `<${kind}>`);
    list = kind;
  };
  for (const line of mdLines(md)) {
    if (FENCE_RE.test(line)) {
      if (fence === null) { close(); fence = []; } else { out.push(`<pre><code>${esc(fence.join("\n"))}</code></pre>`); fence = null; }
      continue;
    }
    if (fence !== null) { fence.push(line); continue; }
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
      close();
      if (m[1].length > 1) out.push(`<h${m[1].length + 1}>${inline(m[2])}</h${m[1].length + 1}>`);
    } else if ((m = line.match(CHECK_RE))) {
      open("check");
      n += 1;
      out.push(`<li><input type="checkbox" data-check="${n}" ${m[2] !== " " ? "checked" : ""} ${readonly ? "disabled" : ""}><span>${inline((m[3] || "").trim())}</span></li>`);
    } else if ((m = line.match(/^\s*[-*]\s+(.*)$/))) {
      open("ul");
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\s*\d+\.\s+(.*)$/))) {
      open("ol");
      out.push(`<li>${inline(m[1])}</li>`);
    } else {
      close();
      if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    }
  }
  close();
  if (fence !== null) out.push(`<pre><code>${esc(fence.join("\n"))}</code></pre>`);
  return out.join("\n");
}

// --- chrome ---
function renderChrome(r) {
  const { board, kind, cards } = S.data;
  $("#title").textContent = board.title || board.id;
  const where = kind === "rollout"
    ? t("sub.rollout", { src: esc(board.source) })
    : t("sub.board", { path: `${esc(S.cfg.home)}/${esc(board.id)}/` });
  $("#sub").innerHTML = `<a class="crumb" href="#/">${I.left} ${t("crumb")}</a> · ${where}`;
  S.inbox = cards.reduce((s, c) => s + num(c.messages_open), 0);
  const tabs = [["board", I.cols, t("tab.board")], ["history", I.hist, t("tab.history")], ["pending", I.warn, t("tab.pending")], ["messages", I.msg, t("tab.messages")]];
  $("#tabs").innerHTML = tabs.map(([v, icon, name]) =>
    `<a class="tab${v === r.view || (r.view === "card" && v === "board") ? " on" : ""}" href="${href(S.board, v)}">${icon} ${name}${v === "messages" && S.inbox ? ` <span class="n">${S.inbox}</span>` : ""}</a>`).join("");
  const cols = Object.keys(board.columns || {}), last = cols[cols.length - 1];
  const known = cards.filter((c) => c.progress != null);
  const avg = known.length ? Math.round(known.reduce((s, c) => s + num(c.progress), 0) / known.length) + "%" : "—";
  $("#stats").innerHTML = `<span>${t("stats.cards")}: <b>${cards.length}</b></span><span>${t("stats.done")}: <b>${cards.filter((c) => c.column === last).length}</b></span><span>${t("stats.avg")}: <b>${avg}</b></span>`;
  $("#toolbar").hidden = r.view !== "board";
  $("#prio-label").style.color = $("#prio").checked ? "var(--teal)" : "";
}

// --- board ---
function cardHtml(c, ro) {
  let chips = `<span class="eid">${label(c.id)}</span>`;
  if (c.priority) chips += `<span class="pp">${I.target} ${t("chip.priority", { n: num(c.priority) })}</span>`;
  for (const tag of c.tags || []) chips += `<span class="crit">${esc(tag)}</span>`;
  if (c.messages_open) chips += `<span class="msg" title="${t("chip.messages")}">${I.msg} ${num(c.messages_open)}</span>`;
  if (c.files_count) chips += `<span class="clip" title="${t("chip.files")}">${I.clip} ${num(c.files_count)}</span>`;
  return `<a class="card${ro ? " ro" : ""}" href="${href(S.board, "card", c.id)}" data-id="${esc(c.id)}" draggable="${ro ? "false" : "true"}">
    <div class="chips">${chips}</div>
    <div class="ctitle">${esc(c.title)}</div>
    <div class="prog"><div class="track"><span style="width:${num(c.progress)}%"></span></div><span class="pct">${pct(c)}</span></div>
    ${c.blocked ? `<div class="line bad">${I.minus} ${esc(c.blocked)}</div>` : ""}
    ${c.waiting ? `<div class="line">${I.wait} ${esc(c.waiting)}</div>` : ""}
    ${c.situation ? `<div class="line sit">${esc(c.situation)}</div>` : ""}
    <div class="foot"><span>${esc(c.estimate || "")}</span><span>${c.due ? I.clock + " " + fmtDate(c.due) : ""}</span></div>
  </a>`;
}

function renderBoard() {
  const ro = S.data.readonly;
  const q = $("#search").value.trim().toLowerCase();
  let list = S.data.cards.filter((c) => !q ||
    [c.id, c.title, c.situation, c.next, c.blocked, c.waiting, ...(c.tags || [])].join(" ").toLowerCase().includes(q));
  if ($("#prio").checked) list = list.filter((c) => c.priority).sort((a, b) => a.priority - b.priority);
  $("#main").innerHTML = `<div class="columns">${Object.entries(S.data.board.columns || {}).map(([key, name]) => {
    const cs = list.filter((c) => c.column === key);
    return `<section class="col k-${esc(key)}" data-col="${esc(key)}"><h2><i class="dot"></i>${esc(name)} <small>${cs.length}</small></h2>
      <p class="desc">${ro ? "" : DESC(key)}</p>${cs.map((c) => cardHtml(c, ro)).join("")}</section>`;
  }).join("")}</div>`;
  if (!ro) wireDrag();
}

function wireDrag() {
  let dragId = null;
  for (const el of document.querySelectorAll(".card[draggable=true]")) {
    el.addEventListener("dragstart", (e) => { dragId = el.dataset.id; el.classList.add("dragging"); e.dataTransfer.setData("text/plain", dragId); });
    el.addEventListener("dragend", () => { el.classList.remove("dragging"); dragId = null; });
  }
  for (const col of document.querySelectorAll(".col")) {
    col.addEventListener("dragover", (e) => { e.preventDefault(); col.classList.add("over"); });
    col.addEventListener("dragleave", () => col.classList.remove("over"));
    col.addEventListener("drop", async (e) => {
      e.preventDefault();
      col.classList.remove("over");
      const id = dragId; // only a card dragged on this page moves; files and text dropped here do not
      dragId = null;
      const c = id && S.data.cards.find((x) => x.id === id);
      if (!c || c.column === col.dataset.col) return;
      const from = c.column;
      c.column = col.dataset.col; // optimistic (Doherty): move now, confirm with the server
      renderBoard();
      try {
        await api(`${cardUrl(id)}/move`, { etag: c.etag, status: col.dataset.col });
      } catch (err) {
        c.column = from;
        renderBoard();
        toast(err.status === 409 ? t("toast.move_conflict") : t("toast.move_fail", { err: err.message }));
        refresh().catch(() => {});
        return;
      }
      toast(t("toast.moved", { col: (S.data.board.columns || {})[col.dataset.col] || col.dataset.col }));
      refresh().catch(() => {});
    });
  }
}

// --- history wording ---
function describe(ev) {
  const ch = ev.changes || {};
  if (ev.kind === "create") return t("ev.create");
  if (ev.kind === "message") return t("ev.message", { text: esc(ev.note) });
  if (ev.kind === "reply") return t("ev.reply", { text: esc(ev.note) });
  if (ev.kind === "attach") return t("ev.attach", { name: esc(ev.name) });
  if (ev.kind === "detach") return t("ev.detach", { name: esc(ev.name) });
  if (ev.kind === "check") {
    const item = String(ev.note || "").replace(/^\[[ x]\]\s*/, "");
    return t(ev.done ? "ev.check" : "ev.uncheck", { text: esc(item) });
  }
  const parts = [];
  if (ch.status) parts.push(ch.status[1] ? t("ev.moved", { col: colName(ch.status[1]) }) : t("ev.auto"));
  if (ch.progress) parts.push(ch.progress[1] == null ? t("ev.progress_none") : t("ev.progress", { n: num(ch.progress[1]) }));
  if (ch.blocked) parts.push(ch.blocked[1] ? t("ev.blocked", { text: esc(ch.blocked[1]) }) : t("ev.unblocked"));
  if (ch.waiting) parts.push(ch.waiting[1] ? t("ev.waiting", { text: esc(ch.waiting[1]) }) : t("ev.unwaiting"));
  if (ch.next && ch.next[1]) parts.push(t("ev.next", { text: esc(ch.next[1]) }));
  const other = Object.keys(ch).filter((k) => !["status", "progress", "blocked", "waiting", "next"].includes(k));
  if (other.length) parts.push(t("ev.updated", { fields: other.map(esc).join(", ") }));
  if (ev.note) parts.unshift(esc(ev.note));
  return parts.join(" · ") || esc(ev.kind);
}
const who = (by) => (by === "human" ? t("who.human") : by === "agent" ? t("who.agent") : esc(by));

function timeline(evs, withCard) {
  if (!evs.length) return `<p class="empty">${t("tl.empty")}</p>`;
  return `<ol class="tl">${evs.map((ev) => `<li class="${ev.by === "human" ? "you" : ""}">
    <time>${fmtDate(ev.ts)} ${esc(String(ev.ts || "").slice(11, 16))} · ${who(ev.by)}${withCard ? ` · <a href="${href(S.board, "card", ev.card)}">${label(ev.card)}</a>` : ""}</time>
    <strong>${describe(ev)}</strong></li>`).join("")}</ol>`;
}

// --- card detail ---
function fileTile(c, f, ro) {
  const url = `${cardUrl(c.id)}/files/${enc(f.name)}`;
  const ext = (f.name.split(".").pop() || "").toLowerCase();
  const open = (inner) => `<a class="open-file" href="${url}" target="_blank" rel="noopener" title="${t("file.open", { name: esc(f.name) })}">${inner}</a>`;
  let preview; // the whole preview opens the file (Fitts): only a video keeps its own controls
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"].includes(ext)) preview = open(`<img src="${url}" alt="${esc(f.name)}" loading="lazy">`);
  else if (["mp4", "webm", "mov", "m4v", "ogv"].includes(ext)) preview = `<video src="${url}" controls preload="metadata"></video>`;
  else preview = open(`<div class="doc">${esc(ext.toUpperCase() || t("file.noext"))}</div>`);
  return `<div class="file">${preview}<a href="${url}" target="_blank" rel="noopener">${esc(f.name)}</a>
    <div class="meta">${fmtSize(num(f.size))} · ${t(f.mode === "link" ? "file.link" : "file.copy")} · ${who(f.by)}</div>
    ${ro ? "" : `<button class="rm" data-rm="${esc(f.name)}" title="${t("file.remove")}" aria-label="${t("file.remove_aria", { name: esc(f.name) })}">×</button>`}</div>`;
}

async function renderCard(id) {
  const c = await api(`${cardUrl(id)}?events=0`);
  S.card = c;
  const ro = S.data.readonly;
  let chips = `<span class="eid">${label(c.id)}</span><span class="status"><i class="dot ${esc(c.column)}"></i> ${colName(c.column)}</span>`;
  if (c.priority) chips += `<span class="pp">${I.target} ${t("chip.priority", { n: num(c.priority) })}</span>`;
  for (const tag of c.tags || []) chips += `<span class="crit">${esc(tag)}</span>`;
  const progress = c.checklist ? t("card.items", { pct: pct(c), done: num(c.checklist[1]), total: num(c.checklist[0]) }) : pct(c);
  const open = c.messages.filter((m) => m.open), done = c.messages.filter((m) => !m.open).slice(-3).reverse();
  $("#main").innerHTML = `<a class="back" href="${href(S.board)}">${I.left} ${t("card.back")}</a>
  <div class="detail"><article class="panel" id="cardpanel">
    <div class="chips">${chips}</div>
    <h1>${esc(c.title)}</h1>
    <div class="kpis"><div class="kpi"><b>${t("kpi.progress")}</b><div>${progress}</div></div>
      <div class="kpi"><b>${t("kpi.estimate")}</b><div>${esc(c.estimate || "—")}${c.due ? ` · ${I.clock} ${fmtDate(c.due)}` : ""}</div></div>
      <div class="kpi"><b>${t("kpi.situation")}</b><div>${esc(c.situation || "—")}</div></div></div>
    ${c.next ? `<div class="hl">${t("card.next", { text: esc(c.next) })}</div>` : ""}
    ${c.blocked ? `<div class="line bad">${I.minus} ${esc(c.blocked)}</div>` : ""}
    ${c.waiting ? `<div class="line">${I.wait} ${esc(c.waiting)}</div>` : ""}
    <div class="md">${renderMd(c.md, ro)}</div>
    <section class="files"><h3>${I.clip} ${t("files.title")} <small>${c.files.length}</small></h3>
      <div class="grid">${c.files.map((f) => fileTile(c, f, ro)).join("")}</div>
      ${ro ? "" : `<div class="drop" id="drop">${t("files.drop")} <label>${t("files.pick")}<input id="file" type="file" multiple hidden></label>. ${t("files.kinds")}</div>`}
    </section>
  </article>
  <aside class="panel side">
    ${ro ? "" : `<h3>${t("ask.title")}</h3><div class="ask">
      <textarea id="ask" placeholder="${t("ask.placeholder")}"></textarea>
      <div class="err" id="err"></div>
      <div class="row"><span class="hint">${t("ask.hint")}</span><button class="btn" id="send">${t("ask.send")}</button></div>
      ${open.map((m) => `<div class="open">${I.msg} <b>${t("ask.waiting")}</b> · “${esc(m.text)}”</div>`).join("")}
      ${done.map((m) => `<div class="answered"><b>${t("ask.agent")}</b> ${esc(m.reply.text)}<br><span>${t("ask.about", { text: esc(m.text) })}</span></div>`).join("")}
    </div>`}
    <h3>${t("card.history")} <small>${c.events.length}</small></h3>${timeline([...c.events].reverse(), false)}
  </aside></div>`;
  if (!ro) wireCard(c);
}

function wireCard(c) {
  const ask = $("#ask"), err = $("#err");
  ask.oninput = () => { err.textContent = ""; };
  $("#send").onclick = async () => {
    const text = ask.value.trim();
    if (!text) { err.textContent = t("ask.empty"); ask.focus(); return; }
    try {
      await api(`${cardUrl(c.id)}/message`, { text });
      ask.value = "";
      await refresh();
      toast(t("toast.sent"));
    } catch (e) { err.textContent = t("ask.fail", { err: e.message }); }
  };
  for (const box of document.querySelectorAll("[data-check]")) {
    box.onchange = async () => {
      try { await api(`${cardUrl(c.id)}/check`, { etag: c.etag, index: Number(box.dataset.check), done: box.checked }); }
      catch (e) { toast(e.status === 409 ? t("toast.check_conflict") : t("toast.error", { err: e.message })); }
      await refresh();
    };
  }
  for (const b of document.querySelectorAll("[data-rm]")) {
    b.onclick = async () => {
      if (!confirm(t("confirm.remove", { name: b.dataset.rm }))) return;
      try { await api(`${cardUrl(c.id)}/detach`, { name: b.dataset.rm }); toast(t("toast.removed")); } catch (e) { toast(t("toast.error", { err: e.message })); }
      await refresh();
    };
  }
  const upload = async (files) => {
    for (const f of files) {
      toast(t("toast.uploading", { name: f.name }));
      try { await api(`${cardUrl(c.id)}/files`, f, f.name); } catch (e) { toast(t("toast.upload_fail", { name: f.name, err: e.message })); return; }
    }
    await refresh();
    toast(files.length > 1 ? t("toast.uploaded_many", { n: files.length }) : t("toast.uploaded_one"));
  };
  $("#file").onchange = (e) => upload([...e.target.files]);
  const panel = $("#cardpanel"), drop = $("#drop");
  panel.addEventListener("dragover", (e) => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); drop.classList.add("over"); } });
  panel.addEventListener("dragleave", (e) => { if (!panel.contains(e.relatedTarget)) drop.classList.remove("over"); });
  panel.addEventListener("drop", (e) => {
    if (!e.dataTransfer.files.length) return;
    e.preventDefault();
    drop.classList.remove("over");
    upload([...e.dataTransfer.files]);
  });
}

// --- other tabs ---
async function renderHistory() {
  const evs = await api(`/api/b/${enc(S.board)}/history?limit=200`);
  $("#main").innerHTML = `<section class="panel side"><h3>${t("history.title")} <small>${evs.length}</small></h3>${timeline(evs, true)}</section>`;
}

async function renderPending() {
  const ps = await api(`/api/b/${enc(S.board)}/pending`);
  $("#main").innerHTML = `<section class="panel side"><h3>${t("pending.title")} <small>${ps.length}</small></h3>${ps.length
    ? `<ul class="list">${ps.map((c) => `<li><a href="${href(S.board, "card", c.id)}">${label(c.id)} · ${esc(c.title)}</a>
        ${c.blocked ? `<span class="line bad">${I.minus} ${esc(c.blocked)}</span>` : ""}${c.waiting ? `<span class="line">${I.wait} ${esc(c.waiting)}</span>` : ""}</li>`).join("")}</ul>`
    : `<p class="empty">${t("pending.empty")}</p>`}</section>`;
}

async function renderInbox() {
  const ms = await api(`/api/b/${enc(S.board)}/inbox`);
  $("#main").innerHTML = `<section class="panel side"><h3>${t("inbox.title")} <small>${ms.length}</small></h3>${ms.length
    ? `<ul class="list">${ms.map((m) => `<li><time>${fmtDate(m.ts)} ${esc(String(m.ts || "").slice(11, 16))}</time>
        <a href="${href(S.board, "card", m.card)}">${label(m.card)} · ${esc(m.title)}</a><span>“${esc(m.text)}”</span></li>`).join("")}</ul>
       <p class="empty">${t("inbox.how")}</p>`
    : `<p class="empty">${t("inbox.empty")}</p>`}</section>`;
}

// --- home: every board, grouped by origin repo ---
const fmtWhen = (ts) => {
  if (!ts) return "—";
  const d = new Date(ts), today = new Date();
  if (Number.isNaN(d.getTime())) return esc(ts);
  const hm = d.toTimeString().slice(0, 5);
  return d.toDateString() === today.toDateString() ? t("when.today", { hm }) : `${fmtDate(ts)} ${hm}`;
};

function mini(b) {
  const c = b.counts || {}, keys = Object.keys(c), total = keys.reduce((s, k) => s + num(c[k]), 0);
  if (!total) return '<div class="mini"></div>';
  const color = (k, i) => (b.kind === "rollout" ? (i === keys.length - 1 ? "done" : "doing") : k);
  const order = b.kind === "rollout" ? [...keys].reverse() : ["done", "final", "doing", "blocked", "todo"].filter((k) => k in c);
  return `<div class="mini">${order.map((k) => num(c[k])
    ? `<span style="width:${(num(c[k]) * 100 / total).toFixed(1)}%;background:var(--${color(k, keys.indexOf(k))})"></span>` : "").join("")}</div>`;
}

function boardCard(b) {
  const chips = `<span class="eid">${esc(b.id)}</span>${b.kind === "rollout" ? `<span class="tag-ro">${t("home.readonly")}</span>` : ""}${b.messages_open ? `<span class="msg">${I.msg} ${num(b.messages_open)}</span>` : ""}${b.error ? `<span class="crit">${t("home.error")}</span>` : ""}`;
  return `<div class="bcard${b.archived ? " arch" : ""}" data-board="${esc(b.id)}"><div class="chips">${chips}</div>
    <a class="t" href="${href(b.id)}">${esc(b.title)}</a>${mini(b)}
    <div class="nums"><span>${t("home.cards")} <b>${num(b.cards)}</b></span><span>${t("home.done")} <b>${num(b.done)}</b></span>
      <span>${t("home.blocked")} <b>${num((b.counts || {}).blocked)}</b></span><span>${t("home.avg")} <b>${b.avg == null ? "—" : num(b.avg) + "%"}</b></span></div>
    <div class="acts"><span class="when">${t("home.updated", { when: fmtWhen(b.updated) })}</span>
      <span><button class="ghost" data-archive="${b.archived ? "0" : "1"}">${t(b.archived ? "home.unarchive" : "home.archive")}</button>
      <a class="btn open-board" href="${href(b.id)}">${t("home.open")}</a></span></div></div>`;
}

function renderHome() {
  const active = S.boards.filter((b) => !b.archived), arch = S.boards.filter((b) => b.archived);
  $("#title").textContent = t("home.title");
  $("#sub").innerHTML = t("home.sub", { path: `${esc(S.cfg.home)}/`, active: active.length, archived: arch.length });
  $("#tabs").innerHTML = "";
  $("#toolbar").hidden = true;
  const q = (($("#home-search") || {}).value || "").trim().toLowerCase();
  const hit = (b) => !q || [b.id, b.title, b.group_name, b.group].join(" ").toLowerCase().includes(q);
  const groups = new Map();
  for (const b of active.filter(hit)) {
    const key = b.kind === "rollout" ? "~rollouts" : b.group || "~none";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(b);
  }
  const latest = (bs) => Math.max(...bs.map((b) => Date.parse(b.updated) || 0));
  const head = (key, bs) => key === "~rollouts" ? `${I.repeat} ${t("home.rollouts")}`
    : key === "~none" ? `${I.folder} ${t("home.no_repo")}` : `${I.folder} ${esc(bs[0].group_name)} <code>${esc(bs[0].group_label || key)}</code>`;
  const section = (title, bs) => `<section class="group"><h2>${title}</h2><div class="boards">${bs
    .sort((a, b) => (Date.parse(b.updated) || 0) - (Date.parse(a.updated) || 0)).map(boardCard).join("")}</div></section>`;
  const body = [...groups.entries()].sort((a, b) => latest(b[1]) - latest(a[1])).map(([k, bs]) => section(head(k, bs), bs)).join("")
    + (S.showArchived && arch.filter(hit).length ? section(`${I.box} ${t("home.archived")}`, arch.filter(hit)) : "");
  const typed = $("#home-search") ? $("#home-search").value : "";
  $("#main").innerHTML = `<div class="home-tools"><label class="search">${I.search}<input id="home-search" placeholder="${t("home.search")}"></label>
    <label class="toggle"><input type="checkbox" id="show-archived" ${S.showArchived ? "checked" : ""}> ${t("home.show_archived", { n: arch.length })}</label>
    <div class="stats"><span>${t("home.order")}</span></div></div>
    ${body || `<p class="empty">${t("home.empty")}</p>`}`;
  const input = $("#home-search");
  input.value = typed;
  input.oninput = () => { renderHome(); const i = $("#home-search"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
  $("#show-archived").onchange = (e) => { S.showArchived = e.target.checked; renderHome(); };
  for (const btn of document.querySelectorAll("[data-archive]")) {
    btn.onclick = async () => {
      const id = btn.closest(".bcard").dataset.board, on = btn.dataset.archive === "1";
      try {
        await api(`/api/boards/${enc(id)}/archive`, { archived: on });
        toast(t(on ? "toast.archived" : "toast.unarchived"));
      } catch (e) { toast(t("toast.fail", { err: e.message })); }
      S.boards = await api("/api/boards");
      renderHome();
    };
  }
}

async function refresh() {
  const r = route();
  S.boards = await api("/api/boards");
  if (!r.board) { S.board = null; S.data = null; renderHome(); return; }
  if (!S.boards.some((b) => b.id === r.board)) { location.hash = "#/"; return; }
  S.board = r.board;
  S.data = await api(`/api/b/${enc(S.board)}`);
  S.rev = S.data.rev;
  S.card = null;
  renderChrome(r);
  if (r.view === "card" && r.id) await renderCard(r.id);
  else if (r.view === "history") await renderHistory();
  else if (r.view === "pending") await renderPending();
  else if (r.view === "messages") await renderInbox();
  else renderBoard();
}

function busy() {
  const ask = $("#ask");
  return !!ask && (ask === document.activeElement || ask.value.trim() !== "");
}

async function poll() {
  if (!S.board || document.hidden) return;
  try {
    const { rev } = await api(`/api/rev?board=${enc(S.board)}`);
    if (rev === S.rev) return;
    if (busy()) { if (!poll.warned) toast(t("toast.busy")); poll.warned = true; return; }
    poll.warned = false;
    await refresh();
  } catch { /* server stopped: keep the last view */ }
}

const run = () => refresh().catch((e) => {
  $("#main").innerHTML = `<section class="panel side"><h3>${t("load.fail")}</h3><p>${esc(e.message)}</p></section>`;
});
async function boot() {
  try {
    S.cfg = await api("/api/config");
    Object.assign(T, await (await fetch(`i18n/${enc(S.cfg.lang)}.json`)).json());
  } catch { /* keep the keys as text rather than a blank page */ }
  document.documentElement.lang = S.cfg.lang;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-placeholder]")) el.placeholder = t(el.dataset.i18nPlaceholder);
  $("#i-search").innerHTML = I.search;
  $("#i-target").innerHTML = I.target;
  window.addEventListener("hashchange", run);
  $("#search").addEventListener("input", () => S.data && renderBoard());
  $("#prio").addEventListener("change", () => { if (S.data) { renderChrome(route()); renderBoard(); } });
  setInterval(poll, 3000);
  run();
}
boot();
