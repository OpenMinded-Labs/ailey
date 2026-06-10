"use client";
import React, { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { loader } from '@monaco-editor/react';
import {
  ChevronRight, ChevronDown, File, Folder, FolderOpen, Plus, Trash2, RefreshCw,
  X, Send, Loader2, ArrowLeft, Save, BookOpen, PenTool, Eye, Moon, Sun,
  MessageCircle, PanelRightClose, PanelRight, FolderPlus, FilePlus,
  Edit3, Download, Sparkles, Camera, BookMarked, FileText, BarChart3,
  ChevronUp, Settings, Search, Type, AlignLeft, Lightbulb, Wand2,
  Library, Upload, Brain, Zap
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

// ── Configure Monaco to use local bundle ────────────────────────────────
loader.config({ paths: { vs: '/monaco/vs' } });

const MonacoEditor = dynamic(() => import('@monaco-editor/react').then(m => m.default), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex flex-col items-center justify-center text-sm text-foreground/30 gap-2">
      <div className="h-5 w-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      <span>Editor lädt…</span>
    </div>
  )
});

// ── Constants ────────────────────────────────────────────────────────────
const API_BASE = typeof window !== 'undefined'
  ? (() => {
      const h = window.location.hostname;
      if (!h || h === 'tauri.localhost' || h === 'localhost' || h === '127.0.0.1') return 'http://127.0.0.1:5502';
      return `http://${h}:5502`;
    })()
  : '';

// ── Types ────────────────────────────────────────────────────────────────
interface FileNode { name: string; path: string; is_dir: boolean; children?: FileNode[]; size?: number; }
interface OpenTab { path: string; name: string; content: string; dirty: boolean; }
interface ChatMsg { id: string; role: 'user' | 'ai'; content: string; ts: number; pending?: boolean; }
interface ProjectMeta {
  title: string; subtitle?: string; author?: string; genre?: string;
  language?: string; status?: string; word_count_target?: number;
  chapters?: { file: string; title?: string; word_count?: number }[];
  characters?: { name: string; description?: string }[];
  notes?: string;
}
interface ProjectInfo { name: string; path: string; title?: string; genre?: string; status?: string; word_count?: number; }
interface Stats {
  total_words: number; total_chars: number; word_count_target: number;
  reading_time_minutes: number; chapters: { file: string; word_count: number; char_count: number }[];
}
interface Snapshot { file: string; path: string; timestamp: string; size: number; }

// ── API helper ───────────────────────────────────────────────────────────
async function api(path: string, opts?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, opts);
  if (!r.ok) return { success: false, error: `HTTP ${r.status}` };
  try { return await r.json(); } catch { return { success: false, error: 'Invalid JSON' }; }
}

// ── File-type colors ─────────────────────────────────────────────────────
function getFileColor(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  if (ext === 'md') return 'text-primary';
  if (ext === 'txt') return 'text-foreground/60';
  if (ext === 'json') return 'text-emerald-400';
  return 'text-foreground/40';
}

