const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");
const institutionPanel = document.getElementById("institution-panel");
const searchFieldSelect = document.getElementById("search-field");
const searchModeSelect = document.getElementById("search-mode");


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
   ARAMA SONUCU KARTI
--------------------------------------------------------- */

function renderWork(work) {
    const authors = work.authors || [];
    const subjects = work.subjects || [];

    const authorNames = authors.length
        ? authors
            .map(author => escapeHtml(author.name))
            .join(", ")
        : "Yazar bilgisi yok";

    const subjectTags = subjects
        .map(subject => `
            <span class="tag">
                ${escapeHtml(subject.label)}
            </span>
        `)
        .join("");

    return `
        <article class="result-card">

            <div class="result-type">
                ESER
            </div>

            <h3>
                <button
                    type="button"
                    class="detail-button record-title"
                    data-work-id="${escapeHtml(work.entity_id)}"
                >${escapeHtml(work.canonical_title)}</button>
            </h3>

            ${
                work.original_title
                    ? `
                        <div class="original-title">
                            ${escapeHtml(work.original_title)}
                        </div>
                      `
                    : ""
            }

            <p class="result-author">
                ${authorNames}
            </p>

            <div class="metadata">

                ${subjectTags}

                ${
                    work.original_language
                        ? `
                            <span class="tag">
                                Özgün dil:
                                ${escapeHtml(work.original_language)}
                            </span>
                          `
                        : ""
                }

            </div>

            ${
                work.description
                    ? `
                        <p class="result-description">
                            ${escapeHtml(work.description)}
                        </p>
                      `
                    : ""
            }



            <button
                type="button"
                class="detail-button"
                data-work-id="${escapeHtml(work.entity_id)}"
            >
                Kaydı görüntüle →
            </button>

        </article>
    `;
}


/* ---------------------------------------------------------
   ARAMA
--------------------------------------------------------- */

function renderInstitutionPanel(institutions, matchingLibraries, selectedLibraryId) {
    if (!institutions.length) {
        institutionPanel.innerHTML = `
            <h2>Üniversiteler / kurumlar</h2>
            <p class="institution-hint">Henüz koleksiyon kaydı bulunan bir kurum yok.</p>
        `;
        return;
    }

    const matchingCounts = new Map(
        matchingLibraries.map(item => [String(item.value), item.count])
    );

    institutionPanel.innerHTML = `
        <div class="institution-panel-heading">
            <h2>Üniversiteler / kurumlar</h2>
            ${selectedLibraryId ? `<button type="button" class="clear-institution-filter">Tüm kurumlar</button>` : ""}
        </div>
        <p class="institution-hint">Kurumun toplam koleksiyon kaydı; parantez içi sayı aramanızla eşleşen eser sayısıdır.</p>
        <ul class="institution-list">
            ${institutions.map(institution => {
                const id = String(institution.value);
                const matches = matchingCounts.get(id);
                const selected = id === String(selectedLibraryId);
                return `
                    <li>
                        <button type="button" class="institution-filter${selected ? " selected" : ""}"
                            data-institution-id="${escapeHtml(id)}" aria-pressed="${selected}">
                            <span class="institution-name">${escapeHtml(institution.label)}</span>
                            <span class="institution-count">${Number(institution.count).toLocaleString("tr-TR")} koleksiyon kaydı${matches === undefined ? "" : ` · ${Number(matches).toLocaleString("tr-TR")} eşleşen eser`}</span>
                        </button>
                    </li>
                `;
            }).join("")}
        </ul>
    `;
}


