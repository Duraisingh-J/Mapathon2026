import { useState, useEffect } from "react";
import Header from './Header';

export default function Layout({ children, activeTab, onNavigate }) {
    const [title, setTitle] = useState("Lake Kolavai (Default)");

    useEffect(() => {
        // Sync title with settings
        const savedProject = localStorage.getItem("neer_project_name");
        if (savedProject) setTitle(savedProject);
    }, [activeTab]); // Update when tab changes to catch settings updates

    const navItems = [
        {
            id: 'dashboard', label: 'Dashboard', icon: (
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-9v9a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>
            )
        },
        {
            id: 'reports', label: 'Reports', icon: (
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
            )
        },
        {
            id: 'settings', label: 'Settings', icon: (
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            )
        }
    ];

    return (
        <div className="flex h-screen bg-slate-950 text-slate-200 overflow-hidden font-sans selection:bg-cyan-500/30">
            {/* Sidebar (Visual Only for now) */}
            <aside className="w-16 lg:w-64 bg-slate-900 border-r border-slate-800 flex flex-col items-center lg:items-start py-6 transition-all duration-300 z-20">
                <div className="px-4 mb-8 w-full flex items-center justify-center lg:justify-start">
                    <img src="/Logo.png" alt="NeerPariksha" className="w-10 h-10 object-contain drop-shadow-[0_0_15px_rgba(34,211,238,0.5)]" />
                    <span className="ml-3 font-heading font-bold text-lg text-white hidden lg:block tracking-tight">NEER<span className="text-cyan-400">PARIKSHA</span></span>
                </div>

                <nav className="flex-1 w-full px-2 space-y-1">
                    {navItems.map(item => (
                        <button
                            key={item.id}
                            onClick={() => onNavigate && onNavigate(item.id)}
                            className={`w-full flex items-center px-4 py-3 rounded-lg transition-all group ${activeTab === item.id
                                ? "bg-slate-800/80 text-cyan-400 border-r-2 border-cyan-400 shadow-lg shadow-black/20"
                                : "text-slate-500 hover:text-slate-200 hover:bg-slate-800"
                                }`}
                        >
                            {item.icon}
                            <span className="ml-3 font-medium text-sm hidden lg:block">{item.label}</span>
                        </button>
                    ))}
                </nav>
            </aside>

            {/* Main Content Info */}
            <div className="flex-1 flex flex-col h-full overflow-hidden relative">
                {/* Slim Header */}
                <header className="h-16 bg-slate-900/50 border-b border-slate-800 flex items-center justify-between px-8 backdrop-blur-md z-10">
                    <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">
                        Project: <span className="text-white">{title}</span>
                    </h2>
                    <div className="flex items-center space-x-4">
                        <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                        <span className="text-xs font-mono text-emerald-400">SYSTEM ONLINE</span>
                    </div>
                </header>

                {/* Scrollable Workspace */}
                <main className="flex-1 overflow-y-auto p-6 lg:p-10 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
                    <div className="max-w-[1600px] mx-auto">
                        {children}
                    </div>
                </main>
            </div>
        </div>
    );
}
