/* LibraryHub yönetim arayüzü.
 *
 * Çerçevesiz, app.js ile aynı kurallar: hash yönlendirme, escapeHtml ile
 * kaçırılmış şablon dizeleri, tek bir fetch sarmalayıcısı.
 *
 * Oturum belirteci localStorage'da tutuluyor. Bu, aynı kaynakta çalışan bir
 * XSS'in belirteci okuyabileceği anlamına gelir; panel bu yüzden sunucudan
 * gelen her değeri escapeHtml'den geçirir. HttpOnly çerez daha güçlü olurdu ve
 * API'nin çerez kabul etmesini gerektirirdi; bu ayrı bir iş.
 */

const API = "/api/v1";
const TOKEN_KEY = "libraryhub.admin.token";


/* ---------------------------------------------------------
   OTURUM
--------------------------------------------------------- */

function token() {
    return window.localStorage.getItem(TOKEN_KEY);
}

function setToken(value) {
    if (value) {
        window.localStorage.setItem(TOKEN_KEY, value);
    } else {
        window.localStorage.removeItem(TOKEN_KEY);
    }
}

let session = null;


/* ---------------------------------------------------------
   GÜVENLİ HTML
--------------------------------------------------------- */

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


/* ---------------------------------------------------------
   API
--------------------------------------------------------- */

class ApiError extends Error {
    constructor(status, detail) {
        super(detail);
        this.status = status;
        this.detail = detail;
    }
}

async function api(path, options = {}) {
    const headers = Object.assign(
        { "Content-Type": "application/json" },
        options.headers || {}
    );

    const current = token();

    if (current) {
        headers.Authorization = `Bearer ${current}`;
    }

    const response = await fetch(`${API}${path}`, {
        method: options.method || "GET",
        headers,
        body: options.body === undefined
            ? undefined
            : JSON.stringify(options.body),
    });

    if (response.status === 204) {
        return null;
    }

    let payload = null;

    try {
        payload = await response.json();
    } catch (error) {
        payload = null;
    }

    if (!response.ok) {
        // FastAPI doğrulama hatalarında `detail` bir liste olur; kullanıcıya
        // "[object Object]" göstermektense alan adlarını söylemek daha iyi.
        let detail = payload && payload.detail;

        if (Array.isArray(detail)) {
            detail = detail
                .map(entry => `${(entry.loc || []).slice(1).join(".")}: ${entry.msg}`)
                .join("; ");
        }

        throw new ApiError(
            response.status,
            detail || `HTTP ${response.status}`
        );
    }

    return payload;
}


/* ---------------------------------------------------------
   DURUM ÇUBUĞU
--------------------------------------------------------- */

const statusBox = document.getElementById("view-status");

function say(message, kind = "") {
    statusBox.textContent = message;
    statusBox.className = `status ${kind}`;
    statusBox.hidden = !message;
}


/* ---------------------------------------------------------
   GİRİŞ
--------------------------------------------------------- */

const loginView = document.getElementById("login-view");
const workspace = document.getElementById("workspace");
const sessionBox = document.getElementById("session");
const loginStatus = document.getElementById("login-status");

document.getElementById("login-form").addEventListener("submit", async event => {
    event.preventDefault();

    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    loginStatus.hidden = false;
    loginStatus.className = "status";
    loginStatus.textContent = "Giriş yapılıyor...";

    try {
        const result = await api("/auth/login", {
            method: "POST",
            body: { email, password },
        });

        if (result.user.role !== "admin") {
            loginStatus.className = "status bad";
            loginStatus.textContent =
                `Bu hesabın rolü '${result.user.role}'. Yönetim ekranları ` +
                "yalnızca 'admin' rolüne açıktır.";
            return;
        }

        setToken(result.token);
        session = result.user;
        loginStatus.hidden = true;

        await enterWorkspace();
    } catch (error) {
        loginStatus.className = "status bad";
        loginStatus.textContent = error.detail || error.message;
    }
});

