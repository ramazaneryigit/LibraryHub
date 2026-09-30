/* LibraryHub · kurumun kendi kütüphane otomasyonu.
 *
 * Aynı kurallar: çerçevesiz, escapeHtml, hash yönlendirme, tek fetch
 * sarmalayıcısı. Yönetim panelinden ayrı bir belirteç anahtarı kullanır, çünkü
 * bir kütüphaneci ile bir platform yöneticisi aynı tarayıcıda oturum açabilir.
 *
 * Bu ekranda `tenant_id` diye bir şey yok. Hangi kütüphane olduğu oturumdan
 * gelir ve veritabanı politikası onu dayatır; istemcinin söyleyebileceği bir şey
 * olsaydı, söyleyebildiği şey yanlış olabilirdi.
 */

const API = "/api/v1";
const TOKEN_KEY = "libraryhub.library.token";


/* --------------------------------------------------------- oturum */

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
let summary = null;


/* --------------------------------------------------------- güvenli html */

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


/* --------------------------------------------------------- api */

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

    let payload = null;

    try {
        payload = await response.json();
    } catch (error) {
        payload = null;
    }

    if (!response.ok) {
        let detail = payload && payload.detail;

        if (Array.isArray(detail)) {
            detail = detail
                .map(entry => `${(entry.loc || []).slice(1).join(".")}: ${entry.msg}`)
                .join("; ");
        }

        const failure = new Error(detail || `HTTP ${response.status}`);
        failure.status = response.status;
        throw failure;
    }

    return payload;
}


/* --------------------------------------------------------- durum */

const statusBox = document.getElementById("view-status");

function say(message, kind = "") {
    statusBox.textContent = message;
    statusBox.className = `status ${kind}`;
    statusBox.hidden = !message;
}


