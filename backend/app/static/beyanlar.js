const API = "/api/v1";
const TOKEN_KEY = "libraryhub.admin.token";
const loginView = document.getElementById("login-view");
const workspace = document.getElementById("workspace");
const sessionBox = document.getElementById("session");
const loginStatus = document.getElementById("login-status");
const queueStatus = document.getElementById("assertion-status-message");
const queue = document.getElementById("assertion-list");
const count = document.getElementById("assertion-count");
const statusFilter = document.getElementById("assertion-status");

function token() {
    return window.localStorage.getItem(TOKEN_KEY);
}

function escapeHtml(value) {
    if (value === null || value === undefined) {
        return "";
    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json" };

    if (token()) {
        headers.Authorization = `Bearer ${token()}`;
    }

    const response = await fetch(`${API}${path}`, {
        method: options.method || "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });

    const result = await response.json().catch(() => null);

    if (!response.ok) {
        const detail = Array.isArray(result?.detail)
            ? result.detail.map(error => error.msg).join("; ")
            : result?.detail;
        const error = new Error(detail || `HTTP ${response.status}`);
        error.status = response.status;
        throw error;
    }

    return result;
}

function showMessage(element, message, kind = "") {
    element.textContent = message;
    element.className = `status ${kind}`;
    element.hidden = !message;
}

function setSession(user) {
    sessionBox.innerHTML = `
        <strong>${escapeHtml(user.display_name || user.email || "Küratör")}</strong>
        <button type="button" id="logout">Çıkış</button>
    `;
    document.getElementById("logout").addEventListener("click", logout);
}

async function login(event) {
    event.preventDefault();
    showMessage(loginStatus, "Giriş yapılıyor...");

    try {
        const result = await api("/auth/login", {
            method: "POST",
            body: {
                email: document.getElementById("login-email").value.trim(),
                password: document.getElementById("login-password").value,
            },
        });

        if (result.user.role !== "admin") {
            throw new Error("Bu alan yalnızca yönetici hesabına açıktır.");
        }

        window.localStorage.setItem(TOKEN_KEY, result.token);
        enterWorkspace(result.user);
    } catch (error) {
        showMessage(loginStatus, error.message, "bad");
    }
}

async function logout() {
    try {
        await api("/auth/logout", { method: "POST" });
    } catch (error) {
        // The session may already have expired; local sign-out still completes.
    }

    window.localStorage.removeItem(TOKEN_KEY);
    workspace.hidden = true;
    loginView.hidden = false;
    sessionBox.innerHTML = "";
    queue.replaceChildren();
}

function displayValue(value) {
    if (typeof value === "string") {
        return value;
    }

    if (value === null || value === undefined) {
        return "Boş değer";
    }

    return JSON.stringify(value, null, 2);
}

function renderAssertions(assertions) {
    if (!assertions.length) {
        queue.innerHTML = '<div class="assertion-empty">Bu durumda gösterilecek beyan yok.</div>';
        return;
    }

    queue.innerHTML = assertions.map(assertion => {
        const source = assertion.source || {};
        const actions = assertion.status === "proposed"
            ? `
                <div class="assertion-actions">
                    <input type="text" maxlength="2000" aria-label="Karar notu" placeholder="Karar notu (isteğe bağlı)">
                    <button type="button" data-decision="rejected" data-id="${escapeHtml(assertion.id)}">Reddet</button>
                    <button type="button" class="primary" data-decision="accepted" data-id="${escapeHtml(assertion.id)}">Kabul et</button>
                </div>
            `
            : "";

        return `
            <article class="assertion-card" data-status="${escapeHtml(assertion.status)}">
                <div class="assertion-main-copy">
                    <div class="assertion-meta">
                        <span class="assertion-field">${escapeHtml(assertion.field)}</span>
                        <span>${escapeHtml(assertion.entity_type)}</span>
                        <span>${escapeHtml(assertion.status)}</span>
                        <span>${assertion.confidence == null ? "" : `Güven ${Math.round(assertion.confidence * 100)}%`}</span>
                    </div>
                    <p class="assertion-value">${escapeHtml(displayValue(assertion.value))}</p>
                    <code class="assertion-entity">${escapeHtml(assertion.entity_id)}</code>
                </div>
                <aside class="assertion-source">
                    <strong>${escapeHtml(source.name || source.code || "Kaynağı belirtilmemiş")}</strong>
                    <span>${escapeHtml(source.code || source.system_type || "")}</span>
                    <span>Güven düzeyi ${escapeHtml(source.trust_level ?? "—")}</span>
                    <span>${escapeHtml(assertion.asserted_at || "")}</span>
                </aside>
                ${actions}
            </article>
        `;
    }).join("");
}

async function loadQueue() {
    showMessage(queueStatus, "Beyanlar yükleniyor...");
    queue.replaceChildren();

    try {
        const status = encodeURIComponent(statusFilter.value);
        const result = await api(`/admin/assertions?status=${status}&limit=200`);
        count.textContent = `${result.count} beyan`;
        renderAssertions(result.assertions || []);
        showMessage(queueStatus, "");
    } catch (error) {
        showMessage(queueStatus, error.message, "bad");
        count.textContent = "";

        if ([401, 403].includes(error.status)) {
            window.localStorage.removeItem(TOKEN_KEY);
            workspace.hidden = true;
            loginView.hidden = false;
        }
    }
}

async function decide(assertionId, decision, note) {
    const buttons = queue.querySelectorAll(`[data-id="${CSS.escape(assertionId)}"]`);
    buttons.forEach(button => { button.disabled = true; });

    try {
        const result = await api(`/assertions/${encodeURIComponent(assertionId)}/decide`, {
            method: "POST",
            body: { decision, note: note || null },
        });

        const applied = result.applied || [];
        const dropped = result.dropped || [];
        const message = decision === "accepted"
            ? `Beyan kabul edildi. Kanonik alana uygulanan: ${applied.join(", ") || "yok"}${dropped.length ? `. Uygulanmayan: ${dropped.join(", ")}` : ""}`
            : "Beyan reddedildi.";

        await loadQueue();
        showMessage(queueStatus, message, "good");
    } catch (error) {
        showMessage(queueStatus, error.message, "bad");
        buttons.forEach(button => { button.disabled = false; });
    }
}

function enterWorkspace(user) {
    loginView.hidden = true;
    workspace.hidden = false;
    setSession(user);
    loadQueue();
}

document.getElementById("login-form").addEventListener("submit", login);
document.getElementById("assertion-refresh").addEventListener("click", loadQueue);
statusFilter.addEventListener("change", loadQueue);

queue.addEventListener("click", event => {
    const button = event.target.closest("[data-decision]");

    if (!button) {
        return;
    }

    const note = button.closest(".assertion-card")
        .querySelector(".assertion-actions input").value.trim();
    decide(button.dataset.id, button.dataset.decision, note);
});

async function restoreSession() {
    if (!token()) {
        loginView.hidden = false;
        return;
    }

    try {
        const result = await api("/auth/me");

        if (result.user?.role !== "admin" && result.role !== "admin") {
            throw new Error("Bu alan yalnızca yönetici hesabına açıktır.");
        }

        enterWorkspace(result.user || result);
    } catch (error) {
        window.localStorage.removeItem(TOKEN_KEY);
        loginView.hidden = false;
    }
}

restoreSession();