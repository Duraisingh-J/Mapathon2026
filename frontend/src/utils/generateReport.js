import jsPDF from "jspdf";
import html2canvas from "html2canvas";

export const generateReport = async (results, projectTitle = "Lake Kolavai (Default)") => {
    const doc = new jsPDF('p', 'mm', 'a4');
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const margin = 15;

    // Helper: Add centered text
    const centerText = (text, y, size = 12, style = "normal") => {
        doc.setFontSize(size);
        doc.setFont("helvetica", style);
        const textWidth = doc.getStringUnitWidth(text) * size / doc.internal.scaleFactor;
        const x = (pageWidth - textWidth) / 2;
        doc.text(text, x, y);
    };

    // Helper: Add section header
    const addSectionHeader = (title, y) => {
        doc.setFillColor(6, 182, 212); // Cyan-500
        doc.rect(margin, y, 4, 8, 'F');
        doc.setFontSize(14);
        doc.setFont("helvetica", "bold");
        doc.setTextColor(30, 41, 59); // Slate-800
        doc.text(title.toUpperCase(), margin + 8, y + 6);
        return y + 15;
    };

    // --- PAGE 1: EXECUTIVE SUMMARY ---

    // 1. Header with Logo placeholder
    doc.setFillColor(15, 23, 42); // Slate-900
    doc.rect(0, 0, pageWidth, 40, 'F');

    doc.setTextColor(255, 255, 255);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(22);
    doc.text("NEERPARIKSHA", margin, 20);

    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(148, 163, 184); // Slate-400
    doc.text("Advanced Geospatial Water Analytics", margin, 27);

    doc.setFontSize(10);
    doc.setTextColor(255, 255, 255);
    const dateStr = new Date().toLocaleDateString('en-US', { minute: '2-digit', hour: '2-digit', day: 'numeric', month: 'long', year: 'numeric' });
    doc.text(dateStr, pageWidth - margin - 50, 20);

    let cursorY = 55;

    // 2. Project Title
    centerText("AUTOMATED WATER SPREAD & VOLUME REPORT", cursorY, 18, "bold");
    cursorY += 10;
    centerText(`Project: ${projectTitle}`, cursorY, 12, "normal");

    cursorY += 20;

    // 3. Mission Statement / Context
    doc.setDrawColor(226, 232, 240); // Slate-200
    doc.setFillColor(248, 250, 252); // Slate-50
    doc.roundedRect(margin, cursorY, pageWidth - (margin * 2), 35, 3, 3, 'FD');

    doc.setFontSize(10);
    doc.setTextColor(71, 85, 105); // Slate-600
    const missionText = "This report provides a comprehensive analysis of the water body using satellite imagery and Digital Elevation Models (DEM). The data below supports environmental monitoring, resource management, and hydraulic capacity planning.";
    doc.text(doc.splitTextToSize(missionText, pageWidth - (margin * 2) - 10), margin + 5, cursorY + 10);

    cursorY += 45;

    // 4. Analysis Results Table
    cursorY = addSectionHeader("Hydrological Metrics", cursorY);

    // If multiple results, summarize the LATEST (first) one for the summary, or average?
    // Let's list all of them in a summary table.

    const headers = ["Date", "Spread Area (Ha)", "Volume @ Base (TMC)"];
    const colWidths = [50, 60, 60];
    let startX = margin;

    // Table Header
    // Table Header
    // doc.setFillColor(241, 245, 249); // Slate-100 -- Removing background for cleaner look? No, keep it.
    doc.setFillColor(6, 182, 212); // Cyan-500 header
    doc.rect(margin, cursorY, pageWidth - (2 * margin), 10, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);

    const headersTable = ["Date", "Spread Area (Ha)", "Volume (TMC)"];
    let colWidthsTable = [60, 60, 60];
    if (pageWidth > 200) colWidthsTable = [60, 60, 60]; // Simple fixed widths for A4

    let currentX = startX + 2;
    headersTable.forEach((h, i) => {
        doc.text(h, currentX, cursorY + 7);
        currentX += colWidthsTable[i];
    });

    cursorY += 10;

    // Table Data
    doc.setFont("helvetica", "normal");
    doc.setTextColor(51, 65, 85);

    if (Array.isArray(results)) {
        results.forEach((res, index) => {
            currentX = startX + 2;
            const date = res.date || `Dataset ${index + 1}`;
            const area = `${res.area_ha}`;

            // Fix: Use current volume to match dashboard
            const vol = res.volume_tmc ? `${res.volume_tmc}` : "0.00";

            const rowData = [date, area, vol];

            // Alternating row color
            if (index % 2 === 1) {
                doc.setFillColor(248, 250, 252);
                doc.rect(margin, cursorY, pageWidth - (2 * margin), 8, 'F');
            }

            rowData.forEach((d, i) => {
                doc.text(d, currentX, cursorY + 6);
                currentX += colWidths[i];
            });
            cursorY += 8;
        });
    }

    cursorY += 15;

    // 5. Chart Snapshot (If visible)
    // 5. Chart Snapshot (If visible)
    // We now have two charts: #area-chart and #volume-chart
    // 5. Chart Snapshot (If visible)
    // 5. Chart Snapshot (If visible)
    const captureChart = async (id, title) => {
        const element = document.querySelector(id);
        if (element) {

            // Check page break
            if (cursorY + 70 > pageHeight - margin) {
                doc.addPage();
                cursorY = margin + 10;
            }
            cursorY = addSectionHeader(title, cursorY);

            try {
                // DIRECT CAPTURE STRATEGY:
                // Modify the ACTUAL element temporarily to ensure it captures well.
                // We save original styles to restore later.
                const originalBackground = element.style.background;
                const originalBorder = element.style.borderRadius;

                // Force solid background for capture (Dark Mode friendly)
                element.style.background = '#0f172a';
                element.style.borderRadius = '0'; // Sharp corners for PDF

                // Wait a moment for style repaint
                await new Promise(r => setTimeout(r, 200));

                const canvas = await html2canvas(element, {
                    scale: 2,
                    backgroundColor: "#0f172a",
                    useCORS: true,
                    logging: false,
                    ignoreElements: (node) => node.tagName === 'NOSCRIPT'
                });

                // Restore original styles
                element.style.background = originalBackground;
                element.style.borderRadius = originalBorder;

                const imgData = canvas.toDataURL("image/png");
                const imgWidth = pageWidth - (2 * margin);
                const imgHeight = (canvas.height * imgWidth) / canvas.width;

                doc.addImage(imgData, 'PNG', margin, cursorY, imgWidth, imgHeight);
                cursorY += imgHeight + 10;
            } catch (e) {
                console.warn(`Failed to capture chart ${id}`, e);
            }
        }
    };

    // await captureChart("#area-chart", "Area Trends");
    // await captureChart("#volume-chart", "Volume Capacity Trends"); 

    // 6. Geospatial Maps
    // Helper to add image from URL
    const addRemoteImage = async (filename, title) => {
        if (!filename) return;

        if (cursorY + 120 > pageHeight - margin) {
            doc.addPage();
            cursorY = margin + 10;
        }

        cursorY = addSectionHeader(title, cursorY);

        const imgUrl = `http://localhost:8000/outputs/${filename}`;

        try {
            // Load image using an Image object to get dimensions
            const img = new Image();
            img.src = imgUrl;
            await new Promise((resolve, reject) => {
                img.onload = resolve;
                img.onerror = reject;
            });

            // Calculate aspect ratio
            const maxW = pageWidth - (2 * margin);
            const maxH = 120; // Max height on page

            let w = maxW;
            let h = (img.height * w) / img.width;

            if (h > maxH) {
                h = maxH;
                w = (img.width * h) / img.height;
            }

            // Center image
            const x = (pageWidth - w) / 2;

            doc.addImage(img, 'PNG', x, cursorY, w, h);
            cursorY += h + 10;

        } catch (err) {
            console.warn(`Failed to verify/load image ${filename}`, err);
        }
    };

    // Composite Map & Combined 3D Map
    // if (results.length > 0 && results[0].composite_map) { ... }

    // 3D Volume Map (Single Combined Map restored)
    if (results.length > 0 && results[0].combined_volume_map) {
        await addRemoteImage(results[0].combined_volume_map, "Multi-Temporal 3D Volumetric View");
    }

    // 7. Individual Analysis Breakdown
    if (results.length > 0) {
        doc.addPage();
        cursorY = margin + 10;
        cursorY = addSectionHeader("Detailed Analysis", cursorY);

        for (const res of results) {
            // Check usage
            if (cursorY + 80 > pageHeight - margin) {
                doc.addPage();
                cursorY = margin + 10;
            }

            // Title
            doc.setFontSize(10);
            doc.setFont("helvetica", "bold");
            doc.setTextColor(30);
            doc.text(`${res.filename} (${res.date})`, margin, cursorY);
            cursorY += 5;

            // Stats Row
            doc.setFontSize(9);
            doc.setFont("helvetica", "normal");
            const volText = res.volume_tmc ? `${res.volume_tmc} TMC` : "0 TMC";
            const areaText = `${res.area_ha} Ha`;
            doc.text(`Spread: ${areaText}   |   Volume: ${volText}`, margin, cursorY);
            cursorY += 5;

            // Image (Result Image or Verification Map)
            const imgFile = res.comparison_map || res.result_image;
            if (imgFile) {
                const imgUrl = `http://localhost:8000/outputs/${imgFile}`;
                try {
                    const img = new Image();
                    img.crossOrigin = "Anonymous";
                    img.src = imgUrl;
                    await new Promise((resolve, reject) => {
                        img.onload = resolve;
                        img.onerror = () => {
                            // Try fallback to comparison map if result image fails?
                            reject()
                        };
                    });

                    const maxW = pageWidth - (2 * margin);
                    const h = (img.height * maxW) / img.width;
                    // Limit height
                    let finalH = h;
                    let finalW = maxW;

                    if (finalH > 100) {
                        finalH = 100;
                        finalW = (img.width * finalH) / img.height;
                    }

                    doc.addImage(img, 'PNG', margin, cursorY, finalW, finalH);
                    cursorY += finalH + 10;

                } catch (e) {
                    doc.text("[Image Unavailable]", margin, cursorY + 10);
                    cursorY += 20;
                }
            } else {
                cursorY += 5;
            }



            cursorY += 5; // Spacing

            // Line separator
            doc.setDrawColor(200);
            doc.line(margin, cursorY, pageWidth - margin, cursorY);
            cursorY += 10;
        }
    }

    // --- Footer ---
    // --- Footer & Watermark ---
    const addFooterAndWatermark = (pageNo) => {
        // Watermark (Center, 36% Opacity)
        doc.setGState(new doc.GState({ opacity: 0.36 }));
        doc.addImage("/Logo.png", "PNG", (pageWidth - 80) / 2, (pageHeight - 80) / 2, 80, 80);
        doc.setGState(new doc.GState({ opacity: 1.0 })); // Reset opacity

        // Footer
        doc.setFontSize(8);
        doc.setTextColor(150);
        doc.text(`Generated by NeerPariksha | Page ${pageNo}`, margin, pageHeight - 10);
    };

    const pageCount = doc.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
        doc.setPage(i);
        addFooterAndWatermark(i);
    }

    // Save
    doc.save(`Water_Analysis_${new Date().toISOString().slice(0, 10)}.pdf`);
};