async function performSearch(query, { searchField = "all", searchMode = "keyword", libraryId = null } = {}) {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
        statusBox.textContent = "Lütfen bir arama terimi girin.";
        resultsBox.innerHTML = "";
        institutionPanel.innerHTML = `
            <h2>Üniversiteler / kurumlar</h2>
            <p class="institution-hint">Kurum toplamları arama yaptıktan sonra gösterilir.</p>
        `;
        return;
    }

    searchInput.value = cleanQuery;
    searchFieldSelect.value = searchField;
    searchModeSelect.value = searchMode;
    statusBox.textContent = searchMode === "semantic"
        ? `"${cleanQuery}" anlam benzerliğine göre aranıyor...`
        : `"${cleanQuery}" aranıyor...`;
    resultsBox.innerHTML = "";

    const params = new URLSearchParams({
        q: cleanQuery,
        search_field: searchField,
        search_mode: searchMode,
    });
    if (libraryId) {
        params.set("library_id", libraryId);
    }
    window.history.replaceState({}, "", `${window.location.pathname}?${params}`);

    try {
        const response = await fetch(`/search?${params}`);
        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`HTTP ${response.status}: ${detail}`);
        }

        const data = await response.json();
        renderInstitutionPanel(
            data.institutions || [],
            data.facets?.library || [],
            libraryId
        );

        if (!data.results || data.results.length === 0) {
            statusBox.textContent = `"${cleanQuery}" için sonuç bulunamadı.`;
            return;
        }

        statusBox.textContent = data.truncated
            ? `${data.count} kayıt bulundu (ilk ${data.count} gösteriliyor — daha fazlası için arama terimini daraltın).`
            : `${data.count} kayıt bulundu.`;
        resultsBox.innerHTML = data.results.map(renderWork).join("");
    } catch (error) {
        console.error("LibraryHub arama hatası:", error);
        statusBox.textContent = `Arama yapılamadı: ${error.message}`;
        resultsBox.innerHTML = `
            <div class="result-card">${escapeHtml(error.message)}</div>
        `;
    }
}


searchForm.addEventListener("submit", event => {
    event.preventDefault();
    performSearch(searchInput.value, {
        searchField: searchFieldSelect.value,
        searchMode: searchModeSelect.value,
        libraryId: new URLSearchParams(window.location.search).get("library_id"),
    });
});

institutionPanel.addEventListener("click", event => {
    const filterButton = event.target.closest("[data-institution-id]");
    const clearButton = event.target.closest(".clear-institution-filter");
    const params = new URLSearchParams(window.location.search);
    const libraryId = filterButton?.dataset.institutionId || null;

    if (!filterButton && !clearButton) {
        return;
    }

    performSearch(searchInput.value, {
        searchField: searchFieldSelect.value,
        searchMode: searchModeSelect.value,
        libraryId: libraryId && libraryId !== params.get("library_id") ? libraryId : null,
    });
});

document.querySelectorAll("[data-query]").forEach(button => {
    button.addEventListener("click", () => {
        searchFieldSelect.value = "all";
        searchModeSelect.value = "keyword";
        performSearch(button.dataset.query, { searchField: "all", searchMode: "keyword", libraryId: null });
    });
});

const initialParams = new URLSearchParams(window.location.search);
if (initialParams.has("q")) {
    performSearch(initialParams.get("q"), {
        searchField: initialParams.get("search_field") || "all",
        searchMode: initialParams.get("search_mode") || "keyword",
        libraryId: initialParams.get("library_id"),
    });
}

/* ---------------------------------------------------------
   ESER DETAYI
--------------------------------------------------------- */

function renderDetailHoldings(holdings) {
    if (!holdings || holdings.length === 0) {
        return "";
    }

    const totalCopies = holdings.reduce(
        (sum, holding) => sum + (holding.item_count || 0),
        0
    );
    const totalHoldings = holdings.reduce(
        (sum, holding) => sum + (holding.holdings || 0),
        0
    );

    const rows = holdings.map(holding => {
        const institution = holding.entity_id
            ? `<button
                   type="button"
                   class="entity-link collective-agent-link"
                   data-agent-id="${escapeHtml(holding.entity_id)}"
               >${escapeHtml(holding.name)}</button>`
            : `<span class="holding-unknown">Kurum kaydedilmemiş</span>`;

        const availability = Object.entries(
            holding.availability || {}
        )
            .map(([status, count]) => `
                <span class="tag">
                    ${escapeHtml(status)}: ${count}
                </span>
            `)
            .join("");

        return `
            <div class="holding-row">
                <div class="holding-institution">
                    ${institution}
                </div>

                <div class="holding-count">
                    ${holding.holdings || 0} koleksiyon kaydı ·
                    ${holding.item_count || 0} nüsha
                </div>

                <div class="holding-availability">
                    ${availability}
                </div>
            </div>
        `;
    }).join("");

    return `
        <div class="detail-holdings">
            <div class="detail-item-title">
                ${totalHoldings} koleksiyon kaydı · ${totalCopies} nüsha · ${holdings.length} kurum
            </div>

            <div class="holdings-list">
                ${rows}
            </div>
        </div>
    `;
}


