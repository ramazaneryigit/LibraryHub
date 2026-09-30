const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");


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

/* Bir eseri tutan kütüphaneler, ağacın tamamından toplanır.
 *
 * API holding'leri ifade → yayın → holding yolunda veriyor; arama sonucu kartı
 * ise "kimde var?" sorusunu ilk bakışta cevaplamalı, yoksa okuyucu her kayda
 * tıklamak zorunda kalır. Aynı kurum birden çok baskıyı tutabildiği için
 * toplanıyor.
 */
function workHoldings(work) {
    const byInstitution = new Map();

    (work.expressions || []).forEach(expression => {
        (expression.manifestations || []).forEach(manifestation => {
            (manifestation.holdings || []).forEach(holding => {
                const key = holding.entity_id || "kaydedilmemis";

                const entry = byInstitution.get(key) || {
                    entity_id: holding.entity_id,
                    name: holding.name,
                    item_count: 0,
                    availability: {},
                };

                entry.item_count += holding.item_count || 0;

                Object.entries(holding.availability || {}).forEach(
                    ([status, count]) => {
                        entry.availability[status] =
                            (entry.availability[status] || 0) + count;
                    }
                );

                byInstitution.set(key, entry);
            });
        });
    });

    return [...byInstitution.values()].sort(
        (left, right) => right.item_count - left.item_count
    );
}


/* Kartta gösterilen kütüphane sayısı. Sınırsız bırakmak, tek bir eserin altında
 * yüz kurum listelemek demekti -- bir kez tam olarak bu oldu ve gerçek
 * kütüphaneler listeyi boğdu. Gerisi sayıyla bildirilir, detayda tamamı var. */
const HOLDINGS_ON_CARD = 5;


function renderWorkHoldings(work) {
    const holdings = workHoldings(work);

    if (holdings.length === 0) {
        return `
            <div class="result-holdings empty">
                Bu eseri tutan kütüphane kaydı yok.
            </div>
        `;
    }

    const totalCopies = holdings.reduce(
        (sum, holding) => sum + holding.item_count,
        0
    );

    const shown = holdings.slice(0, HOLDINGS_ON_CARD);
    const rest = holdings.length - shown.length;

    const rows = shown
        .map(holding => `
            <div class="result-holding">
                <span class="result-holding-name">
                    ${escapeHtml(holding.name) || "Kurum kaydedilmemiş"}
                </span>

                <span class="result-holding-count">
                    ${holding.item_count} nüsha
                </span>
            </div>
        `)
        .join("");

    return `
        <div class="result-holdings">
            <div class="result-holdings-total">
                ${totalCopies} nüsha · ${holdings.length} kütüphane
            </div>

            ${rows}

            ${
                rest > 0
                    ? `
                        <div class="result-holding rest">
                            ve ${rest} kütüphane daha · kaydı görüntüleyin
                        </div>
                      `
                    : ""
            }
        </div>
    `;
}


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
                ${escapeHtml(work.canonical_title)}
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

            ${renderWorkHoldings(work)}

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

async function performSearch(query) {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
        statusBox.textContent =
            "Lütfen bir arama terimi girin.";

        resultsBox.innerHTML = "";
        return;
    }

    searchInput.value = cleanQuery;

    statusBox.textContent =
        `"${cleanQuery}" aranıyor...`;

    resultsBox.innerHTML = "";

    try {

        const response = await fetch(
            `/search?q=${encodeURIComponent(cleanQuery)}`
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data = await response.json();

        if (
            !data.results ||
            data.results.length === 0
        ) {
            statusBox.textContent =
                `"${cleanQuery}" için sonuç bulunamadı.`;

            return;
        }

        // The API caps the result set before duplicates are collapsed, so a
        // full page means "there may be more". Saying so is better than letting
        // the reader assume these are all the matches.
        statusBox.textContent = data.truncated
            ? `${data.count} kayıt bulundu (ilk ${data.count} gösteriliyor — ` +
              `daha fazlası için arama terimini daraltın).`
            : `${data.count} kayıt bulundu.`;

        resultsBox.innerHTML =
            data.results
                .map(renderWork)
                .join("");

    } catch (error) {

        console.error(
            "LibraryHub arama hatası:",
            error
        );

        statusBox.textContent =
            "Arama sırasında bir hata oluştu.";

        resultsBox.innerHTML = `
            <div class="result-card">
                API bağlantısı kurulamadı.
            </div>
        `;
    }
}


/* ---------------------------------------------------------
   ARAMA FORMU
--------------------------------------------------------- */

searchForm.addEventListener(
    "submit",
    event => {

        event.preventDefault();

        performSearch(
            searchInput.value
        );
    }
);


/* ---------------------------------------------------------
   ÖRNEK ARAMA BUTONLARI
--------------------------------------------------------- */

document
    .querySelectorAll("[data-query]")
    .forEach(button => {

        button.addEventListener(
            "click",
            () => {

                performSearch(
                    button.dataset.query
                );
            }
        );

    });


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
                    ${holding.item_count} nüsha
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
                ${totalCopies} nüsha · ${holdings.length} kurum
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
            throw new Error(`HTTP ${response.status}`);
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
            throw new Error(`HTTP ${response.status}`);
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
            throw new Error(`HTTP ${response.status}`);
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
            throw new Error(`HTTP ${response.status}`);
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


async function showSearch(query) {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
        return;
    }

    lastSearchQuery = cleanQuery;

    await originalPerformSearch(cleanQuery);

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
performSearch = async function(query) {
    return showSearch(query);
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