async function logout() {
    try {
        await api("/auth/logout", { method: "POST" });
    } catch (error) {
        // Belirteç zaten geçersiz olabilir; çıkışı yine de tamamla.
    }

    setToken(null);
    session = null;

    workspace.hidden = true;
    loginView.hidden = false;
    sessionBox.innerHTML = "";
    window.location.hash = "";
}


/* ---------------------------------------------------------
   SEKMELER
--------------------------------------------------------- */

const VIEWS = ["proposals", "staff", "tenants"];

function activeView() {
    const name = (window.location.hash || "").replace("#/", "");

    return VIEWS.includes(name) ? name : "proposals";
}

function showView(name) {
    VIEWS.forEach(view => {
        document.getElementById(`view-${view}`).hidden = view !== name;
    });

    document.querySelectorAll(".tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.view === name);
    });
}

document.getElementById("tabs").addEventListener("click", event => {
    const tab = event.target.closest(".tab");

    if (tab) {
        window.location.hash = `#/${tab.dataset.view}`;
    }
});

window.addEventListener("hashchange", () => {
    if (!workspace.hidden) {
        render();
    }
});

async function render() {
    const view = activeView();

    showView(view);
    say("");

    if (view === "proposals") {
        await loadProposals();
    } else if (view === "staff") {
        await loadStaff();
    } else {
        await loadTenants();
    }
}


/* ---------------------------------------------------------
   ÖNERİLER
--------------------------------------------------------- */

let proposals = [];
let selectedProposal = null;

const proposalStatus = document.getElementById("proposal-status");
const proposalList = document.getElementById("proposal-list");
const proposalDetail = document.getElementById("proposal-detail");
const proposalSummary = document.getElementById("proposal-summary");

function changeRows(changes) {
    if (!changes || !changes.length) {
        return '<tr><td colspan="3" class="muted">Değişiklik bildirilmemiş.</td></tr>';
    }

    return changes
        .map(change => `
            <tr>
                <td>${escapeHtml(change.field)}</td>
                <td class="was">${escapeHtml(change.current) || "—"}</td>
                <td class="now">${escapeHtml(change.proposed) || "—"}</td>
            </tr>
        `)
        .join("");
}

function renderProposalDetail() {
    if (!selectedProposal) {
        proposalDetail.hidden = true;
        return;
    }

    const proposal = selectedProposal;
    const canDecide = proposal.status === "pending";
    const canApply = proposal.status === "accepted";

    proposalDetail.hidden = false;
    proposalDetail.innerHTML = `
        <h3>${escapeHtml(proposal.change_type)} · ${escapeHtml(proposal.tenant_name || proposal.tenant_id)}</h3>

        <dl>
            <dt>Gönderen</dt>
            <dd>${escapeHtml(proposal.submitted_by_email) || "—"}</dd>

            <dt>Hedef</dt>
            <dd>${escapeHtml(proposal.target_entity_type) || "—"}
                ${proposal.target_entity_id
                    ? `<code>${escapeHtml(proposal.target_entity_id)}</code>`
                    : ""}</dd>

            <dt>Gerekçe</dt>
            <dd>${escapeHtml(proposal.rationale)}</dd>

            <dt>Kaynak</dt>
            <dd>${escapeHtml(proposal.evidence) || "—"}</dd>

            <dt>Durum</dt>
            <dd><span class="badge ${escapeHtml(proposal.status)}">${escapeHtml(proposal.status)}</span></dd>

            ${proposal.reviewed_by ? `
                <dt>İnceleyen</dt>
                <dd>${escapeHtml(proposal.reviewed_by)}
                    ${proposal.review_note ? `· ${escapeHtml(proposal.review_note)}` : ""}</dd>
            ` : ""}

            ${proposal.applied_at ? `
                <dt>Uygulandı</dt>
                <dd>${escapeHtml(proposal.applied_at)}
                    · ${escapeHtml((proposal.applied_fields || []).join(", "))}</dd>
            ` : ""}
        </dl>

        <table class="changes">
            <thead>
                <tr><th>Alan</th><th>Şu an</th><th>Önerilen</th></tr>
            </thead>
            <tbody>${changeRows(proposal.field_changes)}</tbody>
        </table>

        <div class="actions">
            ${canDecide ? `
                <input id="decision-note" placeholder="Karar notu (isteğe bağlı)">
                <button type="button" class="primary" data-action="accept">Kabul et</button>
                <button type="button" class="danger" data-action="reject">Reddet</button>
            ` : ""}

            ${canApply ? `
                <button type="button" class="primary" data-action="apply">Uygula</button>
                <span class="muted">Yalnızca beyaz listedeki alanlar yazılır.</span>
            ` : ""}

            <button type="button" data-action="close">Kapat</button>
        </div>

        <div id="detail-result" class="result-line"></div>
    `;
}

