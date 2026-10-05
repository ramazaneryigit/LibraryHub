/* LibraryHub · yayınevi çalışma alanı.
 *
 * Aynı kurallar: çerçevesiz, escapeHtml, hash yönlendirme, ayrı belirteç
 * anahtarı. Ekranın tek amacı bir soruyu cevaplamak: "kitaplarım kimde".
 */

const API = "/api/v1";
const TOKEN_KEY = "libraryhub.publisher.token";

let session = null;
let titles = [];


function token() { return window.localStorage.getItem(TOKEN_KEY); }
function setToken(v) { v ? window.localStorage.setItem(TOKEN_KEY, v) : window.localStorage.removeItem(TOKEN_KEY); }

function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    const current = token();
    if (current) headers.Authorization = `Bearer ${current}`;

    const response = await fetch(`${API}${path}`, {
        method: options.method || "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
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
            body: {
                email: document.getElementById("login-email").value.trim(),
                password: document.getElementById("login-password").value,
            },
        });
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

const VIEWS = ["panel", "titles", "declare"];

function activeView() {
    const name = (window.location.hash || "").replace("#/", "");
    return VIEWS.includes(name) ? name : "panel";
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

    if (view === "panel") await loadSummary();
    else if (view === "titles") await loadTitles();
}

const CARDS = [
    ["titles", "Başlık"],
    ["manifestations", "Baskı"],
    ["holdings", "Koleksiyon kaydı"],
    ["libraries", "Kütüphane"],
    ["upcoming", "Yakında"],
];

async function loadSummary() {
    const summary = await api("/publisher/summary");

    document.getElementById("summary-grid").innerHTML = CARDS.map(([key, label]) => `
        <div class="summary-card">
            <div class="summary-value">${escapeHtml(summary[key])}</div>
            <div class="summary-label">${escapeHtml(label)}</div>
        </div>
    `).join("");
}

async function loadTitles() {
    const result = await api("/publisher/titles?limit=500");
    titles = result.titles;

    document.getElementById("holders").hidden = true;
    document.getElementById("titles-summary").textContent = `${result.count} başlık`;

    document.getElementById("titles-list").innerHTML = titles.length
        ? titles.map(title => `
            <div class="item" data-id="${escapeHtml(title.work_entity_id)}">
                <div class="grow">
                    <div class="title">${escapeHtml(title.title)}</div>
                    <div class="sub">
                        ${title.manifestations} baskı · ${title.holdings} koleksiyon kaydı
                    </div>
                </div>
                <span class="badge ${title.libraries ? "applied" : ""}">
                    ${title.libraries} kütüphane
                </span>
            </div>
        `).join("")
        : '<div class="item"><div class="grow"><div class="sub">Kayıtlı kitap yok.</div></div></div>';
}

document.getElementById("titles-list").addEventListener("click", async event => {
    const item = event.target.closest(".item");
    if (!item || !item.dataset.id) return;

    const box = document.getElementById("holders");
    box.hidden = false;
    box.innerHTML = "<p class='muted'>Yükleniyor…</p>";

    try {
        const result = await api(`/publisher/titles/${item.dataset.id}/libraries`);
        const title = titles.find(t => t.work_entity_id === item.dataset.id);

        box.innerHTML = `
            <h3>${escapeHtml(title ? title.title : "")}</h3>
            <p class="muted">${result.count} kütüphane</p>
            ${result.libraries.length ? `
                <div class="list">
                    ${result.libraries.map(row => `
                        <div class="item">
                            <div class="grow">
                                <div class="title">${escapeHtml(row.library)}</div>
                                <div class="sub">${escapeHtml(row.institution)} · ${escapeHtml(row.branch)} · ${escapeHtml(row.edition) || "tarih yok"}</div>
                            </div>
                            <span class="badge">${row.holdings} koleksiyon kaydı</span>
                        </div>
                    `).join("")}
                </div>
            ` : '<p class="muted">Bu kitabı henüz hiçbir kütüphane edinmemiş.</p>'}
        `;
    } catch (error) {
        box.innerHTML = `<p class="bad">${escapeHtml(error.message)}</p>`;
    }
});

document.getElementById("titles-refresh").addEventListener("click", loadTitles);

document.getElementById("declare-form").addEventListener("submit", async event => {
    event.preventDefault();

    const value = id => document.getElementById(id).value.trim() || null;

    try {
        const result = await api("/publisher/titles", {
            method: "POST",
            body: {
                title: document.getElementById("d-title").value.trim(),
                isbn: value("d-isbn"),
                author: value("d-author"),
                publication_date: value("d-date"),
                language: value("d-language"),
                carrier_type: value("d-carrier"),
            },
        });

        say(`Bildirildi: ${result.title}`, "ok");
        document.getElementById("declare-form").reset();
        window.location.hash = "#/titles";
    } catch (error) {
        say(error.message, "bad");
    }
});

async function enter() {
    // There is no publisher-scoped "who am I" endpoint yet, and `/tenant/me`
    // refuses an account with no tenant -- which a publisher is. The screen does
    // not depend on the name, so a failure here must not stop it opening; the
    // name is simply omitted and the session badge carries the kind.
    try {
        session = await api("/auth/me");
    } catch (error) {
        session = null;
    }

    loginView.hidden = true;
    workspace.hidden = false;

    const name = (session && (session.display_name || session.email)) || "Yayınevi";

    document.getElementById("publisher-name").textContent = name;

    document.getElementById("session").innerHTML = `
        <strong>${escapeHtml(name)}</strong>
        <span class="badge">yayınevi</span>
        <button type="button" id="logout">Çıkış</button>
    `;
    document.getElementById("logout").addEventListener("click", logout);

    if (!window.location.hash) window.location.hash = "#/panel";

    try { await render(); } catch (error) { say(error.message, "bad"); }
}

async function start() {
    if (!token()) { loginView.hidden = false; return; }
    try { await enter(); } catch (error) { setToken(null); loginView.hidden = false; }
}

start();
