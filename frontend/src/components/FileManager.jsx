import { useState, useEffect } from "react";
import FileInput from "./FileInput";

export default function FileManager({
    label = "Files",
    accept,
    multiple = true,
    showDate = true,
    onDataChange,
    icon: Icon
}) {
    // Items: { id: string, file: File, date?: string }
    const [items, setItems] = useState([]);

    // Notify parent whenever items change
    useEffect(() => {
        onDataChange(items);
    }, [items, onDataChange]);

    const handleAddFiles = (e) => {
        if (!e.target.files) return;
        const newFiles = Array.from(e.target.files);

        const newItems = newFiles.map(file => ({
            id: Math.random().toString(36).substr(2, 9),
            file: file,
            date: showDate ? new Date().toISOString().split('T')[0] : null // Default to today if showing date
        }));

        if (multiple) {
            setItems(prev => [...prev, ...newItems]);
        } else {
            // Single file mode: Replace existing
            setItems(newItems.slice(0, 1)); // Ensure only one
        }
    };

    const handleRemove = (id) => {
        setItems(prev => prev.filter(item => item.id !== id));
    };

    const handleDateChange = (id, newDate) => {
        setItems(prev => prev.map(item =>
            item.id === id ? { ...item, date: newDate } : item
        ));
    };

    return (
        <div className="space-y-4">
            {/* ADD TRIGGER */}
            {/* If single file mode and we already have a file, hide the input? Or change label to 'Replace'? 
                User said "make the input... for the dem also". 
                Let's keep the input visible so they can swap, but maybe change text if occupied.
                Actually FileInput handles the UI.
            */}
            <FileInput
                label={label}
                accept={accept}
                multiple={multiple}
                onChange={handleAddFiles}
                icon={Icon}
                showPreview={false}
            />

            {/* FILE LIST */}
            {items.length > 0 && (
                <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                        Selected {multiple ? "Files" : "File"} ({items.length})
                    </p>
                    <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-slate-700">
                        {items.map(item => (
                            <div key={item.id} className="flex items-center gap-3 bg-slate-900 border border-slate-800 p-2 rounded-lg group hover:border-slate-700 transition-colors animate-fade-in">
                                {/* Icon */}
                                <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center text-slate-500 flex-shrink-0">
                                    {Icon ? <Icon className="w-4 h-4" /> : (
                                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                        </svg>
                                    )}
                                </div>

                                {/* Details */}
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm text-slate-300 truncate font-medium" title={item.file.name}>
                                        {item.file.name}
                                    </p>
                                    <p className="text-[10px] text-slate-500">
                                        {(item.file.size / (1024 * 1024)).toFixed(2)} MB
                                    </p>
                                </div>

                                {/* Date Input - Only if showDate is true */}
                                {showDate && (
                                    <div>
                                        <input
                                            type="date"
                                            value={item.date}
                                            onChange={(e) => handleDateChange(item.id, e.target.value)}
                                            className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white focus:border-cyan-500 outline-none w-[110px]"
                                        />
                                    </div>
                                )}

                                {/* Remove Button */}
                                <button
                                    onClick={() => handleRemove(item.id)}
                                    className="p-1.5 rounded-full text-slate-500 hover:text-red-400 hover:bg-slate-800 transition-colors"
                                    title="Remove file"
                                >
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