function renderProposalList() {
    if (!proposals.length) {
        proposalList.innerHTML =
            '<div class="item"><div class="grow"><div class="sub">Bu durumda öneri yok.</div></div></div>';
        return;
    }

    proposalList.innerHTML = proposals
        .map(proposal => `
            <div class="item ${selectedProposal && selectedProposal.id === proposal.id ? "selected" : ""}"
                 data-id="${escapeHtml(proposal.id)}">
                <div class="grow">
                    <div class="title">${escapeHtml(proposal.tenant_name || proposal.tenant_id)}</div>
                    <div class="sub">${escapeHtml(proposal.rationale)}</div>
                </div>
                <span class="badge">${escapeHtml(proposal.change_type)}</span>
                <span class="badge ${escapeHtml(proposal.status)}">${escapeHtml(proposal.status)}</span>
            </div>
        `)
        .join("");
}

async function loadProposals() {
    try {
        const summary = await api("/admin/proposals/summary");

        proposalSummary.textContent =
            `${summary.total} öneri · bekleyen ${summary.waiting}`;
    } catch (error) {
        proposalSummary.textContent = "";
    }

    const status = proposalStatus.value;
    const result = await api(`/admin/proposals?status=${encodeURIComponent(status)}`);

    proposals = result.proposals;

    if (selectedProposal && !proposals.some(p => p.id === selectedProposal.id)) {
        selectedProposal = null;
    }

    renderProposalList();
    renderProposalDetail();
}

proposalList.addEventListener("click", event => {
    const item = event.target.closest(".item");

    if (!item || !item.dataset.id) {
        return;
    }

    selectedProposal = proposals.find(p => p.id === item.dataset.id) || null;

    renderProposalList();
    renderProposalDetail();
});

proposalDetail.addEventListener("click", async event => {
    const button = event.target.closest("button[data-action]");

    if (!button || !selectedProposal) {
        return;
    }

    const action = button.dataset.action;
    const resultBox = document.getElementById("detail-result");

    if (action === "close") {
        selectedProposal = null;
        renderProposalList();
        renderProposalDetail();
        return;
    }

    button.disabled = true;

    try {
        if (action === "accept" || action === "reject") {
            const note = (document.getElementById("decision-note") || {}).value || null;

            selectedProposal = await api(
                `/admin/proposals/${selectedProposal.id}/decision`,
                {
                    method: "POST",
                    body: {
                        decision: action === "accept" ? "accepted" : "rejected",
                        note,
                    },
                }
            );

            await loadProposals();
            return;
        }

        if (action === "apply") {
            const result = await api(`/admin/proposals/${selectedProposal.id}/apply`, {
                method: "POST",
            });

            selectedProposal = result.proposal;

            const applied = Object.keys(result.applied || {});
            const dropped = result.dropped || [];

            resultBox.className = dropped.length ? "result-line warn" : "result-line ok";
            resultBox.textContent =
                `Yazılan: ${applied.join(", ") || "—"}` +
                (dropped.length ? ` · beyaz listede olmadığı için elenen: ${dropped.join(", ")}` : "");

            renderProposalDetail();
            await loadProposals();

            // renderProposalDetail yeni bir kutu çizdi; sonucu yeniden koy.
            const again = document.getElementById("detail-result");

            if (again) {
                again.className = resultBox.className;
                again.textContent = resultBox.textContent;
            }
        }
    } catch (error) {
        resultBox.className = "result-line bad";
        resultBox.textContent = error.detail || error.message;
        button.disabled = false;
    }
});

