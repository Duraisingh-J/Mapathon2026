import { useState, useEffect, useCallback } from "react";
import FileInput from "./FileInput";
import Button from "./Button";
import ResultCard from "./ResultCard";
import { analyzeLake } from "../services/api";
import { generateReport } from "../utils/generateReport";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts';

// Icons
const UploadIcon = (props) => (
    <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
    </svg>
);

const MapIcon = (props) => (
    <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
    </svg>
);

const AreaIcon = (props) => (
    <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
    </svg>
);

const VolumeIcon = (props) => (
    <svg {...props} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10l-2 1m0 0l-2-1m2 1v2.5M20 7l-2 1m2-1l-2-1m2 1v2.5M14 4l-2-1-2 1M4 7l2-1M4 7l2 1M4 7v2.5M12 21l-2-1m2 1l2-1m-2 1v-2.5M6 18l-2-1v-2.5M18 18l2-1v-2.5" />
    </svg>
);

const ErrorIcon = (props) => (
    <svg {...props} viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
        <line x1="12" y1="8" x2="12" y2="12" strokeWidth="2"></line>
        <line x1="12" y1="16" x2="12.01" y2="16" strokeWidth="2"></line>
    </svg>
);

import FileManager from "./FileManager";
import { API_URL } from "../config";

// ... existing imports

