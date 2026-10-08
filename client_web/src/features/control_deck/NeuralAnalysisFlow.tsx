import React, { useEffect, useState } from 'react';
import { Brain, Activity, ArrowRight, Code } from 'lucide-react';

export interface TelemetryEvent {
    id: string;
    sub_type: 'swarm_handoff' | 'agent_thought' | 'tool_execution' | 'critique_feedback';
    agent_id: string;
    timestamp: number;
    payload: Record<string, any>;
}

export const NeuralAnalysisFlow: React.FC = () => {
    const [events, setEvents] = useState<TelemetryEvent[]>([]);

    useEffect(() => {
        const ws = new WebSocket('wss://localhost:8443/bus-core');
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'telemetry') {
                    setEvents(prev => [{ ...data, id: crypto.randomUUID() }, ...prev].slice(0, 100));
                }
            } catch (e) {}
        };
        return () => ws.close();
    }, []);

    const renderIcon = (type: string) => {
        switch (type) {
            case 'swarm_handoff': return <ArrowRight className="w-4 h-4 text-purple-400" />;
            case 'agent_thought': return <Brain className="w-4 h-4 text-cyan-400" />;
            case 'tool_execution': return <Code className="w-4 h-4 text-amber-400" />;
            default: return <Activity className="w-4 h-4 text-slate-400" />;
        }
    };

    return (
        <div className="w-full bg-slate-900/60 border border-slate-800 rounded-2xl p-5 backdrop-blur-md flex flex-col h-96">
            <h2 className="font-['Rajdhani'] text-lg font-semibold text-slate-100 mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-indigo-400" />
                Flusso Analisi Futuristico (Neural Telemetry)
            </h2>
            <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
                {events.map((ev) => (
                    <div key={ev.id} className="bg-black/40 border border-slate-800/80 p-3 rounded-xl flex gap-3 animate-fade-in">
                        <div className="mt-1 p-1.5 rounded-lg bg-slate-800/50 border border-slate-700/50 h-fit">
                            {renderIcon(ev.sub_type)}
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="flex justify-between items-start mb-1">
                                <span className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">{ev.agent_id}</span>
                                <span className="text-[10px] font-mono text-slate-500">{new Date(ev.timestamp * 1000).toLocaleTimeString()}</span>
                            </div>
                            {ev.sub_type === 'agent_thought' && (
                                <p className="text-xs text-cyan-300/90 font-mono leading-relaxed border-l-2 border-cyan-500/30 pl-2">
                                    {ev.payload.thought}
                                </p>
                            )}
                            {ev.sub_type === 'swarm_handoff' && (
                                <p className="text-xs text-purple-300/90 flex items-center gap-2">
                                    Handoff a <span className="font-bold">{ev.payload.to}</span>: {ev.payload.reason}
                                </p>
                            )}
                            {ev.sub_type === 'tool_execution' && (
                                <div className="text-[11px] font-mono bg-slate-950 p-2 rounded border border-slate-800 text-amber-300/80 mt-1 truncate">
                                    [EXEC] {ev.payload.tool} - {ev.payload.status} ({ev.payload.detail})
                                </div>
                            )}
                        </div>
                    </div>
                ))}
                {events.length === 0 && (
                    <div className="h-full flex items-center justify-center text-slate-500 text-xs font-mono animate-pulse">
                        In attesa di telemetria neurale...
                    </div>
                )}
            </div>
        </div>
    );
};