proposalStatus.addEventListener("change", loadProposals);
document.getElementById("proposal-refresh").addEventListener("click", loadProposals);


/* ---------------------------------------------------------
   PERSONEL
--------------------------------------------------------- */

let accounts = [];
let tenants = [];
let selectedAccount = null;
let editingAccount = null;

const staffList = document.getElementById("staff-list");
const staffDetail = document.getElementById("staff-detail");
const staffForm = document.getElementById("staff-form");
const staffTenantFilter = document.getElementById("staff-tenant");
const staffFormTenant = document.getElementById("staff-form-tenant");

function tenantOptions(selected) {
    return tenants
        .map(tenant => `
            <option value="${escapeHtml(tenant.id)}" ${tenant.id === selected ? "selected" : ""}>
                ${escapeHtml(tenant.display_name)}
            </option>
        `)
        .join("");
}

function renderStaffDetail() {
    if (!selectedAccount) {
        staffDetail.hidden = true;
        return;
    }

    const account = selectedAccount;
    const isAdmin = account.role === "admin";

    staffDetail.hidden = false;
    staffDetail.innerHTML = `
        <h3>${escapeHtml(account.display_name)}</h3>

        <dl>
            <dt>E-posta</dt>
            <dd>${escapeHtml(account.email)}</dd>

            <dt>Kurum</dt>
            <dd>${escapeHtml(account.tenant_name) || "(platform)"}</dd>

            <dt>Rol</dt>
            <dd><span class="badge ${isAdmin ? "admin" : ""}">${escapeHtml(account.role)}</span></dd>

            <dt>Hesap türü</dt>
            <dd>${escapeHtml(account.account_kind)}</dd>

            <dt>Doğrulanmış</dt>
            <dd>${account.email_verified_at
                    ? escapeHtml(account.email_verified_at)
                    : '<span class="badge inactive">doğrulanmamış</span>'}</dd>

            <dt>Aktif</dt>
            <dd>${account.is_active ? "evet" : '<span class="badge inactive">hayır</span>'}</dd>
        </dl>

        ${isAdmin ? `
            <p class="muted note">
                Yönetici hesapları uygulama üzerinden değiştirilemez. Bu kural
                veritabanındaki bir tetikleyiciyle uygulanır, arayüzde değil.
            </p>
        ` : `
            <div class="actions">
                <button type="button" data-action="edit">Düzenle</button>
                <button type="button" data-action="password">Parola sıfırla</button>
                <button type="button" data-action="revoke">Oturumları bitir</button>
                <button type="button" class="danger" data-action="toggle">
                    ${account.is_active ? "Hesabı kapat" : "Hesabı aç"}
                </button>
                <button type="button" data-action="close">Kapat</button>
            </div>
        `}

        ${isAdmin ? '<div class="actions"><button type="button" data-action="close">Kapat</button></div>' : ""}

        <div id="staff-result" class="result-line"></div>
    `;
}