/* --------------------------------------------------------- giriş */

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
    loginStatus.textContent = "Giriş yapılıyor…";

    try {
        const result = await api("/auth/login", {
            method: "POST",
            body: { email, password },
        });

        if (!result.user.tenant_id) {
            loginStatus.className = "status bad";
            loginStatus.textContent =
                "Bu hesap bir kütüphaneye bağlı değil. Platform yöneticileri " +
                "/admin adresini kullanır.";
            return;
        }

        setToken(result.token);
        loginStatus.hidden = true;

        await enterWorkspace();
    } catch (error) {
        loginStatus.className = "status bad";
        loginStatus.textContent = error.message;
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


/* --------------------------------------------------------- sekmeler */

const VIEWS = ["panel", "holdings", "items", "proposals"];

function activeView() {
    const name = (window.location.hash || "").replace("#/", "");

    return VIEWS.includes(name) ? name : "panel";
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

    if (view === "panel") {
        await loadSummary();
    } else if (view === "holdings") {
        await loadHoldings();
    } else if (view === "items") {
        await loadItems();
    } else {
        await loadProposals();
    }
}


/* --------------------------------------------------------- panel */

const SUMMARY_CARDS = [
    ["holding", "Holding"],
    ["published", "Yayında"],
    ["item", "Nüsha"],
    ["available", "Rafta"],
    ["on_loan", "Ödünçte"],
    ["branch", "Şube"],
    ["pending", "Bekleyen öneri"],
];

async function loadSummary() {
    summary = await api("/tenant/summary");

    const values = {
        holding: summary.holdings,
        published: summary.published_holdings,
        item: summary.items,
        available: summary.available,
        on_loan: summary.on_loan,
        branch: summary.branches,
        pending: summary.pending_proposals,
    };

    document.getElementById("summary-grid").innerHTML = SUMMARY_CARDS
        .map(([key, label]) => `
            <div class="summary-card">
                <div class="summary-value">${values[key]}</div>
                <div class="summary-label">${escapeHtml(label)}</div>
            </div>
        `)
        .join("");
}


/* --------------------------------------------------------- holdingler */

let holdings = [];
let branches = [];
let catalogPicks = {};

async function loadHoldings() {
    const result = await api("/tenant/holdings?limit=200");

    holdings = result.holdings;

    document.getElementById("holding-summary").textContent =
        `${result.count} holding`;

    document.getElementById("holding-list").innerHTML = holdings.length
        ? holdings.map(holding => `
            <div class="item">
                <div class="grow">
                    <div class="title">${escapeHtml(holding.local_holding_key)}</div>
                    <div class="sub">
                        ${escapeHtml(holding.holding_type)} ·
                        ${holding.item_count} nüsha ·
                        ${holding.call_number ? escapeHtml(holding.call_number) : "yer numarası yok"}
                    </div>
                </div>
                <span class="badge ${holding.status === "suppressed" ? "inactive" : ""}">
                    ${escapeHtml(holding.status)}
                </span>
            </div>
        `).join("")
        : '<div class="item"><div class="grow"><div class="sub">Henüz holding yok.</div></div></div>';

    // Nüsha formunun holding seçicisi buradan besleniyor.
    document.getElementById("item-holding").innerHTML = holdings
        .map(holding => `
            <option value="${escapeHtml(holding.id)}">
                ${escapeHtml(holding.local_holding_key)}
            </option>
        `)
        .join("");

    document.getElementById("item-holding-filter").innerHTML =
        '<option value="">Hepsi</option>' +
        holdings.map(holding => `
            <option value="${escapeHtml(holding.id)}">
                ${escapeHtml(holding.local_holding_key)}
            </option>
        `).join("");
}

document.getElementById("holding-new").addEventListener("click", async () => {
    if (!branches.length) {
        const result = await api("/tenant/branches");

        branches = result.branches;

        document.getElementById("holding-branch").innerHTML = branches
            .map(branch => `
                <option value="${escapeHtml(branch.id)}" ${branch.is_default ? "selected" : ""}>
                    ${escapeHtml(branch.name)}
                </option>
            `).join("");
    }

    document.getElementById("holding-form").hidden = false;
    document.getElementById("holding-fields").hidden = true;
    document.getElementById("catalog-results").innerHTML = "";
    document.getElementById("catalog-query").focus();
});

document.getElementById("holding-cancel").addEventListener("click", () => {
    document.getElementById("holding-form").hidden = true;
});

document.getElementById("catalog-search").addEventListener("click", searchCatalog);

document.getElementById("catalog-query").addEventListener("keydown", event => {
    if (event.key === "Enter") {
        event.preventDefault();
        searchCatalog();
    }
});

async function searchCatalog() {
    const query = document.getElementById("catalog-query").value.trim();
    const box = document.getElementById("catalog-results");

    if (!query) {
        return;
    }

    box.innerHTML = '<div class="item"><div class="grow"><div class="sub">Aranıyor…</div></div></div>';

    const result = await api(`/search?q=${encodeURIComponent(query)}&limit=20`);

    catalogPicks = {};

    if (!result.results.length) {
        box.innerHTML = '<div class="item"><div class="grow"><div class="sub">Eşleşen eser yok.</div></div></div>';
        return;
    }

    box.innerHTML = result.results.map(work => {
        const editions = [];

        (work.expressions || []).forEach(expression => {
            (expression.manifestations || []).forEach(manifestation => {
                const key = `m:${manifestation.entity_id}`;

                catalogPicks[key] = {
                    manifestation_entity_id: manifestation.entity_id,
                    label: `${work.canonical_title} — ${manifestation.publication_date || "tarih yok"} ${manifestation.publication_statement || ""}`.trim(),
                };

                editions.push(`
                    <option value="${escapeHtml(key)}">
                        ${escapeHtml(manifestation.publication_date || "tarih yok")}
                        · ${escapeHtml(manifestation.publication_statement || work.canonical_title)}
                    </option>
                `);
            });
        });

        if (!editions.length) {
            return `
                <div class="item">
                    <div class="grow">
                        <div class="title">${escapeHtml(work.canonical_title)}</div>
                        <div class="sub">Bu eserin katalogda baskısı yok — önce katalogda açılmalı.</div>
                    </div>
                </div>
            `;
        }

        return `
            <div class="item">
                <div class="grow">
                    <div class="title">${escapeHtml(work.canonical_title)}</div>
                    <div class="sub">${escapeHtml(work.original_title || "")}</div>
                </div>
                <select class="catalog-pick">${editions.join("")}</select>
            </div>
        `;
    }).join("");
}

document.getElementById("holding-fields").addEventListener("submit", async event => {
    event.preventDefault();

    const pick = document.querySelector(".catalog-pick");

    if (!pick || !catalogPicks[pick.value]) {
        say("Önce katalogdan bir baskı seçin.", "bad");
        return;
    }

    try {
        await api("/tenant/holdings", {
            method: "POST",
            body: {
                branch_id: document.getElementById("holding-branch").value,
                local_holding_key: document.getElementById("holding-key").value.trim(),
                call_number: document.getElementById("holding-call").value.trim() || null,
                manifestation_entity_id: catalogPicks[pick.value].manifestation_entity_id,
            },
        });

        document.getElementById("holding-form").hidden = true;
        document.getElementById("holding-key").value = "";
        document.getElementById("holding-call").value = "";
        say("Holding kaydedildi.", "ok");

        await loadHoldings();
    } catch (error) {
        say(error.message, "bad");
    }
});

document.getElementById("holding-refresh").addEventListener("click", loadHoldings);


/* --------------------------------------------------------- nüshalar */

let items = [];

async function loadItems() {
    if (!holdings.length) {
        await loadHoldings();
    }

    const filter = document.getElementById("item-holding-filter").value;
    const result = await api("/tenant/items?limit=200");

    items = filter
        ? result.items.filter(item => item.id && filter)
        : result.items;

    // `/tenant/items` holding kimliği döndürmüyor; süzgeç sunucuda yapılmalı.
    // Bugün için hepsini gösterip kullanıcıya sayıyı söylemek dürüst olanı.
    document.getElementById("item-summary").textContent = `${result.count} nüsha`;

    document.getElementById("item-list").innerHTML = result.items.length
        ? result.items.map(item => `
            <div class="item" data-id="${escapeHtml(item.id)}">
                <div class="grow">
                    <div class="title">
                        ${escapeHtml(item.barcode) || '<span class="muted">barkodsuz</span>'}
                    </div>
                    <div class="sub">
                        ${escapeHtml(item.shelfmark) || "raf yok"} ·
                        ${escapeHtml(item.call_number) || "yer numarası yok"} ·
                        ${escapeHtml(item.branch_name) || ""}
                    </div>
                </div>
                <span class="badge ${item.availability_status === "available" ? "applied" : ""}">
                    ${escapeHtml(item.availability_status)}
                </span>
                <button type="button" class="item-edit" data-id="${escapeHtml(item.id)}">
                    Durum
                </button>
            </div>
        `).join("")
        : '<div class="item"><div class="grow"><div class="sub">Bu kütüphanede nüsha yok.</div></div></div>';
}

document.getElementById("item-new").addEventListener("click", async () => {
    if (!holdings.length) {
        await loadHoldings();
    }

    if (!holdings.length) {
        say("Önce bir holding ekleyin.", "bad");
        return;
    }

    document.getElementById("item-form").hidden = false;
});

document.getElementById("item-cancel").addEventListener("click", () => {
    document.getElementById("item-form").hidden = true;
});

document.getElementById("item-form").addEventListener("submit", async event => {
    event.preventDefault();

    try {
        await api("/tenant/items", {
            method: "POST",
            body: {
                holding_id: document.getElementById("item-holding").value,
                barcode: document.getElementById("item-barcode").value.trim() || null,
                shelfmark: document.getElementById("item-shelfmark").value.trim() || null,
                availability_status: document.getElementById("item-availability").value,
            },
        });

        document.getElementById("item-form").hidden = true;
        document.getElementById("item-barcode").value = "";
        document.getElementById("item-shelfmark").value = "";
        say("Nüsha kaydedildi.", "ok");

        await loadItems();
    } catch (error) {
        say(error.message, "bad");
    }
});

document.getElementById("item-list").addEventListener("click", async event => {
    const button = event.target.closest(".item-edit");

    if (!button) {
        return;
    }

    const status = window.prompt(
        "Yeni durum: available, on_loan, reference, lost, unknown",
        "available"
    );

    if (!status) {
        return;
    }

    try {
        await api(`/tenant/items/${button.dataset.id}`, {
            method: "PATCH",
            body: { availability_status: status },
        });

        say("Durum güncellendi.", "ok");
        await loadItems();
    } catch (error) {
        say(error.message, "bad");
    }
});

document.getElementById("item-refresh").addEventListener("click", loadItems);
document.getElementById("item-holding-filter").addEventListener("change", loadItems);


/* --------------------------------------------------------- öneriler */

let proposals = [];
let selected = null;

async function loadProposals() {
    const result = await api("/tenant/proposals?limit=100");

    proposals = result.proposals || [];

    document.getElementById("proposal-summary").textContent =
        `${result.count ?? proposals.length} öneri`;

    document.getElementById("proposal-list").innerHTML = proposals.length
        ? proposals.map(proposal => `
            <div class="item ${selected && selected.id === proposal.id ? "selected" : ""}"
                 data-id="${escapeHtml(proposal.id)}">
                <div class="grow">
                    <div class="title">${escapeHtml(proposal.change_type)}</div>
                    <div class="sub">${escapeHtml(proposal.rationale)}</div>
                </div>
                <span class="badge ${escapeHtml(proposal.status)}">
                    ${escapeHtml(proposal.status)}
                </span>
            </div>
        `).join("")
        : '<div class="item"><div class="grow"><div class="sub">Öneri yok.</div></div></div>';

    renderProposalDetail();
}

function renderProposalDetail() {
    const detail = document.getElementById("proposal-detail");

    if (!selected) {
        detail.hidden = true;
        return;
    }

    detail.hidden = false;
    detail.innerHTML = `
        <h3>${escapeHtml(selected.change_type)}</h3>

        <dl>
            <dt>Durum</dt>
            <dd><span class="badge ${escapeHtml(selected.status)}">${escapeHtml(selected.status)}</span></dd>

            <dt>Gerekçe</dt>
            <dd>${escapeHtml(selected.rationale)}</dd>

            ${selected.review_note ? `
                <dt>Yönetici notu</dt>
                <dd>${escapeHtml(selected.review_note)}</dd>
            ` : ""}
        </dl>

        ${selected.status === "pending" ? `
            <div class="actions">
                <button type="button" class="danger" data-action="withdraw">Geri çek</button>
                <button type="button" data-action="close">Kapat</button>
            </div>
        ` : '<div class="actions"><button type="button" data-action="close">Kapat</button></div>'}

        <div id="proposal-result" class="result-line"></div>
    `;
}

document.getElementById("proposal-list").addEventListener("click", event => {
    const item = event.target.closest(".item");

    if (!item || !item.dataset.id) {
        return;
    }

    selected = proposals.find(p => p.id === item.dataset.id) || null;

    loadProposals();
});

document.getElementById("proposal-detail").addEventListener("click", async event => {
    const button = event.target.closest("button[data-action]");

    if (!button || !selected) {
        return;
    }

    if (button.dataset.action === "close") {
        selected = null;
        renderProposalDetail();
        return;
    }

    try {
        await api(`/tenant/proposals/${selected.id}/withdraw`, { method: "POST" });

        selected = null;
        say("Öneri geri çekildi.", "ok");

        await loadProposals();
    } catch (error) {
        document.getElementById("proposal-result").className = "result-line bad";
        document.getElementById("proposal-result").textContent = error.message;
    }
});

document.getElementById("proposal-refresh").addEventListener("click", loadProposals);


/* --------------------------------------------------------- açılış */

async function enterWorkspace() {
    session = await api("/tenant/me");

    loginView.hidden = true;
    workspace.hidden = false;

    document.getElementById("library-name").textContent =
        session.organization_name || session.tenant_name || "Kütüphanem";

    document.getElementById("library-sub").textContent =
        `${session.tenant_name || ""} · kütüphane otomasyonu`;

    sessionBox.innerHTML = `
        <strong>${escapeHtml(session.display_name || session.email)}</strong>
        <span class="badge">${escapeHtml(session.role)}</span>
        <button type="button" id="logout">Çıkış</button>
    `;

    document.getElementById("logout").addEventListener("click", logout);

    if (!window.location.hash) {
        window.location.hash = "#/panel";
    }

    try {
        await render();
    } catch (error) {
        say(error.message, "bad");

        if (error.status === 401 || error.status === 403) {
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
        await enterWorkspace();
    } catch (error) {
        setToken(null);
        loginView.hidden = false;
    }
}

start();
