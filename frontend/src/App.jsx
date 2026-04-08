import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Shield, Zap, RotateCcw, Plus, Clock, ChevronRight, AlertCircle, CheckCircle2, Calendar, Send, Loader2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

import Timeline from './components/Timeline';
import HistoryPanel from './components/HistoryPanel';

const API_BASE = "";



function App() {
  const [tasks, setTasks] = useState([]);
  const [history, setHistory] = useState([]);
  const [isShieldActive, setIsShieldActive] = useState(true);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [newTask, setNewTask] = useState({ title: '', time: '10:00' });

  useEffect(() => {
    fetchTasks();
    fetchHistory();
  }, []);

  const fetchTasks = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/tasks`);
      setTasks(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("Task fetch failed", err);
      setTasks([]);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/history`);
      setHistory(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("History fetch failed", err);
      setHistory([]);
    }
  };

  const loadData = async () => {
    await fetchTasks();
    await fetchHistory();
  };

  const handleRecover = async (e, directMessage = null) => {
    if (e) e.preventDefault();
    const messageToUse = directMessage || input;
    if (!messageToUse.trim() || !isShieldActive) return;
    
    console.log("Sending disruption:", messageToUse);
    setIsLoading(true);

    try {
      await fetch(`${API_BASE}/api/recover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messageToUse }),
      });

      if (!directMessage) setInput('');
      await loadData();
    } catch (err) {
      console.error("Recovery failed", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddTask = async (e) => {
    if (e) e.preventDefault(); 
    if (!newTask.title.trim()) return;

    try {
      // Calculate end_time (start_time + 1 hour)
      const [hours, minutes] = newTask.time.split(':').map(Number);
      const endHours = (hours + 1) % 24;
      const endTime = `${String(endHours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;

      await axios.post(`${API_BASE}/api/tasks`, {
        title: newTask.title,
        start_time: newTask.time,
        end_time: endTime
      });
      setNewTask({ title: '', time: '10:00' });
      await fetchTasks();
      await fetchHistory();
    } catch (err) {
      console.error("Task add failed", err);
    }
  };

  const handleUndo = async () => {
    setIsLoading(true);
    try {
      await axios.post(`${API_BASE}/api/undo`);
      await fetchTasks();
      await fetchHistory();
    } catch (err) {
      console.error("Undo failed", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 font-sans selection:bg-accent-blue/30 overflow-hidden relative">
      {/* Neural Background */}
      <div className="fixed inset-0 pointer-events-none opacity-20">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-accent-blue/20 rounded-full blur-[120px] animate-pulse" />
      </div>

      {/* Header */}
      <header className="h-16 border-b border-white/5 flex items-center justify-between px-6 bg-black/40 backdrop-blur-md z-40">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-accent-blue/10 rounded-xl border border-accent-blue/20">
            <Zap size={20} className="text-accent-blue" />
          </div>
          <h1 className="text-sm font-black tracking-[0.3em] uppercase">
            DISRUPTIONSHIELD <span className="text-zinc-600 font-medium">COORDINATOR</span>
          </h1>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isShieldActive ? 'bg-accent-blue animate-pulse' : 'bg-zinc-700'}`} />
            <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
              {isShieldActive ? 'SHIELD: ACTIVE' : 'SHIELD: STANDBY'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button 
              onClick={handleUndo}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors text-zinc-400 hover:text-zinc-100"
              title="Reverse Last Neural Shift"
            >
              <RotateCcw size={18} />
            </button>
            <button 
              onClick={() => setIsShieldActive(!isShieldActive)}
              className={`p-2 rounded-lg transition-all duration-300 ${isShieldActive ? 'bg-accent-blue/10 text-accent-blue border border-accent-blue/20' : 'bg-zinc-900 text-zinc-600 border border-transparent'}`}
            >
              <Shield size={18} className={isShieldActive ? 'fill-accent-blue/20' : ''} />
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        {/* Left Panel: Controls */}
        <aside className="w-80 border-r border-white/5 flex flex-col bg-black/20 backdrop-blur-md">
          <div className="p-6 flex-1 overflow-y-auto space-y-8 custom-scrollbar">
            
            {/* Disruption Detection Section */}
            <section>
              <div className="flex items-center gap-2 mb-4">
                <AlertCircle size={14} className="text-orange-500" />
                <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Disruption Detection</h2>
              </div>
              <div className="space-y-4">
                <form onSubmit={handleRecover} className="relative group">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Type disruption (e.g., 'traffic jam')..."
                    className="w-full bg-white/[0.03] border border-white/10 rounded-xl py-3 pl-4 pr-12 text-sm focus:outline-none focus:border-accent-blue/50 transition-all placeholder:text-zinc-600"
                  />
                  <button type="submit" disabled={isLoading || !isShieldActive} className="absolute right-2 top-1.5 p-1.5 bg-accent-blue rounded-lg text-black hover:scale-105 transition-transform active:scale-95 shadow-lg shadow-accent-blue/20">
                    {isLoading ? <Loader2 size={18} className="animate-spin" /> : <ChevronRight size={18} strokeWidth={2.5} />}
                  </button>
                </form>

                <div className="grid grid-cols-2 gap-2">
                  {['TRAFFIC', 'POWER', 'MEETING', 'EMERGENCY'].map((tag) => (
                    <button
                      key={tag}
                      onClick={() => { 
                        const msg = tag.toLowerCase();
                        setInput(msg); 
                        // Directly trigger recovery logic
                        handleRecover(null, msg); 
                      }}
                      className="py-2.5 rounded-lg bg-white/[0.02] border border-white/5 text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200 hover:border-white/10 transition-all"
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            {/* Quick Add Task */}
            <section className="pt-8 border-t border-white/5">
              <div className="flex items-center gap-2 mb-4">
                <Plus size={14} className="text-accent-blue" />
                <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Dispatch Task</h2>
              </div>
              <form onSubmit={handleAddTask} className="space-y-3">
                <input
                  type="text"
                  value={newTask.title}
                  onChange={(e) => setNewTask({...newTask, title: e.target.value})}
                  placeholder="Task title..."
                  className="w-full bg-white/[0.03] border border-white/10 rounded-xl py-3 px-4 text-sm focus:outline-none focus:border-accent-blue/50 transition-all"
                />
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <Clock className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" size={14} />
                    <input
                      type="time"
                      value={newTask.time}
                      onChange={(e) => setNewTask({...newTask, time: e.target.value})}
                      className="w-full bg-white/[0.03] border border-white/10 rounded-xl py-3 pl-10 pr-4 text-sm focus:outline-none focus:border-accent-blue/50 transition-all color-scheme-dark"
                    />
                  </div>
                  <button type="submit" className="p-3 bg-white/[0.03] border border-white/10 rounded-xl text-zinc-400 hover:text-accent-blue hover:border-accent-blue/30 transition-all">
                    <Plus size={20} />
                  </button>
                </div>
              </form>
            </section>
          </div>

          <div className="p-6 bg-black/40 border-t border-white/5">
                <div className="p-4 rounded-2xl bg-accent-blue/5 border border-accent-blue/10 relative overflow-hidden group">
                  <div className="absolute top-0 right-0 p-3 opacity-20 transition-opacity">
                    <Shield size={40} className="text-accent-blue" />
                  </div>
                  <h4 className="text-[10px] font-black uppercase tracking-widest text-accent-blue mb-1">Protection Status</h4>
                  <p className="text-xs font-bold text-zinc-100 mb-2">SYNAPTIC SHIELD: ENABLED</p>
                  <p className="text-[9px] leading-relaxed text-zinc-500 font-medium uppercase tracking-tight">
                    Real-time AI monitoring active. All detected disruptions will trigger autonomous schedule recovery.
                  </p>
                </div>
          </div>
        </aside>

        {/* Center Panel: Timeline */}
        <section className="flex-1 h-full border-r border-white/5">
          <Timeline tasks={tasks} />
        </section>

        {/* Right Panel: History */}
        <aside className="w-80 h-full overflow-hidden">
          <HistoryPanel logs={history} />
        </aside>
      </main>

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.1); }
        .text-accent-blue { color: #3b82f6; }
        .bg-accent-blue { background-color: #3b82f6; }
        .border-accent-blue { border-color: #3b82f6; }
        input[type="time"]::-webkit-calendar-picker-indicator {
          filter: invert(0.5) sepia(1) saturate(5) hue-rotate(175deg);
        }
      `}} />
    </div>
  );
}

export default App;
