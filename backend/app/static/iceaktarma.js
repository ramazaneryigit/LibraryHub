/* LibraryHub · içe aktarma ekranı.
 *
 * İki iş: dosya yükle, ve geçmiş koşuların raporunu oku. Rapor bir yanıt
 * gövdesinde yaşayıp kaybolmaz -- sunucuda saklanır, çünkü operatör yanıtı bir
 * kez okur ve sekmeyi kapatır.
 */

const API = "/api/v1";
const TOKEN_KEY = "libraryhub.ingest.token";

let batches = [];
let opened = null;


function token() { return window.localStorage.getItem(TOKEN_KEY); }
function setToken(v) { v ? window.localStorage.setItem(TOKEN_KEY, v) : window.localStorage.removeItem(TOKEN_KEY); }

function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    const current = token();
    if (current) headers.Authorization = `Bearer ${current}`;

    const response = await fetch(`${API}${path}`, {
        method: options.method || "GET",
        headers,
        body: options.body,
    });

    let payload = null;
    try { payload = await response.json(); } catch (error) { payload = null; }

    if (!response.ok) {
        let detail = payload && payload.detail;
        if (Array.isArray(detail)) detail = detail.map(e => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
        const failure = new Error(detail || `HTTP ${response.status}`);
        failure.status = response.status;
        throw failure;
    }

    return payload;
}

const statusBox = document.getElementById("view-status");
function say(message, kind = "") {
    statusBox.textContent = message;
    statusBox.className = `status ${kind}`;
    statusBox.hidden = !message;
}

const loginView = document.getElementById("login-view");
const workspace = document.getElementById("workspace");

document.getElementById("login-form").addEventListener("submit", async event => {
    event.preventDefault();
    const box = document.getElementById("login-status");
    box.hidden = false;
    box.className = "status";
    box.textContent = "Giriş yapılıyor…";

    try {
        const result = await api("/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: document.getElementById("login-email").value.trim(),
                password: document.getElementById("login-password").value,
            }),
        });

        if (result.user.principal_kind !== "platform" && result.user.role !== "admin") {
            throw new Error("Bu ekran platform yöneticisi içindir.");
        }

        setToken(result.token);
        box.hidden = true;
        await enter();
    } catch (error) {
        box.className = "status bad";
        box.textContent = error.message;
    }
});

async function logout() {
    try { await api("/auth/logout", { method: "POST" }); } catch (error) { /* belirteç zaten geçersiz olabilir */ }
    setToken(null);
    workspace.hidden = true;
    loginView.hidden = false;
    document.getElementById("session").innerHTML = "";
}

const VIEWS = ["upload", "batches"];
function activeView() {
    const name = (window.location.hash || "").replace("#/", "");
    return VIEWS.includes(name) ? name : "upload";
}

function showView(name) {
    VIEWS.forEach(view => { document.getElementById(`view-${view}`).hidden = view !== name; });
    document.querySelectorAll(".tab").forEach(tab => tab.classList.toggle("active", tab.dataset.view === name));
}

document.getElementById("tabs").addEventListener("click", event => {
    const tab = event.target.closest(".tab");
    if (tab) window.location.hash = `#/${tab.dataset.view}`;
});

window.addEventListener("hashchange", () => { if (!workspace.hidden) render(); });

async function render() {
    const view = activeView();
    showView(view);
    say("");

    if (view === "batches") await loadBatches();
}


/* ------------------------------------------------------------ rapor */

function reportHtml(report) {
    if (!report) {
        return '<p class="muted">Bu koşu için rapor saklanmamış.</p>';
    }

    const problems = Object.entries(report.problems || {});

    return `
        <div class="summary-grid">
            <div class="summary-card"><div class="summary-value">${report.total}</div><div class="summary-label">Alınan</div></div>
            <div class="summary-card"><div class="summary-value">${report.created}</div><div class="summary-label">Yeni</div></div>
            <div class="summary-card"><div class="summary-value">${report.holdings ?? 0}</div><div class="summary-label">Koleksiyon kaydı</div></div>
            <div class="summary-card"><div class="summary-value">${report.unchanged}</div><div class="summary-label">Zaten vardı</div></div>
            <div class="summary-card"><div class="summary-value">${report.failed}</div><div class="summary-label">Eşleşmedi</div></div>
        </div>

        ${problems.length ? `
            <h4>Neden eşleşmedi</h4>
            <div class="list">
                ${problems.map(([reason, count]) => `
                    <div class="item">
                        <div class="grow"><div class="sub">${escapeHtml(reason)}</div></div>
                        <span class="badge">${count}</span>
                    </div>
                `).join("")}
            </div>
        ` : '<p class="muted">Eşleşmeyen kayıt yok.</p>'}

        ${(report.unreadable || []).length ? `
            <h4>Okunamayan</h4>
            <div class="list">
                ${report.unreadable.map(line => `
                    <div class="item"><div class="grow"><div class="sub">${escapeHtml(line)}</div></div></div>
                `).join("")}
            </div>
        ` : ""}
    `;
}


