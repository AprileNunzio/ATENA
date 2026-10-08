import React, { useEffect, useState } from 'react';
import { Folder, X, MessageSquare } from 'lucide-react';

interface ProjectState {
    project_id: string;
    name: string;
    goal: string;
    status: string;
    chat_history: {user?: string, agent?: string}[];
}

export const ProjectWidget: React.FC = () => {
    const [project, setProject] = useState<ProjectState | null>(null);
    const [projectsList, setProjectsList] = useState<ProjectState[] | null>(null);
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        const ws = new WebSocket('wss://localhost:8443/bus-core');
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'telemetry' && data.sub_type === 'project_mode') {
                    if (data.payload.is_list) {
                        setProjectsList(data.payload.projects);
                        setProject(null);
                        setExpanded(true);
                    } else if (data.payload.status === 'ACTIVE' || data.payload.status === 'PENDING') {
                        setProject(data.payload as ProjectState);
                        setProjectsList(null);
                        if (!project) setExpanded(true);
                    } else {
                        setProject(null);
                        setProjectsList(null);
                        setExpanded(false);
                    }
                }
            } catch (e) {}
        };
        return () => ws.close();
    }, [project]);

    if (!project && (!projectsList || projectsList.length === 0)) return null;

    return (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
            {expanded && project && (
                <div className="bg-slate-900/95 backdrop-blur-xl border border-indigo-500/30 shadow-2xl shadow-black/50 rounded-2xl w-96 mb-4 overflow-hidden animate-fade-in flex flex-col">
                    <div className="bg-gradient-to-r from-indigo-900/60 to-slate-900/60 p-4 border-b border-slate-700/50 flex justify-between items-center">
                        <div className="min-w-0 pr-4">
                            <h3 className="font-['Rajdhani'] font-bold text-slate-100 flex items-center gap-2 text-lg">
                                <Folder className="w-5 h-5 text-indigo-400" />
                                <span className="truncate">{project.name}</span>
                            </h3>
                            <p className="text-xs text-indigo-200/70 truncate mt-1 font-mono">{project.goal}</p>
                        </div>
                        <button onClick={() => setExpanded(false)} className="text-slate-400 hover:text-white transition-colors p-1 bg-black/20 rounded-lg"><X className="w-4 h-4" /></button>
                    </div>
                    <div className="p-4 flex-1 h-72 overflow-y-auto custom-scrollbar space-y-4">
                        {project.chat_history.map((msg, i) => (
                            <div key={i} className={`flex ${msg.user ? 'justify-end' : 'justify-start'}`}>
                                <div className={`text-sm p-3 max-w-[85%] leading-relaxed ${msg.user ? 'bg-indigo-600 text-white rounded-2xl rounded-tr-sm shadow-md' : 'bg-slate-800/80 text-slate-200 rounded-2xl rounded-tl-sm border border-slate-700/50'}`}>
                                    {msg.user || msg.agent}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            {expanded && projectsList && !project && (
                <div className="bg-slate-900/95 backdrop-blur-xl border border-indigo-500/30 shadow-2xl shadow-black/50 rounded-2xl w-96 mb-4 overflow-hidden animate-fade-in flex flex-col">
                    <div className="bg-gradient-to-r from-indigo-900/60 to-slate-900/60 p-4 border-b border-slate-700/50 flex justify-between items-center">
                        <h3 className="font-['Rajdhani'] font-bold text-slate-100 flex items-center gap-2 text-lg">
                            <Folder className="w-5 h-5 text-indigo-400" /> Progetti Aperti ({projectsList.length})
                        </h3>
                        <button onClick={() => setExpanded(false)} className="text-slate-400 hover:text-white transition-colors p-1 bg-black/20 rounded-lg"><X className="w-4 h-4" /></button>
                    </div>
                    <div className="p-4 flex-1 max-h-72 overflow-y-auto custom-scrollbar space-y-3">
                        {projectsList.map((p, i) => (
                            <div key={i} className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                                <div className="font-bold text-indigo-300">{p.name}</div>
                                <div className="text-xs text-slate-400 mt-1">{p.goal}</div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            
            {!expanded && (
                <button 
                    onClick={() => setExpanded(true)}
                    className="bg-indigo-600 hover:bg-indigo-500 text-white p-3.5 rounded-full shadow-lg shadow-indigo-900/50 border border-indigo-400/30 transition-all flex items-center gap-3 animate-fade-in cursor-pointer group"
                >
                    <Folder className="w-5 h-5" />
                    <span className="font-['Rajdhani'] font-semibold pr-2 text-sm">Modalità Progetto</span>
                </button>
            )}
        </div>
    );
};