function renderDetailManifestations(manifestations) {
    if (!manifestations || manifestations.length === 0) {
        return "";
    }

    return manifestations.map(manifestation => {
        const publishers = manifestation.publishers || [];

        return `
            <div class="detail-manifestation">

                <h4>Yayım</h4>

                ${manifestation.publication_statement ? `
                    <p class="publication-title">
                        ${escapeHtml(manifestation.publication_statement)}
                    </p>
                ` : ""}

                <div class="metadata">
                    ${manifestation.publication_date ? `
                        <span class="tag">
                            ${escapeHtml(manifestation.publication_date)}
                        </span>
                    ` : ""}

                    ${manifestation.edition_statement ? `
                        <span class="tag">
                            ${escapeHtml(manifestation.edition_statement)}
                        </span>
                    ` : ""}

                    ${manifestation.carrier_type ? `
                        <span class="tag">
                            ${escapeHtml(manifestation.carrier_type)}
                        </span>
                    ` : ""}

                    ${manifestation.extent ? `
                        <span class="tag">
                            ${escapeHtml(manifestation.extent)}
                        </span>
                    ` : ""}
                </div>

                
				${publishers.length ? `
					<p>
						<strong>Yayıncı:</strong>

						${publishers.map(publisher => `
							<button
							type="button"
							class="entity-link collective-agent-link"
							data-agent-id="${escapeHtml(publisher.entity_id)}"
							>
						${escapeHtml(publisher.name)}
							</button>
							`).join(", ")}
					</p>
				` : ""}

                ${renderDetailHoldings(manifestation.holdings)}
            </div>
        `;
    }).join("");
}


function renderDetailExpressions(expressions) {
    if (!expressions || expressions.length === 0) {
        return `
            <p class="empty-detail">
                Bu eser için Expression kaydı bulunmuyor.
            </p>
        `;
    }

    return expressions.map(expression => {
        const agents = expression.agents || [];

        return `
            <div class="detail-expression">

                <div class="expression-header">
                    <h3>Expression</h3>

                    ${expression.language ? `
                        <span class="language-badge">
                            ${escapeHtml(expression.language)}
                        </span>
                    ` : ""}
                </div>

                ${expression.description ? `
                    <p>${escapeHtml(expression.description)}</p>
                ` : ""}

                ${expression.expression_form ? `
                    <p>
                        <strong>Biçim:</strong>
                        ${escapeHtml(expression.expression_form)}
                    </p>
                ` : ""}

                
                ${agents.length ? `
					<p>
						<strong>Katkı sağlayan:</strong>

						${agents.map(agent => `
							<button
							type="button"
							class="entity-link person-link"
							data-person-id="${escapeHtml(agent.entity_id)}"
							>
							${escapeHtml(agent.name)}
							</button>
								${agent.role
									? ` (${escapeHtml(agent.role)})`
									: ""
							}
        `				).join(", ")}
					</p>
` : ""}

                ${renderDetailManifestations(expression.manifestations)}
            </div>
        `;
    }).join("");
}


function renderWorkDetail(work) {
    const authors = work.authors || [];
    const subjects = work.subjects || [];

    const authorsHtml = authors.length ? `
        <div class="detail-authors">
            ${authors.map(author => `
                <button
                    type="button"
                    class="entity-link person-link"
                    data-person-id="${escapeHtml(author.entity_id)}"
                >
                    ${escapeHtml(author.name)}
                </button>
            `).join(", ")}
        </div>
    ` : "";

    return `
        <div class="detail-page">

            <button
                type="button"
                id="back-to-results"
                class="back-button"
            >
                ← Arama sonuçlarına dön
            </button>

            <div class="detail-hero">

                <div class="result-type">
                    ESER
                </div>

                <h2>
                    ${escapeHtml(work.canonical_title)}
                </h2>

                ${work.original_title ? `
                    <div class="detail-original-title">
                        ${escapeHtml(work.original_title)}
                    </div>
                ` : ""}

                ${authorsHtml}

                <div class="metadata">
                    ${subjects.map(subject => `
                        <button
                            type="button"
                            class="tag concept-link"
                            data-concept-id="${escapeHtml(subject.entity_id)}"
                        >
                            ${escapeHtml(subject.label)}
                        </button>
                    `).join("")}

                    ${work.original_language ? `
                        <span class="tag">
                            Özgün dil:
                            ${escapeHtml(work.original_language)}
                        </span>
                    ` : ""}
                </div>

                ${work.description ? `
                    <p class="detail-description">
                        ${escapeHtml(work.description)}
                    </p>
                ` : ""}

            </div>

            <section class="detail-content">

                <h2>Sürümler ve yayınlar</h2>

                ${renderDetailExpressions(work.expressions)}

            </section>

        </div>
    `;
}