// ══════════════════════════════════════════════════════════════════════════
// AILEY AUTHOR MODE — Prosa-Schreibmodus
// ══════════════════════════════════════════════════════════════════════════
export default function AuthorModePage() {
  const router = useRouter();

  // ── Theme (synced with main app) ───────────────────────────────────────
  const uiToEditor: Record<string, 'ailey-author-dark'|'ailey-author-cyber'|'ailey-author-light'> = {
    dark: 'ailey-author-dark', cyber: 'ailey-author-cyber', light: 'ailey-author-light', ailey: 'ailey-author-dark'
  };
  const editorToUi: Record<string, 'dark'|'cyber'|'light'> = {
    'ailey-author-dark': 'dark', 'ailey-author-cyber': 'cyber', 'ailey-author-light': 'light'
  };
  const [uiTheme, setUiTheme] = useState<'dark'|'cyber'|'light'|'rainbowpunk'|'ailey'>(() => {
    if (typeof window !== 'undefined') {
      const v = localStorage.getItem('ailey-ui-theme');
      if (v && ['dark','light','cyber','rainbowpunk','ailey'].includes(v)) return v as any;
    }
    return 'dark';
  });
  const editorThemeName = uiToEditor[uiTheme] || 'ailey-author-dark';
  const isCyber = uiTheme === 'cyber';

  useEffect(() => {
    document.documentElement.classList.toggle('dark', uiTheme !== 'light');
    document.documentElement.classList.toggle('cyber', uiTheme === 'cyber');
    document.documentElement.classList.toggle('rainbowpunk', uiTheme === 'rainbowpunk');
    // Ailey theme in Author mode → Steampunk sub-theme
    document.documentElement.classList.toggle('steampunk', uiTheme === 'ailey');
    document.documentElement.classList.remove('ailey-mood');
    document.documentElement.removeAttribute('data-ailey-mood');
  }, [uiTheme]);

  // ── Activate/deactivate author mode (freezes LifeSim needs) ──
  useEffect(() => {
    fetch(`${API_BASE}/api/author/mode`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({active: true}) }).catch(() => {});
    return () => { fetch(`${API_BASE}/api/author/mode`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({active: false}) }).catch(() => {}); };
  }, []);

  function toggleTheme() {
    const order: Array<'dark'|'cyber'|'rainbowpunk'|'ailey'|'light'> = ['dark','cyber','rainbowpunk','ailey','light'];
    const idx = order.indexOf(uiTheme);
    const next = order[(idx + 1) % order.length];
    setUiTheme(next);
    localStorage.setItem('ailey-ui-theme', next);
    document.documentElement.classList.toggle('dark', next !== 'light');
    document.documentElement.classList.toggle('cyber', next === 'cyber');
    document.documentElement.classList.toggle('rainbowpunk', next === 'rainbowpunk');
    document.documentElement.classList.toggle('steampunk', next === 'ailey');
    document.documentElement.classList.remove('ailey-mood');
    document.documentElement.removeAttribute('data-ailey-mood');
    // Also switch Monaco theme
    if (monacoRef.current) {
      monacoRef.current.editor.setTheme(uiToEditor[next] || 'ailey-author-dark');
    }
  }

  // ── State ──────────────────────────────────────────────────────────────
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [activeProjectName, setActiveProjectName] = useState('');
  const [projectMeta, setProjectMeta] = useState<ProjectMeta | null>(null);
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [fileTreeLoading, setFileTreeLoading] = useState(false);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());

  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);

  // KI Chat
  const [chatVisible, setChatVisible] = useState(true);
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([
    { id: 'welcome', role: 'ai', content: 'Hey! ✍️ Ich bin Ailey im **Autoren-Modus**. Ich kann dir beim Schreiben helfen — weiterschreiben, lektorieren, brainstormen. Wähl einen Modus und leg los!', ts: Date.now() }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [chatMode, setChatMode] = useState<'fragen' | 'weiterschreiben' | 'lektorat' | 'brainstorm' | 'recherche'>('fragen');

  // Author generation settings (token limits)
  const [authorGenSettings, setAuthorGenSettings] = useState<Record<string,number>>({author_write:1500, author_review:1000});
  const authorGenLoaded = useRef(false);
  async function loadAuthorGenSettings() {
    try {
      const r = await fetch(`${API_BASE}/api/admin/generation-settings`);
      if (r.ok) { const j = await r.json(); if (j.success) { setAuthorGenSettings(prev => ({...prev, ...j.settings})); authorGenLoaded.current = true; } }
    } catch {}
  }
  async function updateAuthorGenSetting(key: string, value: number) {
    setAuthorGenSettings(prev => ({...prev, [key]: value}));
    try { await fetch(`${API_BASE}/api/admin/generation-settings`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({[key]: value}) }); } catch {}
  }
  useEffect(() => { if (!authorGenLoaded.current) loadAuthorGenSettings(); }, []);
  const [authorSettingsOpen, setAuthorSettingsOpen] = useState(false);

  // Stats
  const [stats, setStats] = useState<Stats | null>(null);
  const [showStats, setShowStats] = useState(false);

  // Snapshots
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [snapshotBusy, setSnapshotBusy] = useState(false);

  // Project creation
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectTitle, setNewProjectTitle] = useState('');
  const [newProjectGenre, setNewProjectGenre] = useState('');
  const [deletingProject, setDeletingProject] = useState<string | null>(null);

  // File operations
  const [newFileName, setNewFileName] = useState('');
  const [newFileDir, setNewFileDir] = useState<string | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');

  // Side panel
  const [sidePanel, setSidePanel] = useState<'explorer' | 'stats' | 'snapshots' | 'knowledge'>('explorer');

  // ── Mobile responsiveness ─────────────────────────────────────────────
  const [isMobile, setIsMobile] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileChatOpen, setMobileChatOpen] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      setIsMobile(e.matches);
      if (e.matches) setChatVisible(false);
    };
    handler(mq);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Knowledge Base (Project-RAG)
  const [ragDocuments, setRagDocuments] = useState<{source:string; title:string; doc_type:string; chunks:number; total_chars:number}[]>([]);
  const [ragDocsLoading, setRagDocsLoading] = useState(false);
  const [ragUploading, setRagUploading] = useState(false);
  const [ragUploadMsg, setRagUploadMsg] = useState('');
  const ragUploadRef = useRef<HTMLInputElement>(null);
  const [ragSearchQuery, setRagSearchQuery] = useState('');
  const [ragSearchResults, setRagSearchResults] = useState<{text:string; source:string; title:string; score:number}[]>([]);
  const [ragSearching, setRagSearching] = useState(false);
  // Auto-Notes (Qwen Coder analysis)
  const [autoNotes, setAutoNotes] = useState<any>(null);
  const [autoNotesLoading, setAutoNotesLoading] = useState(false);
  const [autoNotesEnabled, setAutoNotesEnabled] = useState(true);
  const lastAnalysisRef = useRef<number>(0);

  // Refs
  const chatEndRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const autosaveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const openTabsRef = useRef(openTabs);

  useEffect(() => { openTabsRef.current = openTabs; }, [openTabs]);

  // ── Word count for current tab ─────────────────────────────────────────
  const currentTab = openTabs.find(t => t.path === activeTab);
  const currentWordCount = currentTab ? currentTab.content.split(/\s+/).filter(Boolean).length : 0;
  const currentCharCount = currentTab ? currentTab.content.length : 0;

  // ── Autosave ───────────────────────────────────────────────────────────
  async function autosaveAll(): Promise<boolean> {
    const dirty = openTabs.filter(t => t.dirty);
    if (dirty.length === 0) return true;
    try {
      const r = await api('/api/author/autosave', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: dirty.map(t => ({ path: t.path, content: t.content })) })
      });
      if (r.success && r.saved?.length) {
        const savedSet = new Set(r.saved as string[]);
        setOpenTabs(prev => prev.map(t => savedSet.has(t.path) ? { ...t, dirty: false } : t));
        return true;
      }
    } catch {}
    return false;
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────
  useEffect(() => {
    loadProjects();
    // Autosave every 30s
    autosaveTimerRef.current = setInterval(() => {
      const dirty = openTabsRef.current.filter(t => t.dirty);
      if (dirty.length > 0) {
        fetch(`${API_BASE}/api/author/autosave`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ files: dirty.map(t => ({ path: t.path, content: t.content })) }),
        }).then(r => r.json()).then(r => {
          if (r.success && r.saved?.length) {
            const savedSet = new Set(r.saved as string[]);
            setOpenTabs(prev => prev.map(t => savedSet.has(t.path) ? { ...t, dirty: false } : t));
          }
        }).catch(() => {});
      }
    }, 30000);
    return () => { if (autosaveTimerRef.current) clearInterval(autosaveTimerRef.current); };
  }, []);

  // ── Projects ───────────────────────────────────────────────────────────
  async function loadProjects() {
    try {
      const r = await api('/api/author/projects');
      if (r.success) setProjects(r.projects || []);
    } catch {}
  }

  async function createProject() {
    if (!newProjectName.trim()) return;
    const r = await api('/api/author/projects', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newProjectName.trim(), title: newProjectTitle || newProjectName, genre: newProjectGenre })
    });
    if (r.success) {
      setShowNewProject(false);
      setNewProjectName(''); setNewProjectTitle(''); setNewProjectGenre('');
      loadProjects();
      openProject(r.project.path, r.project.name);
    }
  }

  async function deleteProject(path: string, name: string) {
    if (!confirm(`Schreibprojekt "${name}" wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`)) return;
    setDeletingProject(path);
    try {
      const r = await api('/api/author/projects', {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      if (r && r.success) {
        loadProjects();
        if (activeProject === path) { setActiveProject(null); setActiveProjectName(''); setOpenTabs([]); setActiveTab(null); }
      } else {
        alert(r?.error || 'Löschen fehlgeschlagen');
      }
    } catch { } finally {
      setDeletingProject(null);
    }
  }

  async function openProject(path: string, name?: string) {
    const pName = name || path.split('/').pop() || '';
    setActiveProject(path);
    setActiveProjectName(pName);
    setOpenTabs([]);
    setActiveTab(null);
    loadFileTree(path);
    loadMeta(pName);
    loadStats(pName);
    loadSnapshots(pName);
  }

  // ── Meta ───────────────────────────────────────────────────────────────
  async function loadMeta(name: string) {
    try {
      const r = await api(`/api/author/meta/${name}`);
      if (r.success) setProjectMeta(r.meta);
    } catch {}
  }

  // ── Stats ──────────────────────────────────────────────────────────────
  async function loadStats(name: string) {
    try {
      const r = await api(`/api/author/stats/${name}`);
      if (r.success) setStats(r);
    } catch {}
  }

  // ── Snapshots ──────────────────────────────────────────────────────────
  async function loadSnapshots(name: string) {
    try {
      const r = await api(`/api/author/snapshots/${name}`);
      if (r.success) setSnapshots(r.snapshots || []);
    } catch {}
  }

  async function createSnapshot() {
    if (!activeProjectName || snapshotBusy) return;
    setSnapshotBusy(true);
    await autosaveAll();
    const r = await api(`/api/author/snapshot/${activeProjectName}`, { method: 'POST' });
    if (r.success) loadSnapshots(activeProjectName);
    setSnapshotBusy(false);
  }

  // ── File Tree ──────────────────────────────────────────────────────────
  async function loadFileTree(projectPath?: string) {
    const name = projectPath ? projectPath.split('/').pop() : activeProjectName;
    if (!name) return;
    setFileTreeLoading(true);
    try {
      const r = await api(`/api/author/tree/${name}`);
      if (r.success) setFileTree(r.tree || []);
    } catch {}
    setFileTreeLoading(false);
  }

  function toggleDir(path: string) {
    setExpandedDirs(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }

  // ── File Operations ────────────────────────────────────────────────────
  async function openFile(node: FileNode) {
    if (node.is_dir) { toggleDir(node.path); return; }
    const existing = openTabs.find(t => t.path === node.path);
    if (existing) { setActiveTab(node.path); return; }
    try {
      const r = await api(`/api/author/file?path=${encodeURIComponent(node.path)}`);
      if (r.success) {
        const tab: OpenTab = { path: node.path, name: node.name, content: r.content || '', dirty: false };
        setOpenTabs(prev => [...prev, tab]);
        setActiveTab(node.path);
      }
    } catch {}
  }

  async function saveFile(path: string) {
    const tab = openTabs.find(t => t.path === path);
    if (!tab) return;
    const r = await api('/api/author/file', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content: tab.content })
    });
    if (r.success) {
      setOpenTabs(prev => prev.map(t => t.path === path ? { ...t, dirty: false } : t));
      if (activeProjectName) loadStats(activeProjectName);
      // Trigger Qwen auto-analysis in background after save
      if (autoNotesEnabled && tab.name.endsWith('.md')) {
        setTimeout(triggerAutoAnalysis, 500);
      }
    }
  }

  async function createFile(dir: string, name: string) {
    if (!name.trim()) return;
    const fullPath = dir ? `${dir}/${name.trim()}` : `${activeProject}/${name.trim()}`;
    const r = await api('/api/author/file', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: fullPath })
    });
    if (r.success) {
      loadFileTree();
      setNewFileName(''); setNewFileDir(null);
      setOpenTabs(prev => [...prev, { path: fullPath, name: name.trim(), content: r.content || '', dirty: false }]);
      setActiveTab(fullPath);
    }
  }

  async function createFolder(dir: string, name: string) {
    if (!name.trim()) return;
    const fullPath = dir ? `${dir}/${name.trim()}` : `${activeProject}/${name.trim()}`;
    await api('/api/author/mkdir', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: fullPath })
    });
    loadFileTree();
    setNewFileName(''); setNewFileDir(null);
  }

  async function deleteFile(path: string) {
    if (!confirm(`"${path.split('/').pop()}" wirklich löschen?`)) return;
    await api('/api/author/file', {
      method: 'DELETE', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    setOpenTabs(prev => prev.filter(t => t.path !== path));
    if (activeTab === path) setActiveTab(openTabs.find(t => t.path !== path)?.path || null);
    loadFileTree();
  }

  async function renameFile(oldPath: string, newName: string) {
    if (!newName.trim()) { setRenamingPath(null); return; }
    const dir = oldPath.substring(0, oldPath.lastIndexOf('/'));
    const newPath = `${dir}/${newName.trim()}`;
    const r = await api('/api/author/rename', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_path: oldPath, new_path: newPath })
    });
    if (r.success) {
      setOpenTabs(prev => prev.map(t => t.path === oldPath ? { ...t, path: r.new_path, name: newName.trim() } : t));
      if (activeTab === oldPath) setActiveTab(r.new_path);
      loadFileTree();
    }
    setRenamingPath(null); setRenameValue('');
  }

  function closeTab(path: string, e?: React.MouseEvent) {
    e?.stopPropagation();
    setOpenTabs(prev => prev.filter(t => t.path !== path));
    if (activeTab === path) {
      const remaining = openTabs.filter(t => t.path !== path);
      setActiveTab(remaining.length > 0 ? remaining[remaining.length - 1].path : null);
    }
  }

  function onEditorChange(value: string | undefined) {
    if (!activeTab || value === undefined) return;
    setOpenTabs(prev => prev.map(t => t.path === activeTab ? { ...t, content: value, dirty: true } : t));
  }

  // ── Knowledge Base (Project-RAG) Functions ─────────────────────────────
  async function loadRagDocuments() {
    if (!activeProjectName) return;
    setRagDocsLoading(true);
    try {
      const r = await api(`/api/author/rag/${activeProjectName}/documents`);
      if (r.success) setRagDocuments(r.documents || []);
    } catch {} finally { setRagDocsLoading(false); }
  }

  async function handleRagUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; if (!file || !activeProjectName) return;
    setRagUploading(true); setRagUploadMsg('');
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await fetch(`${API_BASE}/api/author/rag/${activeProjectName}/upload`, { method: 'POST', body: form });
      const j = await r.json();
      if (j.success) {
        setRagUploadMsg(`✓ ${j.filename}: ${j.chunks} Chunks`);
        loadRagDocuments();
      } else { setRagUploadMsg(j.error || 'Fehler'); }
    } catch (err: any) { setRagUploadMsg(err?.message || 'Fehler'); }
    finally { setRagUploading(false); if (ragUploadRef.current) ragUploadRef.current.value = ''; }
  }

  async function deleteRagDocument(source: string) {
    if (!activeProjectName || !confirm(`"${source}" aus Wissensbasis entfernen?`)) return;
    try {
      const r = await api(`/api/author/rag/${activeProjectName}/document`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source }) });
      if (r.success) loadRagDocuments();
    } catch {}
  }

  async function searchRag() {
    if (!ragSearchQuery.trim() || !activeProjectName) return;
    setRagSearching(true);
    try {
      const r = await api(`/api/author/rag/${activeProjectName}/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: ragSearchQuery, limit: 5 }) });
      if (r.success) setRagSearchResults(r.results || []);
    } catch {} finally { setRagSearching(false); }
  }

  async function loadAutoNotes() {
    if (!activeProjectName) return;
    setAutoNotesLoading(true);
    try {
      const r = await api(`/api/author/rag/${activeProjectName}/notes`);
      if (r.success && r.notes?.length > 0) {
        // Get the latest analysis
        const latest = r.notes[r.notes.length - 1];
        setAutoNotes(latest?.analysis || null);
      }
    } catch {} finally { setAutoNotesLoading(false); }
  }

  async function triggerAutoAnalysis() {
    const tab = openTabs.find(t => t.path === activeTab);
    if (!tab || !activeProjectName || !autoNotesEnabled) return;
    // Rate-limit: max once every 30 seconds
    if (Date.now() - lastAnalysisRef.current < 30000) return;
    lastAnalysisRef.current = Date.now();
    setAutoNotesLoading(true);
    try {
      const r = await api(`/api/author/rag/${activeProjectName}/auto-analyze`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: tab.content, filename: tab.name, mode: 'full' }),
      });
      if (r.success && r.notes) setAutoNotes(r.notes);
    } catch {} finally { setAutoNotesLoading(false); }
  }

  // Load RAG docs when knowledge panel opens
  useEffect(() => {
    if (sidePanel === 'knowledge' && activeProjectName) {
      loadRagDocuments();
      loadAutoNotes();
    }
  }, [sidePanel, activeProjectName]);

  // ── Leave Author Mode ─────────────────────────────────────────────────
  async function leaveAuthorMode() {
    const dirty = openTabs.filter(t => t.dirty);
    if (dirty.length > 0) {
      const saved = await autosaveAll();
      if (!saved && !confirm(`Ungespeicherte Änderungen. Trotzdem verlassen?`)) return;
    }
    router.push('/');
  }

  // ── KI Chat ────────────────────────────────────────────────────────────
  async function sendChat() {
    const msg = chatInput.trim();
    const tab = openTabs.find(t => t.path === activeTab);

    // For weiterschreiben/lektorat, we can send without a message
    if (!msg && !['weiterschreiben', 'lektorat'].includes(chatMode)) return;
    if (chatBusy) return;

    const userContent = msg || (chatMode === 'weiterschreiben' ? '→ Weiterschreiben' : '→ Lektorat');
    const userMsg: ChatMsg = { id: `u${Date.now()}`, role: 'user', content: userContent, ts: Date.now() };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setChatBusy(true);

    const pendingMsg: ChatMsg = { id: `p${Date.now()}`, role: 'ai', content: '', ts: Date.now(), pending: true };
    setChatMessages(prev => [...prev, pendingMsg]);

    try {
      const r = await fetch(`${API_BASE}/api/author/ai/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          mode: chatMode,
          text_context: tab ? tab.content : '',
          project_name: activeProjectName,
          filename: tab?.name || '',
        })
      });
      const j = await r.json();
      const reply = j.reply || j.error || 'Keine Antwort';
      setChatMessages(prev => prev.map(m =>
        m.id === pendingMsg.id ? { ...m, content: reply, pending: false } : m
      ));

      // If "weiterschreiben", offer to insert text into editor
      if (chatMode === 'weiterschreiben' && j.success && j.reply && tab) {
        // Auto-insert at cursor / end of file
        const editor = editorRef.current;
        if (editor) {
          const model = editor.getModel();
          if (model) {
            const pos = editor.getPosition() || { lineNumber: model.getLineCount(), column: 1 };
            const lastLine = model.getLineCount();
            const lastCol = model.getLineMaxColumn(lastLine);
            editor.executeEdits('ailey-author', [{
              range: { startLineNumber: lastLine, startColumn: lastCol, endLineNumber: lastLine, endColumn: lastCol },
              text: '\n\n' + j.reply,
              forceMoveMarkers: true,
            }]);
            // Mark dirty
            setOpenTabs(prev => prev.map(t => t.path === activeTab ? { ...t, content: model.getValue(), dirty: true } : t));
          }
        }
      }
    } catch (e: any) {
      setChatMessages(prev => prev.map(m =>
        m.id === pendingMsg.id ? { ...m, content: `⚠️ ${e?.message || 'Fehler'}`, pending: false } : m
      ));
    }
    setChatBusy(false);
    setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
  }

  // ── Keyboard shortcuts ─────────────────────────────────────────────────
  useEffect(() => {
    function handleKeyDown(e: globalThis.KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); if (activeTab) saveFile(activeTab); }
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') { e.preventDefault(); setChatVisible(v => !v); }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab, openTabs]);

  // ── Monaco config ──────────────────────────────────────────────────────
  function handleEditorMount(editor: any, monaco: any) {
    editorRef.current = editor;
    monacoRef.current = monaco;

    // ── Author Dark (rose accent, matching Ailey Dark) ──────────────────
    monaco.editor.defineTheme('ailey-author-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '6b7280', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'be123c' },
        { token: 'string', foreground: '22c55e' },
        { token: 'emphasis', foreground: 'be123c', fontStyle: 'italic' },
        { token: 'strong', foreground: 'e2e8f0', fontStyle: 'bold' },
        { token: '', foreground: 'e2e8f0' },
      ],
      colors: {
        'editor.background': '#0f0f0f',
        'editor.foreground': '#d4d4d8',
        'editor.lineHighlightBackground': '#1a1a1a',
        'editor.selectionBackground': '#be123c33',
        'editorCursor.foreground': '#be123c',
        'editorLineNumber.foreground': '#2a2a2a',
        'editorLineNumber.activeForeground': '#be123c',
        'editorWidget.background': '#111111',
        'minimap.background': '#0a0a0a',
        'scrollbarSlider.background': '#be123c22',
        'scrollbarSlider.hoverBackground': '#be123c44',
      }
    });

    // ── Author Cyber Punk (teal accent, matching Cyber theme) ───────────
    monaco.editor.defineTheme('ailey-author-cyber', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '5c6370', fontStyle: 'italic' },
        { token: 'keyword', foreground: '00d4aa' },
        { token: 'string', foreground: '7ee787' },
        { token: 'emphasis', foreground: '00d4aa', fontStyle: 'italic' },
        { token: 'strong', foreground: 'c9d1d9', fontStyle: 'bold' },
        { token: '', foreground: 'c9d1d9' },
      ],
      colors: {
        'editor.background': '#1a1d23',
        'editor.foreground': '#c9d1d9',
        'editor.lineHighlightBackground': '#22262e',
        'editor.selectionBackground': '#00d4aa33',
        'editorCursor.foreground': '#00d4aa',
        'editorLineNumber.foreground': '#3a3f47',
        'editorLineNumber.activeForeground': '#00d4aa',
        'editorWidget.background': '#22262e',
        'minimap.background': '#13161c',
        'scrollbarSlider.background': '#00d4aa22',
        'scrollbarSlider.hoverBackground': '#00d4aa44',
      }
    });

    // ── Author Light ────────────────────────────────────────────────────
    monaco.editor.defineTheme('ailey-author-light', {
      base: 'vs',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '6b7280', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'be123c' },
        { token: 'string', foreground: '16a34a' },
        { token: 'emphasis', foreground: 'be123c', fontStyle: 'italic' },
        { token: 'strong', foreground: '1a1a1a', fontStyle: 'bold' },
        { token: '', foreground: '1a1a1a' },
      ],
      colors: {
        'editor.background': '#fafafa',
        'editor.foreground': '#1a1a1a',
        'editor.lineHighlightBackground': '#f0f0f0',
        'editor.selectionBackground': '#be123c22',
        'editorCursor.foreground': '#be123c',
        'editorLineNumber.foreground': '#cccccc',
        'editorLineNumber.activeForeground': '#be123c',
        'editorWidget.background': '#ffffff',
        'minimap.background': '#fafafa',
        'scrollbarSlider.background': '#be123c22',
        'scrollbarSlider.hoverBackground': '#be123c44',
      }
    });

    monaco.editor.setTheme(editorThemeName);
  }

  // ── File Tree Renderer ─────────────────────────────────────────────────
  function FileTreeNode({ node, depth = 0 }: { node: FileNode; depth?: number }) {
    const isExpanded = expandedDirs.has(node.path);
    const isActive = activeTab === node.path;
    const isRenaming = renamingPath === node.path;
    const isHidden = node.name.startsWith('.') && node.name !== '.ailey_author.json';
    if (isHidden) return null;

    if (isRenaming) {
      return (
        <div className="px-2 py-[3px]" style={{ paddingLeft: `${12 + depth * 16}px` }}>
          <input title="Umbenennen" placeholder="Neuer Name…"
            className="w-full bg-background border border-primary/50 rounded px-1.5 py-0.5 text-[12px] text-foreground outline-none focus:border-primary"
            value={renameValue} onChange={e => setRenameValue(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') renameFile(node.path, renameValue); if (e.key === 'Escape') { setRenamingPath(null); setRenameValue(''); } }}
            onBlur={() => { setRenamingPath(null); setRenameValue(''); }}
            autoFocus />
        </div>
      );
    }

    const icon = node.is_dir
      ? (node.name === 'kapitel' ? '📖' : node.name === 'notizen' ? '📝' : undefined)
      : undefined;

    return (
      <div>
        <div
          className={`flex items-center gap-1.5 px-2 py-[3px] text-[12px] cursor-pointer group transition-colors
            ${isActive ? 'bg-primary/15 text-foreground border-r-2 border-r-primary' : 'text-foreground/70 hover:bg-foreground/5 hover:text-foreground'}`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          onClick={() => openFile(node)}
          onDoubleClick={(e) => { e.stopPropagation(); setRenamingPath(node.path); setRenameValue(node.name); }}
        >
          {node.is_dir ? (
            <>
              {isExpanded ? <ChevronDown className="h-3 w-3 shrink-0 text-foreground/40" /> : <ChevronRight className="h-3 w-3 shrink-0 text-foreground/40" />}
              {icon ? <span className="text-sm">{icon}</span> : (isExpanded ? <FolderOpen className="h-3.5 w-3.5 shrink-0 text-primary" /> : <Folder className="h-3.5 w-3.5 shrink-0 text-primary/70" />)}
            </>
          ) : (
            <>
              <span className="w-3" />
              <File className={`h-3.5 w-3.5 shrink-0 ${getFileColor(node.name)}`} />
            </>
          )}
          <span className="truncate flex-1">{node.name}</span>
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button title="Umbenennen" className="p-0.5 hover:text-primary" onClick={(e) => { e.stopPropagation(); setRenamingPath(node.path); setRenameValue(node.name); }}><Edit3 className="h-3 w-3" /></button>
            <button title="Löschen" className="p-0.5 hover:text-red-400" onClick={(e) => { e.stopPropagation(); deleteFile(node.path); }}><Trash2 className="h-3 w-3" /></button>
          </div>
        </div>
        {node.is_dir && isExpanded && node.children?.map(child => (
          <FileTreeNode key={child.path} node={child} depth={depth + 1} />
        ))}
      </div>
    );
  }

  // ── Markdown renderer (simple) ─────────────────────────────────────────
  function renderMarkdown(text: string) {
    return text
      .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-foreground">$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em class="opacity-80">$1</em>')
      .replace(/`([^`]+)`/g, '<code class="bg-black/50 px-1 py-0.5 rounded text-[11px] text-primary">$1</code>')
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-black/50 rounded-lg p-2 mt-1.5 mb-1.5 text-[11px] overflow-x-auto border border-foreground/5 font-mono"><code>$2</code></pre>');
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ── PROJECT PICKER ─────────────────────────────────────────────────────
  // ══════════════════════════════════════════════════════════════════════════
  if (!activeProject) {
    return (
      <div className="min-h-screen bg-background text-foreground flex flex-col">
        <div className="h-11 bg-background border-b border-primary/30 flex items-center px-5 gap-3 shrink-0">
          <button onClick={() => router.push('/')} className="flex items-center gap-2 text-xs text-foreground/60 hover:text-foreground transition-colors" title="Zurück zu Ailey">
            <ArrowLeft className="h-3.5 w-3.5" /> Zurück zu Ailey
          </button>
          <div className="flex-1" />
          <button onClick={toggleTheme} className="p-1.5 rounded-md hover:bg-primary/10 transition-colors mr-2" title={uiTheme==='dark'?'Dark Mode':uiTheme==='cyber'?'Cyber Punk':uiTheme==='rainbowpunk'?'Rainbowpunk 🌈':uiTheme==='ailey'?'Steampunk ⚙️':'Light Mode'}>
            {uiTheme==='dark'?<Moon className="h-3.5 w-3.5"/>:uiTheme==='cyber'?<Sparkles className="h-3.5 w-3.5 text-primary"/>:uiTheme==='rainbowpunk'?<span className="text-sm leading-none">🌈</span>:uiTheme==='ailey'?<span className="text-sm leading-none">⚙️</span>:<Sun className="h-3.5 w-3.5"/>}
          </button>
          <img src="/ailey-emotes/ailey-writing-diary.jpg" alt="Ailey Author" className="h-6 w-6 rounded-full object-cover" />
          <span className="text-xs font-bold tracking-wide">A!LEY AUTHOR</span>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="max-w-lg w-full px-8 space-y-10">
            <div className="text-center space-y-3">
              <div className="relative inline-block">
                <img src="/ailey-emotes/ailey-writing-diary.jpg" alt="Ailey Author"
                  className="h-24 w-24 mx-auto rounded-2xl border-2 border-primary/40 object-cover shadow-lg shadow-primary/10" />
              </div>
              <h1 className="text-4xl font-black">
                A<span className="text-primary">!</span>LEY AUTHOR
              </h1>
              <p className="text-sm text-foreground/50">Prosa schreiben mit KI-Unterstützung</p>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-foreground/90">Schreibprojekte</h2>
                <Button size="sm" variant="outline" className="h-7 text-xs bg-transparent border-primary/40 text-foreground hover:bg-primary/10 hover:border-primary" onClick={() => setShowNewProject(true)}>
                  <Plus className="h-3 w-3 mr-1" /> Neues Projekt
                </Button>
              </div>

              {showNewProject && (
                <div className="bg-card border border-primary/30 rounded-lg p-4 space-y-2">
                  <Input className="h-8 text-xs bg-background border-border text-foreground placeholder:text-foreground/30" placeholder="Projektname (URL-sicher)…" value={newProjectName} onChange={e => setNewProjectName(e.target.value)} autoFocus />
                  <Input className="h-8 text-xs bg-background border-border text-foreground placeholder:text-foreground/30" placeholder="Titel…" value={newProjectTitle} onChange={e => setNewProjectTitle(e.target.value)} />
                  <Input className="h-8 text-xs bg-background border-border text-foreground placeholder:text-foreground/30" placeholder="Genre (optional)…" value={newProjectGenre} onChange={e => setNewProjectGenre(e.target.value)} onKeyDown={e => e.key === 'Enter' && createProject()} />
                  <div className="flex gap-2">
                    <Button size="sm" className="h-7 text-xs bg-primary hover:bg-primary/80 text-primary-foreground" onClick={createProject}>Erstellen</Button>
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-foreground/50 hover:text-foreground" onClick={() => setShowNewProject(false)}><X className="h-3 w-3" /></Button>
                  </div>
                </div>
              )}

              {projects.length === 0 && !showNewProject && (
                <div className="text-center py-16 text-sm text-foreground/30">
                  <BookOpen className="h-12 w-12 mx-auto mb-4 text-primary/30" />
                  Noch keine Projekte.<br />Erstelle dein erstes Schreibprojekt.
                </div>
              )}

              <div className="space-y-2">
                {projects.map(p => (
                  <div key={p.path} className="relative group/proj">
                    <button onClick={() => openProject(p.path, p.name)}
                      className="w-full text-left flex items-center gap-3 px-4 py-3.5 rounded-xl bg-card border border-border hover:border-primary/60 hover:bg-card/80 transition-all group">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        <BookOpen className="h-5 w-5 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-foreground truncate">{p.title || p.name}</div>
                        <div className="text-[10px] text-foreground/30 truncate flex items-center gap-2">
                          {p.genre && <span className="text-primary/50">{p.genre}</span>}
                          <span>{p.status || 'Entwurf'}</span>
                        </div>
                      </div>
                      <ChevronRight className="h-4 w-4 text-foreground/0 group-hover:text-foreground/40 transition-colors mr-6" />
                    </button>
                    <button
                      onClick={e => { e.stopPropagation(); deleteProject(p.path, p.title || p.name); }}
                      disabled={deletingProject === p.path}
                      className="absolute right-3 top-1/2 -translate-y-1/2 w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover/proj:opacity-100 hover:bg-primary/20 transition-all"
                      title="Projekt löschen">
                      {deletingProject === p.path
                        ? <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
                        : <Trash2 className="h-3.5 w-3.5 text-primary/60 hover:text-primary" />}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ── MAIN WRITING LAYOUT ────────────────────────────────────────────────
  // ══════════════════════════════════════════════════════════════════════════
  return (
    <div className="h-screen bg-background text-foreground flex flex-col overflow-hidden select-none">

      {/* ── Title Bar ─────────────────────────────────────────────────── */}
      <div className="h-10 bg-background border-b border-primary/20 flex items-center px-2 md:px-4 gap-1.5 md:gap-2.5 shrink-0 text-xs">
        <button onClick={leaveAuthorMode} className="flex items-center gap-1.5 text-foreground/50 hover:text-foreground transition-colors" title="Zurück">
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        <div className="w-px h-4 bg-foreground/10" />
        {isMobile && (
          <button onClick={() => { setMobileSidebarOpen(!mobileSidebarOpen); setMobileChatOpen(false); }} className="p-1.5 rounded-md hover:bg-foreground/5 transition-colors" title="Kapitel">
            <BookMarked className={`h-3.5 w-3.5 ${mobileSidebarOpen ? 'text-primary' : 'text-foreground/50'}`} />
          </button>
        )}
        <img src="/ailey-emotes/ailey-writing-diary.jpg" alt="Ailey" className="h-5 w-5 rounded-full object-cover hidden sm:block" />
        <span className="font-bold text-foreground hidden sm:inline">A<span className="text-primary">!</span>LEY AUTHOR</span>
        <span className="text-foreground/20 hidden sm:inline">·</span>
        <span className="text-foreground/50 truncate max-w-[100px] md:max-w-none">{projectMeta?.title || activeProjectName}</span>
        <div className="flex-1" />
        <span className="text-[10px] text-foreground/15 hidden lg:inline">⌘S Speichern · ⌘B KI-Panel</span>
        <button onClick={toggleTheme} className="p-1.5 rounded-md hover:bg-primary/10 transition-colors mr-1" title={uiTheme==='dark'?'Dark Mode':uiTheme==='cyber'?'Cyber Punk':uiTheme==='rainbowpunk'?'Rainbowpunk 🌈':uiTheme==='ailey'?'Steampunk ⚙️':'Light Mode'}>
          {uiTheme==='dark'?<Moon className="h-3.5 w-3.5"/>:uiTheme==='cyber'?<Sparkles className="h-3.5 w-3.5 text-primary"/>:uiTheme==='rainbowpunk'?<span className="text-sm leading-none">🌈</span>:uiTheme==='ailey'?<span className="text-sm leading-none">⚙️</span>:<Sun className="h-3.5 w-3.5"/>}
        </button>
        <button onClick={() => {
          if (isMobile) { setMobileChatOpen(!mobileChatOpen); setMobileSidebarOpen(false); }
          else setChatVisible(!chatVisible);
        }} className="p-1.5 rounded-md hover:bg-foreground/5 transition-colors" title="KI-Panel (⌘B)">
          {(isMobile ? mobileChatOpen : chatVisible) ? <PanelRightClose className="h-3.5 w-3.5 text-primary" /> : <PanelRight className="h-3.5 w-3.5 text-foreground/50" />}
        </button>
      </div>

      {/* ── Main Area ─────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden relative">

        {/* ── Mobile sidebar overlay backdrop ──────────────────────────── */}
        {isMobile && mobileSidebarOpen && (
          <div className="absolute inset-0 bg-black/60 z-30" onClick={() => setMobileSidebarOpen(false)} />
        )}

        {/* ── Activity Bar + Sidebar (hidden on mobile, overlay when open) ─ */}
        <div className={`${isMobile ? (mobileSidebarOpen ? 'absolute left-0 top-0 bottom-0 z-40 flex' : 'hidden') : 'flex'} shrink-0`}>

        {/* ── Activity Bar ────────────────────────────────────────────── */}
        <div className="w-12 bg-background border-r border-foreground/5 flex flex-col items-center py-2 gap-1 shrink-0">
          <button onClick={() => setSidePanel('explorer')} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${sidePanel === 'explorer' ? 'bg-primary/15 text-primary' : 'text-foreground/40 hover:text-foreground hover:bg-foreground/5'}`} title="Kapitel">
            <BookMarked className="h-4.5 w-4.5" />
          </button>
          <button onClick={() => { setSidePanel('stats'); if (activeProjectName) loadStats(activeProjectName); }} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${sidePanel === 'stats' ? 'bg-primary/15 text-primary' : 'text-foreground/40 hover:text-foreground hover:bg-foreground/5'}`} title="Statistiken">
            <BarChart3 className="h-4.5 w-4.5" />
          </button>
          <button onClick={() => { setSidePanel('snapshots'); if (activeProjectName) loadSnapshots(activeProjectName); }} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${sidePanel === 'snapshots' ? 'bg-primary/15 text-primary' : 'text-foreground/40 hover:text-foreground hover:bg-foreground/5'}`} title="Snapshots">
            <Camera className="h-4.5 w-4.5" />
          </button>
          <button onClick={() => setSidePanel('knowledge')} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${sidePanel === 'knowledge' ? 'bg-primary/15 text-primary' : 'text-foreground/40 hover:text-foreground hover:bg-foreground/5'}`} title="Wissensbasis">
            <Library className="h-4.5 w-4.5" />
          </button>
          <div className="flex-1" />
        </div>

        {/* ── Sidebar Panel ───────────────────────────────────────────── */}
        <div className="w-56 bg-background border-r border-foreground/5 flex flex-col shrink-0">

          {/* ═══ Explorer ═══ */}
          {sidePanel === 'explorer' && (
            <>
              <div className="h-9 flex items-center justify-between px-3 text-[11px] uppercase tracking-wider text-foreground/40 border-b border-foreground/5">
                <span className="font-semibold">Kapitel & Dateien</span>
                <div className="flex items-center gap-0.5">
                  <button onClick={() => { setNewFileDir(activeProject); setNewFileName(''); }} className="p-1 rounded hover:bg-foreground/5" title="Neue Datei"><FilePlus className="h-3 w-3 text-foreground/40 hover:text-foreground" /></button>
                  <button onClick={() => { const name = prompt('Ordnername:'); if (name) createFolder(activeProject!, name); }} className="p-1 rounded hover:bg-foreground/5" title="Neuer Ordner"><FolderPlus className="h-3 w-3 text-foreground/40 hover:text-foreground" /></button>
                  <button onClick={() => loadFileTree()} className="p-1 rounded hover:bg-foreground/5" title="Aktualisieren"><RefreshCw className="h-3 w-3 text-foreground/40 hover:text-foreground" /></button>
                </div>
              </div>
              {newFileDir !== null && (
                <div className="px-2 py-1.5 border-b border-foreground/5">
                  <Input className="h-6 text-[11px] bg-background border-border text-foreground placeholder:text-foreground/30" placeholder="Dateiname…" value={newFileName} autoFocus
                    onChange={e => setNewFileName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') createFile(newFileDir || activeProject!, newFileName); if (e.key === 'Escape') { setNewFileDir(null); setNewFileName(''); } }} />
                </div>
              )}
              <div className="flex-1 overflow-y-auto py-1">
                {fileTreeLoading ? (
                  <div className="flex items-center justify-center py-8"><Loader2 className="h-4 w-4 animate-spin text-primary/50" /></div>
                ) : fileTree.length === 0 ? (
                  <div className="text-center text-[11px] text-foreground/20 py-8">Leeres Projekt</div>
                ) : (
                  fileTree.map(node => <FileTreeNode key={node.path} node={node} />)
                )}
              </div>
              <div className="border-t border-foreground/5 px-3 py-2">
                <button onClick={() => { setActiveProject(null); setOpenTabs([]); setActiveTab(null); }} className="text-[10px] text-foreground/30 hover:text-primary transition-colors">
                  ← Projekt wechseln
                </button>
              </div>
            </>
          )}

          {/* ═══ Stats ═══ */}
          {sidePanel === 'stats' && (
            <>
              <div className="h-9 flex items-center px-3 text-[11px] uppercase tracking-wider text-foreground/40 border-b border-foreground/5">
                <span className="font-semibold">Statistiken</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-4">
                {stats ? (
                  <>
                    <div className="space-y-2">
                      <div className="flex justify-between text-[12px]">
                        <span className="text-foreground/60">Wörter gesamt</span>
                        <span className="font-bold text-primary">{stats.total_words.toLocaleString('de-DE')}</span>
                      </div>
                      {stats.word_count_target > 0 && (
                        <div>
                          <div className="flex justify-between text-[10px] text-foreground/40 mb-1">
                            <span>Fortschritt</span>
                            <span>{Math.round(stats.total_words / stats.word_count_target * 100)}%</span>
                          </div>
                          <div className="h-1.5 bg-foreground/10 rounded-full overflow-hidden">
                            <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${Math.min(100, stats.total_words / stats.word_count_target * 100)}%` }} />
                          </div>
                        </div>
                      )}
                      <div className="flex justify-between text-[11px] text-foreground/40">
                        <span>Zeichen</span><span>{stats.total_chars.toLocaleString('de-DE')}</span>
                      </div>
                      <div className="flex justify-between text-[11px] text-foreground/40">
                        <span>Lesezeit</span><span>~{stats.reading_time_minutes} Min.</span>
                      </div>
                    </div>
                    {stats.chapters.length > 0 && (
                      <div className="border-t border-foreground/5 pt-3">
                        <div className="text-[10px] uppercase tracking-wider text-foreground/30 font-semibold mb-2">Kapitel</div>
                        <div className="space-y-1.5">
                          {stats.chapters.map((ch, i) => (
                            <div key={i} className="flex items-center justify-between text-[11px]">
                              <span className="text-foreground/50 truncate flex-1">{ch.file.replace('.md', '')}</span>
                              <span className="text-primary/70 ml-2">{ch.word_count}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center text-[11px] text-foreground/20 py-8">Lade…</div>
                )}
              </div>
            </>
          )}

          {/* ═══ Snapshots ═══ */}
          {sidePanel === 'snapshots' && (
            <>
              <div className="h-9 flex items-center justify-between px-3 text-[11px] uppercase tracking-wider text-foreground/40 border-b border-foreground/5">
                <span className="font-semibold">Snapshots</span>
                <button onClick={createSnapshot} disabled={snapshotBusy} className="p-1 rounded hover:bg-foreground/5" title="Snapshot erstellen">
                  {snapshotBusy ? <Loader2 className="h-3 w-3 animate-spin text-primary" /> : <Camera className="h-3 w-3 text-foreground/40 hover:text-primary" />}
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                {snapshots.length === 0 ? (
                  <div className="text-center text-[11px] text-foreground/20 py-8 px-3">
                    <Camera className="h-8 w-8 mx-auto mb-3 text-foreground/10" />
                    Noch keine Snapshots.<br />Klicke 📷 um ein Backup zu erstellen.
                  </div>
                ) : (
                  <div className="py-1">
                    {snapshots.map((s, i) => (
                      <div key={i} className="px-3 py-1.5 text-[11px] text-foreground/50 border-b border-foreground/[0.03] flex items-center gap-2">
                        <Camera className="h-3 w-3 text-primary/50 shrink-0" />
                        <span className="flex-1 truncate">{s.timestamp}</span>
                        <span className="text-[9px] text-foreground/20">{(s.size / 1024).toFixed(0)} KB</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ═══ Knowledge Base ═══ */}
          {sidePanel === 'knowledge' && (
            <>
              <div className="h-9 flex items-center justify-between px-3 text-[11px] uppercase tracking-wider text-foreground/40 border-b border-foreground/5">
                <span className="font-semibold">Wissensbasis</span>
                <div className="flex items-center gap-1">
                  <button onClick={loadRagDocuments} className="p-1 rounded hover:bg-foreground/5" title="Aktualisieren">
                    <RefreshCw className={`h-3 w-3 text-foreground/40 hover:text-primary ${ragDocsLoading ? 'animate-spin' : ''}`} />
                  </button>
                  <button onClick={() => ragUploadRef.current?.click()} disabled={ragUploading} className="p-1 rounded hover:bg-foreground/5" title="Referenzdokument hochladen">
                    {ragUploading ? <Loader2 className="h-3 w-3 animate-spin text-primary" /> : <Upload className="h-3 w-3 text-foreground/40 hover:text-primary" />}
                  </button>
                  <input ref={ragUploadRef} type="file" title="Referenzdokument hochladen" accept=".pdf,.txt,.md,.docx,.epub,.html,.rtf,.json,.csv" onChange={handleRagUpload} className="hidden" />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-2 space-y-3">
                {/* Upload message */}
                {ragUploadMsg && (
                  <div className={`text-[10px] px-2 py-1 rounded ${ragUploadMsg.startsWith('✓') ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'}`}>
                    {ragUploadMsg}
                  </div>
                )}

                {/* Search */}
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-wider text-foreground/30 font-semibold">Suche</div>
                  <div className="flex items-center gap-1">
                    <input className="flex-1 bg-card border border-foreground/10 rounded px-2 py-1 text-[11px] text-foreground outline-none placeholder:text-foreground/25 focus:border-primary/60"
                      value={ragSearchQuery} onChange={e => setRagSearchQuery(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') searchRag(); }}
                      placeholder="Charakter, Ort, Szene…" />
                    <button onClick={searchRag} disabled={ragSearching} className="p-1 rounded hover:bg-primary/10">
                      {ragSearching ? <Loader2 className="h-3 w-3 animate-spin text-primary" /> : <Search className="h-3 w-3 text-primary" />}
                    </button>
                  </div>
                  {ragSearchResults.length > 0 && (
                    <div className="space-y-1.5 mt-1">
                      {ragSearchResults.map((hit, i) => (
                        <div key={i} className="bg-card border border-foreground/5 rounded-lg p-2 text-[10px]">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-primary/70 font-medium truncate">{hit.title || hit.source}</span>
                            <span className="text-foreground/20 ml-1">{(hit.score * 100).toFixed(0)}%</span>
                          </div>
                          <div className="text-foreground/50 line-clamp-3">{hit.text}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Documents */}
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-wider text-foreground/30 font-semibold">Referenz-Dokumente</div>
                  {ragDocuments.filter(d => d.doc_type !== 'auto_notes').length === 0 ? (
                    <div className="text-center text-[10px] text-foreground/20 py-4 px-2">
                      <Library className="h-6 w-6 mx-auto mb-2 text-foreground/10" />
                      Keine Referenzdokumente.<br />
                      <span className="text-foreground/30">Lade Bücher, Charakter-Infos oder Recherche-Material hoch.</span>
                    </div>
                  ) : (
                    ragDocuments.filter(d => d.doc_type !== 'auto_notes').map((doc, i) => (
                      <div key={i} className="flex items-center gap-2 px-2 py-1.5 text-[11px] rounded hover:bg-foreground/5 group">
                        <FileText className="h-3 w-3 text-primary/50 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="text-foreground/70 truncate">{doc.title || doc.source}</div>
                          <div className="text-[9px] text-foreground/30">{doc.chunks} Chunks · {Math.round(doc.total_chars / 1000)}k Zeichen</div>
                        </div>
                        <button onClick={() => deleteRagDocument(doc.source)} className="p-0.5 opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:text-red-400" title="Entfernen">
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    ))
                  )}
                </div>

                {/* Auto-Notes by Qwen Coder */}
                <div className="space-y-1 border-t border-foreground/5 pt-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] uppercase tracking-wider text-foreground/30 font-semibold flex items-center gap-1">
                      <Zap className="h-3 w-3" /> Auto-Notizen
                    </div>
                    <div className="flex items-center gap-1">
                      {autoNotesLoading && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
                      <button onClick={() => setAutoNotesEnabled(!autoNotesEnabled)} className={`text-[9px] px-1.5 py-0.5 rounded ${autoNotesEnabled ? 'bg-primary/15 text-primary' : 'bg-foreground/5 text-foreground/30'}`}>
                        {autoNotesEnabled ? 'An' : 'Aus'}
                      </button>
                      <button onClick={triggerAutoAnalysis} disabled={autoNotesLoading} className="p-0.5 rounded hover:bg-foreground/5" title="Jetzt analysieren">
                        <Brain className="h-3 w-3 text-foreground/40 hover:text-primary" />
                      </button>
                    </div>
                  </div>
                  <div className="text-[9px] text-foreground/25">
                    Qwen2.5-Coder analysiert deinen Text und extrahiert automatisch Charaktere, Orte, Plot-Punkte.
                  </div>
                  {autoNotes ? (
                    <div className="space-y-2 mt-1">
                      {/* Characters */}
                      {autoNotes.characters?.length > 0 && (
                        <div>
                          <div className="text-[9px] text-primary/60 font-semibold uppercase mb-0.5">Charaktere</div>
                          {autoNotes.characters.map((c: any, i: number) => (
                            <div key={i} className="text-[10px] text-foreground/60 py-0.5 flex items-start gap-1">
                              <span className="text-primary font-medium">{c.name}</span>
                              {c.role && <span className="text-foreground/25">({c.role})</span>}
                              {c.description && <span className="text-foreground/40">— {c.description}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      {/* Locations */}
                      {autoNotes.locations?.length > 0 && (
                        <div>
                          <div className="text-[9px] text-primary/60 font-semibold uppercase mb-0.5">Orte</div>
                          {autoNotes.locations.map((l: any, i: number) => (
                            <div key={i} className="text-[10px] text-foreground/60 py-0.5">
                              <span className="text-primary/80 font-medium">{l.name}</span>
                              {l.description && <span className="text-foreground/40"> — {l.description}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      {/* Plot Points */}
                      {autoNotes.plot_points?.length > 0 && (
                        <div>
                          <div className="text-[9px] text-primary/60 font-semibold uppercase mb-0.5">Handlung</div>
                          {autoNotes.plot_points.map((p: any, i: number) => (
                            <div key={i} className="text-[10px] text-foreground/50 py-0.5">• {p}</div>
                          ))}
                        </div>
                      )}
                      {/* Themes */}
                      {autoNotes.themes?.length > 0 && (
                        <div>
                          <div className="text-[9px] text-primary/60 font-semibold uppercase mb-0.5">Themen</div>
                          <div className="flex flex-wrap gap-1">
                            {autoNotes.themes.map((t: any, i: number) => (
                              <span key={i} className="text-[9px] bg-primary/10 text-primary/70 rounded px-1.5 py-0.5">{t}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {/* Relationships */}
                      {autoNotes.relationships?.length > 0 && (
                        <div>
                          <div className="text-[9px] text-primary/60 font-semibold uppercase mb-0.5">Beziehungen</div>
                          {autoNotes.relationships.map((r: any, i: number) => (
                            <div key={i} className="text-[10px] text-foreground/50 py-0.5">
                              <span className="text-primary/80">{r.from}</span>
                              <span className="text-foreground/25"> → </span>
                              <span className="text-primary/80">{r.to}</span>
                              {r.type && <span className="text-foreground/30"> ({r.type})</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      {/* Style Notes */}
                      {autoNotes.style_notes && (
                        <div>
                          <div className="text-[9px] text-primary/60 font-semibold uppercase mb-0.5">Stil</div>
                          <div className="text-[10px] text-foreground/40 italic">{autoNotes.style_notes}</div>
                        </div>
                      )}
                      {/* Raw fallback */}
                      {autoNotes.raw_analysis && (
                        <div className="text-[10px] text-foreground/40 whitespace-pre-wrap bg-card p-2 rounded border border-foreground/5">
                          {autoNotes.raw_analysis}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center text-[10px] text-foreground/15 py-3">
                      {autoNotesEnabled ? 'Speichere eine .md Datei um die Analyse zu starten' : 'Auto-Analyse deaktiviert'}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
        </div>{/* end Activity Bar + Sidebar wrapper */}
        <div className="flex-1 flex flex-col min-w-0">

          {/* Tab Bar */}
          <div className="h-10 bg-background flex items-center overflow-x-auto shrink-0 border-b border-foreground/5 gap-px px-1">
            {openTabs.map(tab => (
              <button key={tab.path} onClick={() => { setActiveTab(tab.path); if (isMobile) setMobileSidebarOpen(false); }}
                className={`h-8 flex items-center gap-1.5 px-2 md:px-3 text-[11px] md:text-[12px] rounded-lg shrink-0 group transition-colors my-1
                  ${activeTab === tab.path
                    ? 'bg-card text-foreground shadow-sm shadow-primary/10'
                    : 'text-foreground/40 hover:bg-foreground/5 hover:text-foreground/70'
                  }`}>
                <File className={`h-3 w-3 shrink-0 ${getFileColor(tab.name)}`} />
                <span className="truncate max-w-[120px]">{tab.name}</span>
                {tab.dirty && <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />}
                <button title="Tab schließen" onClick={(e) => closeTab(tab.path, e)} className="ml-0.5 opacity-0 group-hover:opacity-40 hover:!opacity-100 p-0.5 rounded hover:bg-foreground/10 hover:text-foreground">
                  <X className="h-3 w-3" />
                </button>
              </button>
            ))}
            <div className="flex-1" />
            {currentTab && (
              <div className="flex items-center gap-2 pr-2 shrink-0 text-[10px] text-foreground/30">
                <span>{currentWordCount} <span className="hidden sm:inline">Wörter</span><span className="sm:hidden">W</span></span>
                <span className="text-foreground/10 hidden md:inline">·</span>
                <span className="hidden md:inline">{currentCharCount} Zeichen</span>
                <span className="text-foreground/10 hidden md:inline">·</span>
                <span className="hidden md:inline">~{Math.max(1, Math.round(currentWordCount / 250))} Min. Lesezeit</span>
                <button title="Speichern (⌘S)" onClick={() => saveFile(currentTab.path)}
                  className={`ml-1 md:ml-2 px-2 py-1 rounded text-[10px] flex items-center gap-1 transition-colors ${currentTab.dirty ? 'text-primary hover:bg-primary/10' : 'text-foreground/30 hover:text-foreground hover:bg-foreground/5'}`}>
                  <Save className="h-3 w-3" /> {isMobile ? '' : (currentTab.dirty ? 'Speichern' : 'Gespeichert')}
                </button>
              </div>
            )}
          </div>

          {/* Editor */}
          <div className="flex-1 min-h-0">
            {currentTab ? (
              <MonacoEditor
                height="100%"
                theme={editorThemeName}
                language="markdown"
                value={currentTab.content}
                onChange={onEditorChange}
                onMount={handleEditorMount}
                options={{
                  fontSize: isMobile ? 14 : 16,
                  fontFamily: "'Georgia', 'Merriweather', 'Crimson Pro', serif",
                  lineHeight: isMobile ? 24 : 28,
                  wordWrap: 'on',
                  minimap: { enabled: false },
                  lineNumbers: 'off',
                  glyphMargin: false,
                  folding: false,
                  renderLineHighlight: 'none',
                  scrollBeyondLastLine: true,
                  padding: { top: isMobile ? 16 : 40, bottom: isMobile ? 40 : 120 },
                  overviewRulerBorder: false,
                  hideCursorInOverviewRuler: true,
                  renderWhitespace: 'none',
                  automaticLayout: true,
                  cursorBlinking: 'smooth',
                  cursorSmoothCaretAnimation: 'on',
                  smoothScrolling: true,
                  roundedSelection: true,
                  tabSize: 2,
                  autoClosingBrackets: 'never',
                  autoClosingQuotes: 'never',
                  quickSuggestions: false,
                  suggestOnTriggerCharacters: false,
                  parameterHints: { enabled: false },
                  acceptSuggestionOnEnter: 'off',
                  stickyScroll: { enabled: false },
                  bracketPairColorization: { enabled: false },
                  guides: { indentation: false },
                }}
              />
            ) : (
              <div className="h-full flex items-center justify-center">
                <div className="text-center space-y-3">
                  <img src="/ailey-emotes/ailey-writing-diary.jpg" alt="Ailey schreibt" className="h-20 w-20 mx-auto rounded-2xl object-cover opacity-20" />
                  <div className="text-sm text-foreground/25">Öffne ein Kapitel aus der Seitenleiste</div>
                  <div className="text-[10px] text-foreground/15">Distraction-free writing · Serif Font · KI-Assistenz</div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Right Sidebar: KI Panel ─────────────────────────────────── */}
        {(isMobile ? mobileChatOpen : chatVisible) && (
          <div className={`${isMobile ? 'absolute inset-0 z-40' : 'w-80 shrink-0'} bg-background border-l border-foreground/5 flex flex-col`}>
            {/* Header */}
            <div className="h-9 flex items-center justify-between px-3 text-[11px] border-b border-foreground/5 shrink-0">
              <div className="flex items-center gap-1.5">
                <img src="/ailey-emotes/ailey-writing-diary.jpg" alt="Ailey" className="w-5 h-5 rounded-full object-cover" />
                <span className="font-semibold text-foreground">Ailey</span>
                <span className="text-foreground/30">· Lektorin</span>
              </div>
              <button title="Panel schließen" onClick={() => { if (isMobile) setMobileChatOpen(false); else setChatVisible(false); }} className="p-1 rounded hover:bg-foreground/5"><X className="h-3 w-3 text-foreground/40" /></button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {chatMessages.map(msg => (
                <div key={msg.id} className={`text-[12px] leading-relaxed ${msg.role === 'user' ? 'text-right' : 'flex items-start gap-2'}`}>
                  {msg.role === 'ai' && <img src="/ailey-emotes/ailey-writing-diary.jpg" alt="Ailey" className="w-5 h-5 rounded-full object-cover shrink-0 mt-0.5" />}
                  <div className={`inline-block max-w-[95%] rounded-xl px-3 py-2 ${
                    msg.role === 'user'
                      ? 'bg-primary/15 text-foreground border border-primary/20'
                      : 'bg-card text-foreground/80 border border-foreground/5'
                  }`}>
                    {msg.pending ? (
                      <div className="flex items-center gap-2">
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                        <span className="text-foreground/40">Ailey schreibt…</span>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                    )}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* Mode buttons + Input */}
            <div className="border-t border-foreground/5 p-2.5 shrink-0 space-y-2">
              {/* Quick action buttons */}
              <div className="flex flex-wrap gap-1">
                {([
                  { id: 'weiterschreiben' as const, icon: <Wand2 className="h-3 w-3" />, label: 'Weiterschreiben' },
                  { id: 'lektorat' as const, icon: <Eye className="h-3 w-3" />, label: 'Lektorat' },
                  { id: 'brainstorm' as const, icon: <Lightbulb className="h-3 w-3" />, label: 'Brainstorm' },
                  { id: 'recherche' as const, icon: <Search className="h-3 w-3" />, label: 'Recherche' },
                  { id: 'fragen' as const, icon: <MessageCircle className="h-3 w-3" />, label: 'Fragen' },
                ]).map(m => (
                  <button key={m.id} onClick={() => {
                    setChatMode(m.id);
                    // Auto-send for weiterschreiben/lektorat
                    if (m.id === 'weiterschreiben' || m.id === 'lektorat') {
                      setChatMode(m.id);
                      // trigger via timeout so state updates
                      setTimeout(() => {
                        const tab = openTabsRef.current.find(t => t.path === activeTab);
                        if (tab) sendChat();
                      }, 100);
                    }
                  }}
                    className={`px-2 py-1 rounded-md text-[10px] font-medium transition-all flex items-center gap-1 ${
                      chatMode === m.id
                        ? 'bg-primary/20 text-primary border border-primary/30'
                        : 'bg-transparent text-foreground/40 border border-transparent hover:text-foreground/60 hover:bg-foreground/5'
                    }`}>
                    {m.icon} {m.label}
                  </button>
                ))}
                <button onClick={() => setAuthorSettingsOpen(!authorSettingsOpen)}
                  className={`px-1.5 py-1 rounded-md text-[10px] transition-all ${authorSettingsOpen ? 'text-primary bg-primary/10' : 'text-foreground/30 hover:text-foreground/50'}`}
                  title="Token-Einstellungen">
                  <Settings className="h-3 w-3" />
                </button>
              </div>
              {authorSettingsOpen && (
                <div className="flex flex-col gap-1.5 px-1 py-1.5 rounded-lg bg-foreground/[0.03] border border-foreground/5">
                  {([
                    {key:'author_write',  label:'Weiterschreiben', active: chatMode === 'weiterschreiben'},
                    {key:'author_review', label:'Lektorat & Co.',  active: chatMode !== 'weiterschreiben'},
                  ] as {key:string;label:string;active:boolean}[]).map(item => (
                    <div key={item.key} className="flex items-center gap-2">
                      <span className={`text-[10px] w-28 shrink-0 ${item.active ? 'text-primary' : 'text-foreground/40'}`}>{item.label}</span>
                      <input type="range" min={200} max={16384} step={100} title={`${item.label} Token-Limit`}
                        value={authorGenSettings[item.key] ?? 1000}
                        onChange={e => setAuthorGenSettings(prev => ({...prev, [item.key]: parseInt(e.target.value)}))}
                        onMouseUp={e => updateAuthorGenSetting(item.key, parseInt((e.target as HTMLInputElement).value))}
                        onTouchEnd={() => updateAuthorGenSetting(item.key, authorGenSettings[item.key] ?? 1000)}
                        className="flex-1 h-1 accent-primary"
                      />
                      <span className="text-[9px] tabular-nums font-mono text-foreground/40 w-12 text-right">{authorGenSettings[item.key] ?? '—'}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-1.5">
                <input className="flex-1 bg-card border border-foreground/10 rounded-lg px-3 py-2 text-[12px] text-foreground outline-none placeholder:text-foreground/25 focus:border-primary/60 transition-colors"
                  value={chatInput} onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
                  placeholder={
                    chatMode === 'weiterschreiben' ? 'Enter: Text wird fortgesetzt…' :
                    chatMode === 'lektorat' ? 'Enter: Text wird analysiert…' :
                    chatMode === 'brainstorm' ? 'Worüber brainstormen?' :
                    chatMode === 'recherche' ? 'Was recherchieren?' :
                    'Frag Ailey etwas…'
                  }
                  disabled={chatBusy} />
                <button title="Senden" onClick={sendChat} disabled={chatBusy} className="p-2 rounded-lg bg-primary text-primary-foreground transition-colors disabled:opacity-40 hover:bg-primary/80">
                  <Send className="h-3.5 w-3.5" />
                </button>
              </div>
              {currentTab && (
                <div className="text-[10px] text-foreground/25 truncate flex items-center gap-1">
                  <FileText className="h-2.5 w-2.5 text-primary/50" />
                  {currentTab.name} · {currentWordCount} Wörter
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Status Bar ────────────────────────────────────────────────── */}
      <div className="h-7 bg-primary flex items-center px-2 md:px-4 text-[10px] md:text-[11px] text-primary-foreground shrink-0 z-20">
        <div className="flex items-center gap-2 md:gap-3 min-w-0">
          <span className="flex items-center gap-1 font-medium truncate">
            <PenTool className="h-3 w-3 shrink-0" />
            <span className="truncate">{projectMeta?.title || activeProjectName}</span>
          </span>
          {projectMeta?.genre && <span className="text-primary-foreground/60 hidden md:inline">· {projectMeta.genre}</span>}
          {currentTab && (
            <>
              <span className="text-primary-foreground/40 hidden sm:inline">·</span>
              <span className="text-primary-foreground/80 hidden sm:inline">{currentTab.name}</span>
            </>
          )}
          {currentTab?.dirty && <span className="text-primary-foreground/70">● <span className="hidden sm:inline">unsaved</span></span>}
        </div>
        <div className="flex-1" />
        {stats && (
          <div className="flex items-center gap-2 md:gap-3 mr-2 md:mr-3">
            <span className="text-primary-foreground/70">{stats.total_words.toLocaleString('de-DE')} <span className="hidden sm:inline">Wörter</span><span className="sm:hidden">W</span></span>
            {stats.word_count_target > 0 && (
              <span className="text-primary-foreground/50 hidden sm:inline">{Math.round(stats.total_words / stats.word_count_target * 100)}%</span>
            )}
          </div>
        )}
        <span className="text-primary-foreground/60 hidden sm:inline">A!LEY AUTHOR v1.0</span>
      </div>
    </div>
  );
}
