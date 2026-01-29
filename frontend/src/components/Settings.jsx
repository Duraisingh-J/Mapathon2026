import { useState, useEffect } from "react";
import Button from "./Button";

export default function Settings() {
    const [projectName, setProjectName] = useState("Lake Kolavai (Default)");
    const [defaultBaseLevel, setDefaultBaseLevel] = useState("100");
    const [themeMode, setThemeMode] = useState("deep-ocean");

    useEffect(() => {
        const savedProject = localStorage.getItem("neer_project_name");
        if (savedProject) setProjectName(savedProject);

        const savedLevel = localStorage.getItem("neer_default_level");
        if (savedLevel) setDefaultBaseLevel(savedLevel);
    }, []);

    const handleSave = () => {
        localStorage.setItem("neer_project_name", projectName);
        localStorage.setItem("neer_default_level", defaultBaseLevel);
        alert("Settings Saved!");
    };

    return (
        <div className="max-w-2xl mx-auto space-y-8 animate-fade-in">
            <div className="flex items-center justify-between border-b border-slate-800 pb-6">
                <div>
                    <h2 className="text-2xl font-bold font-heading text-white">System Settings</h2>
                    <p className="text-slate-400 text-sm mt-1">Configure global application parameters and defaults.</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center border border-slate-700">
                    <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                </div>
            </div>

            <div className="glass-panel p-6 rounded-xl border border-slate-800 space-y-6">
                <div>
                    <h3 className="text-lg font-semibold text-white mb-4">Project Configuration</h3>
                    <div className="grid gap-6">
                        <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-400 uppercase tracking-wide">Default Project Name</label>
                            <input
                                type="text"
                                value={projectName}
                                onChange={(e) => setProjectName(e.target.value)}
                                className="w-full px-4 py-3 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-cyan-500 transition-colors"
                            />
                            <p className="text-xs text-slate-500">This name will appear in the dashboard header and generated reports.</p>
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-400 uppercase tracking-wide">Default Base Level (Meters)</label>
                            <input
                                type="number"
                                value={defaultBaseLevel}
                                onChange={(e) => setDefaultBaseLevel(e.target.value)}
                                className="w-full px-4 py-3 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-cyan-500 transition-colors"
                            />
                            <p className="text-xs text-slate-500">Pre-fill this value in the analysis dashboard.</p>
                        </div>
                    </div>
                </div>

                <div className="pt-6 border-t border-slate-800">
                    <h3 className="text-lg font-semibold text-white mb-4">Interface Preferences</h3>
                    <div className="flex items-center space-x-4">
                        <button className="px-4 py-2 rounded-lg bg-cyan-900/20 border border-cyan-500/50 text-cyan-400 text-sm font-medium">Deep Ocean (Active)</button>
                        <button className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-500 text-sm font-medium opacity-50 cursor-not-allowed">Light Mode (Coming Soon)</button>
                    </div>
                </div>
            </div>

            <div className="flex justify-end">
                <Button onClick={handleSave} className="bg-emerald-600 hover:bg-emerald-500 text-white px-8">
                    Save Changes
                </Button>
            </div>
        </div>
    );
}
