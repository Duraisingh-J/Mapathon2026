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
    doc.setFillColor(241, 245, 249); // Slate-100
    doc.rect(margin, cursorY, pageWidth - (2 * margin), 10, 'F');
    doc.setTextColor(15, 23, 42);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);

    let currentX = startX + 2;
    headers.forEach((h, i) => {
        doc.text(h, currentX, cursorY + 7);
        currentX += colWidths[i];
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
            // User requested: "only area and capacity @40 as volume"
            // So we show "volume_at_level_tmc" as the Volume column if available, 
            // otherwise fallback to calculated volume if they didn't provide base level.
            // But context implies they want the "Capacity" value there.
            const vol = res.volume_at_level_tmc
                ? `${res.volume_at_level_tmc}`
                : `${res.volume_tmc}`;

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

    await captureChart("#area-chart", "Area Trends");
    await captureChart("#volume-chart", "Volume Capacity Trends");


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
        doc.text(`Generated by NeerPariksha AI | Page ${pageNo}`, margin, pageHeight - 10);
    };

    const pageCount = doc.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
        doc.setPage(i);
        addFooterAndWatermark(i);
    }

    // Save
    doc.save(`Water_Analysis_${new Date().toISOString().slice(0, 10)}.pdf`);
};
