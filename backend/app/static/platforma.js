const healthLight = document.getElementById("health-light");
const healthLabel = document.getElementById("health-label");
const healthDetail = document.getElementById("health-detail");
const checkedAt = document.getElementById("checked-at");
const apiVersion = document.getElementById("api-version");
const refreshButton = document.getElementById("health-refresh");

async function refreshHealth() {
    healthLight.className = "status-light checking";
    healthLabel.textContent = "Bağlantı denetleniyor";
    healthDetail.textContent = "LibraryHub API";
    refreshButton.disabled = true;

    try {
        const response = await fetch("/health", { cache: "no-store" });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        if (result.status !== "healthy" && result.status !== "ok") {
            throw new Error("API sağlıklı yanıt vermedi");
        }

        healthLight.className = "status-light online";
        healthLabel.textContent = "Servis çalışıyor";
        healthDetail.textContent = "LibraryHub API yanıt veriyor";
        apiVersion.textContent = result.version
            ? `API sürümü ${result.version}`
            : "API çalışır durumda";
    } catch (error) {
        healthLight.className = "status-light offline";
        healthLabel.textContent = "Servise ulaşılamıyor";
        healthDetail.textContent = error.message || "Bağlantı kurulamadı";
        apiVersion.textContent = "API şu anda yanıt vermiyor";
    } finally {
        checkedAt.textContent = new Intl.DateTimeFormat("tr-TR", {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(new Date());
        refreshButton.disabled = false;
    }
}

refreshButton.addEventListener("click", refreshHealth);
refreshHealth();