function renderStaffList() {
    if (!accounts.length) {
        staffList.innerHTML =
            '<div class="item"><div class="grow"><div class="sub">Bu filtrede hesap yok.</div></div></div>';
        return;
    }

    staffList.innerHTML = accounts
        .map(account => `
            <div class="item ${selectedAccount && selectedAccount.id === account.id ? "selected" : ""}"
                 data-id="${escapeHtml(account.id)}">
                <div class="grow">
                    <div class="title">${escapeHtml(account.email)}</div>
                    <div class="sub">
                        ${escapeHtml(account.display_name)}
                        · ${escapeHtml(account.tenant_name) || "platform"}
                    </div>
                </div>
                <span class="badge ${account.role === "admin" ? "admin" : ""}">${escapeHtml(account.role)}</span>
                ${account.email_verified_at ? "" : '<span class="badge">doğrulanmamış</span>'}
                ${account.is_active ? "" : '<span class="badge inactive">kapalı</span>'}
            </div>
        `)
        .join("");
}

async function loadStaff() {
    if (!tenants.length) {
        const result = await api("/admin/tenants");
        tenants = result.tenants;
        staffTenantFilter.innerHTML =
            '<option value="">Hepsi</option>' + tenantOptions(null);
        staffFormTenant.innerHTML = tenantOptions(null);
    }

    const params = new URLSearchParams();

    if (staffTenantFilter.value) {
        params.set("tenant_id", staffTenantFilter.value);
    }

    const role = document.getElementById("staff-role").value;

    if (role) {
        params.set("role", role);
    }

    const query = params.toString();
    const result = await api(`/admin/users${query ? `?${query}` : ""}`);

    accounts = result.accounts;

    if (selectedAccount && !accounts.some(a => a.id === selectedAccount.id)) {
        selectedAccount = null;
    }

    renderStaffList();
    renderStaffDetail();
}

function openStaffForm(account) {
    editingAccount = account || null;

    document.getElementById("staff-form-title").textContent =
        account ? `Düzenle: ${account.email}` : "Yeni hesap";

    document.getElementById("staff-form-email").value = account ? account.email : "";
    document.getElementById("staff-form-email").disabled = Boolean(account);
    document.getElementById("staff-form-name").value = account ? account.display_name : "";
    document.getElementById("staff-form-role").value = account ? account.role : "librarian";
    document.getElementById("staff-form-tenant").value =
        account ? account.tenant_id : (staffTenantFilter.value || tenants[0]?.id || "");

    const passwordField = document.querySelector(".staff-password-field");
    const passwordInput = document.getElementById("staff-form-password");

    passwordField.hidden = Boolean(account);
    passwordInput.required = !account;

    document.getElementById("staff-form-note").hidden = Boolean(account);

    staffForm.hidden = false;
}

staffForm.addEventListener("submit", async event => {
    event.preventDefault();

    const name = document.getElementById("staff-form-name").value.trim();
    const role = document.getElementById("staff-form-role").value;

    try {
        if (editingAccount) {
            selectedAccount = await api(`/admin/users/${editingAccount.id}`, {
                method: "PATCH",
                body: { display_name: name, role, is_active: editingAccount.is_active },
            });
        } else {
            selectedAccount = await api("/admin/users", {
                method: "POST",
                body: {
                    tenant_id: document.getElementById("staff-form-tenant").value,
                    email: document.getElementById("staff-form-email").value.trim(),
                    display_name: name,
                    role,
                    password: document.getElementById("staff-form-password").value,
                },
            });
        }

        staffForm.hidden = true;
        editingAccount = null;
        say("");
        await loadStaff();
    } catch (error) {
        say(error.detail || error.message, "bad");
    }
});

document.getElementById("staff-form-cancel").addEventListener("click", () => {
    staffForm.hidden = true;
    editingAccount = null;
});

document.getElementById("staff-new").addEventListener("click", () => openStaffForm(null));

staffList.addEventListener("click", event => {
    const item = event.target.closest(".item");

    if (!item || !item.dataset.id) {
        return;
    }

    selectedAccount = accounts.find(a => a.id === item.dataset.id) || null;

    renderStaffList();
    renderStaffDetail();
});

