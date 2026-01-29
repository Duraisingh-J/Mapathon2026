export const analyzeLake = async (satelliteFile, demFile) => {
    const form = new FormData();
    form.append("satellite", satelliteFile);
    if (demFile) {
        form.append("dem", demFile);
    }

    const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
    console.log("[DEBUG] Sending request to backend at:", API_URL);
    try {
        const res = await fetch(`${API_URL}/analyze`, {
            method: "POST",
            body: form,
        });

        console.log("[DEBUG] Response status:", res.status);

        if (!res.ok) {
            const errText = await res.text();
            console.error("[DEBUG] Error response:", errText);
            throw new Error(`Error: ${res.status} ${res.statusText} - ${errText}`);
        }

        const data = await res.json();
        console.log("[DEBUG] Response data:", data);
        return data;
    } catch (error) {
        console.error("Analysis failed:", error);
        throw error;
    }
};
