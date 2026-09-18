const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");

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

function renderAgents(agents) {
    if (!agents || agents.length === 0) {
        return "";
    }

    return agents.map(agent => `
        <span class="tag">
            ${escapeHtml(agent.name)}
            ${agent.role ? ` · ${escapeHtml(agent.role)}` : ""}
        </span>
    `).join("");
}

function renderItems(items) {
    if (!items || items.length === 0) {
        return "";
    }

    return items.map(item => {
        const institutions = item.holding_institutions || [];

        return `
            <div class="item">
                <strong>Nüsha</strong><br>

                ${item.barcode
                    ? `Barkod: ${escapeHtml(item.barcode)}<br>`
                    : ""}

                ${item.shelfmark
                    ? `Yer numarası: ${escapeHtml(item.shelfmark)}<br>`
                    : ""}

                ${item.availability_status
                    ? `Durum: ${escapeHtml(item.availability_status)}<br>`
                    : ""}

                ${institutions.length
                    ? `Kütüphane: ${institutions
                        .map(i => escapeHtml(i.name))
                        .join(", ")}`
                    : ""}
            </div>
        `;
    }).join("");
}

function renderManifestations(manifestations) {
    if (!manifestations || manifestations.length === 0) {
        return "";
    }

    return manifestations.map(manifestation => {
        const publishers = manifestation.publishers || [];

        return `
            <div class="manifestation">

                <strong>Yayım / Manifestation</strong>

                <p>
                    ${manifestation.publication_statement
                        ? escapeHtml(manifestation.publication_statement)
                        : "Yayım bilgisi belirtilmemiş"}
                </p>

                <div class="metadata">

                    ${manifestation.publication_date
                        ? `<span class="tag">${escapeHtml(manifestation.publication_date)}</span>`
                        : ""}

                    ${manifestation.edition_statement
                        ? `<span class="tag">${escapeHtml(manifestation.edition_statement)}</span>`
                        : ""}

                    ${manifestation.carrier_type
                        ? `<span class="tag">${escapeHtml(manifestation.carrier_type)}</span>`
                        : ""}

                    ${manifestation.extent
                        ? `<span class="tag">${escapeHtml(manifestation.extent)}</span>`
                        : ""}

                </div>

                ${publishers.length
                    ? `<p><strong>Yayıncı:</strong>
                        ${publishers
                            .map(p => escapeHtml(p.name))
                            .join(", ")}
                       </p>`
                    : ""}

                ${renderItems(manifestation.items)}

            </div>
        `;
    }).join("");
}

function renderExpressions(expressions) {
    if (!expressions || expressions.length === 0) {
        return "";
    }

    return expressions.map(expression => `
        <div class="expression">

            <strong>Expression</strong>

            <div class="metadata">
                ${expression.language
                    ? `<span class="tag">Dil: ${escapeHtml(expression.language)}</span>`
                    : ""}

                ${expression.expression_form
                    ? `<span class="tag">Biçim: ${escapeHtml(expression.expression_form)}</span>`
                    : ""}
            </div>

            ${expression.description
                ? `<p>${escapeHtml(expression.description)}</p>`
                : ""}

            ${expression.agents && expression.agents.length
                ? `
                    <p><strong>Katkı sağlayan:</strong></p>
                    <div class="metadata">
                        ${renderAgents(expression.agents)}
                    </div>
                  `
                : ""}

            ${renderManifestations(expression.manifestations)}

        </div>
    `).join("");
}

function renderWork(work) {
    const authors = work.authors || [];
    const subjects = work.subjects || [];

    return `
        <article class="result-card">

            <h3>${escapeHtml(work.canonical_title)}</h3>

            ${work.original_title
                ? `<div class="original-title">
                    Özgün başlık: ${escapeHtml(work.original_title)}
                   </div>`
                : ""}

            <div class="metadata">

                ${authors.map(author => `
                    <span class="tag">
                        Yazar: ${escapeHtml(author.name)}
                    </span>
                `).join("")}

                ${subjects.map(subject => `
                    <span class="tag">
                        Konu: ${escapeHtml(subject.label)}
                    </span>
                `).join("")}

                ${work.original_language
                    ? `<span class="tag">
                        Özgün dil: ${escapeHtml(work.original_language)}
                       </span>`
                    : ""}

            </div>

            ${work.description
                ? `<p>${escapeHtml(work.description)}</p>`
                : ""}

            <div class="detail-section">
                <h4>Bibliyografik yapı</h4>
                ${renderExpressions(work.expressions)}
            </div>

        </article>
    `;
}

async function performSearch(query) {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
        return;
    }

    searchInput.value = cleanQuery;

    statusBox.textContent = `"${cleanQuery}" aranıyor...`;
    resultsBox.innerHTML = "";

    try {
        const response = await fetch(
            `/search?q=${encodeURIComponent(cleanQuery)}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (!data.results || data.results.length === 0) {
            statusBox.textContent =
                `"${cleanQuery}" için sonuç bulunamadı.`;
            return;
        }

        statusBox.textContent =
            `${data.count} kayıt bulundu.`;

        resultsBox.innerHTML =
            data.results.map(renderWork).join("");

    } catch (error) {
        console.error(error);

        statusBox.textContent =
            "Arama sırasında bir hata oluştu. API bağlantısını kontrol edin.";
    }
}

searchForm.addEventListener("submit", event => {
    event.preventDefault();
    performSearch(searchInput.value);
});

document.querySelectorAll("[data-query]").forEach(button => {
    button.addEventListener("click", () => {
        performSearch(button.dataset.query);
    });
});