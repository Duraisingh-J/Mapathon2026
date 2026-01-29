export default function Header() {
    return (
        <header className="fixed top-0 left-0 right-0 z-50 glass-panel border-b-0">
            <div className="container mx-auto px-6 h-20 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                    <img src="/Logo.png" alt="NeerPariksha" className="w-10 h-10 object-contain drop-shadow-[0_0_10px_rgba(34,211,238,0.3)]" />
                    <div className="flex flex-col">
                        <span className="text-xl font-bold font-heading tracking-tight text-white">
                            NEER<span className="text-cyan-400">PARIKSHA</span>
                        </span>
                        <span className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold">
                            Advanced Water Resource Analytics
                        </span>
                    </div>
                </div>
                <nav>
                    <a href="#" className="text-sm font-medium text-slate-400 hover:text-cyan-400 transition-colors px-4 py-2 hover:bg-white/5 rounded-lg">
                        Documentation
                    </a>
                </nav>
            </div>
        </header>
    );
}
