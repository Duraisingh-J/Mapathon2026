
import { useState } from "react";

export default function FileInput({ label, onChange, accept, icon: Icon, multiple, showPreview = true }) {
    const [files, setFiles] = useState([]);

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            const selectedFiles = Array.from(e.target.files);
            setFiles(selectedFiles);
            // If we are not showing preview, we might want to clear internal state 
            // after bubbling up, so the input is "fresh" for next add? 
            // Actually, if multiple=true and we want "incremental" in the parent,
            // the parent will handle the accumulation. 
            // This component just reports "change".
        } else {
            setFiles([]);
        }
        onChange(e);

        // Reset input value to allow selecting same file again if needed (common in incremental)
        e.target.value = "";
    }

    return (
        <div className="relative group/input">
            <label className="block text-xs font-bold text-slate-500 mb-1.5 uppercase tracking-wide group-hover/input:text-cyan-400 transition-colors">
                {label}
            </label>
            <div className="relative">
                <input
                    type="file"
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
                    onChange={handleFileChange}
                    accept={accept}
                    multiple={multiple}
                />
                <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 flex items-center justify-between hover:border-cyan-500/50 transition-colors group-hover/input:bg-slate-800">
                    <div className="flex items-center space-x-3 overflow-hidden">
                        <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center text-slate-400 group-hover/input:text-cyan-400">
                            {Icon ? <Icon className="w-4 h-4" /> : (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                </svg>
                            )}
                        </div>
                        <div className="flex-1 min-w-0">
                            {files.length > 0 && showPreview ? (
                                <p className="text-sm text-emerald-400 font-medium truncate">
                                    {files.length} file{files.length > 1 ? 's' : ''} selected
                                </p>
                            ) : (
                                <p className="text-sm text-slate-500 truncate group-hover/input:text-slate-300">
                                    {multiple ? "Add files..." : "Select file..."}
                                </p>
                            )}
                        </div>
                    </div>

                    <div className="px-3 py-1 bg-slate-800 rounded text-xs font-semibold text-slate-500 uppercase group-hover/input:bg-slate-700 group-hover/input:text-slate-300 transition-colors">
                        Browse
                    </div>
                </div>
            </div>
        </div>
    );
}