/* ----------------------------------------------------------- yükleme */

document.getElementById("upload-form").addEventListener("submit", async event => {
    event.preventDefault();

    const file = document.getElementById("file").files[0];

    if (!file) {
        say("Bir dosya seçin.", "bad");
        return;
    }

    const source = document.getElementById("source").value.trim();
    const name = document.getElementById("name").value.trim();
    const limit = document.getElementById("limit").value.trim();

    const query = new URLSearchParams({ source, name });
    if (limit) query.set("limit", limit);

    say(`Yükleniyor: ${file.name} (${Math.round(file.size / 1024)} KB)…`);

    try {
        const report = await api(`/ingest/marc?${query}`, {
            method: "POST",
            headers: { "Content-Type": "application/marc" },
            body: await file.arrayBuffer(),
        });

        say(
            `${report.total} kayıt okundu, ${report.created} yeni, ` +
            `${report.failed} eşleşmedi.`,
            report.failed ? "" : "ok",
        );

        const box = document.getElementById("upload-report");
        box.hidden = false;
        box.className = "card";
        box.innerHTML = `<h3>Rapor</h3>${reportHtml(report)}`;

        document.getElementById("upload-form").reset();
    } catch (error) {
        say(error.message, "bad");
    }
});


/* ------------------------------------------------------------ geçmiş */

async function loadBatches() {
    const result = await api("/ingest/batches?limit=100");
    batches = result.batches;

    document.getElementById("batches-summary").textContent = `${result.count} koşu`;
    document.getElementById("batch-detail").hidden = true;

    document.getElementById("batches-list").innerHTML = batches.length
        ? batches.map(entry => `
            <div class="item" data-id="${escapeHtml(entry.id)}">
                <div class="grow">
                    <div class="title">${escapeHtml(entry.source_system)}</div>
                    <div class="sub">
                        ${entry.total} kayıt · ${entry.created} yeni ·
                        ${entry.unchanged} zaten vardı
                    </div>
                </div>
                <span class="badge ${entry.failed ? "" : "applied"}">
                    ${entry.failed} eşleşmedi
                </span>
            </div>
        `).join("")
        : '<div class="item"><div class="grow"><div class="sub">Henüz yükleme yok.</div></div></div>';
}

document.getElementById("batches-list").addEventListener("click", async event => {
    const item = event.target.closest(".item");
    if (!item || !item.dataset.id) return;

    opened = item.dataset.id;

    const box = document.getElementById("batch-detail");
    box.hidden = false;
    box.className = "detail";
    box.innerHTML = "<p class='muted'>Yükleniyor…</p>";

    try {
        const entry = await api(`/ingest/batches/${item.dataset.id}`);
        box.innerHTML = `<h3>${escapeHtml(entry.source_system)}</h3>${reportHtml(entry.report)}`;
    } catch (error) {
        box.innerHTML = `<p class="bad">${escapeHtml(error.message)}</p>`;
    }
});

document.getElementById("batches-refresh").addEventListener("click", loadBatches);


/* ------------------------------------------------------------ açılış */

async function enter() {
    loginView.hidden = true;
    workspace.hidden = false;

    document.getElementById("session").innerHTML = `
        <button type="button" id="logout">Çıkış</button>
    `;
    document.getElementById("logout").addEventListener("click", logout);

    if (!window.location.hash) window.location.hash = "#/upload";

    try { await render(); } catch (error) { say(error.message, "bad"); }
}

async function start() {
    if (!token()) { loginView.hidden = false; return; }
    try { await enter(); } catch (error) { setToken(null); loginView.hidden = false; }
}

start();