export default function Dashboard() {
    const [satelliteData, setSatelliteData] = useState([]); // [{ file, date, id }]
    const [dem, setDem] = useState(null); // Now might be object similar to satelliteData item or just file? 
    // Let's keep logic simple: FileManager returns array. For dem (single), we take items[0]?.file

    const [baseLevel, setBaseLevel] = useState(() => localStorage.getItem("neer_default_level") || "");
    // const [dates, setDates] = useState(""); 
    // const [sat, setSat] = useState(null); 

    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [error, setError] = useState(null);

    // Load defaults from Settings
    useEffect(() => {
        const savedLevel = localStorage.getItem("neer_default_level");
        if (savedLevel) setBaseLevel(savedLevel);
    }, []);

    const handleDownload = async () => {
        if (!result) return;
        setDownloading(true);
        try {
            const projectTitle = localStorage.getItem("neer_project_name") || "Lake Kolavai (Default)";
            await generateReport(result, projectTitle);
        } catch (err) {
            console.error(err);
            setError("Failed to generate report.");
        } finally {
            setDownloading(false);
        }
    };

    const submit = async () => {
        if (satelliteData.length === 0) {
            alert("Please add at least one satellite image.");
            setError("Please add at least one satellite image.");
            return;
        }

        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const files = satelliteData.map(item => item.file);
            const dateString = satelliteData.map(item => item.date).join(",");

            // DEBUG ALERT - Removed to prevent blocking UI
            // alert(`Sending ${files.length} files to backend...`);

            const data = await analyzeLake(files, dem, baseLevel, dateString);
            console.log("Analysis Result:", data);

            if (data.error) {
                setError(data.error);
                setResult(null); // Clear previous results to avoid stale/bad state
            } else if (!data || (Array.isArray(data) && data.length === 0)) {
                alert("Backend returned no results.");
                setError("Analysis completed but returned no results. Please check input files.");
                setResult(null);
            } else {
                setResult(data);
                console.log("Analysis Success:", data);
            }
        } catch (err) {
            console.error(err);
            alert("Frontend Error: " + err.message);
            setError(err.message || "Failed to analyze data.");
        } finally {
            setLoading(false);
        }
    };

    // Callback handlers to prevent infinite render loops in FileManager
    const handleSatelliteChange = useCallback((items) => {
        setSatelliteData(items);
        // Only clear result if the user is actively changing files, which usually implies a new analysis is needed.
        // However, if this fires on mount due to default state, we must be careful.
        // FileManager returns formatted items. It might fire on init. 
        // We shouldn't clear result aggressively unless we know it's a user action.
        // For now, let's clear to be safe, assuming useCallback fixes the loop.
        setResult(null);
        setError(null);
    }, []);

    const handleDemChange = useCallback((items) => {
        setDem(items[0] ? items[0].file : null);
        setError(null);
    }, []);

    return (
        <div className="space-y-8 animate-fade-in pb-10">
            {/* TOP SECTION: CONTROLS & COMPOSITE MAP */}
            {/* Added details: items-stretch to make columns equal height */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">

                {/* LEFT: CONTROLS */}
                {/* flex flex-col to allow inner panel to grow if needed, though sticky usually limits it. 
                    User asked to "extend" input section. We'll make the glass-panel full height */ }
                <div className="lg:col-span-4 flex flex-col">
                    <div className="glass-panel p-5 rounded-lg border border-slate-800 bg-slate-900/80 sticky top-4 h-full">
                        <div className="flex items-center justify-between mb-6 border-b border-slate-800 pb-4">
                            <h2 className="text-sm font-bold font-heading text-white uppercase tracking-widest flex items-center">
                                <span className="w-1.5 h-4 bg-cyan-500 rounded-sm mr-2"></span>
                                Analysis Controls
                            </h2>
                            <div className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-400 font-mono">v2.1</div>
                        </div>

                        <div className="space-y-5">
                            <FileManager
                                label="Satellite Imagery"
                                accept=".tif,.tiff"
                                multiple={true}
                                showDate={true}
                                icon={UploadIcon}
                                onDataChange={handleSatelliteChange}
                            />

                            <FileManager
                                label="DEM File (Required for Volume)"
                                accept=".tif,.tiff"
                                multiple={false}
                                showDate={false}
                                icon={MapIcon}
                                onDataChange={handleDemChange}
                            />

                            <div className="group">
                                <label className="block text-xs font-bold text-slate-500 mb-1.5 uppercase tracking-wide group-hover:text-cyan-400 transition-colors">
                                    Base Level (m)
                                </label>
                                <div className="relative">
                                    <input
                                        type="number"
                                        step="0.1"
                                        placeholder="e.g. 100"
                                        value={baseLevel}
                                        onChange={(e) => setBaseLevel(e.target.value)}
                                        className="w-full pl-3 pr-16 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 placeholder-slate-600 text-sm focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all font-mono"
                                    />
                                    {/* Adjusted position: top-1/2 -translate-y-1/2 for perfect center */}
                                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-600 font-semibold pointer-events-none">METERS</span>
                                </div>
                            </div>

                            <Button
                                onClick={submit}
                                disabled={loading}
                                className="w-full h-10 mt-2 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-sm tracking-wide rounded border-0 shadow-lg shadow-cyan-900/20"
                            >
                                {loading ? (
                                    <span className="flex items-center justify-center space-x-2">
                                        <img src="/Logo.png" className="w-5 h-5 animate-pulse object-contain" alt="Loading" />
                                        <span>PROCESSING...</span>
                                    </span>
                                ) : (
                                    <span>RUN ANALYSIS</span>
                                )}
                            </Button>

                            {error && (
                                <div className="p-3 rounded bg-red-900/20 border border-red-900/30 flex items-start space-x-2 text-red-400 text-xs mt-2">
                                    <ErrorIcon className="w-4 h-4 flex-shrink-0 mt-0.5" />
                                    <span>{error}</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* RIGHT: COMPOSITE MAP (Or Placeholder) */}
                <div className="lg:col-span-8">
                    {/* Header for Results */}
                    {result && (
                        <div className="flex items-center justify-between bg-slate-900/50 p-4 rounded-lg border-b border-slate-800 mb-6">
                            <h3 className="text-lg font-bold font-heading text-white flex items-center">
                                <span className="w-2 h-2 bg-emerald-500 rounded-full mr-3 shadow-[0_0_10px_rgba(16,185,129,0.5)]"></span>
                                Overview
                            </h3>
                            <Button
                                onClick={handleDownload}
                                disabled={downloading}
                                className="!w-auto !py-1.5 !px-3 text-xs bg-emerald-600 hover:bg-emerald-500 border-0 rounded font-semibold uppercase tracking-wide"
                            >
                                {downloading ? "Generating..." : "Download Report"}
                            </Button>
                        </div>
                    )}

                    {!result ? (
                        <div className="h-[500px] flex flex-col items-center justify-center border-2 border-dashed border-slate-800 rounded-xl bg-slate-900/30">
                            <div className="w-20 h-20 rounded-full bg-slate-800 flex items-center justify-center mb-6 shadow-inner">
                                <svg className="w-10 h-10 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                                </svg>
                            </div>
                            <h3 className="text-xl font-bold font-heading text-slate-500 mb-2">Awaiting Data</h3>
                            <p className="text-slate-600 max-w-sm text-center text-sm">
                                Select input files to begin.
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Composite Map */}
                            {Array.isArray(result) && result.length > 0 && result[0].composite_map && (
                                <div className="glass-panel p-2 rounded-lg border border-slate-700 bg-slate-900 shadow-lg">
                                    <div className="p-3 border-b border-slate-800 mb-2 flex justify-between items-center">
                                        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                                            Multi-Temporal Composite Map
                                        </h4>
                                        <span className="text-[10px] text-cyan-500 bg-cyan-900/20 px-2 py-0.5 rounded border border-cyan-900/30">Boundary Overlay</span>
                                    </div>
                                    <div className="flex justify-center bg-white p-2 rounded">
                                        <img
                                            src={`${API_URL}/outputs/${result[0].composite_map}`}
                                            alt="Composite Map"
                                            className="max-h-[500px] w-auto object-contain"
                                        />
                                    </div>
                                </div>
                            )}

                            {/* 3D Volume Map */}
                            {Array.isArray(result) && result.length > 0 && result[0].volume_map_3d && (
                                <div className="glass-panel p-2 rounded-lg border border-slate-700 bg-slate-900 shadow-lg mt-6">
                                    <div className="p-3 border-b border-slate-800 mb-2 flex justify-between items-center">
                                        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                                            3D Volumetric Analysis
                                        </h4>
                                        <span className="text-[10px] text-purple-500 bg-purple-900/20 px-2 py-0.5 rounded border border-purple-900/30">Terrain + Water Levels</span>
                                    </div>
                                    <div className="flex justify-center bg-white p-2 rounded">
                                        <img
                                            src={`${API_URL}/outputs/${result[0].combined_volume_map}`}
                                            alt="3D Volume Map"
                                            className="max-h-[500px] w-auto object-contain"
                                        />
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>



            {/* MIDDLE SECTION: GRAPHS (Full Width) */}
            {result && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Chart 1: Area */}
                    <div id="area-chart" className="glass-panel p-6 rounded-lg border border-slate-800">
                        <h4 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-6 border-b border-slate-800 pb-2 flex justify-between items-center">
                            <span>Spread Area vs Date</span>
                            <span className="text-[10px] text-cyan-500 bg-cyan-900/20 px-2 py-1 rounded">Visual Metric</span>
                        </h4>
                        <div className="w-full h-[350px]">
                            <ResponsiveContainer width="100%" height={350}>
                                <LineChart data={result} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />

                                    {/* Base Area Reference Line */}
                                    {result.length > 0 && (
                                        <ReferenceLine
                                            y={result[0].area_ha}
                                            label={{ value: 'BASE', fill: '#ef4444', fontSize: 10, position: 'insideTopRight' }}
                                            stroke="#ef4444"
                                            strokeDasharray="3 3"
                                            opacity={0.5}
                                        />
                                    )}

                                    <XAxis
                                        dataKey="filename"
                                        stroke="#64748b"
                                        tick={({ x, y, payload }) => {
                                            if (!payload || !payload.value) return null;
                                            const val = payload.value;
                                            const chunks = val.match(/.{1,10}/g) || [val];
                                            return (
                                                <g transform={`translate(${x},${y})`}>
                                                    <text x={0} y={0} dy={10} textAnchor="middle" fill="#64748b" fontSize={10}>
                                                        {chunks.map((chunk, i) => (
                                                            <tspan x={0} dy={i === 0 ? 0 : 10} key={i}>{chunk}</tspan>
                                                        ))}
                                                    </text>
                                                </g>
                                            );
                                        }}
                                        tickLine={false}
                                        axisLine={false}
                                        interval={0}
                                        height={60}
                                    />
                                    <YAxis stroke="#06b6d4" tick={{ fill: '#06b6d4', fontSize: 10 }} tickLine={false} axisLine={false} label={{ value: 'Ha', angle: -90, position: 'insideLeft', fill: '#06b6d4', fontSize: 10 }} />
                                    <Tooltip
                                        content={({ active, payload, label }) => {
                                            if (active && payload && payload.length) {
                                                const data = payload[0].payload;
                                                const isBase = data.id.endsWith("_0"); // Assuming first is base
                                                return (
                                                    <div className="bg-slate-900 border border-slate-700 p-3 rounded shadow-xl">
                                                        <p className="text-xs text-slate-400 font-mono mb-1">{label}</p>
                                                        <p className="text-lg font-bold text-white">
                                                            {data.area_ha} <span className="text-xs text-slate-500">Ha</span>
                                                        </p>
                                                        <div className="mt-1 pt-1 border-t border-slate-800">
                                                            <p className={`text-xs font-bold ${data.pct_change > 0 ? "text-emerald-400" : (data.pct_change < 0 ? "text-red-400" : "text-slate-500")}`}>
                                                                {isBase ? "BASE IMAGE" : `${data.pct_change > 0 ? "+" : ""}${data.pct_change}% vs Base`}
                                                            </p>
                                                            <p className="text-[10px] text-slate-500 mt-0.5">
                                                                Vol: {data.volume_tmc} TMC
                                                            </p>
                                                        </div>
                                                    </div>
                                                );
                                            }
                                            return null;
                                        }}
                                        labelFormatter={(label, payload) => payload[0]?.payload?.date ? `${label} (${payload[0].payload.date})` : label}
                                    />
                                    <Legend />
                                    <Line
                                        type="monotone"
                                        dataKey="area_ha"
                                        stroke="#06b6d4"
                                        name="Area (Ha)"
                                        strokeWidth={3}
                                        dot={{ r: 5, fill: '#06b6d4', stroke: '#fff', strokeWidth: 2 }}
                                        activeDot={{ r: 8 }}
                                        isAnimationActive={false}
                                    />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Chart 2: Volume */}
                    <div id="volume-chart" className="glass-panel p-6 rounded-lg border border-slate-800">
                        <h4 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-6 border-b border-slate-800 pb-2 flex justify-between items-center">
                            <span>Volume vs Date</span>
                            <span className="text-[10px] text-emerald-500 bg-emerald-900/20 px-2 py-1 rounded">Hydrologic Metric</span>
                        </h4>
                        <div className="w-full h-[350px]">
                            <ResponsiveContainer width="100%" height={350}>
                                <LineChart data={result} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                    <XAxis
                                        dataKey="filename"
                                        stroke="#64748b"
                                        tick={{ fill: '#64748b', fontSize: 10 }}
                                        tickLine={false}
                                        axisLine={false}
                                        dy={10}
                                        tickFormatter={(val) => val.length > 15 ? val.substring(0, 15) + '...' : val}
                                    />
                                    <YAxis
                                        type="number"
                                        stroke="#10b981"
                                        tick={{ fill: '#10b981', fontSize: 10 }}
                                        tickLine={false}
                                        axisLine={false}
                                        label={{ value: 'TMC', angle: -90, position: 'insideLeft', fill: '#10b981', fontSize: 10 }}
                                        domain={['auto', 'auto']}
                                        tickFormatter={(val) => parseFloat(val).toFixed(2)}
                                    />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#10b981', borderRadius: '4px' }}
                                        itemStyle={{ color: '#fff' }}
                                        cursor={{ stroke: '#10b981', strokeWidth: 1 }}
                                    />
                                    <Legend />
                                    <Line
                                        type="monotone"
                                        dataKey="volume_tmc"
                                        stroke="#10b981"
                                        name="Volume (TMC)"
                                        strokeWidth={3}
                                        dot={{ r: 5, fill: '#10b981', stroke: '#fff', strokeWidth: 2 }}
                                        activeDot={{ r: 8 }}
                                        isAnimationActive={false}
                                    />
                                    {result.length > 0 && result[0].base_level && (
                                        <ReferenceLine
                                            y={result[0].volume_at_level_tmc}
                                            label={{
                                                value: `Capacity @ ${result[0].base_level}m`,
                                                fill: '#64748b',
                                                fontSize: 10,
                                                position: 'insideTopRight'
                                            }}
                                            stroke="#64748b"
                                            strokeDasharray="3 3"
                                        />
                                    )}
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            )}



            {/* BOTTOM SECTION: DETAILED CARDS */}
            {result && (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                    {Array.isArray(result) ? result.map((res, idx) => (
                        <div key={idx} className="glass-panel p-5 rounded-lg border-l-[3px] border-l-cyan-600 bg-slate-900 border border-slate-800 relative shadow-xl">
                            <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-2">
                                {/* Removed truncate and max-w to show full filename */}
                                <div className="flex flex-col">
                                    <span className="text-white font-mono font-bold text-xs break-all" title={res.filename}>
                                        {res.filename || `DATASET ${idx + 1}`}
                                    </span>
                                </div>
                                <span className="text-[10px] text-slate-500 font-mono tracking-tighter">
                                    {res.date}
                                </span>
                            </div>

                            <div className="space-y-3">
                                <ResultCard
                                    title="Spread"
                                    value={res.area_ha}
                                    unit="Ha"
                                    icon={AreaIcon}
                                    color="cyan"
                                    subText={res.pct_change != 0 ? `${res.pct_change > 0 ? "+" : ""}${res.pct_change}% vs Base` : (idx === 0 ? "Base Image" : "No Change")}
                                    subColor={res.pct_change > 0 ? "text-emerald-400" : (res.pct_change < 0 ? "text-red-400" : "text-slate-500")}
                                />

                                <ResultCard
                                    title="Volume"
                                    value={res.volume_tmc}
                                    unit="TMC"
                                    icon={VolumeIcon}
                                    color="emerald"
                                />

                                {res.water_level && (
                                    <div className="text-right -mt-2 mb-2 mr-2">
                                        <span className="text-[10px] text-slate-500 font-mono">
                                            Detected Level: {res.water_level}m
                                        </span>
                                    </div>
                                )}

                                {(res.comparison_map || res.result_image) && (
                                    <div className="mt-4 border border-slate-800 rounded overflow-hidden">
                                        <div className="bg-slate-800 px-2 py-1 text-[10px] text-slate-400 font-bold uppercase tracking-wider flex justify-between">
                                            <span>{res.comparison_map ? "Comparison (Base vs Current)" : "Water Extraction"}</span>
                                        </div>
                                        <img
                                            src={`${API_URL}/outputs/${res.comparison_map || res.result_image}`}
                                            alt="Analysis Map"
                                            className="w-full h-auto object-cover opacity-90 hover:opacity-100 transition-opacity"
                                        />
                                    </div>
                                )}
                            </div>
                        </div>
                    )) : null}
                </div>
            )}
        </div>
    );

}