async function openWorkDetail(workId) {
    statusBox.textContent = "Eser kaydı yükleniyor...";

    try {
        const response = await fetch(
            `/works/${encodeURIComponent(workId)}/detail`
        );

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`HTTP ${response.status}: ${detail}`);
        }

        const work = await response.json();

        statusBox.textContent = "";

        resultsBox.innerHTML =
            renderWorkDetail(work);

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });

    } catch (error) {
        console.error(
            "LibraryHub detay hatası:",
            error
        );

        statusBox.textContent =
            "Eser ayrıntıları yüklenemedi.";
    }
}


async function openConcept(conceptId) {
    statusBox.textContent = "Konsept kaydı yükleniyor...";
    resultsBox.innerHTML = "";

    try {
        const response = await fetch(
            `/search/concept/${encodeURIComponent(conceptId)}`
        );

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`HTTP ${response.status}: ${detail}`);
        }

        const data = await response.json();

        statusBox.textContent = "";

        const concept = data.concept || {};
        const results = data.results || [];

        resultsBox.innerHTML = `
            <div class="detail-page">

                <button
                    type="button"
                    class="back-button"
                    id="back-from-concept"
                >
                    ← Önceki görünüme dön
                </button>

                <div class="detail-hero">

                    <div class="result-type">
                        KONSEPT
                    </div>

                    <h2>
                        ${escapeHtml(concept.preferred_label)}
                    </h2>

                </div>

                <section class="detail-content">

                    <h2>İlişkili eserler (${results.length})</h2>

                    ${
                        results.length
                            ? results.map(entry => `
                                <article class="concept-work-card">

                                    <h3>
                                        ${escapeHtml(
                                            entry.canonical_title
                                        )}
                                    </h3>

                                    <button
                                        type="button"
                                        class="detail-button"
                                        data-work-id="${
                                            escapeHtml(
                                                entry.work_entity_id
                                            )
                                        }"
                                    >
                                        Eseri görüntüle →
                                    </button>

                                </article>
                            `).join("")
                            : `
                                <p class="empty-detail">
                                    Bu konseptle ilişkili eser bulunamadı.
                                </p>
                              `
                    }

                </section>

            </div>
        `;

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });

    } catch (error) {
        console.error(
            "LibraryHub konsept hatası:",
            error
        );

        statusBox.textContent =
            "Konsept kaydı yüklenemedi.";
    }
}


async function openPerson(personId) {
    statusBox.textContent = "Kişi kaydı yükleniyor...";
    resultsBox.innerHTML = "";

    try {
        const response = await fetch(
            `/persons/${encodeURIComponent(personId)}/works`
        );

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`HTTP ${response.status}: ${detail}`);
        }

        const person = await response.json();

        statusBox.textContent = "";

        const works = person.works || [];

        resultsBox.innerHTML = `
            <div class="detail-page">

                <button
                    type="button"
                    class="back-button"
                    id="back-from-person"
                >
                    ← Önceki görünüme dön
                </button>

                <div class="detail-hero">

                    <div class="result-type">
                        KİŞİ
                    </div>

                    <h2>
                        ${escapeHtml(person.canonical_name)}
                    </h2>

                    ${person.biography ? `
                        <p class="detail-description">
                            ${escapeHtml(person.biography)}
                        </p>
                    ` : ""}

                </div>

                <section class="detail-content">

                    <h2>İlişkili eserler</h2>

                    ${
                        works.length
                            ? works.map(entry => `
                                <article class="person-work-card">

                                    <div class="relation-label">
                                        ${escapeHtml(entry.role || "ilişkili")}
                                    </div>

                                    <h3>
                                        ${escapeHtml(
                                            entry.work.canonical_title
                                        )}
                                    </h3>

                                    ${entry.work.original_title ? `
                                        <div class="original-title">
                                            ${escapeHtml(
                                                entry.work.original_title
                                            )}
                                        </div>
                                    ` : ""}

                                    <button
                                        type="button"
                                        class="detail-button"
                                        data-work-id="${
                                            escapeHtml(
                                                entry.work.entity_id
                                            )
                                        }"
                                    >
                                        Eseri görüntüle →
                                    </button>

                                </article>
                            `).join("")
                            : `
                                <p class="empty-detail">
                                    Bu kişiyle ilişkili eser bulunamadı.
                                </p>
                              `
                    }

                </section>

            </div>
        `;

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });

    } catch (error) {
        console.error(
            "LibraryHub kişi hatası:",
            error
        );

        statusBox.textContent =
            "Kişi kaydı yüklenemedi.";
    }
}

