/* LibraryHub · otorite kuyruğu.
 *
 * Kuyruk doluyordu ve okunacak yeri yoktu; bu ekran o boşluğu kapatır. Kararlar
 * birbirinden farklı: birleştirmek eserleri taşır, diğer ikisi yalnızca kararı
 * hatırlar -- ki aynı çift bir daha önerilmesin.
 */

const API = "/api/v1";
const TOKEN_KEY = "libraryhub.authority.token";

let candidates = [];


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
        if (Array.isArray(detail)) detail = detail.map(e => e.msg).join("; ");
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

        if (result.user.role !== "admin") {
            throw new Error("Bu ekran yönetici içindir.");
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

const VIEWS = ["open", "merged", "kept_separate", "dismissed"];
function activeView() {
    const name = (window.location.hash || "").replace("#/", "");
    return VIEWS.includes(name) ? name : "open";
}

function showView(name) {
    document.querySelectorAll(".tab").forEach(tab => tab.classList.toggle("active", tab.dataset.view === name));
}

document.getElementById("tabs").addEventListener("click", event => {
    const tab = event.target.closest(".tab");
    if (tab) window.location.hash = `#/${tab.dataset.view}`;
});

window.addEventListener("hashchange", () => { if (!workspace.hidden) load(); });

const REASON = {
    "ayni ad": "aynı ad",
    "ayni ORCID": "aynı ORCID",
    "ayni tarihler": "aynı tarihler",
    "ayni soyad ve bas harfler": "aynı soyad ve baş harfler",
    "benzer ad": "benzer ad",
};

const DECIDABLE = "open";

async function load() {
    const status = activeView();
    showView(status);
    say("");

    const result = await api(`/admin/authority?status=${status}`);
    candidates = result.candidates;

    document.getElementById("summary").textContent = `${result.count} kayıt`;

    document.getElementById("list").innerHTML = candidates.length
        ? candidates.map(entry => `
            <div class="item" data-id="${escapeHtml(entry.id)}">
                <div class="grow">
                    <div class="title">
                        ${escapeHtml(entry.incoming_name)}
                        <span class="muted">→</span>
                        ${escapeHtml(entry.candidate_name)}
                    </div>
                    <div class="sub">
                        ${escapeHtml(REASON[entry.reason] || entry.reason)}
                        · skor ${entry.score}
                        ${entry.source ? " · " + escapeHtml(entry.source) : ""}
                    </div>
                </div>
                ${status === DECIDABLE ? `
                    <button type="button" class="primary" data-act="merge">Birleştir</button>
                    <button type="button" data-act="separate">Ayrı tut</button>
                    <button type="button" data-act="dismiss">Yoksay</button>
                ` : `<span class="badge applied">${escapeHtml(entry.status)}</span>`}
            </div>
        `).join("")
        : '<div class="item"><div class="grow"><div class="sub">Bu listede kayıt yok.</div></div></div>';
}

document.getElementById("list").addEventListener("click", async event => {
    const button = event.target.closest("button[data-act]");
    if (!button) return;

    const item = button.closest(".item");
    const act = button.dataset.act;

    if (act === "merge") {
        const entry = candidates.find(c => c.id === item.dataset.id);

        if (!window.confirm(
            `"${entry.incoming_name}" kaydının eserleri "${entry.candidate_name}" ` +
            `kaydına taşınacak. Emin misiniz?`
        )) return;
    }

    button.disabled = true;

    try {
        const result = await api(`/admin/authority/${item.dataset.id}/${act}`, {
            method: "POST",
            body: { note: null },
        });

        say(
            act === "merge"
                ? `Birleştirildi; ${result.relations_moved} ilişki taşındı.`
                : "Karar kaydedildi.",
            "ok",
        );

        await load();
    } catch (error) {
        say(error.message, "bad");
        button.disabled = false;
    }
});

document.getElementById("refresh").addEventListener("click", load);

async function enter() {
    loginView.hidden = true;
    workspace.hidden = false;

    document.getElementById("session").innerHTML =
        '<button type="button" id="logout">Çıkış</button>';
    document.getElementById("logout").addEventListener("click", logout);

    if (!window.location.hash) window.location.hash = "#/open";

    try { await load(); } catch (error) { say(error.message, "bad"); }
}

async function start() {
    if (!token()) { loginView.hidden = false; return; }
    try { await enter(); } catch (error) { setToken(null); loginView.hidden = false; }
}

start();
