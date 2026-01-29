export const analyzeLake = async (satelliteFiles, demFile, baseLevel, dates) => {
    const form = new FormData();

    // Check if satelliteFiles is an array or FileList, loop and append
    if (satelliteFiles) {
        if (satelliteFiles.length && typeof satelliteFiles[Symbol.iterator] === 'function') {
            for (let i = 0; i < satelliteFiles.length; i++) {
                form.append("satellite", satelliteFiles[i]);
            }
        } else {
            // Single file fallback
            form.append("satellite", satelliteFiles);
        }
    }

    if (demFile) {
        form.append("dem", demFile);
    }
    if (baseLevel) {
        form.append("base_level", baseLevel);
    }
    if (dates) {
        form.append("dates", dates);
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
        return data; // This will now be an array
    } catch (error) {
        console.error("Analysis failed:", error);
        throw error;
    }
};