async function openCollectiveAgent(agentId) {
    statusBox.textContent = "Kurum kaydı yükleniyor...";
    resultsBox.innerHTML = "";

    try {
        const response = await fetch(
            `/collective-agents/${encodeURIComponent(agentId)}/works`
        );

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(`HTTP ${response.status}: ${detail}`);
        }

        const agent = await response.json();

        statusBox.textContent = "";

        const works = agent.works || [];

        resultsBox.innerHTML = `
            <div class="detail-page">

                <button
                    type="button"
                    class="back-button"
                    id="back-from-collective-agent"
                >
                    ← Önceki görünüme dön
                </button>

                <div class="detail-hero">

                    <div class="result-type">
                        KURUM / ORGANİZASYON
                    </div>

                    <h2>
                        ${escapeHtml(agent.canonical_name)}
                    </h2>

                    ${agent.agent_type ? `
                        <div class="metadata">
                            <span class="tag">
                                ${escapeHtml(agent.agent_type)}
                            </span>
                        </div>
                    ` : ""}

                    ${agent.description ? `
                        <p class="detail-description">
                            ${escapeHtml(agent.description)}
                        </p>
                    ` : ""}

                </div>

                <section class="detail-content">

                    <h2>İlişkili eserler (${works.length})</h2>

                    ${
                        works.length
                            ? works.map(entry => `
                                <article class="person-work-card">

                                    <div class="relation-label">
                                        ${escapeHtml(
                                            entry.role || "ilişkili"
                                        )}
                                    </div>

                                    <h3>
                                        ${escapeHtml(
                                            entry.work.canonical_title
                                        )}
                                    </h3>

                                    ${entry.work.original_title ? `
                                        <div class="original-title">
                                            ${escapeHtml(
                                                entry.work.original_title
                                            )}
                                        </div>
                                    ` : ""}

                                    <button
                                        type="button"
                                        class="detail-button"
                                        data-work-id="${escapeHtml(
                                            entry.work.entity_id
                                        )}"
                                    >
                                        Eseri görüntüle →
                                    </button>

                                </article>
                            `).join("")
                            : `
                                <p class="empty-detail">
                                    Bu kurumla ilişkili eser bulunamadı.
                                </p>
                              `
                    }

                </section>

            </div>
        `;

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });

    } catch (error) {
        console.error(
            "LibraryHub collective agent hatası:",
            error
        );

        statusBox.textContent =
            "Kurum kaydı yüklenemedi.";
    }
}
/* ---------------------------------------------------------
   SONUÇ / DETAY TIKLAMALARI
--------------------------------------------------------- */

let lastSearchQuery = "";

let currentView = null;
let isSyncingHash = false;

const originalPerformSearch = performSearch;


/*
    Adres (hash) tek doğruluk kaynağıdır.

    Gezinme önceden yalnızca bellekteki bir yığında tutuluyordu; tarayıcının
    geri tuşu, sayfayı yenileme ve bir kaydın bağlantısını paylaşma
    çalışmıyordu. Artık her görünümün bir adresi var ve tarayıcının kendi
    geçmişi yığın görevi görüyor. Bkz. docs/architecture-v2.md §0.12.
*/

function viewToHash(view) {
    if (!view) {
        return "#/";
    }

    switch (view.type) {
        case "search":
            return `#/search/${encodeURIComponent(view.query)}`;

        case "work":
            return `#/work/${view.id}`;

        case "person":
            return `#/person/${view.id}`;

        case "concept":
            return `#/concept/${view.id}`;

        case "collective-agent":
            return `#/agent/${view.id}`;

        default:
            return "#/";
    }
}


