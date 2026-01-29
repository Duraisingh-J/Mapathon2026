import React from 'react';
import Button from './Button';

export default function Reports({ results }) {
    // Mock Data if no results
    const history = results || [
        { id: "REP-001", date: "2023-01-15", area: 450.2, volume: 1.2, status: "Completed" },
        { id: "REP-002", date: "2023-06-20", area: 320.5, volume: 0.8, status: "Completed" },
    ];

    return (
        <div className="max-w-4xl mx-auto space-y-8 animate-fade-in">
            <div className="flex items-center justify-between border-b border-slate-800 pb-6">
                <div>
                    <h2 className="text-2xl font-bold font-heading text-white">Analysis Reports</h2>
                    <p className="text-slate-400 text-sm mt-1">Access generated insights and export historical data.</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center border border-slate-700">
                    <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                </div>
            </div>

            <div className="glass-panel rounded-xl overflow-hidden border border-slate-800">
                <div className="p-6 border-b border-slate-800 flex justify-between items-center">
                    <h3 className="font-semibold text-white">Recent Analyses</h3>
                    <Button className="!w-auto !px-4 !py-2 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700">
                        Export CSV
                    </Button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="bg-slate-900/50 text-slate-400 text-xs uppercase tracking-wider">
                                <th className="px-6 py-4 font-semibold">Report ID</th>
                                <th className="px-6 py-4 font-semibold">Observation Date</th>
                                <th className="px-6 py-4 font-semibold">Area (Ha)</th>
                                <th className="px-6 py-4 font-semibold">Volume (TMC)</th>
                                <th className="px-6 py-4 font-semibold">Status</th>
                                <th className="px-6 py-4 font-semibold text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                            {Array.isArray(history) && history.map((item, idx) => (
                                <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                                    <td className="px-6 py-4 text-sm font-mono text-slate-300">
                                        {item.id || `REP-00${idx + 1}`}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-white">
                                        {item.date}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-slate-300">
                                        {item.area_ha || item.area}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-slate-300">
                                        {item.volume_tmc || item.volume}
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                            Completed
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <button className="text-cyan-400 hover:text-cyan-300 text-sm font-medium">Download</button>
                                    </td>
                                </tr>
                            ))}

                            {(!history || history.length === 0) && (
                                <tr>
                                    <td colSpan="6" className="px-6 py-12 text-center text-slate-500">
                                        No reports found. Run an analysis to generate data.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