staffDetail.addEventListener("click", async event => {
    const button = event.target.closest("button[data-action]");

    if (!button || !selectedAccount) {
        return;
    }

    const action = button.dataset.action;
    const resultBox = document.getElementById("staff-result");

    if (action === "close") {
        selectedAccount = null;
        renderStaffList();
        renderStaffDetail();
        return;
    }

    if (action === "edit") {
        openStaffForm(selectedAccount);
        return;
    }

    button.disabled = true;

    try {
        if (action === "password") {
            const password = window.prompt(
                "Yeni parola (en az 10 karakter). Eski oturumlar iptal edilir:"
            );

            if (!password) {
                button.disabled = false;
                return;
            }

            const result = await api(`/admin/users/${selectedAccount.id}/password`, {
                method: "POST",
                body: { password },
            });

            resultBox.className = "result-line ok";
            resultBox.textContent = `Parola değiştirildi · iptal edilen oturum: ${result.revoked_sessions}`;
            button.disabled = false;
            return;
        }

        if (action === "revoke") {
            const result = await api(`/admin/users/${selectedAccount.id}/sessions/revoke`, {
                method: "POST",
            });

            resultBox.className = "result-line ok";
            resultBox.textContent = `İptal edilen oturum: ${result.revoked_sessions}`;
            button.disabled = false;
            return;
        }

        if (action === "toggle") {
            selectedAccount = await api(`/admin/users/${selectedAccount.id}`, {
                method: "PATCH",
                body: { is_active: !selectedAccount.is_active },
            });

            renderStaffList();
            renderStaffDetail();
            return;
        }
    } catch (error) {
        resultBox.className = "result-line bad";
        resultBox.textContent = error.detail || error.message;
        button.disabled = false;
    }
});

staffTenantFilter.addEventListener("change", loadStaff);
document.getElementById("staff-role").addEventListener("change", loadStaff);
document.getElementById("staff-refresh").addEventListener("click", loadStaff);


/* ---------------------------------------------------------
   KURUMLAR
--------------------------------------------------------- */

document.getElementById("tenant-refresh").addEventListener("click", () => loadTenants());

async function loadTenants() {
    const result = await api("/admin/tenants");

    tenants = result.tenants;

    document.getElementById("tenant-summary").textContent = `${result.count} kurum`;

    document.getElementById("tenant-list").innerHTML = result.tenants
        .map(tenant => `
            <div class="item">
                <div class="grow">
                    <div class="title">${escapeHtml(tenant.display_name)}</div>
                    <div class="sub"><code>${escapeHtml(tenant.slug)}</code></div>
                </div>
                <span class="badge">${escapeHtml(tenant.staff_count)} personel</span>
            </div>
        `)
        .join("");
}


/* ---------------------------------------------------------
   AÇILIŞ
--------------------------------------------------------- */

async function enterWorkspace() {
    loginView.hidden = true;
    workspace.hidden = false;

    sessionBox.innerHTML = `
        <strong>${escapeHtml(session.email)}</strong>
        <span class="badge admin">${escapeHtml(session.role)}</span>
        <button type="button" id="logout">Çıkış</button>
    `;

    document.getElementById("logout").addEventListener("click", logout);

    if (!window.location.hash) {
        window.location.hash = "#/proposals";
    }

    try {
        await render();
    } catch (error) {
        say(error.detail || error.message, "bad");

        if (error.status === 401) {
            await logout();
        }
    }
}

async function start() {
    if (!token()) {
        loginView.hidden = false;
        return;
    }

    try {
        // `/auth/me` returns the account itself; `/auth/login` wraps it in
        // `{token, expires_at, user}`. Not the same shape, so not the same code.
        const me = await api("/auth/me");

        if (me.role !== "admin") {
            setToken(null);
            loginView.hidden = false;
            loginStatus.hidden = false;
            loginStatus.className = "status bad";
            loginStatus.textContent =
                `Bu hesabın rolü '${me.role}'; yönetim ekranları ` +
                "yalnızca 'admin' rolüne açıktır.";
            return;
        }

        session = me;
        await enterWorkspace();
    } catch (error) {
        setToken(null);
        loginView.hidden = false;
    }
}

start();