function parseHash() {
    const raw = window.location.hash.replace(/^#\/?/, "");

    if (!raw) {
        return null;
    }

    const parts = raw.split("/");
    const kind = parts.shift();
    const value = decodeURIComponent(parts.join("/"));

    if (!value) {
        return null;
    }

    if (kind === "search") {
        return { type: "search", query: value };
    }

    if (kind === "work") {
        return { type: "work", id: value };
    }

    if (kind === "person") {
        return { type: "person", id: value };
    }

    if (kind === "concept") {
        return { type: "concept", id: value };
    }

    if (kind === "agent") {
        return { type: "collective-agent", id: value };
    }

    return null;
}


function syncHash() {
    const target = viewToHash(currentView);

    if (window.location.hash !== target) {
        isSyncingHash = true;
        window.location.hash = target;
    }
}


function showHome() {
    currentView = null;
    searchInput.value = "";
    statusBox.textContent =
        "Aramaya başlamak için yukarıdaki kutuyu kullanın.";
    resultsBox.innerHTML = "";
}


async function showSearch(query, options = {}) {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
        return;
    }

    lastSearchQuery = cleanQuery;

    const params = new URLSearchParams(window.location.search);
    const searchOptions = {
        searchField: options.searchField ?? params.get("search_field") ?? "all",
        searchMode: options.searchMode ?? params.get("search_mode") ?? "keyword",
        libraryId: Object.prototype.hasOwnProperty.call(options, "libraryId")
            ? options.libraryId
            : params.get("library_id"),
    };
    await originalPerformSearch(cleanQuery, searchOptions);

    currentView = {
        type: "search",
        query: cleanQuery
    };

    syncHash();
}


async function showWork(workId) {
    await openWorkDetail(workId);

    currentView = {
        type: "work",
        id: workId
    };

    syncHash();
}


async function showPerson(personId) {
    await openPerson(personId);

    currentView = {
        type: "person",
        id: personId
    };

    syncHash();
}


async function showConcept(conceptId) {
    await openConcept(conceptId);

    currentView = {
        type: "concept",
        id: conceptId
    };

    syncHash();
}


async function showCollectiveAgent(agentId) {
    await openCollectiveAgent(agentId);

    currentView = {
        type: "collective-agent",
        id: agentId
    };

    syncHash();
}


async function renderView(view) {
    if (!view) {
        showHome();
        return;
    }

    if (view.type === "search") {
        await showSearch(view.query);
    }

    else if (view.type === "work") {
        await showWork(view.id);
    }

    else if (view.type === "person") {
        await showPerson(view.id);
    }

    else if (view.type === "concept") {
        await showConcept(view.id);
    }

    else if (view.type === "collective-agent") {
        await showCollectiveAgent(view.id);
    }

    else {
        showHome();
    }
}


async function goBack() {
    // Adres tek doğruluk kaynağı olduğu için yığın artık tarayıcının kendi
    // geçmişidir.
    if (window.history.length > 1) {
        window.history.back();
        return;
    }

    window.location.hash = "";
}


window.addEventListener(
    "hashchange",
    async () => {
        // syncHash() tarafından yazılan değişiklikleri yok say; aksi hâlde
        // her gezinme kendini yeniden tetikler.
        if (isSyncingHash) {
            isSyncingHash = false;
            return;
        }

        await renderView(parseHash());
    }
);


window.addEventListener(
    "load",
    async () => {
        if (window.location.hash) {
            await renderView(parseHash());
        }
    }
);


/*
    Mevcut arama formu ve örnek arama düğmeleri
    performSearch() çağırdığı için onları da yeni
    navigasyon sistemine bağlıyoruz.
*/
performSearch = async function(query, options) {
    return showSearch(query, options);
};


resultsBox.addEventListener(
    "click",
    async event => {

        const backButton =
            event.target.closest(
                "#back-to-results, " +
                "#back-from-person, " +
                "#back-from-concept, " +
                "#back-from-collective-agent"
            );

        if (backButton) {
            await goBack();
            return;
        }


        const detailButton =
            event.target.closest(".detail-button");

        if (detailButton) {
            await showWork(
                detailButton.dataset.workId
            );
            return;
        }


        const collectiveAgentButton =
            event.target.closest(
                ".collective-agent-link"
            );

        if (collectiveAgentButton) {
            await showCollectiveAgent(
                collectiveAgentButton.dataset.agentId
            );
            return;
        }


        const personButton =
            event.target.closest(".person-link");

        if (personButton) {
            await showPerson(
                personButton.dataset.personId
            );
            return;
        }


        const conceptButton =
            event.target.closest(".concept-link");

        if (conceptButton) {
            await showConcept(
                conceptButton.dataset.conceptId
            );
            return;
        }
    }
);