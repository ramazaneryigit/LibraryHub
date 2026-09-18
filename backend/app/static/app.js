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

        statusBox.textContent =
            `${data.count} kayıt bulundu.`;

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

function renderDetailItems(items) {
    if (!items || items.length === 0) {
        return "";
    }

    return items.map(item => {
        const institutions = item.holding_institutions || [];

        return `
            <div class="detail-item">
                <div class="detail-item-title">Kütüphane nüshası</div>

                <div class="detail-grid">
                    ${item.barcode ? `
                        <div>
                            <span>Barkod</span>
                            <strong>${escapeHtml(item.barcode)}</strong>
                        </div>
                    ` : ""}

                    ${item.shelfmark ? `
                        <div>
                            <span>Yer numarası</span>
                            <strong>${escapeHtml(item.shelfmark)}</strong>
                        </div>
                    ` : ""}

                    ${item.availability_status ? `
                        <div>
                            <span>Durum</span>
                            <strong>${escapeHtml(item.availability_status)}</strong>
                        </div>
                    ` : ""}

                    
					${institutions.length ? `
						<div>
						<span>Kurum</span>
						<strong>
						${institutions.map(institution => `
						<button
						type="button"
						class="entity-link collective-agent-link"
						data-agent-id="${escapeHtml(institution.entity_id)}"
						>
											${escapeHtml(institution.name)}
							</button>
									`).join(", ")}
										</strong>
						</div>
					` : ""}
                </div>
            
        `;
    }).join("");
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

                ${renderDetailItems(manifestation.items)}
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
let lastViewType = "search"; // search, work, person, concept

const originalPerformSearch = performSearch;

performSearch = async function(query) {
    lastSearchQuery = query.trim();
    lastViewType = "search";
    return originalPerformSearch(query);
};


resultsBox.addEventListener(
    "click",
    event => {

        const detailButton =
            event.target.closest(".detail-button");

        if (detailButton) {
            openWorkDetail(
                detailButton.dataset.workId
            );
            lastViewType = "work";
            return;
        }

        const backButton =
            event.target.closest("#back-to-results");

        if (backButton && lastSearchQuery) {
            performSearch(lastSearchQuery);
            return;
        }
		const backFromCollectiveAgent =
			event.target.closest("#back-from-collective-agent");

		if (backFromCollectiveAgent && lastSearchQuery) {
			performSearch(lastSearchQuery);
			return;
}
        const backFromPerson =
            event.target.closest("#back-from-person");

        if (backFromPerson && lastSearchQuery) {
            performSearch(lastSearchQuery);
            return;
        }

        const backFromConcept =
            event.target.closest("#back-from-concept");

        if (backFromConcept && lastSearchQuery) {
            performSearch(lastSearchQuery);
            return;
        }
		const collectiveAgentButton =
			event.target.closest(".collective-agent-link");

		if (collectiveAgentButton) {
			openCollectiveAgent(
			collectiveAgentButton.dataset.agentId
		);
			lastViewType = "collective-agent";
			return;
}
        const personButton =
            event.target.closest(".person-link");

        if (personButton) {
            openPerson(
                personButton.dataset.personId
            );
            lastViewType = "person";
            return;
        }

        const conceptButton =
            event.target.closest(".concept-link");

        if (conceptButton) {
            openConcept(
                conceptButton.dataset.conceptId
            );
            lastViewType = "concept";
            return;
        }
    }
);