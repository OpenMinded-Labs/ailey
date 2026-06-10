"use client";
import React, { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { loader } from '@monaco-editor/react';
import * as Diff from 'diff';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  ChevronRight, ChevronDown, File, Folder, FolderOpen, Plus, Trash2, RefreshCw,
  Terminal as TermIcon, X, Send, Loader2, ArrowLeft, Play, Save, Code2,
  MessageCircle, PanelRightClose, PanelRight, FolderPlus, FilePlus,
  Check, XCircle, GitBranch, Search, Edit3, Copy, Download,
  ChevronUp, Eye, FileCode, Zap, Upload, Globe, Server, Settings,
  AlertTriangle, Bug, ToggleLeft, ToggleRight, Sparkles, Square, ExternalLink, Package
} from 'lucide-react';

// ── Configure Monaco to use local bundle from /public (not CDN) ────────────
loader.config({ paths: { vs: '/monaco/vs' } });

// ── Dynamic imports (Monaco heavy, don't SSR) ──────────────────────────────
const MonacoEditor = dynamic(() => import('@monaco-editor/react').then(m => m.default), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex flex-col items-center justify-center text-sm text-white/30 gap-2">
      <div className="h-5 w-5 border-2 border-[#be123c]/30 border-t-[#be123c] rounded-full animate-spin" />
      <span>Editor lädt…</span>
    </div>
  )
});

// ── Constants ────────────────────────────────────────────────────────────────
const API_BASE = typeof window !== 'undefined'
  ? (() => {
      const h = window.location.hostname;
      if (!h || h === 'tauri.localhost' || h === 'localhost' || h === '127.0.0.1') return 'http://127.0.0.1:5502';
      return `http://${h}:5502`;
    })()
  : '';
const LANG_MAP: Record<string, string> = {
  'py': 'python', 'js': 'javascript', 'jsx': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
  'html': 'html', 'htm': 'html', 'css': 'css', 'scss': 'scss', 'json': 'json',
  'md': 'markdown', 'rs': 'rust', 'toml': 'toml', 'yaml': 'yaml', 'yml': 'yaml',
  'sh': 'shell', 'bash': 'shell', 'zsh': 'shell', 'php': 'php', 'sql': 'sql',
  'xml': 'xml', 'svg': 'xml', 'txt': 'plaintext', 'log': 'plaintext',
  'c': 'c', 'cpp': 'cpp', 'h': 'c', 'hpp': 'cpp', 'swift': 'swift',
  'rb': 'ruby', 'go': 'go', 'java': 'java', 'kt': 'kotlin',
};
function getLang(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return LANG_MAP[ext] || 'plaintext';
}

// ── ANSI color parser ────────────────────────────────────────────────────────
interface AnsiSegment { text: string; color?: string; bold?: boolean; }
function parseAnsi(raw: string): AnsiSegment[] {
  const segments: AnsiSegment[] = [];
  const regex = /\x1b\[([0-9;]*)m/g;
  let lastIdx = 0;
  let curColor: string | undefined;
  let curBold = false;
  const ANSI_COLORS: Record<string, string> = {
    '30': '#555', '31': '#be123c', '32': '#22c55e', '33': '#eab308', '34': '#6366f1',
    '35': '#d946ef', '36': '#0891b2', '37': '#e5e5e5',
    '90': '#777', '91': '#f43f5e', '92': '#4ade80', '93': '#facc15', '94': '#818cf8',
    '95': '#e879f9', '96': '#22d3ee', '97': '#ffffff',
  };
  let match;
  while ((match = regex.exec(raw)) !== null) {
    if (match.index > lastIdx) {
      segments.push({ text: raw.slice(lastIdx, match.index), color: curColor, bold: curBold });
    }
    const codes = match[1].split(';').filter(Boolean);
    for (const c of codes) {
      if (c === '0') { curColor = undefined; curBold = false; }
      else if (c === '1') { curBold = true; }
      else if (ANSI_COLORS[c]) { curColor = ANSI_COLORS[c]; }
    }
    lastIdx = regex.lastIndex;
  }
  if (lastIdx < raw.length) {
    segments.push({ text: raw.slice(lastIdx), color: curColor, bold: curBold });
  }
  return segments;
}

// ── Diff Computation (using 'diff' package) ─────────────────────────────────
interface DiffLine { type: 'add' | 'remove' | 'same'; text: string; }
function computeDiff(oldText: string, newText: string): DiffLine[] {
  const changes = Diff.diffLines(oldText, newText);
  const result: DiffLine[] = [];
  for (const part of changes) {
    const lines = part.value.replace(/\n$/, '').split('\n');
    for (const line of lines) {
      if (part.added) result.push({ type: 'add', text: line });
      else if (part.removed) result.push({ type: 'remove', text: line });
      else result.push({ type: 'same', text: line });
    }
  }
  return result;
}

// ── File-type icon colors (Ailey palette) ────────────────────────────────────
function getFileColor(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  if (['py'].includes(ext)) return 'text-[#0891b2]';
  if (['js','jsx','ts','tsx'].includes(ext)) return 'text-[#eab308]';
  if (['html','htm'].includes(ext)) return 'text-[#be123c]';
  if (['css','scss'].includes(ext)) return 'text-[#6366f1]';
  if (['json','yaml','yml','toml'].includes(ext)) return 'text-[#22c55e]';
  if (['md','txt'].includes(ext)) return 'text-white/60';
  if (['rs'].includes(ext)) return 'text-[#f97316]';
  if (['sh','bash','zsh'].includes(ext)) return 'text-[#22c55e]';
  return 'text-[#0891b2]/70';
}

// ── Types ────────────────────────────────────────────────────────────────────
interface FileNode { name: string; path: string; is_dir: boolean; children?: FileNode[]; size?: number; }
interface OpenTab { path: string; name: string; content: string; dirty: boolean; language: string; }
interface ChatMsg {
  id: string; role: 'user' | 'ai'; content: string; ts: number; pending?: boolean;
  actions?: AgentAction[];
}
interface AgentAction {
  type: 'edit_file' | 'run_command' | 'create_file' | 'patch_file';
  path?: string; content?: string; command?: string; id: string;
  status?: 'pending' | 'accepted' | 'rejected';
  stdout?: string; stderr?: string; returncode?: number;
  patches?: { search: string; replace: string }[];
  patch_count?: number;
}
interface ProjectMeta { name: string; path: string; language?: string; last_accessed?: number; }
interface GitInfo { is_git: boolean; branch: string; dirty: boolean; change_count: number; changes: { status: string; file: string }[]; last_commit?: { hash: string; message: string; ago: string } }
interface SearchResult { file: string; line: number; text: string; relative: string; }

// ── API helpers ──────────────────────────────────────────────────────────────
async function api(path: string, opts?: RequestInit) {
  const r = await fetch(`${API_BASE}${path}`, opts);
  if (!r.ok) {
    console.error(`[api] HTTP ${r.status} for ${path}`);
    return { success: false, error: `HTTP ${r.status}` };
  }
  try {
    return await r.json();
  } catch {
    console.error(`[api] Invalid JSON for ${path}`);
    return { success: false, error: 'Invalid JSON response' };
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// AILEY CODE MODE — Full IDE Interface v2.0
// Features: Monaco Editor, xterm.js Terminal, Agentic Coding, Git, Search
// Styled: Ailey dark punk — black, rose #be123c, cyan #0891b2
// ══════════════════════════════════════════════════════════════════════════════
export default function CodeModePage() {
  const router = useRouter();
  // ── State ────────────────────────────────────────────────────────────────
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [fileTreeLoading, setFileTreeLoading] = useState(false);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());

  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);

  // Terminal state (plaintext — xterm.js would require WebSocket which static export can't do)
  const [termOutput, setTermOutput] = useState<string[]>(['$ Ailey Code Terminal bereit.\n']);
  const [termInput, setTermInput] = useState('');
  const [termBusy, setTermBusy] = useState(false);
  const [termVisible, setTermVisible] = useState(true);
  const [termHistory, setTermHistory] = useState<string[]>([]);
  const [termHistoryIdx, setTermHistoryIdx] = useState(-1);

  // Chat
  const [chatVisible, setChatVisible] = useState(true);
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([
    { id: 'welcome', role: 'ai', content: 'Hey! 👋 Ich bin Ailey im **Code-Modus**. Ich sehe deinen Code und kann dir helfen — erklären, debuggen, refactoren. Ich kann auch Dateien direkt bearbeiten oder Befehle ausführen. Frag einfach!', ts: Date.now() }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [chatMode, setChatMode] = useState<'fragen' | 'bearbeiten' | 'agent'>('bearbeiten');

  // Agent Loop state
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentTaskId, setAgentTaskId] = useState<string | null>(null);
  const [agentSteps, setAgentSteps] = useState<{event: string; data: any; ts: number}[]>([]);
  const [agentPlan, setAgentPlan] = useState<{steps: {id: number; title: string; status: string; comment?: string}[]} | null>(null);
  const [agentActivities, setAgentActivities] = useState<{icon: string; label: string; success: boolean; detail?: string; ts: number}[]>([]);

  // Web Preview
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);

  // Project
  const [codeModeActive, setCodeModeActive] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [showNewProject, setShowNewProject] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState('standard');
  const [deletingProject, setDeletingProject] = useState<string | null>(null);

  // File operations
  const [newFileName, setNewFileName] = useState('');
  const [newFileDir, setNewFileDir] = useState<string | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [dragOverPath, setDragOverPath] = useState<string | null>(null);
  const [diffView, setDiffView] = useState<{ path: string; oldContent: string; newContent: string } | null>(null);

  // Git
  const [gitInfo, setGitInfo] = useState<GitInfo | null>(null);

  // Search
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchTruncated, setSearchTruncated] = useState(false);

  // Sidebar panel
  const [sidePanel, setSidePanel] = useState<'explorer' | 'search' | 'git' | 'ftp' | 'settings'>('explorer');

  // FTP/SFTP
  const [ftpConnected, setFtpConnected] = useState(false);
  const [ftpHost, setFtpHost] = useState('');
  const [ftpUser, setFtpUser] = useState('');
  const [ftpPass, setFtpPass] = useState('');
  const [ftpPort, setFtpPort] = useState('22');
  const [ftpProtocol, setFtpProtocol] = useState<'sftp' | 'ftp'>('sftp');
  const [ftpRemotePath, setFtpRemotePath] = useState('/');
  const [ftpFiles, setFtpFiles] = useState<{ name: string; is_dir: boolean; size?: number }[]>([]);
  const [ftpBusy, setFtpBusy] = useState(false);
  const [ftpError, setFtpError] = useState('');

  // Coder model (Qwen2.5-Coder — autocomplete + lint)
  // Persist settings in localStorage
  const [coderAutocomplete, setCoderAutocomplete] = useState(() => {
    if (typeof window !== 'undefined') { const v = localStorage.getItem('ailey-code-autocomplete'); return v !== null ? v === 'true' : true; } return true;
  });
  const [coderLint, setCoderLint] = useState(() => {
    if (typeof window !== 'undefined') { const v = localStorage.getItem('ailey-code-lint'); return v !== null ? v === 'true' : true; } return true;
  });
  const [coderLoaded, setCoderLoaded] = useState(false);
  const [coderBusy, setCoderBusy] = useState(false);

  // Generation settings (token limits per code chat mode)
  const [codeGenSettings, setCodeGenSettings] = useState<Record<string,number>>({code_ask:1500, code_edit:2500, code_agent:2000});
  const codeGenLoaded = useRef(false);
  async function loadCodeGenSettings() {
    try {
      const r = await fetch(`${API_BASE}/api/admin/generation-settings`);
      if (r.ok) { const j = await r.json(); if (j.success) { setCodeGenSettings(prev => ({...prev, ...j.settings})); codeGenLoaded.current = true; } }
    } catch {}
  }
  async function updateCodeGenSetting(key: string, value: number) {
    setCodeGenSettings(prev => ({...prev, [key]: value}));
    try { await fetch(`${API_BASE}/api/admin/generation-settings`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({[key]: value}) }); } catch {}
  }
  useEffect(() => { if (!codeGenLoaded.current) loadCodeGenSettings(); }, []);
  // Unified theme — synced with chat via single localStorage key
  const uiToEditor: Record<string, 'ailey-dark'|'cyber-punk'|'vs-dark'|'hc-black'|'vs'> = { dark: 'ailey-dark', cyber: 'cyber-punk', rainbowpunk: 'ailey-dark', ailey: 'cyber-punk', light: 'vs' };
  const editorToUi: Record<string, 'dark'|'cyber'|'rainbowpunk'|'ailey'|'light'> = { 'ailey-dark': 'dark', 'cyber-punk': 'cyber', 'vs-dark': 'dark', 'hc-black': 'dark', 'vs': 'light' };
  const [editorTheme, setEditorTheme] = useState<'ailey-dark' | 'cyber-punk' | 'vs-dark' | 'hc-black' | 'vs'>(() => {
    if (typeof window !== 'undefined') {
      // Read unified theme key first, fallback to legacy code-specific key
      const unified = localStorage.getItem('ailey-ui-theme');
      if (unified && uiToEditor[unified]) return uiToEditor[unified];
      const v = localStorage.getItem('ailey-code-theme');
      if (v && ['ailey-dark','cyber-punk','vs-dark','hc-black','vs'].includes(v)) return v as any;
    }
    return 'ailey-dark';
  });
  // Apply CSS classes on mount based on theme
  useEffect(() => {
    const ui = editorToUi[editorTheme] || 'dark';
    const uiStored = localStorage.getItem('ailey-ui-theme') || 'dark';
    document.documentElement.classList.toggle('dark', ui !== 'light');
    document.documentElement.classList.toggle('cyber', ui === 'cyber' || uiStored === 'ailey');
    document.documentElement.classList.toggle('rainbowpunk', uiStored === 'rainbowpunk');
    document.documentElement.classList.remove('ailey-mood', 'steampunk');
    document.documentElement.removeAttribute('data-ailey-mood');
  }, [editorTheme]);

  // Theme-aware accent color for all themes
  const isCyber = editorTheme === 'cyber-punk';
  const themeAccents: Record<string, string> = {
    'ailey-dark': '#be123c',
    'cyber-punk': '#00d4aa',
    'vs-dark': '#007acc',
    'hc-black': '#f38518',
    'vs': '#007acc',
  };
  const accent = themeAccents[editorTheme] || '#be123c';

  // ── System Stats ─────────────────────────────────────────────────────
  interface SysStats {
    cpu: { percent: number }; ram: { used_gb: number; total_gb: number; percent: number };
    temperature: { cpu_temp_c: number | null; thermal_pressure: string };
    thermal_level: number; model: { status: string }; idle_thinker: { enabled: boolean };
  }
  const [sysStats, setSysStats] = useState<SysStats | null>(null);
  const [showStats, setShowStats] = useState(false);
  useEffect(() => {
    let active = true;
    async function poll() {
      try {
        const r = await fetch(`${API_BASE}/api/system/stats`);
        if (r.ok && active) { const j = await r.json(); if (j.success) setSysStats(j); }
      } catch {}
    }
    poll();
    const iv = setInterval(poll, 10000);
    return () => { active = false; clearInterval(iv); };
  }, []);

  // ── Mobile responsiveness ─────────────────────────────────────────────
  const [isMobile, setIsMobile] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileChatOpen, setMobileChatOpen] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      setIsMobile(e.matches);
      if (e.matches) { setChatVisible(false); setTermVisible(false); }
    };
    handler(mq);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const [diagnostics, setDiagnostics] = useState<{ line: number; severity: string; message: string; file?: string }[]>([]);
  const [lintBusy, setLintBusy] = useState(false);
  const [errorsVisible, setErrorsVisible] = useState(false);
  const lintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lintBusyRef = useRef(false);
  const lintAbortRef = useRef<AbortController | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const completionProviderRef = useRef<any>(null);

  // Refs
  const termRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const autosaveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Chat scroll nav helpers
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const [showNav, setShowNav] = useState(false);
  const _navTimer = useRef<number | null>(null);
  const lastScrollTop = useRef<number | null>(null);
  const onChatScroll = useCallback(() => {
    const el = chatScrollRef.current;
    if(!el) return;
    const st = el.scrollTop;
    const prev = lastScrollTop.current ?? st;
    const delta = prev - st; // positive when scrolling up
    lastScrollTop.current = st;
    if(delta > 10) {
      setShowNav(true);
      if(_navTimer.current) window.clearTimeout(_navTimer.current);
      _navTimer.current = window.setTimeout(() => setShowNav(false), 1600);
    }
  }, []);
  const leavingRef = useRef(false); // Prevents double-deactivate
  const openTabsRef = useRef(openTabs); // Always up-to-date for callbacks
  const chatMessagesRef = useRef(chatMessages); // For deactivateCodeMode cleanup
  const activeProjectRef = useRef(activeProject); // For deactivateCodeMode cleanup

  // Keep refs in sync
  useEffect(() => { openTabsRef.current = openTabs; }, [openTabs]);
  useEffect(() => { chatMessagesRef.current = chatMessages; }, [chatMessages]);
  useEffect(() => { activeProjectRef.current = activeProject; }, [activeProject]);

  // ── Unsaved files helper ───────────────────────────────────────────────
  const getUnsavedTabs = useCallback(() => openTabs.filter(t => t.dirty), [openTabs]);

  async function autosaveAll(): Promise<boolean> {
    /** Save all dirty tabs via batch endpoint. Returns true if all saved. */
    const dirty = openTabs.filter(t => t.dirty);
    if (dirty.length === 0) return true;
    try {
      const r = await api('/api/code/autosave', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: dirty.map(t => ({ path: t.path, content: t.content })) })
      });
      if (r.success && r.saved?.length) {
        const savedSet = new Set(r.saved as string[]);
        setOpenTabs(prev => prev.map(t => savedSet.has(t.path) ? { ...t, dirty: false } : t));
        return r.errors?.length === 0;
      }
    } catch {}
    return false;
  }

  // ── Activate/Deactivate Code Mode ──────────────────────────────────────
  useEffect(() => {
    leavingRef.current = false;
    activateCodeMode();

    // Warn about unsaved files on page close + deactivate code mode
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Autosave via beacon (batch save) — use ref to get latest tabs
      const dirty = openTabsRef.current.filter(t => t.dirty);
      if (dirty.length > 0) {
        // Try to save via sendBeacon (fire-and-forget)
        navigator.sendBeacon(
          `${API_BASE}/api/code/autosave`,
          JSON.stringify({ files: dirty.map(t => ({ path: t.path, content: t.content })) })
        );
      }
      // Deactivate code mode
      navigator.sendBeacon(`${API_BASE}/api/code/mode`, JSON.stringify({ active: false }));
    };
    window.addEventListener('beforeunload', handleBeforeUnload);

    // Periodic autosave every 30 seconds
    autosaveTimerRef.current = setInterval(() => {
      const dirty = openTabsRef.current.filter(t => t.dirty);
      if (dirty.length > 0) {
        fetch(`${API_BASE}/api/code/autosave`, {
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

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      if (autosaveTimerRef.current) clearInterval(autosaveTimerRef.current);
      if (!leavingRef.current) deactivateCodeMode();
    };
  }, []);

  async function activateCodeMode() {
    try {
      await api('/api/code/mode', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: true }) });
      setCodeModeActive(true);
    } catch { setCodeModeActive(true); }
    loadProjects();
  }

  async function deactivateCodeMode() {
    try {
      // Send session data for project meta + context injection
      const project = activeProjectRef.current || activeProject;
      const sessionData: any = { active: false };
      if (project) {
        sessionData.project = project;
        sessionData.open_files = (openTabsRef.current || openTabs).map(t => t.name);
        // Send last chat messages for topic tracking
        sessionData.chat_messages = (chatMessagesRef.current || chatMessages)
          .filter(m => m.role === 'user' || m.role === 'ai')
          .slice(-10)
          .map(m => ({ role: m.role, content: m.content.substring(0, 200) }));
      }
      await api('/api/code/mode', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sessionData)
      });
    } catch { }
  }

  /** Leave Code Mode → navigate to main page. Autosaves unsaved files first. */
  async function leaveCodeMode() {
    const dirty = openTabs.filter(t => t.dirty);
    if (dirty.length > 0) {
      // Try autosave first
      const allSaved = await autosaveAll();
      if (!allSaved) {
        // Some files failed to save — ask user
        const fileNames = dirty.map(t => t.name).join(', ');
        if (!confirm(`${dirty.length} Datei(en) nicht gespeichert: ${fileNames}\n\nTrotzdem verlassen? (Änderungen könnten verloren gehen)`)) {
          return; // User cancelled
        }
      }
    }
    // Clean up coder state
    if (completionProviderRef.current) {
      completionProviderRef.current.dispose();
      completionProviderRef.current = null;
    }
    if (lintTimerRef.current) clearTimeout(lintTimerRef.current);
    if (autosaveTimerRef.current) clearInterval(autosaveTimerRef.current);
    // Clear Monaco markers
    if (monacoRef.current && editorRef.current) {
      const model = editorRef.current.getModel();
      if (model) monacoRef.current.editor.setModelMarkers(model, 'ailey-coder', []);
    }
    setDiagnostics([]);
    leavingRef.current = true;
    // Fire-and-forget: don't block navigation on slow backend calls (model unload, RAG ingest)
    deactivateCodeMode().catch(()=>{});
    router.push('/');
  }

  // ── Projects ───────────────────────────────────────────────────────────
  async function loadProjects() {
    try {
      const r = await api('/api/code/projects');
      if (r.success) setProjects(r.projects || []);
    } catch { }
  }

  async function createProject() {
    if (!newProjectName.trim()) return;
    try {
      const r = await api('/api/code/projects', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProjectName.trim(), template: selectedTemplate })
      });
      if (r && r.success) {
        setShowNewProject(false);
        setNewProjectName('');
        setSelectedTemplate('standard');
        loadProjects();
        openProject(r.project.path);
      } else {
        console.error('[createProject] Error:', r?.error || 'Unbekannter Fehler');
      }
    } catch (e) {
      console.error('[createProject] Fetch error:', e);
    }
  }

  async function deleteProject(path: string, name: string) {
    if (!confirm(`Projekt "${name}" wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`)) return;
    setDeletingProject(path);
    try {
      const r = await api('/api/code/projects', {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      if (r && r.success) {
        loadProjects();
        if (activeProject === path) { setActiveProject(null); setOpenTabs([]); setActiveTab(null); }
      } else {
        alert(r?.error || 'Löschen fehlgeschlagen');
      }
    } catch (e) {
      console.error('[deleteProject] Fetch error:', e);
    } finally {
      setDeletingProject(null);
    }
  }

  async function openProject(path: string) {
    setActiveProject(path);
    setOpenTabs([]);
    setActiveTab(null);
    setGitInfo(null);
    loadFileTree(path);
    loadGitStatus(path);
  }

  // ── File Tree ──────────────────────────────────────────────────────────
  async function loadFileTree(projectPath?: string) {
    const p = projectPath || activeProject;
    if (!p) return;
    setFileTreeLoading(true);
    try {
      const r = await api(`/api/code/files?path=${encodeURIComponent(p)}`);
      if (r && r.success) setFileTree(r.tree || []);
      else console.error('[loadFileTree] Error:', r?.error || 'Unbekannter Fehler');
    } catch (e) {
      console.error('[loadFileTree] Fetch error:', e);
    }
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
      const r = await api(`/api/code/file?path=${encodeURIComponent(node.path)}`);
      if (r && r.success) {
        const tab: OpenTab = { path: node.path, name: node.name, content: r.content || '', dirty: false, language: getLang(node.name) };
        setOpenTabs(prev => [...prev, tab]);
        setActiveTab(node.path);
      } else {
        console.error('[openFile] API error:', r?.error || 'Unbekannter Fehler');
      }
    } catch (e) {
      console.error('[openFile] Fetch error:', e);
    }
  }

  async function openFilePath(filePath: string, line?: number) {
    // Open a file by path (used from search results)
    const name = filePath.split('/').pop() || filePath;
    const existing = openTabs.find(t => t.path === filePath);
    if (existing) {
      setActiveTab(filePath);
      if (line && editorRef.current) {
        setTimeout(() => {
          editorRef.current?.revealLineInCenter(line);
          editorRef.current?.setPosition({ lineNumber: line, column: 1 });
        }, 100);
      }
      return;
    }
    try {
      const r = await api(`/api/code/file?path=${encodeURIComponent(filePath)}`);
      if (r && r.success) {
        const tab: OpenTab = { path: filePath, name, content: r.content || '', dirty: false, language: getLang(name) };
        setOpenTabs(prev => [...prev, tab]);
        setActiveTab(filePath);
        if (line) {
          setTimeout(() => {
            editorRef.current?.revealLineInCenter(line);
            editorRef.current?.setPosition({ lineNumber: line, column: 1 });
          }, 200);
        }
      } else {
        console.error('[openFilePath] API error:', r?.error || 'Unbekannter Fehler');
      }
    } catch (e) {
      console.error('[openFilePath] Fetch error:', e);
    }
  }

  async function saveFile(path: string) {
    const tab = openTabs.find(t => t.path === path);
    if (!tab) return;
    try {
      const r = await api('/api/code/file', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, content: tab.content }) });
      if (r.success) {
        setOpenTabs(prev => prev.map(t => t.path === path ? { ...t, dirty: false } : t));
        // Trigger lint after save
        if (coderLint) runLint(path, tab.content, tab.name, tab.language);
      }
    } catch { }
  }

  async function createFile(dir: string, name: string) {
    if (!name.trim()) return;
    try {
      const fullPath = dir ? `${dir}/${name.trim()}` : `${activeProject}/${name.trim()}`;
      const r = await api('/api/code/file', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: fullPath, content: null, project: activeProject }) });
      loadFileTree();
      setNewFileName('');
      setNewFileDir(null);
      // Auto-open new file with template content
      if (r.success && r.content !== undefined) {
        const ext = name.split('.').pop()?.toLowerCase() || '';
        const lang = { py: 'python', js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript', html: 'html', css: 'css', scss: 'scss', json: 'json', md: 'markdown', rs: 'rust', sh: 'shell', yaml: 'yaml', yml: 'yaml', toml: 'toml' }[ext] || 'plaintext';
        setOpenTabs(prev => [...prev.filter(t => t.path !== fullPath), { path: fullPath, name: name.trim(), content: r.content, dirty: false, language: lang }]);
        setActiveTab(fullPath);
      }
    } catch { }
  }

  async function createFolder(dir: string, name: string) {
    if (!name.trim()) return;
    try {
      const fullPath = dir ? `${dir}/${name.trim()}` : `${activeProject}/${name.trim()}`;
      await api('/api/code/mkdir', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: fullPath }) });
      loadFileTree();
      setNewFileName('');
      setNewFileDir(null);
    } catch { }
  }

  async function deleteFile(path: string) {
    if (!confirm(`"${path.split('/').pop()}" wirklich löschen?`)) return;
    try {
      await api('/api/code/file', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
      setOpenTabs(prev => prev.filter(t => t.path !== path));
      if (activeTab === path) setActiveTab(openTabs.find(t => t.path !== path)?.path || null);
      loadFileTree();
    } catch { }
  }

  async function renameFile(oldPath: string, newName: string) {
    if (!newName.trim()) { setRenamingPath(null); return; }
    const dir = oldPath.substring(0, oldPath.lastIndexOf('/'));
    const newPath = `${dir}/${newName.trim()}`;
    try {
      const r = await api('/api/code/rename', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_path: oldPath, new_path: newPath })
      });
      if (r.success) {
        // Update open tabs if the renamed file was open
        setOpenTabs(prev => prev.map(t => t.path === oldPath ? { ...t, path: r.new_path, name: newName.trim(), language: getLang(newName.trim()) } : t));
        if (activeTab === oldPath) setActiveTab(r.new_path);
        loadFileTree();
      }
    } catch { }
    setRenamingPath(null);
    setRenameValue('');
  }

  async function moveFile(sourcePath: string, targetDir: string) {
    const fileName = sourcePath.split('/').pop() || '';
    const newPath = `${targetDir}/${fileName}`;
    if (sourcePath === newPath || sourcePath === targetDir) return;
    try {
      const r = await api('/api/code/rename', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_path: sourcePath, new_path: newPath })
      });
      if (r.success) {
        setOpenTabs(prev => prev.map(t => t.path === sourcePath ? { ...t, path: r.new_path, name: fileName } : t));
        if (activeTab === sourcePath) setActiveTab(r.new_path);
        loadFileTree();
      }
    } catch { }
    setDragOverPath(null);
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

  // ── Git ────────────────────────────────────────────────────────────────
  async function loadGitStatus(projectPath?: string) {
    const p = projectPath || activeProject;
    if (!p) return;
    try {
      const r = await api(`/api/code/git?path=${encodeURIComponent(p)}`);
      if (r.success) setGitInfo(r as GitInfo);
    } catch { }
  }

  // ── Search ─────────────────────────────────────────────────────────────
  async function runSearch() {
    if (!searchQuery.trim() || !activeProject) return;
    setSearchBusy(true);
    setSearchResults([]);
    try {
      const r = await api('/api/code/search', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, path: activeProject })
      });
      if (r.success) {
        setSearchResults(r.results || []);
        setSearchTruncated(r.truncated || false);
      }
    } catch { }
    setSearchBusy(false);
  }

  // ── Terminal ───────────────────────────────────────────────────────────
  async function execCommand(cmd: string) {
    if (!cmd.trim() || termBusy) return;
    setTermOutput(prev => [...prev, `$ ${cmd}\n`]);
    setTermInput('');
    setTermHistory(prev => [cmd, ...prev.slice(0, 50)]);
    setTermHistoryIdx(-1);
    setTermBusy(true);
    try {
      const r = await api('/api/code/exec', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: cmd, cwd: activeProject || undefined }) });
      if (r.success) {
        const out = (r.stdout || '') + (r.stderr ? `\n⚠️ ${r.stderr}` : '');
        setTermOutput(prev => [...prev, out ? out + '\n' : '(kein Output)\n']);
      } else {
        setTermOutput(prev => [...prev, `❌ ${r.error || 'Fehler'}\n`]);
      }
    } catch (e: any) {
      setTermOutput(prev => [...prev, `❌ ${e?.message || 'Netzwerkfehler'}\n`]);
    }
    setTermBusy(false);
    setTimeout(() => termRef.current?.scrollTo(0, termRef.current.scrollHeight), 50);
  }

  function handleTermKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { execCommand(termInput); }
    else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (termHistory.length > 0) {
        const newIdx = Math.min(termHistoryIdx + 1, termHistory.length - 1);
        setTermHistoryIdx(newIdx);
        setTermInput(termHistory[newIdx]);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (termHistoryIdx > 0) {
        const newIdx = termHistoryIdx - 1;
        setTermHistoryIdx(newIdx);
        setTermInput(termHistory[newIdx]);
      } else {
        setTermHistoryIdx(-1);
        setTermInput('');
      }
    }
  }

  // ── Agentic Actions ───────────────────────────────────────────────────
  async function acceptAction(msgId: string, action: AgentAction) {
    try {
      const r = await api('/api/code/action', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: action.type, path: action.path, content: action.content, command: action.command, cwd: activeProject || undefined, patch_count: action.patch_count })
      });
      if (r.success) {
        // Update action status in chat
        setChatMessages(prev => prev.map(msg => {
          if (msg.id !== msgId) return msg;
          return { ...msg, actions: msg.actions?.map(a => a.id === action.id ? { ...a, status: 'accepted' } : a) };
        }));

        if ((action.type === 'edit_file' || action.type === 'create_file' || action.type === 'patch_file') && action.path) {
          // Refresh the file in editor if open
          const tab = openTabs.find(t => t.path === action.path);
          if (tab && action.content) {
            setOpenTabs(prev => prev.map(t => t.path === action.path ? { ...t, content: action.content!, dirty: false } : t));
            // Directly update Monaco editor model if this is the active tab
            if (activeTab === action.path && editorRef.current && monacoRef.current) {
              const model = editorRef.current.getModel();
              if (model && model.getValue() !== action.content) {
                // Use pushEditOperations to preserve undo stack
                const fullRange = model.getFullModelRange();
                editorRef.current.executeEdits('ailey-accept', [{
                  range: fullRange,
                  text: action.content!,
                  forceMoveMarkers: true,
                }]);
              }
            }
          } else if (action.type === 'create_file' && action.content) {
            // Auto-open newly created file
            const name = action.path.split('/').pop() || 'new';
            const lang = getLang(name);
            setOpenTabs(prev => [...prev, { path: action.path!, name, content: action.content!, dirty: false, language: lang }]);
            setActiveTab(action.path!);
          } else if ((action.type === 'edit_file' || action.type === 'patch_file') && action.content && !tab) {
            // File not open yet — open it with the new content
            const name = action.path.split('/').pop() || 'file';
            const lang = getLang(name);
            setOpenTabs(prev => [...prev, { path: action.path!, name, content: action.content!, dirty: false, language: lang }]);
            setActiveTab(action.path!);
          }
          loadFileTree();
        }
        if (action.type === 'run_command') {
          // Show output in terminal
          const out = (r.stdout || '') + (r.stderr ? `\n⚠️ ${r.stderr}` : '');
          setTermOutput(prev => [...prev, `$ ${action.command}\n`, out ? out + '\n' : '(kein Output)\n']);
          setTermVisible(true);
        }
      }
    } catch { }
  }

  function rejectAction(msgId: string, actionId: string) {
    setChatMessages(prev => prev.map(msg => {
      if (msg.id !== msgId) return msg;
      return { ...msg, actions: msg.actions?.map(a => a.id === actionId ? { ...a, status: 'rejected' } : a) };
    }));
  }

  // ── Diff Preview for agentic edits ────────────────────────────────────
  async function loadDiffForAction(action: AgentAction) {
    if (!action.path || !action.content) return;
    try {
      const r = await api(`/api/code/file?path=${encodeURIComponent(action.path)}`);
      const oldContent = r.success ? (r.content || '') : '';
      setDiffView({ path: action.path, oldContent, newContent: action.content });
    } catch {
      setDiffView({ path: action.path, oldContent: '(Datei nicht gefunden — wird neu erstellt)', newContent: action.content });
    }
  }

  // ── File Download/Export ──────────────────────────────────────────────
  function downloadFile(path: string, content: string, filename: string) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ── Project Export (ZIP) ──────────────────────────────────────────────
  async function handleExportProject() {
    if (!activeProject || exportBusy) return;
    setExportBusy(true);
    try {
      const r = await api('/api/tools/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: 'export_project', arguments: { project_root: activeProject } }),
      });
      if (r.download_url) {
        window.open(`${API_BASE}${r.download_url}`, '_blank');
      } else if (r.error) {
        alert(`Export fehlgeschlagen: ${r.error}`);
      }
    } catch (e) {
      console.error('Export error:', e);
    } finally {
      setExportBusy(false);
    }
  }

  // ── Project Preview (Dev Server) ──────────────────────────────────────
  async function handlePreviewProject() {
    if (!activeProject || previewBusy) return;
    setPreviewBusy(true);
    try {
      const r = await api('/api/tools/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: 'preview_web', arguments: { project_root: activeProject } }),
      });
      if (r.url) {
        setPreviewUrl(r.url);
        setPreviewVisible(true);
      } else if (r.error) {
        alert(`Preview fehlgeschlagen: ${r.error}`);
      }
    } catch (e) {
      console.error('Preview error:', e);
    } finally {
      setPreviewBusy(false);
    }
  }

  // ── FTP/SFTP ──────────────────────────────────────────────────────────
  async function ftpConnect() {
    setFtpBusy(true);
    setFtpError('');
    try {
      const r = await api('/api/code/ftp/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: ftpHost, user: ftpUser, password: ftpPass, port: parseInt(ftpPort), protocol: ftpProtocol })
      });
      if (r.success) {
        setFtpConnected(true);
        ftpListDir(ftpRemotePath);
      } else {
        setFtpError(r.error || 'Verbindung fehlgeschlagen');
      }
    } catch (e: any) {
      setFtpError(e?.message || 'Netzwerkfehler');
    }
    setFtpBusy(false);
  }

  async function ftpDisconnect() {
    try { await api('/api/code/ftp/disconnect', { method: 'POST' }); } catch {}
    setFtpConnected(false);
    setFtpFiles([]);
    setFtpRemotePath('/');
  }

  async function ftpListDir(remotePath: string) {
    setFtpBusy(true);
    try {
      const r = await api(`/api/code/ftp/list?path=${encodeURIComponent(remotePath)}`);
      if (r.success) {
        setFtpFiles(r.files || []);
        setFtpRemotePath(remotePath);
      } else {
        setFtpError(r.error || 'Fehler beim Lesen');
      }
    } catch {}
    setFtpBusy(false);
  }

  async function ftpUploadFile(localPath: string, remotePath: string) {
    setFtpBusy(true);
    try {
      const r = await api('/api/code/ftp/upload', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ local_path: localPath, remote_path: remotePath })
      });
      if (r.success) {
        setTermOutput(prev => [...prev, `✅ Upload: ${localPath.split('/').pop()} → ${remotePath}\n`]);
        ftpListDir(ftpRemotePath);
      } else {
        setFtpError(r.error || 'Upload fehlgeschlagen');
      }
    } catch {}
    setFtpBusy(false);
  }

  async function ftpDownloadFile(remotePath: string, localDir: string) {
    setFtpBusy(true);
    try {
      const r = await api('/api/code/ftp/download', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remote_path: remotePath, local_dir: localDir })
      });
      if (r.success) {
        setTermOutput(prev => [...prev, `✅ Download: ${remotePath} → ${localDir}\n`]);
        loadFileTree();
      } else {
        setFtpError(r.error || 'Download fehlgeschlagen');
      }
    } catch {}
    setFtpBusy(false);
  }

  // ── Coder Model (Qwen2.5-Coder) ──────────────────────────────────────
  // Load coder settings on mount — poll until coder model is loaded
  useEffect(() => {
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;
    async function loadCoderSettings() {
      try {
        const r = await api('/api/code/coder/settings');
        if (r.success) {
          setCoderAutocomplete(r.autocomplete_enabled);
          setCoderLint(r.lint_enabled);
          setCoderLoaded(r.model_loaded);
          // If not loaded yet, retry every 2s (up to 15 attempts = 30s)
          if (!r.model_loaded && attempts < 15) {
            attempts++;
            pollTimer = setTimeout(loadCoderSettings, 2000);
          }
        }
      } catch {}
    }
    if (codeModeActive) loadCoderSettings();
    return () => { if (pollTimer) clearTimeout(pollTimer); };
  }, [codeModeActive]);

  async function toggleCoderSetting(key: 'autocomplete' | 'lint', value: boolean) {
    try {
      const r = await api('/api/code/coder/settings', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value })
      });
      if (r.success) {
        setCoderAutocomplete(r.autocomplete_enabled);
        setCoderLint(r.lint_enabled);
        setCoderLoaded(r.model_loaded);
        localStorage.setItem('ailey-code-autocomplete', String(r.autocomplete_enabled));
        localStorage.setItem('ailey-code-lint', String(r.lint_enabled));
      }
    } catch {}
  }

  async function coderControl(action: 'load' | 'unload' | 'reload') {
    setCoderBusy(true);
    try {
      const r = await api('/api/code/coder/control', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      if (r.success !== undefined) setCoderLoaded(!!r.model_loaded);
    } catch {}
    setCoderBusy(false);
  }

  function switchTheme(theme: 'ailey-dark' | 'cyber-punk' | 'vs-dark' | 'hc-black' | 'vs') {
    setEditorTheme(theme);
    const ui = editorToUi[theme] || 'dark';
    localStorage.setItem('ailey-code-theme', theme);
    localStorage.setItem('ailey-ui-theme', ui);
    document.documentElement.classList.toggle('dark', ui !== 'light');
    document.documentElement.classList.toggle('cyber', ui === 'cyber');
    document.documentElement.classList.toggle('rainbowpunk', ui === 'rainbowpunk');
    document.documentElement.classList.remove('ailey-mood', 'steampunk');
    document.documentElement.removeAttribute('data-ailey-mood');
    if (monacoRef.current) monacoRef.current.editor.setTheme(theme);
  }

  // Auto-lint on idle (2 seconds after last edit, or on file open)
  useEffect(() => {
    if (!coderLint || !activeTab) return;
    const tab = openTabs.find(t => t.path === activeTab);
    if (!tab) return;

    if (lintTimerRef.current) clearTimeout(lintTimerRef.current);
    lintTimerRef.current = setTimeout(() => {
      runLint(tab.path, tab.content, tab.name, tab.language);
    }, tab.dirty ? 2000 : 500); // Faster initial lint on file open

    return () => { if (lintTimerRef.current) clearTimeout(lintTimerRef.current); };
  }, [openTabs, activeTab, coderLint]);

  async function runLint(path: string, code: string, filename: string, language: string) {
    // Skip if already running — use ref to avoid stale closure
    if (lintBusyRef.current) return;
    lintBusyRef.current = true;
    setLintBusy(true);

    // Abort previous request if still pending
    if (lintAbortRef.current) lintAbortRef.current.abort();
    const abort = new AbortController();
    lintAbortRef.current = abort;

    try {
      const r = await api('/api/code/lint', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, filename, language }),
        signal: abort.signal,
      });
      if (r.success) {
        const diags = (r.diagnostics || []).map((d: any) => ({ ...d, file: filename }));
        // Replace diagnostics for this file, keep others
        setDiagnostics(prev => [
          ...prev.filter(d => d.file !== filename),
          ...diags,
        ]);
        // Show error panel if errors found
        if (diags.some((d: any) => d.severity === 'error')) {
          setErrorsVisible(true);
        }
        // Apply Monaco markers
        if (monacoRef.current && editorRef.current) {
          const model = editorRef.current.getModel();
          if (model) {
            const markers = diags.map((d: any) => ({
              severity: d.severity === 'error' ? monacoRef.current.MarkerSeverity.Error :
                       d.severity === 'warning' ? monacoRef.current.MarkerSeverity.Warning :
                       monacoRef.current.MarkerSeverity.Info,
              message: `[Ailey Coder] ${d.message}`,
              startLineNumber: d.line,
              startColumn: 1,
              endLineNumber: d.line,
              endColumn: 1000,
            }));
            monacoRef.current.editor.setModelMarkers(model, 'ailey-coder', markers);
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') console.error('[Lint]', e);
    }
    lintBusyRef.current = false;
    setLintBusy(false);
  }

  // Register Monaco inline completion provider
  useEffect(() => {
    if (!monacoRef.current || !coderAutocomplete) {
      // Dispose existing provider if autocomplete disabled
      if (completionProviderRef.current) {
        completionProviderRef.current.dispose();
        completionProviderRef.current = null;
      }
      return;
    }

    const monaco = monacoRef.current;

    // Register inline completions provider
    completionProviderRef.current = monaco.languages.registerInlineCompletionsProvider(
      { pattern: '**' }, // all languages
      {
        provideInlineCompletions: async (model: any, position: any) => {
          // Don't complete on empty lines or very short content
          const fullText = model.getValue();
          if (fullText.length < 10) return { items: [] };

          // Get code before and after cursor
          const offset = model.getOffsetAt(position);
          const codeBefore = fullText.substring(0, offset);
          const codeAfter = fullText.substring(offset);

          // Don't trigger on every keystroke — debounce via backend
          if (codeBefore.length < 5) return { items: [] };

          try {
            const r = await fetch(`${API_BASE}/api/code/complete`, {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                code_before: codeBefore,
                code_after: codeAfter,
                language: model.getLanguageId() || 'plaintext',
              })
            });
            const j = await r.json();
            if (j.success && j.completion) {
              return {
                items: [{
                  insertText: j.completion,
                  range: {
                    startLineNumber: position.lineNumber,
                    startColumn: position.column,
                    endLineNumber: position.lineNumber,
                    endColumn: position.column,
                  },
                }],
              };
            }
          } catch {}
          return { items: [] };
        },
        freeInlineCompletions: () => {},
      }
    );

    return () => {
      if (completionProviderRef.current) {
        completionProviderRef.current.dispose();
        completionProviderRef.current = null;
      }
    };
  }, [coderAutocomplete, monacoRef.current]);

  // ── HTML/JSX Auto-Closing Tag Suggestion ──────────────────────────────
  // When user types "<" in HTML/JSX/TSX, suggest the closing tag for the
  // nearest unclosed opening tag. Shown as ghost text (Tab to accept).
  const closingTagProviderRef = useRef<any>(null);
  useEffect(() => {
    if (!monacoRef.current) return;
    const monaco = monacoRef.current;
    const htmlLangs = ['html', 'javascript', 'javascriptreact', 'typescript', 'typescriptreact', 'xml', 'svg', 'vue', 'php'];

    // Dispose previous
    if (closingTagProviderRef.current) {
      closingTagProviderRef.current.dispose();
      closingTagProviderRef.current = null;
    }

    closingTagProviderRef.current = monaco.languages.registerInlineCompletionsProvider(
      htmlLangs.map((l: string) => ({ language: l })),
      {
        provideInlineCompletions: async (model: any, position: any) => {
          const textUntilPos = model.getValueInRange({
            startLineNumber: 1, startColumn: 1,
            endLineNumber: position.lineNumber, endColumn: position.column,
          });

          // Only trigger when user just typed "<" (last char)
          if (!textUntilPos.endsWith('<')) return { items: [] };

          // Self-closing / void tags that never need a closing tag
          const voidTags = new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);

          // Find the nearest unclosed opening tag by scanning backwards
          // Simple stack-based approach
          const tagRegex = /<\/?([a-zA-Z][a-zA-Z0-9.:-]*)\b[^>]*\/?>/g;
          const stack: string[] = [];
          let match;
          while ((match = tagRegex.exec(textUntilPos.slice(0, -1))) !== null) {
            const fullMatch = match[0];
            const tagName = match[1];
            // Skip self-closing tags and void tags
            if (fullMatch.endsWith('/>') || voidTags.has(tagName.toLowerCase())) continue;
            if (fullMatch.startsWith('</')) {
              // Closing tag: pop matching from stack
              const idx = stack.lastIndexOf(tagName);
              if (idx !== -1) stack.splice(idx, 1);
            } else {
              // Opening tag
              stack.push(tagName);
            }
          }

          if (stack.length === 0) return { items: [] };

          // Suggest closing the most recent unclosed tag
          const tagToClose = stack[stack.length - 1];
          const closingText = `/${tagToClose}>`;

          return {
            items: [{
              insertText: closingText,
              range: {
                startLineNumber: position.lineNumber,
                startColumn: position.column,
                endLineNumber: position.lineNumber,
                endColumn: position.column,
              },
            }],
          };
        },
        freeInlineCompletions: () => {},
      }
    );

    return () => {
      if (closingTagProviderRef.current) {
        closingTagProviderRef.current.dispose();
        closingTagProviderRef.current = null;
      }
    };
  }, [monacoRef.current]);

  // ── Elapsed Timer component for code chat generation ─────────────────
  function CodeChatTimer({ active }: { active: boolean }) {
    const [elapsed, setElapsed] = useState(0);
    useEffect(() => {
      if (!active) { setElapsed(0); return; }
      setElapsed(0);
      const iv = setInterval(() => setElapsed(e => e + 1), 1000);
      return () => clearInterval(iv);
    }, [active]);
    if (!active || elapsed < 1) return null;
    const phases = ['Kontext sammeln', 'Generiert', 'Generiert', 'Code schreiben', 'Code schreiben', 'Fast fertig'];
    const phase = phases[Math.min(Math.floor(elapsed / 8), phases.length - 1)];
    return (
      <span className="text-[10px] text-white/25 tabular-nums">
        {phase}… {elapsed}s
      </span>
    );
  }

  // ── Ailey Code Chat ───────────────────────────────────────────────────
  async function sendCodeChat() {
    const msg = chatInput.trim();
    if (!msg || chatBusy) return;

    const currentTab = openTabs.find(t => t.path === activeTab);
    const fileContext = currentTab ? { filename: currentTab.name, language: currentTab.language, content: currentTab.content.substring(0, 4000), path: currentTab.path } : null;

    // Collect open files for broader context in bearbeiten + agent mode
    const openFilesContext = (chatMode === 'agent' || chatMode === 'bearbeiten') ? openTabs.map(t => ({
      filename: t.name, language: t.language, content: t.content.substring(0, 1500), path: t.path
    })) : [];

    const userMsg: ChatMsg = { id: `u${Date.now()}`, role: 'user', content: msg, ts: Date.now() };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setChatBusy(true);

    // ── Agent Loop Mode: Use /api/agent/run + SSE ────────────────────
    if (chatMode === 'agent') {
      setAgentRunning(true);
      setAgentSteps([]);
      setAgentPlan(null);
      setAgentActivities([]);
      const agentMsg: ChatMsg = { id: `agent${Date.now()}`, role: 'ai', content: '💜 Agent startet...', ts: Date.now(), pending: true };
      setChatMessages(prev => [...prev, agentMsg]);
      
      try {
        const r = await fetch(`${API_BASE}/api/agent/run`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task: msg,
            mode: 'code',
            project: activeProject,
            max_steps: 25,
          })
        });
        if (!r.ok) { throw new Error('Agent-Start fehlgeschlagen'); }
        const { task_id } = await r.json();
        setAgentTaskId(task_id);

        // Connect to SSE stream
        const evtSource = new EventSource(`${API_BASE}/api/agent/stream/${task_id}`);
        const steps: {event: string; data: any; ts: number}[] = [];
        let accumulatedText = '';

        evtSource.addEventListener('step', (e) => {
          const d = JSON.parse(e.data);
          steps.push({ event: 'step', data: d, ts: Date.now() });
          setAgentSteps([...steps]);
          setChatMessages(prev => prev.map(m => m.id === agentMsg.id ? { ...m, content: `💜 Agent — Schritt ${d.step}/${d.max_steps}...`, pending: true } : m));
        });

        evtSource.addEventListener('message', (e) => {
          try {
            const d = JSON.parse(e.data);
            if (d.text) {
              accumulatedText += (accumulatedText ? '\n\n' : '') + d.text;
              steps.push({ event: 'message', data: d, ts: Date.now() });
              setAgentSteps([...steps]);
            }
          } catch {}
        });

        evtSource.addEventListener('tool_action', (e) => {
          const d = JSON.parse(e.data);
          steps.push({ event: 'tool_action', data: d, ts: Date.now() });
          setAgentSteps([...steps]);
          setChatMessages(prev => prev.map(m => m.id === agentMsg.id ? { ...m, content: `🔧 ${d.tool}(${Object.keys(d.arguments || {}).join(', ')})...`, pending: true } : m));
        });

        evtSource.addEventListener('tool_result', (e) => {
          const d = JSON.parse(e.data);
          steps.push({ event: 'tool_result', data: d, ts: Date.now() });
          setAgentSteps([...steps]);
          // Refresh files if write/create/patch tools were used
          if (['write_file', 'create_file', 'patch_file', 'delete_file'].includes(d.tool)) {
            loadFileTree();
            // Refresh open tab if the modified file is open
            if (d.result?.path) {
              const tab = openTabs.find(t => t.path === d.result.path);
              if (tab) {
                fetch(`${API_BASE}/api/code/file?path=${encodeURIComponent(d.result.path)}`)
                  .then(r => r.json())
                  .then(j => {
                    if (j.success && j.content !== undefined) {
                      setOpenTabs(prev => prev.map(t => t.path === d.result.path ? { ...t, content: j.content, dirty: false } : t));
                    }
                  }).catch(() => {});
              }
            }
          }
          // Auto-open preview panel when dev server starts
          if (d.tool === 'preview_web' && d.result?.url) {
            setPreviewUrl(d.result.url);
            setPreviewVisible(true);
          }
          // Auto-download ZIP exports
          if (d.tool === 'export_project' && d.result?.download_url) {
            window.open(`${API_BASE}${d.result.download_url}`, '_blank');
          }
        });

        // ── Plan & Activity SSE events ──────────────────────────────
        evtSource.addEventListener('plan', (e) => {
          try {
            const d = JSON.parse(e.data);
            setAgentPlan(d.plan || null);
          } catch {}
        });

        evtSource.addEventListener('plan_update', (e) => {
          try {
            const d = JSON.parse(e.data);
            setAgentPlan(prev => {
              if (!prev) return prev;
              const updated = { ...prev, steps: prev.steps.map(s => {
                if (s.id === d.step_id) {
                  return { ...s, ...(d.status ? { status: d.status } : {}), ...(d.comment ? { comment: d.comment } : {}) };
                }
                return s;
              })};
              return updated;
            });
          } catch {}
        });

        evtSource.addEventListener('activity', (e) => {
          try {
            const d = JSON.parse(e.data);
            setAgentActivities(prev => [...prev, { ...d, ts: Date.now() }]);
          } catch {}
        });

        evtSource.addEventListener('thinking', (e) => {
          try {
            const d = JSON.parse(e.data);
            setChatMessages(prev => prev.map(m => m.id === agentMsg.id ? { ...m, content: `🧠 Schritt ${d.step} — denkt: _${d.text}_`, pending: true } : m));
          } catch {}
        });

        evtSource.addEventListener('done', (e) => {
          const d = JSON.parse(e.data);
          steps.push({ event: 'done', data: d, ts: Date.now() });
          setAgentSteps([...steps]);
          const summary = `✅ Agent fertig! ${d.tool_calls || 0} Tool-Aufrufe in ${d.elapsed || '?'}s`;
          const fullContent = accumulatedText ? `${accumulatedText}\n\n---\n${summary}` : summary;
          setChatMessages(prev => prev.map(m => m.id === agentMsg.id ? { ...m, content: fullContent, pending: false } : m));
          setAgentRunning(false);
          setAgentTaskId(null);
          setChatBusy(false);
          loadFileTree();
          evtSource.close();
        });

        evtSource.addEventListener('agent_error', (e) => {
          try {
            const d = JSON.parse(e.data);
            steps.push({ event: 'error', data: d, ts: Date.now() });
            setAgentSteps([...steps]);
            setChatMessages(prev => prev.map(m => m.id === agentMsg.id ? { ...m, content: `⚠️ Agent-Fehler: ${d.error}`, pending: false } : m));
          } catch {}
          setAgentRunning(false);
          setChatBusy(false);
          evtSource.close();
        });

        evtSource.addEventListener('stopped', (e) => {
          setChatMessages(prev => prev.map(m => m.id === agentMsg.id ? { ...m, content: '⛔ Agent gestoppt', pending: false } : m));
          setAgentRunning(false);
          setChatBusy(false);
          evtSource.close();
        });

        evtSource.addEventListener('finished', (e) => {
          evtSource.close();
          if (agentRunning) {
            setAgentRunning(false);
            setChatBusy(false);
          }
        });

        evtSource.onerror = () => {
          evtSource.close();
          setAgentRunning(false);
          setChatBusy(false);
        };

      } catch (err: any) {
        setChatMessages(prev => prev.map(m => m.id === agentMsg.id ? { ...m, content: `⚠️ ${err.message || 'Agent-Fehler'}`, pending: false } : m));
        setAgentRunning(false);
        setChatBusy(false);
      }
      return;
    }

    // ── Normal modes (fragen / bearbeiten) ───────────────────────────
    const pendingMsg: ChatMsg = { id: `p${Date.now()}`, role: 'ai', content: '', ts: Date.now(), pending: true };
    setChatMessages(prev => [...prev, pendingMsg]);
    setChatInput('');
    setChatBusy(true);

    // Set up abort controller for stop button
    const abortCtrl = new AbortController();
    chatAbortRef.current = abortCtrl;

    try {
      const r = await fetch(`${API_BASE}/api/code/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        signal: abortCtrl.signal,
        body: JSON.stringify({
          message: msg,
          file_context: fileContext,
          project: activeProject,
          mode: chatMode,
          open_files: openFilesContext,
        })
      });
      if (r.ok) {
        const j = await r.json();
        const aiReply = j.reply || j.message || 'Keine Antwort';
        const actions: AgentAction[] = (j.actions || []).map((a: any) => ({
          ...a,
          status: (j.mode === 'agent' && a.status) ? a.status : 'pending'
        }));

        setChatMessages(prev => prev.map(m =>
          m.id === pendingMsg.id ? { ...m, content: aiReply, pending: false, actions: actions.length > 0 ? actions : undefined } : m
        ));

        // In agent mode, actions are already executed by the backend
        // Refresh file tree and update open tabs if files were modified
        if (j.mode === 'agent' && actions.length > 0) {
          loadFileTree();
          // Refresh content of any open tabs that were modified by agent
          for (const action of actions) {
            if ((action.type === 'edit_file' || action.type === 'create_file' || action.type === 'patch_file') && action.path && action.content && action.status === 'accepted') {
              const tab = openTabs.find(t => t.path === action.path);
              if (tab) {
                setOpenTabs(prev => prev.map(t => t.path === action.path ? { ...t, content: action.content!, dirty: false } : t));
                // Directly update Monaco if this is the active tab
                if (activeTab === action.path && editorRef.current && monacoRef.current) {
                  const model = editorRef.current.getModel();
                  if (model && model.getValue() !== action.content) {
                    const fullRange = model.getFullModelRange();
                    editorRef.current.executeEdits('ailey-agent', [{
                      range: fullRange,
                      text: action.content!,
                      forceMoveMarkers: true,
                    }]);
                  }
                }
              } else if (action.content) {
                // File not open — auto-open it so user sees the change
                const name = (action.path || '').split('/').pop() || 'file';
                const lang = getLang(name);
                setOpenTabs(prev => [...prev, { path: action.path!, name, content: action.content!, dirty: false, language: lang }]);
                setActiveTab(action.path!);
              }
            }
            if (action.type === 'run_command' && action.status === 'accepted') {
              const out = (action.stdout || '') + (action.stderr ? `\n⚠️ ${action.stderr}` : '');
              if (out.trim()) {
                setTermOutput(prev => [...prev, `$ ${action.command}\n`, out + '\n']);
                setTermVisible(true);
              }
            }
          }
        }
      } else {
        setChatMessages(prev => prev.map(m =>
          m.id === pendingMsg.id ? { ...m, content: '⚠️ Fehler bei der Anfrage', pending: false } : m
        ));
      }
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        setChatMessages(prev => prev.map(m =>
          m.id === pendingMsg.id ? { ...m, content: '⛔ Abgebrochen', pending: false } : m
        ));
      } else {
        setChatMessages(prev => prev.map(m =>
          m.id === pendingMsg.id ? { ...m, content: `⚠️ ${e?.message || 'Netzwerkfehler'}`, pending: false } : m
        ));
      }
    }
    chatAbortRef.current = null;
    setChatBusy(false);
    setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
  }

  // ── Keyboard shortcuts ─────────────────────────────────────────────────
  useEffect(() => {
    function handleKeyDown(e: globalThis.KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); if (activeTab) saveFile(activeTab); }
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'f') { e.preventDefault(); setSidePanel('search'); setSearchVisible(true); }
      if ((e.metaKey || e.ctrlKey) && e.key === '`') { e.preventDefault(); setTermVisible(v => !v); }
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') { e.preventDefault(); setChatVisible(v => !v); }
      if (e.key === 'Escape' && diffView) { e.preventDefault(); setDiffView(null); }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab, openTabs, diffView]);

  useEffect(() => { termRef.current?.scrollTo(0, termRef.current.scrollHeight); }, [termOutput]);

  // Periodically refresh git status
  useEffect(() => {
    if (!activeProject) return;
    const interval = setInterval(() => loadGitStatus(), 15000);
    return () => clearInterval(interval);
  }, [activeProject]);

  // ── Custom Monaco theme (Ailey colors) ─────────────────────────────────
  function handleEditorMount(editor: any, monaco: any) {
    editorRef.current = editor;
    monacoRef.current = monaco;
    monaco.editor.defineTheme('ailey-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '6b7280', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'be123c' },
        { token: 'string', foreground: '22c55e' },
        { token: 'number', foreground: 'f59e0b' },
        { token: 'type', foreground: '0891b2' },
        { token: 'function', foreground: '60a5fa' },
        { token: 'variable', foreground: 'e2e8f0' },
        { token: 'operator', foreground: 'be123c' },
        { token: 'delimiter', foreground: '94a3b8' },
      ],
      colors: {
        'editor.background': '#0a0a0a',
        'editor.foreground': '#e2e8f0',
        'editor.lineHighlightBackground': '#1a1a1a',
        'editor.selectionBackground': '#be123c33',
        'editor.inactiveSelectionBackground': '#be123c1a',
        'editorCursor.foreground': '#be123c',
        'editorLineNumber.foreground': '#333333',
        'editorLineNumber.activeForeground': '#be123c',
        'editor.selectionHighlightBackground': '#0891b21a',
        'editorIndentGuide.background': '#1a1a1a',
        'editorIndentGuide.activeBackground': '#333333',
        'editorWidget.background': '#111111',
        'editorWidget.border': '#be123c44',
        'editorSuggestWidget.background': '#111111',
        'editorSuggestWidget.border': '#be123c44',
        'editorSuggestWidget.selectedBackground': '#be123c22',
        'minimap.background': '#050505',
        'scrollbarSlider.background': '#be123c22',
        'scrollbarSlider.hoverBackground': '#be123c44',
        'scrollbarSlider.activeBackground': '#be123c66',
      }
    });

    // ── Cyber Punk theme (anthracite + teal-green gradients) ───────────────
    monaco.editor.defineTheme('cyber-punk', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '5c6370', fontStyle: 'italic' },
        { token: 'keyword', foreground: '00d4aa' },
        { token: 'string', foreground: '7ee787' },
        { token: 'number', foreground: 'ffd700' },
        { token: 'type', foreground: '79c0ff' },
        { token: 'function', foreground: '56d4dd' },
        { token: 'variable', foreground: 'c9d1d9' },
        { token: 'operator', foreground: '00d4aa' },
        { token: 'delimiter', foreground: '6e7681' },
        { token: 'regexp', foreground: '7ee787' },
        { token: 'tag', foreground: '56d4dd' },
        { token: 'attribute.name', foreground: '00d4aa' },
        { token: 'attribute.value', foreground: '7ee787' },
      ],
      colors: {
        'editor.background': '#1a1d23',
        'editor.foreground': '#c9d1d9',
        'editor.lineHighlightBackground': '#22262e',
        'editor.selectionBackground': '#00d4aa33',
        'editor.inactiveSelectionBackground': '#00d4aa1a',
        'editorCursor.foreground': '#00d4aa',
        'editorLineNumber.foreground': '#3a3f47',
        'editorLineNumber.activeForeground': '#00d4aa',
        'editor.selectionHighlightBackground': '#56d4dd1a',
        'editorIndentGuide.background': '#262a33',
        'editorIndentGuide.activeBackground': '#3a3f47',
        'editorWidget.background': '#1e2228',
        'editorWidget.border': '#00d4aa44',
        'editorSuggestWidget.background': '#1e2228',
        'editorSuggestWidget.border': '#00d4aa44',
        'editorSuggestWidget.selectedBackground': '#00d4aa22',
        'minimap.background': '#161920',
        'scrollbarSlider.background': '#00d4aa22',
        'scrollbarSlider.hoverBackground': '#00d4aa44',
        'scrollbarSlider.activeBackground': '#00d4aa66',
        'editorBracketMatch.background': '#00d4aa22',
        'editorBracketMatch.border': '#00d4aa66',
      }
    });

    // Apply saved theme (or default)
    const savedTheme = localStorage.getItem('ailey-code-theme') || 'ailey-dark';
    monaco.editor.setTheme(savedTheme);

    // Enable validation for supported languages
    monaco.languages.typescript.typescriptDefaults.setDiagnosticsOptions({
      noSemanticValidation: false,
      noSyntaxValidation: false,
    });
    monaco.languages.typescript.javascriptDefaults.setDiagnosticsOptions({
      noSemanticValidation: false,
      noSyntaxValidation: false,
    });
    monaco.languages.typescript.javascriptDefaults.setCompilerOptions({
      target: monaco.languages.typescript.ScriptTarget.ESNext,
      allowNonTsExtensions: true,
      moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
      module: monaco.languages.typescript.ModuleKind.ESNext,
      jsx: monaco.languages.typescript.JsxEmit.React,
      allowJs: true,
    });
    monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
      validate: true,
      allowComments: true,
      trailingCommas: 'ignore',
    });
    monaco.languages.css.cssDefaults.setOptions({
      validate: true,
      lint: { compatibleVendorPrefixes: 'warning', duplicateProperties: 'warning' },
    });
    monaco.languages.html.htmlDefaults.setOptions({
      validate: true,
      format: { tabSize: 2, insertSpaces: true },
    });

    // Store refs
    editorRef.current = editor;
    monacoRef.current = monaco;
  }

  // ── File Tree Renderer ─────────────────────────────────────────────────
  function FileTreeNode({ node, depth = 0 }: { node: FileNode; depth?: number }) {
    const isExpanded = expandedDirs.has(node.path);
    const isActive = activeTab === node.path;
    const isRenaming = renamingPath === node.path;

    if (isRenaming) {
      return (
        <div className="px-2 py-[3px]" style={{ paddingLeft: `${12 + depth * 16}px` }}>
          <input
            title="Umbenennen"
            placeholder="Neuer Name…"
            className="w-full bg-black border border-[#be123c]/50 rounded px-1.5 py-0.5 text-[12px] text-white outline-none focus:border-[#be123c]"
            value={renameValue}
            onChange={e => setRenameValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') renameFile(node.path, renameValue);
              if (e.key === 'Escape') { setRenamingPath(null); setRenameValue(''); }
            }}
            onBlur={() => { setRenamingPath(null); setRenameValue(''); }}
            autoFocus
          />
        </div>
      );
    }

    return (
      <div>
        <div
          className={`flex items-center gap-1.5 px-2 py-[3px] text-[12px] cursor-pointer group transition-colors
            ${dragOverPath === node.path && node.is_dir ? 'bg-[#0891b2]/20 ring-1 ring-[#0891b2]/40' : ''}
            ${isActive ? 'bg-[#be123c]/15 text-white border-r-2 border-r-[#be123c]' : 'text-white/70 hover:bg-white/5 hover:text-white'}`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData('text/plain', node.path);
            e.dataTransfer.effectAllowed = 'move';
          }}
          onDragOver={(e) => {
            if (node.is_dir) {
              e.preventDefault();
              e.dataTransfer.dropEffect = 'move';
              setDragOverPath(node.path);
            }
          }}
          onDragLeave={() => { if (dragOverPath === node.path) setDragOverPath(null); }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            const sourcePath = e.dataTransfer.getData('text/plain');
            if (sourcePath && node.is_dir) moveFile(sourcePath, node.path);
            setDragOverPath(null);
          }}
          onClick={() => openFile(node)}
          onDoubleClick={(e) => {
            e.stopPropagation();
            setRenamingPath(node.path);
            setRenameValue(node.name);
          }}
        >
          {node.is_dir ? (
            <>
              {isExpanded ? <ChevronDown className="h-3 w-3 shrink-0 text-white/40" /> : <ChevronRight className="h-3 w-3 shrink-0 text-white/40" />}
              {isExpanded ? <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[#be123c]" /> : <Folder className="h-3.5 w-3.5 shrink-0 text-[#be123c]/70" />}
            </>
          ) : (
            <>
              <span className="w-3" />
              <File className={`h-3.5 w-3.5 shrink-0 ${getFileColor(node.name)}`} />
            </>
          )}
          <span className="truncate flex-1">{node.name}</span>
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button title="Umbenennen" className="p-0.5 hover:text-[#0891b2]" onClick={(e) => { e.stopPropagation(); setRenamingPath(node.path); setRenameValue(node.name); }}>
              <Edit3 className="h-3 w-3" />
            </button>
            <button title="Löschen" className="p-0.5 hover:text-[#be123c]" onClick={(e) => { e.stopPropagation(); deleteFile(node.path); }}>
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        </div>
        {node.is_dir && isExpanded && node.children?.map(child => (
          <FileTreeNode key={child.path} node={child} depth={depth + 1} />
        ))}
      </div>
    );
  }

  // ── Render helpers ─────────────────────────────────────────────────────
  function renderMarkdown(text: string) {
    return text
      .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-white">$1</strong>')
      .replace(/`([^`]+)`/g, '<code class="bg-black/50 px-1 py-0.5 rounded text-[11px] text-[#0891b2]">$1</code>')
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-black/50 rounded-lg p-2 mt-1.5 mb-1.5 text-[11px] overflow-x-auto border border-white/5 font-mono"><code>$2</code></pre>');
  }

  const currentTab = openTabs.find(t => t.path === activeTab);

  // ══════════════════════════════════════════════════════════════════════════
  // ── PROJECT PICKER ─────────────────────────────────────────────────────
  // ══════════════════════════════════════════════════════════════════════════
  if (!activeProject) {
    return (
      <div className="min-h-screen bg-black text-white flex flex-col">
        {/* Top bar */}
        <div className="h-11 bg-[#0a0a0a] border-b border-[#be123c]/30 flex items-center px-5 gap-3 shrink-0">
          <button onClick={() => { deactivateCodeMode(); router.push('/'); }} className="flex items-center gap-2 text-xs text-white/60 hover:text-white transition-colors" title="Zurück zu Ailey">
            <ArrowLeft className="h-3.5 w-3.5" /> Zurück zu Ailey
          </button>
          <div className="flex-1" />
          <Code2 className="h-4 w-4 text-[#be123c]" />
          <span className="text-xs font-bold tracking-wide">A!LEY CODE</span>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="max-w-lg w-full px-4 md:px-8 space-y-8 md:space-y-10">
            {/* Hero */}
            <div className="text-center space-y-3">
              <div className="relative inline-block">
                <img src="/images/emotes/ailey-coding.jpg" alt="Ailey Coding" className="h-24 w-24 mx-auto rounded-2xl object-cover border-2 border-[#be123c]/40 shadow-lg shadow-[#be123c]/10" />
                <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-[#0891b2] rounded-full animate-pulse" />
              </div>
              <h1 className="text-4xl font-black">
                A<span className="text-[#be123c]">!</span>LEY CODE
              </h1>
              <p className="text-sm text-white/50">IDE mit integrierter KI · Punk-Style Coding</p>
            </div>

            {/* Project list */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-white/90">Projekte</h2>
                <Button size="sm" variant="outline" className="h-7 text-xs bg-transparent border-[#be123c]/40 text-white hover:bg-[#be123c]/10 hover:border-[#be123c]" onClick={() => setShowNewProject(true)}>
                  <Plus className="h-3 w-3 mr-1" /> Neues Projekt
                </Button>
              </div>

              {showNewProject && (
                <div className="bg-[#111] border border-[#be123c]/30 rounded-xl p-4 space-y-3">
                  <div className="flex gap-2 items-center">
                    <Input className="h-8 text-xs bg-black border-[#333] text-white placeholder:text-white/30 focus-visible:ring-[#be123c]/30" placeholder="Projektname…" value={newProjectName} onChange={e => setNewProjectName(e.target.value)} onKeyDown={e => e.key === 'Enter' && createProject()} autoFocus />
                    <Button size="sm" variant="ghost" className="h-8 text-xs text-white/50 hover:text-white shrink-0" onClick={() => setShowNewProject(false)}><X className="h-3 w-3" /></Button>
                  </div>
                  {/* Template selection */}
                  <div className="space-y-1.5">
                    <div className="text-[10px] text-white/40 font-medium uppercase tracking-wider">Template</div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {[
                        { id: 'standard', label: 'Standard', icon: '📄', desc: 'Leeres Projekt' },
                        { id: 'web', label: 'Web', icon: '🌐', desc: 'HTML / CSS / JS' },
                        { id: 'python', label: 'Python', icon: '🐍', desc: 'main.py + tests' },
                        { id: 'rust', label: 'Rust', icon: '🦀', desc: 'Cargo + src/main.rs' },
                        { id: 'php', label: 'PHP', icon: '🐘', desc: 'index.php + composer' },
                        { id: 'joomla_plugin', label: 'Joomla Plugin', icon: '🧩', desc: 'Plugin-Boilerplate' },
                        { id: 'joomla_module', label: 'Joomla Modul', icon: '📦', desc: 'Modul-Boilerplate' },
                        { id: 'joomla_component', label: 'Joomla Component', icon: '⚙️', desc: 'Component-Struktur' },
                      ].map(t => (
                        <button key={t.id} onClick={() => setSelectedTemplate(t.id)}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all border text-xs ${selectedTemplate === t.id ? 'bg-[#be123c]/15 border-[#be123c]/60 text-white' : 'bg-black/40 border-white/8 text-white/50 hover:border-white/20 hover:text-white/80'}`}>
                          <span className="text-base leading-none">{t.icon}</span>
                          <div>
                            <div className="font-semibold leading-tight">{t.label}</div>
                            <div className="text-[9px] text-white/30 leading-tight">{t.desc}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                  <Button size="sm" className="w-full h-8 text-xs bg-[#be123c] hover:bg-[#be123c]/80 text-white" onClick={createProject} disabled={!newProjectName.trim()}>
                    <Plus className="h-3 w-3 mr-1" /> Projekt erstellen
                  </Button>
                </div>
              )}

              {projects.length === 0 && !showNewProject && (
                <div className="text-center py-16 text-sm text-white/30">
                  <Folder className="h-12 w-12 mx-auto mb-4 text-[#be123c]/30" />
                  Noch keine Projekte.<br />Erstelle eins oder öffne einen Ordner.
                </div>
              )}

              <div className="space-y-2">
                {projects.map(p => (
                  <div key={p.path} className="relative group/proj">
                    <button onClick={() => openProject(p.path)}
                      className="w-full text-left flex items-center gap-3 px-4 py-3.5 rounded-xl bg-[#111] border border-[#222] hover:border-[#be123c]/60 hover:bg-[#1a1a1a] transition-all group">
                      <div className="w-10 h-10 rounded-lg bg-[#be123c]/10 flex items-center justify-center shrink-0">
                        <Folder className="h-5 w-5 text-[#be123c]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-white truncate">{p.name}</div>
                        <div className="text-[10px] text-white/30 truncate">{p.path}</div>
                      </div>
                      {p.language && <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#0891b2]/15 text-[#0891b2] border border-[#0891b2]/20">{p.language}</span>}
                      <ChevronRight className="h-4 w-4 text-white/0 group-hover:text-white/40 transition-colors mr-6" />
                    </button>
                    {/* Delete button — appears on hover */}
                    <button
                      onClick={e => { e.stopPropagation(); deleteProject(p.path, p.name); }}
                      disabled={deletingProject === p.path}
                      className="absolute right-3 top-1/2 -translate-y-1/2 w-7 h-7 rounded-lg bg-[#be123c]/0 hover:bg-[#be123c]/20 flex items-center justify-center opacity-0 group-hover/proj:opacity-100 transition-all"
                      title="Projekt löschen">
                      {deletingProject === p.path
                        ? <Loader2 className="h-3.5 w-3.5 text-[#be123c] animate-spin" />
                        : <Trash2 className="h-3.5 w-3.5 text-[#be123c]/70 hover:text-[#be123c]" />}
                    </button>
                  </div>
                ))}
              </div>

              {/* Open external folder */}
              <div className="pt-4 border-t border-white/10">
                <Button size="sm" variant="outline" className="w-full h-9 text-xs bg-transparent border-white/10 text-white/60 hover:bg-white/5 hover:text-white hover:border-white/20"
                  onClick={async () => {
                    const path = prompt('Ordner-Pfad eingeben:');
                    if (path) openProject(path);
                  }}>
                  <FolderOpen className="h-3.5 w-3.5 mr-1.5" /> Ordner öffnen…
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ── MAIN IDE LAYOUT ────────────────────────────────────────────────────
  // ══════════════════════════════════════════════════════════════════════════
  return (
    <div className="h-screen bg-black text-white flex flex-col overflow-hidden select-none">

      {/* ── Title Bar ─────────────────────────────────────────────────── */}
      <div className="h-10 bg-[#0a0a0a] border-b border-[#be123c]/20 flex items-center px-2 md:px-4 gap-1.5 md:gap-2.5 shrink-0 text-xs">
        <button onClick={leaveCodeMode} className="flex items-center gap-1.5 text-white/50 hover:text-white transition-colors" title="Zurück zum Hauptmenü">
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        <div className="w-px h-4 bg-white/10" />
        {isMobile && (
          <button onClick={() => { setMobileSidebarOpen(!mobileSidebarOpen); setMobileChatOpen(false); }} className="p-1.5 rounded-md hover:bg-white/5 transition-colors" title="Dateien">
            <FileCode className={`h-3.5 w-3.5 ${mobileSidebarOpen ? 'text-[#be123c]' : 'text-white/50'}`} />
          </button>
        )}
        <Code2 className="h-3.5 w-3.5 text-[#be123c]" />
        <span className="font-bold text-white hidden sm:inline">A<span className="text-[#be123c]">!</span>LEY CODE</span>
        <span className="text-white/20 hidden sm:inline">·</span>
        <span className="text-white/50 truncate max-w-[100px] md:max-w-none">{activeProject?.split('/').pop()}</span>
        <div className="flex-1" />
        {/* Shortcuts hint */}
        <span className="text-[10px] text-white/15 hidden lg:inline">⌘S Save · ⌘⇧F Search · ⌘` Terminal · ⌘B Chat</span>
        <button onClick={() => {
          if (isMobile) { setMobileChatOpen(!mobileChatOpen); setMobileSidebarOpen(false); }
          else setChatVisible(!chatVisible);
        }} className="p-1.5 rounded-md hover:bg-white/5 transition-colors" title="Ailey Chat (⌘B)">
          {(isMobile ? mobileChatOpen : chatVisible) ? <PanelRightClose className="h-3.5 w-3.5 text-[#0891b2]" /> : <PanelRight className="h-3.5 w-3.5 text-white/50" />}
        </button>
        <button onClick={() => setErrorsVisible(!errorsVisible)} className="relative p-1.5 rounded-md hover:bg-white/5 transition-colors" title="Errors Panel">
          <Bug className={`h-3.5 w-3.5 ${errorsVisible ? 'text-[#be123c]' : diagnostics.length > 0 ? 'text-[#eab308]' : 'text-white/50'}`} />
          {diagnostics.length > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] rounded-full bg-[#be123c] text-[8px] font-bold flex items-center justify-center text-white px-[3px]">{diagnostics.length}</span>
          )}
        </button>
        <button onClick={() => setTermVisible(!termVisible)} className="p-1.5 rounded-md hover:bg-white/5 transition-colors hidden md:flex" title="Terminal (⌘`)">
          <TermIcon className={`h-3.5 w-3.5 ${termVisible ? 'text-[#0891b2]' : 'text-white/50'}`} />
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

        {/* ── Activity Bar (icon strip) ───────────────────────────────── */}
        <div className="w-12 bg-[#0a0a0a] border-r border-white/5 flex flex-col items-center py-2 gap-1 shrink-0">
          <button onClick={() => setSidePanel('explorer')} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${sidePanel === 'explorer' ? 'bg-[#be123c]/15 text-[#be123c]' : 'text-white/40 hover:text-white hover:bg-white/5'}`} title="Explorer">
            <FileCode className="h-4.5 w-4.5" />
          </button>
          <button onClick={() => { setSidePanel('search'); }} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${sidePanel === 'search' ? 'bg-[#be123c]/15 text-[#be123c]' : 'text-white/40 hover:text-white hover:bg-white/5'}`} title="Suche (⌘⇧F)">
            <Search className="h-4.5 w-4.5" />
          </button>
          <button onClick={() => { setSidePanel('git'); loadGitStatus(); }} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors relative ${sidePanel === 'git' ? 'bg-[#be123c]/15 text-[#be123c]' : 'text-white/40 hover:text-white hover:bg-white/5'}`} title="Git">
            <GitBranch className="h-4.5 w-4.5" />
            {gitInfo?.dirty && <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#eab308]" />}
          </button>
          <button onClick={() => setSidePanel('ftp')} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors relative ${sidePanel === 'ftp' ? 'bg-[#be123c]/15 text-[#be123c]' : 'text-white/40 hover:text-white hover:bg-white/5'}`} title="FTP/SFTP">
            <Server className="h-4.5 w-4.5" />
            {ftpConnected && <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#22c55e]" />}
          </button>
          <div className="flex-1" />
          <button onClick={() => setSidePanel('settings')} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${sidePanel === 'settings' ? 'bg-[#be123c]/15 text-[#be123c]' : 'text-white/40 hover:text-white hover:bg-white/5'}`} title="Einstellungen">
            <Settings className="h-4.5 w-4.5" />
          </button>
        </div>

        {/* ── Sidebar Panel ───────────────────────────────────────────── */}
        <div className="w-56 bg-[#0a0a0a] border-r border-white/5 flex flex-col shrink-0">

          {/* ═══ Explorer Panel ═══ */}
          {sidePanel === 'explorer' && (
            <>
              <div className="h-9 flex items-center justify-between px-3 text-[11px] uppercase tracking-wider text-white/40 border-b border-white/5">
                <span className="font-semibold">Explorer</span>
                <div className="flex items-center gap-0.5">
                  <button onClick={() => { setNewFileDir(activeProject); setNewFileName(''); }} className="p-1 rounded hover:bg-white/5" title="Neue Datei"><FilePlus className="h-3 w-3 text-white/40 hover:text-white" /></button>
                  <button onClick={() => { const name = prompt('Ordnername:'); if (name) createFolder(activeProject!, name); }} className="p-1 rounded hover:bg-white/5" title="Neuer Ordner"><FolderPlus className="h-3 w-3 text-white/40 hover:text-white" /></button>
                  <button onClick={() => loadFileTree()} className="p-1 rounded hover:bg-white/5" title="Aktualisieren"><RefreshCw className="h-3 w-3 text-white/40 hover:text-white" /></button>
                </div>
              </div>

              {newFileDir !== null && (
                <div className="px-2 py-1.5 border-b border-white/5">
                  <Input className="h-6 text-[11px] bg-black border-[#333] text-white placeholder:text-white/30" placeholder="Dateiname…" value={newFileName} autoFocus
                    onChange={e => setNewFileName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') createFile(newFileDir || activeProject!, newFileName);
                      if (e.key === 'Escape') { setNewFileDir(null); setNewFileName(''); }
                    }} />
                </div>
              )}

              <div className={`flex-1 overflow-y-auto overflow-x-hidden py-1 ${dragOverPath === activeProject ? 'ring-1 ring-inset ring-[#0891b2]/30' : ''}`}
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragOverPath(activeProject); }}
                onDragLeave={() => { if (dragOverPath === activeProject) setDragOverPath(null); }}
                onDrop={(e) => { e.preventDefault(); const src = e.dataTransfer.getData('text/plain'); if (src && activeProject) moveFile(src, activeProject); setDragOverPath(null); }}
              >
                {fileTreeLoading ? (
                  <div className="flex items-center justify-center py-8"><Loader2 className="h-4 w-4 animate-spin text-[#be123c]/50" /></div>
                ) : fileTree.length === 0 ? (
                  <div className="text-center text-[11px] text-white/20 py-8">Leeres Projekt</div>
                ) : (
                  fileTree.map(node => <FileTreeNode key={node.path} node={node} />)
                )}
              </div>

              <div className="border-t border-white/5 px-3 py-2">
                <button onClick={() => { setActiveProject(null); setOpenTabs([]); setActiveTab(null); setGitInfo(null); }} className="text-[10px] text-white/30 hover:text-[#be123c] transition-colors">
                  ← Projekt wechseln
                </button>
              </div>
            </>
          )}

          {/* ═══ Search Panel ═══ */}
          {sidePanel === 'search' && (
            <>
              <div className="h-9 flex items-center px-3 text-[11px] uppercase tracking-wider text-white/40 border-b border-white/5">
                <span className="font-semibold">Suche</span>
              </div>
              <div className="px-2 py-2 border-b border-white/5">
                <div className="flex gap-1">
                  <Input
                    className="h-7 text-[11px] bg-black border-[#333] text-white placeholder:text-white/30 focus-visible:ring-[#be123c]/30"
                    placeholder="Suchbegriff…"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') runSearch(); }}
                    autoFocus
                  />
                  <button onClick={runSearch} disabled={searchBusy} className="p-1.5 rounded bg-[#be123c]/20 hover:bg-[#be123c]/30 text-[#be123c] disabled:opacity-40">
                    {searchBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto">
                {searchResults.length === 0 && !searchBusy && (
                  <div className="text-center text-[11px] text-white/20 py-8">
                    {searchQuery ? 'Keine Ergebnisse' : 'Suchbegriff eingeben'}
                  </div>
                )}
                {searchResults.map((result, i) => (
                  <button
                    key={`${result.file}-${result.line}-${i}`}
                    className="w-full text-left px-3 py-1.5 text-[11px] hover:bg-white/5 transition-colors border-b border-white/[0.03]"
                    onClick={() => openFilePath(result.file, result.line)}
                  >
                    <div className="flex items-center gap-1 text-white/60">
                      <File className={`h-2.5 w-2.5 shrink-0 ${getFileColor(result.relative)}`} />
                      <span className="truncate">{result.relative}</span>
                      <span className="text-white/30 shrink-0">:{result.line}</span>
                    </div>
                    <div className="text-white/40 truncate mt-0.5 font-mono text-[10px]">{result.text}</div>
                  </button>
                ))}
                {searchTruncated && (
                  <div className="text-center text-[10px] text-[#eab308] py-2">Ergebnisse auf 200 begrenzt</div>
                )}
              </div>
            </>
          )}

          {/* ═══ Git Panel ═══ */}
          {sidePanel === 'git' && (
            <>
              <div className="h-9 flex items-center justify-between px-3 text-[11px] uppercase tracking-wider text-white/40 border-b border-white/5">
                <span className="font-semibold">Git</span>
                <button onClick={() => loadGitStatus()} className="p-1 rounded hover:bg-white/5" title="Aktualisieren">
                  <RefreshCw className="h-3 w-3 text-white/40 hover:text-white" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                {!gitInfo ? (
                  <div className="text-center text-[11px] text-white/20 py-8"><Loader2 className="h-4 w-4 animate-spin mx-auto text-[#be123c]/50" /></div>
                ) : !gitInfo.is_git ? (
                  <div className="text-center text-[11px] text-white/30 py-8 px-3">
                    <GitBranch className="h-8 w-8 mx-auto mb-3 text-white/15" />
                    Kein Git-Repository
                    <div className="mt-3">
                      <button onClick={() => execCommand('git init')} className="text-[10px] text-[#0891b2] hover:underline">
                        git init ausführen
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="py-2">
                    {/* Branch info */}
                    <div className="px-3 py-1.5 flex items-center gap-2 text-[12px]">
                      <GitBranch className="h-3.5 w-3.5 text-[#be123c]" />
                      <span className="font-medium text-white">{gitInfo.branch}</span>
                      {gitInfo.dirty && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[#eab308]/15 text-[#eab308]">{gitInfo.change_count} Änderungen</span>}
                    </div>

                    {/* Last commit */}
                    {gitInfo.last_commit && (
                      <div className="px-3 py-1.5 text-[11px] text-white/40">
                        <span className="text-[#0891b2] font-mono">{gitInfo.last_commit.hash}</span>{' '}
                        {gitInfo.last_commit.message}
                        <span className="text-white/25 ml-1">{gitInfo.last_commit.ago}</span>
                      </div>
                    )}

                    {/* Changes */}
                    {gitInfo.changes.length > 0 && (
                      <div className="mt-2 border-t border-white/5 pt-1">
                        <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-white/30 font-semibold">Änderungen</div>
                        {gitInfo.changes.map((change, i) => (
                          <button key={i} className="w-full text-left px-3 py-1 text-[11px] hover:bg-white/5 flex items-center gap-2"
                            onClick={() => { if (activeProject) openFilePath(`${activeProject}/${change.file}`); }}>
                            <span className={`font-mono text-[10px] w-3 ${
                              change.status === 'M' ? 'text-[#eab308]' :
                              change.status === 'A' || change.status === '?' ? 'text-[#22c55e]' :
                              change.status === 'D' ? 'text-[#be123c]' : 'text-white/40'
                            }`}>{change.status === '?' ? 'U' : change.status}</span>
                            <span className="text-white/60 truncate">{change.file}</span>
                          </button>
                        ))}
                      </div>
                    )}

                    {!gitInfo.dirty && (
                      <div className="px-3 py-4 text-[11px] text-white/30 text-center">
                        ✓ Working tree clean
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ═══ FTP/SFTP Panel ═══ */}
          {sidePanel === 'ftp' && (
            <>
              <div className="h-9 flex items-center justify-between px-3 text-[11px] uppercase tracking-wider text-white/40 border-b border-white/5">
                <span className="font-semibold">FTP / SFTP</span>
                {ftpConnected && (
                  <button onClick={ftpDisconnect} className="text-[10px] text-[#be123c] hover:text-[#be123c]/80" title="Trennen">Trennen</button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto">
                {!ftpConnected ? (
                  <div className="p-3 space-y-2">
                    <div className="flex gap-1">
                      <button onClick={() => setFtpProtocol('sftp')} className={`flex-1 text-[10px] py-1 rounded ${ftpProtocol === 'sftp' ? 'bg-[#0891b2]/20 text-[#0891b2] border border-[#0891b2]/30' : 'bg-white/5 text-white/40 border border-white/5'}`}>SFTP</button>
                      <button onClick={() => setFtpProtocol('ftp')} className={`flex-1 text-[10px] py-1 rounded ${ftpProtocol === 'ftp' ? 'bg-[#0891b2]/20 text-[#0891b2] border border-[#0891b2]/30' : 'bg-white/5 text-white/40 border border-white/5'}`}>FTP</button>
                    </div>
                    <input className="w-full bg-black border border-white/10 rounded px-2 py-1.5 text-[11px] text-white outline-none focus:border-[#be123c]/40 placeholder:text-white/20"
                      placeholder="Host (z.B. example.com)" value={ftpHost} onChange={e => setFtpHost(e.target.value)} />
                    <div className="flex gap-1">
                      <input className="flex-1 bg-black border border-white/10 rounded px-2 py-1.5 text-[11px] text-white outline-none focus:border-[#be123c]/40 placeholder:text-white/20"
                        placeholder="Benutzer" value={ftpUser} onChange={e => setFtpUser(e.target.value)} />
                      <input className="w-14 bg-black border border-white/10 rounded px-2 py-1.5 text-[11px] text-white outline-none focus:border-[#be123c]/40 placeholder:text-white/20"
                        placeholder="Port" value={ftpPort} onChange={e => setFtpPort(e.target.value)} />
                    </div>
                    <input className="w-full bg-black border border-white/10 rounded px-2 py-1.5 text-[11px] text-white outline-none focus:border-[#be123c]/40 placeholder:text-white/20"
                      placeholder="Passwort" type="password" value={ftpPass} onChange={e => setFtpPass(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') ftpConnect(); }} />
                    <button onClick={ftpConnect} disabled={ftpBusy || !ftpHost || !ftpUser}
                      className="w-full py-1.5 rounded text-[11px] font-medium bg-[#0891b2]/20 text-[#0891b2] hover:bg-[#0891b2]/30 border border-[#0891b2]/30 disabled:opacity-30 flex items-center justify-center gap-1.5">
                      {ftpBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Globe className="h-3 w-3" />}
                      Verbinden
                    </button>
                    {ftpError && <div className="text-[10px] text-[#be123c] bg-[#be123c]/10 rounded px-2 py-1">{ftpError}</div>}
                  </div>
                ) : (
                  <div>
                    {/* Remote path breadcrumb */}
                    <div className="px-3 py-1.5 flex items-center gap-1 text-[10px] text-white/40 border-b border-white/5">
                      <Globe className="h-3 w-3 text-[#22c55e]" />
                      <span className="text-[#22c55e] font-mono truncate">{ftpHost}</span>
                      <span className="text-white/20">:</span>
                      <span className="text-white/50 font-mono truncate">{ftpRemotePath}</span>
                    </div>
                    {/* Navigation */}
                    {ftpRemotePath !== '/' && (
                      <button className="w-full text-left px-3 py-1 text-[11px] hover:bg-white/5 text-white/40"
                        onClick={() => ftpListDir(ftpRemotePath.split('/').slice(0, -1).join('/') || '/')}>
                        ← ..
                      </button>
                    )}
                    {ftpBusy ? (
                      <div className="text-center py-6"><Loader2 className="h-4 w-4 animate-spin mx-auto text-[#0891b2]/50" /></div>
                    ) : ftpFiles.length === 0 ? (
                      <div className="text-center text-[11px] text-white/20 py-6">Leer</div>
                    ) : (
                      ftpFiles.map((f, i) => (
                        <div key={i} className="flex items-center gap-2 px-3 py-1 text-[11px] hover:bg-white/5 group cursor-pointer"
                          onClick={() => { if (f.is_dir) ftpListDir(`${ftpRemotePath === '/' ? '' : ftpRemotePath}/${f.name}`); }}>
                          {f.is_dir ? <Folder className="h-3 w-3 text-[#be123c]/70 shrink-0" /> : <File className="h-3 w-3 text-[#0891b2]/70 shrink-0" />}
                          <span className="text-white/60 truncate flex-1">{f.name}</span>
                          {!f.is_dir && activeProject && (
                            <button title="Herunterladen" className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-[#22c55e]"
                              onClick={(e) => { e.stopPropagation(); ftpDownloadFile(`${ftpRemotePath === '/' ? '' : ftpRemotePath}/${f.name}`, activeProject); }}>
                              <Download className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      ))
                    )}
                    {/* Upload current file */}
                    {activeTab && ftpConnected && (
                      <div className="border-t border-white/5 px-3 py-2">
                        <button onClick={() => { if (activeTab) ftpUploadFile(activeTab, `${ftpRemotePath}/${activeTab.split('/').pop()}`); }}
                          className="w-full text-[10px] py-1.5 rounded bg-[#22c55e]/10 text-[#22c55e] hover:bg-[#22c55e]/20 border border-[#22c55e]/20 flex items-center justify-center gap-1">
                          <Upload className="h-3 w-3" /> Upload: {activeTab.split('/').pop()}
                        </button>
                      </div>
                    )}
                    {ftpError && <div className="mx-3 mt-1 text-[10px] text-[#be123c] bg-[#be123c]/10 rounded px-2 py-1">{ftpError}</div>}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ═══ Settings Panel ═══ */}
          {sidePanel === 'settings' && (
            <>
              <div className="h-9 flex items-center px-3 text-[11px] uppercase tracking-wider text-white/40 border-b border-white/5">
                <span className="font-semibold">Einstellungen</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-4">
                {/* AI Coder Settings */}
                <div className="space-y-2">
                  <div className="text-[10px] uppercase tracking-wider text-white/30 font-semibold">KI-Coder (Qwen)</div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-[11px] text-white/60">Autocomplete</span>
                    <button onClick={() => { toggleCoderSetting('autocomplete', !coderAutocomplete); setCoderAutocomplete(!coderAutocomplete); }}
                      className={`flex items-center gap-1 text-[11px] transition-colors ${coderAutocomplete ? 'text-[#22c55e]' : 'text-white/30'}`}>
                      {coderAutocomplete ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
                      {coderAutocomplete ? 'An' : 'Aus'}
                    </button>
                  </div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-[11px] text-white/60">Lint / Fehlercheck</span>
                    <button onClick={() => { toggleCoderSetting('lint', !coderLint); setCoderLint(!coderLint); }}
                      className={`flex items-center gap-1 text-[11px] transition-colors ${coderLint ? 'text-[#22c55e]' : 'text-white/30'}`}>
                      {coderLint ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
                      {coderLint ? 'An' : 'Aus'}
                    </button>
                  </div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-[11px] text-white/60">Coder-Modell</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${coderLoaded ? 'bg-[#22c55e]/15 text-[#22c55e]' : 'bg-white/5 text-white/30'}`}>
                      {coderBusy ? '⏳ …' : coderLoaded ? '✓ Geladen' : '○ Nicht geladen'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 pt-1">
                    {coderLoaded ? (
                      <>
                        <button onClick={() => coderControl('unload')} disabled={coderBusy}
                          className="flex-1 text-[10px] py-1.5 rounded-md bg-white/[0.04] hover:bg-red-500/15 text-white/40 hover:text-red-400 transition-colors disabled:opacity-30">
                          Entladen
                        </button>
                        <button onClick={() => coderControl('reload')} disabled={coderBusy}
                          className="flex-1 text-[10px] py-1.5 rounded-md bg-white/[0.04] hover:bg-[#0891b2]/15 text-white/40 hover:text-[#0891b2] transition-colors disabled:opacity-30">
                          Neu laden
                        </button>
                      </>
                    ) : (
                      <button onClick={() => coderControl('load')} disabled={coderBusy}
                        className="flex-1 text-[10px] py-1.5 rounded-md bg-[#22c55e]/10 hover:bg-[#22c55e]/20 text-[#22c55e]/70 hover:text-[#22c55e] transition-colors disabled:opacity-30">
                        {coderBusy ? 'Wird geladen…' : 'Modell laden'}
                      </button>
                    )}
                  </div>
                </div>

                {/* Editor Settings */}
                <div className="space-y-2 border-t border-white/5 pt-3">
                  <div className="text-[10px] uppercase tracking-wider text-white/30 font-semibold">Editor</div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-[11px] text-white/60">Autosave</span>
                    <span className="text-[10px] text-[#22c55e]">Alle 30s</span>
                  </div>
                  <div className="space-y-1.5 pt-1">
                    <span className="text-[11px] text-white/60">Theme</span>
                    <div className="grid grid-cols-2 gap-1.5">
                      {([
                        { id: 'ailey-dark' as const, label: 'Ailey Dark', color: '#be123c' },
                        { id: 'cyber-punk' as const, label: 'Cyber Punk', color: '#00d4aa' },
                        { id: 'vs-dark' as const, label: 'VS Dark', color: '#569cd6' },
                        { id: 'hc-black' as const, label: 'High Contrast', color: '#f9f9f9' },
                        { id: 'vs' as const, label: 'Light', color: '#1e1e1e' },
                      ]).map(t => (
                        <button key={t.id} onClick={() => switchTheme(t.id)}
                          className={`text-[10px] py-1.5 px-2 rounded-md transition-colors text-left ${
                            editorTheme === t.id
                              ? 'bg-white/10 ring-1 ring-white/20'
                              : 'bg-white/[0.03] hover:bg-white/[0.06]'
                          }`}>
                          <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: t.color }} />
                          <span className={editorTheme === t.id ? 'text-white' : 'text-white/40'}>{t.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* FTP Quick Connect */}
                <div className="space-y-2 border-t border-white/5 pt-3">
                  <div className="text-[10px] uppercase tracking-wider text-white/30 font-semibold">Token-Limits (Chat)</div>
                  {([
                    {key:'code_ask',   label:'Fragen',     mode:'fragen'},
                    {key:'code_edit',  label:'Bearbeiten', mode:'bearbeiten'},
                    {key:'code_agent', label:'Agent',      mode:'agent'},
                  ] as {key:string;label:string;mode:string}[]).map(item => (
                    <div key={item.key} className="space-y-0.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] text-white/60">{item.label}</span>
                        <span className="text-[10px] text-white/40 tabular-nums font-mono">{codeGenSettings[item.key] ?? '—'}</span>
                      </div>
                      <input type="range" min={200} max={16384} step={100} title={`${item.label} Token-Limit`}
                        value={codeGenSettings[item.key] ?? 1500}
                        onChange={e => setCodeGenSettings(prev => ({...prev, [item.key]: parseInt(e.target.value)}))}
                        onMouseUp={e => updateCodeGenSetting(item.key, parseInt((e.target as HTMLInputElement).value))}
                        onTouchEnd={() => updateCodeGenSetting(item.key, codeGenSettings[item.key] ?? 1500)}
                        className="w-full h-1 accent-[#be123c]"
                      />
                    </div>
                  ))}
                </div>

                <div className="space-y-2 border-t border-white/5 pt-3">
                  <div className="text-[10px] uppercase tracking-wider text-white/30 font-semibold">Verbindungen</div>
                  <button onClick={() => setSidePanel('ftp')} className="w-full text-left px-3 py-2 rounded-lg bg-white/[0.03] hover:bg-white/5 text-[11px] text-white/50 hover:text-white/70 flex items-center gap-2 transition-colors">
                    <Server className="h-3.5 w-3.5 text-[#0891b2]" />
                    <span>FTP / SFTP</span>
                    {ftpConnected && <span className="ml-auto text-[9px] text-[#22c55e]">Verbunden</span>}
                  </button>
                </div>

                {/* Keyboard Shortcuts */}
                <div className="space-y-2 border-t border-white/5 pt-3">
                  <div className="text-[10px] uppercase tracking-wider text-white/30 font-semibold">Tastenkürzel</div>
                  <div className="space-y-1.5 text-[10px]">
                    {[
                      ['⌘S', 'Speichern'],
                      ['⌘⇧F', 'Suche'],
                      ['⌘`', 'Terminal'],
                      ['⌘B', 'Chat'],
                      ['Esc', 'Diff schließen'],
                    ].map(([key, desc]) => (
                      <div key={key} className="flex items-center justify-between py-0.5">
                        <span className="text-white/40">{desc}</span>
                        <kbd className="px-1.5 py-0.5 rounded bg-white/5 text-white/50 font-mono text-[9px]">{key}</kbd>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Version */}
                <div className="border-t border-white/5 pt-3 text-center text-[10px] text-white/20">
                  A!LEY CODE v2.6 · Qwen2.5-Coder 1.5B
                </div>
              </div>
            </>
          )}
        </div>
        </div>{/* end Activity Bar + Sidebar wrapper */}

        {/* ── Center: Editor + Terminal ────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0">

          {/* Tab Bar */}
          <div className="h-10 bg-[#0a0a0a] flex items-center overflow-x-auto shrink-0 border-b border-white/5 gap-px px-1">
            {openTabs.map(tab => (
              <button key={tab.path} onClick={() => { setActiveTab(tab.path); if (isMobile) setMobileSidebarOpen(false); }}
                className={`h-8 flex items-center gap-1.5 px-2 md:px-3 text-[11px] md:text-[12px] rounded-lg shrink-0 group transition-colors my-1
                  ${activeTab === tab.path
                    ? 'bg-[#1a1a1a] text-white shadow-sm shadow-[#be123c]/10'
                    : 'text-white/40 hover:bg-white/5 hover:text-white/70'
                  }`}>
                <File className={`h-3 w-3 shrink-0 ${getFileColor(tab.name)}`} />
                <span className="truncate max-w-[80px] md:max-w-[120px]">{tab.name}</span>
                {tab.dirty && <span className="w-1.5 h-1.5 rounded-full bg-[#be123c] shrink-0" />}
                <button title="Tab schließen" onClick={(e) => closeTab(tab.path, e)} className="ml-0.5 opacity-0 group-hover:opacity-40 hover:!opacity-100 p-0.5 rounded hover:bg-white/10 hover:text-white">
                  <X className="h-3 w-3" />
                </button>
              </button>
            ))}
            <div className="flex-1" />
            {activeProject && !isMobile && (
              <div className="flex items-center gap-0.5 shrink-0 border-r border-white/5 pr-1 mr-0.5">
                <button title="Projekt als ZIP exportieren" onClick={handleExportProject} disabled={exportBusy}
                  className="h-7 px-2 rounded text-[10px] text-white/30 hover:text-[#22c55e] hover:bg-[#22c55e]/10 flex items-center gap-1 transition-colors disabled:opacity-30">
                  {exportBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Package className="h-3 w-3" />} ZIP
                </button>
                <button title="Web-Preview starten" onClick={handlePreviewProject} disabled={previewBusy}
                  className="h-7 px-2 rounded text-[10px] text-white/30 hover:text-[#38bdf8] hover:bg-[#38bdf8]/10 flex items-center gap-1 transition-colors disabled:opacity-30">
                  {previewBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Globe className="h-3 w-3" />} Preview
                </button>
              </div>
            )}
            {currentTab && (
              <div className="flex items-center gap-0.5 pr-1 shrink-0">
                <button title="Datei herunterladen/exportieren" onClick={() => downloadFile(currentTab.path, currentTab.content, currentTab.name)}
                  className="h-7 px-2 rounded text-[10px] text-white/30 hover:text-white hover:bg-white/5 hidden md:flex items-center gap-1 transition-colors">
                  <Download className="h-3 w-3" /> Export
                </button>
                <button title="Speichern (⌘S)" onClick={() => saveFile(currentTab.path)}
                  className={`h-7 px-2 rounded text-[10px] flex items-center gap-1 transition-colors ${currentTab.dirty ? 'text-[#be123c] hover:bg-[#be123c]/10' : 'text-white/30 hover:text-white hover:bg-white/5'}`}>
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
                theme={editorTheme}
                language={currentTab.language}
                value={currentTab.content}
                onChange={onEditorChange}
                onMount={handleEditorMount}
                options={{
                  fontSize: isMobile ? 12 : 13,
                  fontFamily: "var(--font-geist-mono), 'JetBrains Mono', 'Fira Code', Menlo, monospace",
                  minimap: { enabled: !isMobile, showSlider: 'mouseover' },
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  tabSize: 2,
                  wordWrap: 'on',
                  cursorBlinking: 'smooth',
                  cursorSmoothCaretAnimation: 'on',
                  smoothScrolling: true,
                  padding: { top: isMobile ? 8 : 12, bottom: isMobile ? 8 : 12 },
                  lineNumbers: isMobile ? 'off' : 'on',
                  glyphMargin: !isMobile,
                  folding: !isMobile,
                  bracketPairColorization: { enabled: true },
                  renderLineHighlight: 'gutter',
                  roundedSelection: true,
                  quickSuggestions: { other: true, comments: false, strings: true },
                  suggestOnTriggerCharacters: true,
                  parameterHints: { enabled: true },
                  autoClosingBrackets: 'always',
                  autoClosingQuotes: 'always',
                  autoIndent: 'full',
                  formatOnPaste: true,
                  formatOnType: true,
                  foldingStrategy: 'indentation',
                  showFoldingControls: 'mouseover',
                  matchBrackets: 'always',
                  occurrencesHighlight: 'singleFile',
                  renderWhitespace: 'selection',
                  guides: { indentation: true, bracketPairs: true },
                  suggest: {
                    showKeywords: true,
                    showSnippets: true,
                    showFunctions: true,
                    showVariables: true,
                    showClasses: true,
                    showInterfaces: true,
                    showModules: true,
                    showProperties: true,
                    showMethods: true,
                    insertMode: 'replace',
                    filterGraceful: true,
                  },
                  inlineSuggest: { enabled: true },
                  linkedEditing: true,
                  colorDecorators: true,
                  stickyScroll: { enabled: true },
                }}
              />
            ) : (
              <div className="h-full flex items-center justify-center">
                <div className="text-center space-y-3">
                  <Code2 className="h-16 w-16 mx-auto text-[#be123c]/15" />
                  <div className="text-sm text-white/25">Öffne eine Datei aus dem Explorer</div>
                  <div className="text-[10px] text-white/15">⌘S Speichern · ⌘⇧F Suche · ⌘` Terminal</div>
                </div>
              </div>
            )}
          </div>

          {/* Terminal */}
          {termVisible && !errorsVisible && (
            <div className={`${isMobile ? 'h-32' : 'h-48'} bg-[#050505] border-t border-[#be123c]/15 flex flex-col shrink-0`}>
              <div className="h-8 bg-[#0a0a0a] border-b border-white/5 flex items-center px-3 gap-2 text-[11px] shrink-0">
                <TermIcon className="h-3 w-3 text-[#0891b2]" />
                <span className="text-white/60 font-medium">Terminal</span>
                <div className="flex-1" />
                {termBusy && <Loader2 className="h-3 w-3 animate-spin text-[#be123c]" />}
                <button onClick={() => setTermOutput(['$ Terminal bereinigt.\n'])} className="text-[10px] text-white/30 hover:text-white transition-colors" title="Clear">Clear</button>
                <button onClick={() => setTermVisible(false)} className="p-0.5 rounded hover:bg-white/5" title="Terminal schließen">
                  <X className="h-3 w-3 text-white/30 hover:text-white" />
                </button>
              </div>
              <div ref={termRef} className="flex-1 overflow-y-auto p-3 font-mono text-[12px] text-white/80 whitespace-pre-wrap">
                {termOutput.map((line, i) => {
                  // Check for special prefixes first
                  if (line.startsWith('$')) {
                    return <span key={i} className="text-[#0891b2]">{line}</span>;
                  }
                  if (line.startsWith('❌') || line.startsWith('⚠️')) {
                    return <span key={i} className="text-[#be123c]">{line}</span>;
                  }
                  // Parse ANSI escape codes for colored output
                  const segments = parseAnsi(line);
                  if (segments.length === 1 && !segments[0].color && !segments[0].bold) {
                    return <span key={i}>{segments[0].text}</span>;
                  }
                  return (
                    <span key={i}>
                      {segments.map((seg, j) => (
                        <span key={j} style={{ color: seg.color, fontWeight: seg.bold ? 700 : undefined }}>{seg.text}</span>
                      ))}
                    </span>
                  );
                })}
              </div>
              <div className="flex items-center gap-1.5 px-3 py-1.5 border-t border-white/5 shrink-0">
                <span className="text-[#0891b2] text-[12px] font-mono font-bold">$</span>
                <input className="flex-1 bg-transparent border-none outline-none text-[12px] font-mono text-white/90 placeholder:text-white/20"
                  value={termInput} onChange={e => setTermInput(e.target.value)}
                  onKeyDown={handleTermKeyDown}
                  placeholder="Befehl eingeben… (↑↓ History)" disabled={termBusy} />
                <button title="Ausführen" onClick={() => execCommand(termInput)} disabled={termBusy} className="p-1 rounded hover:bg-white/5">
                  <Play className="h-3 w-3 text-[#0891b2]" />
                </button>
              </div>
            </div>
          )}

          {/* Errors Console — mutually exclusive with Terminal */}
          {errorsVisible && (
            <div className="h-48 bg-[#050505] border-t border-[#be123c]/15 flex flex-col shrink-0">
              <div className="h-8 bg-[#0a0a0a] border-b border-white/5 flex items-center px-3 gap-2 text-[11px] shrink-0">
                <Bug className="h-3 w-3 text-[#be123c]" />
                <span className="text-white/60 font-medium">Fehler & Warnungen</span>
                {diagnostics.length > 0 && (
                  <span className="min-w-[18px] h-[16px] rounded-full bg-[#be123c]/20 text-[#be123c] text-[10px] font-bold flex items-center justify-center px-1">{diagnostics.length}</span>
                )}
                <div className="flex-1" />
                {lintBusy && <Loader2 className="h-3 w-3 animate-spin text-[#eab308]" />}
                <button
                  onClick={() => {
                    const tab = openTabs.find(t => t.path === activeTab);
                    if (tab) runLint(tab.path, tab.content, tab.name, tab.language);
                  }}
                  disabled={lintBusy || !activeTab}
                  className="text-[10px] text-white/30 hover:text-white transition-colors disabled:opacity-30"
                  title="Lint jetzt ausführen"
                >
                  <Sparkles className="h-3 w-3 inline mr-1" />Lint
                </button>
                <button onClick={() => setDiagnostics([])} className="text-[10px] text-white/30 hover:text-white transition-colors" title="Alle Fehler löschen">Clear</button>
                <button onClick={() => setErrorsVisible(false)} className="p-0.5 rounded hover:bg-white/5" title="Fehler schließen">
                  <X className="h-3 w-3 text-white/30 hover:text-white" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                {diagnostics.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-white/20 text-[11px]">
                    {lintBusy ? 'Analysiere Code…' : 'Keine Fehler gefunden ✨'}
                  </div>
                ) : (
                  <div className="divide-y divide-white/5">
                    {diagnostics.map((d, i) => (
                      <button
                        key={i}
                        className="w-full text-left px-3 py-1.5 hover:bg-white/5 transition-colors flex items-start gap-2 text-[11px]"
                        onClick={() => {
                          // Navigate to error line in editor
                          if (editorRef.current && d.line) {
                            editorRef.current.revealLineInCenter(d.line);
                            editorRef.current.setPosition({ lineNumber: d.line, column: 1 });
                            editorRef.current.focus();
                          }
                        }}
                      >
                        <span className="mt-0.5 shrink-0">
                          {d.severity === 'error' ? (
                            <XCircle className="h-3 w-3 text-[#be123c]" />
                          ) : d.severity === 'warning' ? (
                            <AlertTriangle className="h-3 w-3 text-[#eab308]" />
                          ) : (
                            <Bug className="h-3 w-3 text-[#0891b2]" />
                          )}
                        </span>
                        <span className="flex-1 text-white/70">{d.message}</span>
                        <span className="text-white/30 shrink-0">
                          {d.file && <span className="mr-1">{d.file}</span>}
                          Ln {d.line}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── Right Sidebar: Ailey Code Chat ──────────────────────────── */}
        {(isMobile ? mobileChatOpen : chatVisible) && (
          <div className={`${isMobile ? 'absolute inset-0 z-40' : 'w-80 shrink-0'} bg-[#0a0a0a] border-l border-white/5 flex flex-col`}>
            {/* Chat header */}
            <div className="h-9 flex items-center justify-between px-3 text-[11px] border-b border-white/5 shrink-0">
              <div className="flex items-center gap-1.5">
                <div className="w-5 h-5 rounded-full bg-[#be123c]/20 flex items-center justify-center">
                  <Zap className="h-3 w-3 text-[#be123c]" />
                </div>
                <span className="font-semibold text-white">Ailey</span>
                <span className="text-white/30">· Code</span>
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${
                  chatMode === 'agent' ? 'bg-[#be123c]/15 text-[#be123c] border-[#be123c]/20' :
                  chatMode === 'bearbeiten' ? 'bg-[#0891b2]/15 text-[#0891b2] border-[#0891b2]/20' :
                  'bg-[#22c55e]/15 text-[#22c55e] border-[#22c55e]/20'
                }`}>{chatMode === 'agent' ? 'Agent' : chatMode === 'bearbeiten' ? 'Bearbeiten' : 'Fragen'}</span>
              </div>
              <button title="Chat schließen (⌘B)" onClick={() => { if (isMobile) setMobileChatOpen(false); else setChatVisible(false); }} className="p-1 rounded hover:bg-white/5"><X className="h-3 w-3 text-white/40" /></button>
            </div>

            {/* ── Agent Plan Banner (compact hover dropdown) ──────────────── */}
            {agentPlan && agentPlan.steps.length > 0 && (
              <div className="border-b border-[#be123c]/15 bg-[#0d0d0d] px-3 py-1.5 shrink-0 relative group/plan">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 cursor-default">
                    <span className="text-[10px] font-medium text-[#be123c]">📋 Plan</span>
                    <span className="text-[9px] text-white/25">
                      {agentPlan.steps.filter(s => s.status === 'done').length}/{agentPlan.steps.length}
                    </span>
                    {(() => { const active = agentPlan.steps.find(s => s.status === 'active'); return active ? (
                      <span className="text-[9px] text-white/50 truncate max-w-[180px]">— {active.title}</span>
                    ) : null; })()}
                    <ChevronDown className="h-2.5 w-2.5 text-white/20 group-hover/plan:text-white/40 transition-colors" />
                  </div>
                  {!agentRunning && (
                    <button title="Plan ausblenden" onClick={() => setAgentPlan(null)} className="text-white/20 hover:text-white/40">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  )}
                </div>
                {/* Hover dropdown with all steps */}
                <div className="absolute left-0 right-0 top-full z-50 hidden group-hover/plan:block">
                  <div className="mx-2 mt-0.5 bg-[#1a1a1a] border border-white/10 rounded-md shadow-xl p-2 space-y-0.5 max-h-[300px] overflow-y-auto">
                    {agentPlan.steps.map(s => (
                      <div key={s.id} className="flex items-start gap-1.5 text-[10px]">
                        <span className="mt-[1px] shrink-0">
                          {s.status === 'done' ? <Check className="h-3 w-3 text-[#22c55e]" /> :
                           s.status === 'active' ? <Loader2 className="h-3 w-3 text-[#be123c] animate-spin" /> :
                           <span className="inline-block w-3 h-3 rounded-full border border-white/15" />}
                        </span>
                        <div className="flex-1 min-w-0">
                          <span className={s.status === 'done' ? 'text-white/30 line-through' : s.status === 'active' ? 'text-white/80' : 'text-white/40'}>
                            {s.title}
                          </span>
                          {s.comment && (
                            <div className="text-[9px] text-white/25 mt-0.5 truncate">{s.comment}</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Chat messages */}
            <div
              ref={chatScrollRef}
              onScroll={onChatScroll}
              className="flex-1 overflow-y-auto p-3 space-y-3 relative"
            >
              {/* Floating nav that appears briefly on up-scroll */}
              <div className={`absolute left-1/2 -translate-x-1/2 top-2 z-50 transition-opacity duration-200 ${showNav ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
                <div className="bg-black/60 text-white/90 px-3 py-1 rounded-full text-[12px] shadow-md backdrop-blur">
                  ↑ Schnell-Navigation
                </div>
              </div>
              {chatMessages.map(msg => (
                <div key={msg.id}>
                  <div className={`text-[12px] leading-relaxed ${msg.role === 'user' ? 'text-right' : 'flex items-start gap-2'}`}>
                    {msg.role === 'ai' && <img src="/images/emotes/ailey-coding.jpg" alt="Ailey" className="w-5 h-5 rounded-full object-cover shrink-0 mt-0.5 border border-[#be123c]/30" />}
                    <div className={`inline-block max-w-[95%] rounded-xl px-3 py-2 ${
                      msg.role === 'user'
                        ? 'bg-[#be123c]/15 text-white border border-[#be123c]/20'
                        : 'bg-[#111] text-white/80 border border-white/5'
                    }`}>
                      {msg.pending ? (
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-3 w-3 animate-spin text-[#be123c]" />
                          <span className="text-white/40">Ailey generiert…</span>
                          <CodeChatTimer active={msg.pending && chatBusy} />
                        </div>
                      ) : (
                        <div className="whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                      )}
                    </div>
                  </div>

                  {/* ── Inline Agent Activities (below the pending AI message) ── */}
                  {msg.pending && agentRunning && agentActivities.length > 0 && msg.role === 'ai' && (
                    <div className="ml-7 mt-1.5 space-y-0.5">
                      {agentActivities.map((act, idx) => (
                        <div key={idx} className="flex items-center gap-1.5 text-[10px] text-white/40 leading-tight">
                          <span className="shrink-0 w-3 text-center">
                            {act.success ? <Check className="h-2.5 w-2.5 text-[#22c55e] inline" /> : <span className="text-[#be123c]">✗</span>}
                          </span>
                          <span className={act.success ? 'text-white/35' : 'text-[#be123c]/60'}>
                            {act.icon} {act.label}
                          </span>
                          {act.detail && <span className="text-white/15 truncate max-w-[120px]">· {act.detail}</span>}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Agentic Actions — Accept/Reject */}
                  {msg.actions && msg.actions.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {msg.actions.map(action => (
                        <div key={action.id} className={`rounded-lg border text-[11px] overflow-hidden ${
                          action.status === 'accepted' ? 'border-[#22c55e]/30 bg-[#22c55e]/5' :
                          action.status === 'rejected' ? 'border-white/10 bg-white/[0.02] opacity-50' :
                          'border-[#0891b2]/30 bg-[#0891b2]/5'
                        }`}>
                          {/* Action header */}
                          <div className="flex items-center gap-2 px-3 py-1.5">
                            {action.type === 'edit_file' || action.type === 'create_file' || action.type === 'patch_file' ? (
                              <>
                                <FileCode className="h-3.5 w-3.5 text-[#0891b2]" />
                                <span className="text-white/70 flex-1 truncate">
                                  {action.type === 'create_file' ? 'Neue Datei' : action.type === 'patch_file' ? `Patch (${action.patch_count || '?'}×)` : 'Datei'}: <span className="text-[#0891b2] font-mono">{action.path?.split('/').pop()}</span>
                                </span>
                              </>
                            ) : (
                              <>
                                <TermIcon className="h-3.5 w-3.5 text-[#eab308]" />
                                <span className="text-white/70 flex-1 truncate">
                                  Befehl: <span className="text-[#eab308] font-mono">{action.command}</span>
                                </span>
                              </>
                            )}

                            {action.status === 'accepted' ? (
                              <span className="text-[10px] text-[#22c55e] flex items-center gap-1"><Check className="h-3 w-3" /> Angenommen</span>
                            ) : action.status === 'rejected' ? (
                              <span className="text-[10px] text-white/40 flex items-center gap-1"><XCircle className="h-3 w-3" /> Abgelehnt</span>
                            ) : (
                              <div className="flex items-center gap-1">
                                <button onClick={() => acceptAction(msg.id, action)}
                                  className="px-2 py-0.5 rounded bg-[#22c55e]/20 text-[#22c55e] hover:bg-[#22c55e]/30 text-[10px] flex items-center gap-1">
                                  <Check className="h-3 w-3" /> Accept
                                </button>
                                <button onClick={() => rejectAction(msg.id, action.id)}
                                  className="px-2 py-0.5 rounded bg-white/5 text-white/40 hover:bg-white/10 text-[10px] flex items-center gap-1">
                                  <XCircle className="h-3 w-3" /> Reject
                                </button>
                              </div>
                            )}
                          </div>

                          {/* Code preview / Diff for file edits */}
                          {(action.type === 'edit_file' || action.type === 'create_file' || action.type === 'patch_file') && action.content && action.status === 'pending' && (
                            <div className="border-t border-white/5">
                              <div className="flex items-center justify-between px-2 py-1 bg-black/30">
                                <span className="text-[9px] text-white/30 font-mono">{action.path?.split('/').pop()}</span>
                                <button
                                  onClick={() => loadDiffForAction(action)}
                                  className="text-[9px] text-[#0891b2] hover:text-[#0891b2]/80 flex items-center gap-1"
                                >
                                  <Eye className="h-2.5 w-2.5" /> Diff
                                </button>
                              </div>
                              <div className="max-h-28 overflow-y-auto">
                                <pre className="p-2 text-[10px] font-mono text-white/50 whitespace-pre-wrap">{action.content.substring(0, 500)}{action.content.length > 500 ? '\n…' : ''}</pre>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* Agent Activity Panel */}
            {agentRunning && (agentSteps.length > 0 || agentActivities.length > 0) && (
              <div className="border-t border-[#be123c]/20 bg-[#0a0a0a] max-h-44 overflow-y-auto px-3 py-2 shrink-0">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <Loader2 className="h-3 w-3 animate-spin text-[#be123c]" />
                    <span className="text-[10px] font-medium text-[#be123c]">Agent läuft</span>
                    {agentPlan && (
                      <span className="text-[9px] text-white/20 ml-1">
                        {agentPlan.steps.filter(s => s.status === 'done').length}/{agentPlan.steps.length} Schritte
                      </span>
                    )}
                  </div>
                  <button
                    title="Agent stoppen"
                    onClick={async () => {
                      if (agentTaskId) {
                        await fetch(`${API_BASE}/api/agent/stop`, {
                          method: 'POST', headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ task_id: agentTaskId })
                        });
                      }
                    }}
                    className="px-2 py-0.5 rounded text-[9px] bg-[#be123c]/20 text-[#be123c] hover:bg-[#be123c]/30 border border-[#be123c]/30"
                  >⛔ Stopp</button>
                </div>
                {/* Recent activities — compact checkmark list */}
                <div className="space-y-0.5">
                  {agentActivities.slice(-10).map((act, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-[10px] leading-tight">
                      <span className="shrink-0 w-3 text-center">
                        {act.success ? <Check className="h-2.5 w-2.5 text-[#22c55e] inline" /> : <span className="text-[#be123c]">✗</span>}
                      </span>
                      <span className={act.success ? 'text-white/40' : 'text-[#be123c]/70'}>
                        {act.icon} {act.label}
                      </span>
                    </div>
                  ))}
                  {/* Show current tool if no activities yet */}
                  {agentActivities.length === 0 && agentSteps.slice(-3).map((s, i) => (
                    <div key={i} className="text-[10px] text-white/30 truncate">
                      {s.event === 'tool_action' && <span>🔧 {s.data.tool}...</span>}
                      {s.event === 'step' && <span>📍 Schritt {s.data.step}/{s.data.max_steps}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Chat input */}
            <div className="border-t border-white/5 p-2.5 shrink-0">
              {/* Mode selector */}
              <div className="flex items-center gap-1 mb-2">
                {(['fragen', 'bearbeiten', 'agent'] as const).map(m => (
                  <button key={m} onClick={() => setChatMode(m)}
                    className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-all ${
                      chatMode === m
                        ? m === 'agent' ? 'border' : m === 'bearbeiten' ? 'bg-[#0891b2]/20 text-[#0891b2] border border-[#0891b2]/30'
                          : 'bg-[#22c55e]/20 text-[#22c55e] border border-[#22c55e]/30'
                        : 'bg-transparent text-white/40 border border-transparent hover:text-white/60 hover:bg-white/5'
                    }`}
                    style={chatMode === m && m === 'agent' ? { backgroundColor: `${accent}20`, color: accent, borderColor: `${accent}4d` } : undefined}>
                    {m === 'fragen' ? '💬 Fragen' : m === 'bearbeiten' ? '✏️ Bearbeiten' : '💜 Agent'}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                <input className="flex-1 bg-[#111] border border-white/10 rounded-lg px-3 py-2 text-[12px] text-white outline-none placeholder:text-white/25 transition-colors"
                  style={{ ['--tw-ring-color' as any]: `${accent}66` }}
                  value={chatInput} onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendCodeChat(); } }}
                  placeholder={chatMode === 'fragen' ? 'Frag Ailey etwas…' : chatMode === 'agent' ? 'Was soll Ailey tun?' : 'Code bearbeiten…'}
                  disabled={chatBusy || agentRunning}
                  onFocus={e => e.currentTarget.style.borderColor = `${accent}66`}
                  onBlur={e => e.currentTarget.style.borderColor = ''} />
                {(agentRunning || chatBusy) ? (
                  <button title="Stoppen" onClick={async () => {
                    if (agentRunning && agentTaskId) {
                      await fetch(`${API_BASE}/api/agent/stop`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task_id: agentTaskId })
                      });
                    } else if (chatAbortRef.current) {
                      chatAbortRef.current.abort();
                    }
                  }} className="p-2 rounded-lg text-white transition-colors animate-pulse"
                    style={{ backgroundColor: accent }}>
                    <Square className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button title="Senden" onClick={sendCodeChat} disabled={chatBusy} className="p-2 rounded-lg text-white transition-colors disabled:opacity-40"
                    style={{ backgroundColor: accent }}>
                    <Send className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              {currentTab && (
                <div className="text-[10px] text-white/25 mt-1.5 truncate flex items-center gap-1">
                  <File className={`h-2.5 w-2.5 ${getFileColor(currentTab.name)}`} />
                  {currentTab.name} · Ailey sieht diese Datei
                  {chatMode === 'agent' && <span style={{ color: `${accent}80` }} className="ml-1">· Autonomer Modus</span>}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Diff Preview Overlay ──────────────────────────────────────── */}
      {diffView && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-8" onClick={() => setDiffView(null)}>
          <div className="w-full max-w-4xl max-h-[80vh] bg-[#0a0a0a] rounded-xl border border-[#be123c]/30 overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="h-10 flex items-center justify-between px-4 border-b border-white/10 shrink-0">
              <div className="flex items-center gap-2 text-[12px]">
                <Eye className="h-4 w-4 text-[#0891b2]" />
                <span className="text-white font-medium">Diff Preview</span>
                <span className="text-white/40 font-mono text-[11px]">{diffView.path.split('/').pop()}</span>
              </div>
              <button title="Schließen" onClick={() => setDiffView(null)} className="p-1 rounded hover:bg-white/10"><X className="h-4 w-4 text-white/50" /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-1">
              <div className="font-mono text-[11px] leading-[18px]">
                {(() => {
                  const lines = computeDiff(diffView.oldContent, diffView.newContent);
                  let lineOld = 0, lineNew = 0;
                  return lines.map((dl, i) => {
                    if (dl.type === 'same') { lineOld++; lineNew++; }
                    else if (dl.type === 'remove') { lineOld++; }
                    else { lineNew++; }
                    return (
                      <div key={i} className={`flex ${
                        dl.type === 'add' ? 'bg-[#22c55e]/10' :
                        dl.type === 'remove' ? 'bg-[#be123c]/10' : ''
                      }`}>
                        <span className="w-10 text-right pr-2 text-white/20 select-none shrink-0">
                          {dl.type !== 'add' ? lineOld : ''}
                        </span>
                        <span className="w-10 text-right pr-2 text-white/20 select-none shrink-0">
                          {dl.type !== 'remove' ? lineNew : ''}
                        </span>
                        <span className={`w-4 text-center select-none shrink-0 ${
                          dl.type === 'add' ? 'text-[#22c55e]' :
                          dl.type === 'remove' ? 'text-[#be123c]' : 'text-white/10'
                        }`}>
                          {dl.type === 'add' ? '+' : dl.type === 'remove' ? '−' : ' '}
                        </span>
                        <span className={`flex-1 whitespace-pre-wrap ${
                          dl.type === 'add' ? 'text-[#22c55e]/80' :
                          dl.type === 'remove' ? 'text-[#be123c]/80' : 'text-white/50'
                        }`}>{dl.text}</span>
                      </div>
                    );
                  });
                })()}
              </div>
            </div>
            <div className="h-8 flex items-center px-4 border-t border-white/10 text-[10px] text-white/30 shrink-0">
              <span className="text-[#be123c]">−</span> Entfernt &nbsp;·&nbsp; <span className="text-[#22c55e]">+</span> Hinzugefügt &nbsp;·&nbsp; Esc zum Schließen
            </div>
          </div>
        </div>
      )}

      {/* ── Web Preview Panel ─────────────────────────────────────── */}
      {previewVisible && previewUrl && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-6" onClick={() => setPreviewVisible(false)}>
          <div className="w-full max-w-5xl h-[85vh] bg-[#0a0a0a] rounded-xl border border-[#be123c]/30 overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="h-10 flex items-center justify-between px-4 border-b border-white/10 shrink-0">
              <div className="flex items-center gap-2 text-[12px]">
                <Globe className="h-4 w-4 text-[#22c55e]" />
                <span className="text-white font-medium">Web Preview</span>
                <span className="text-white/40 font-mono text-[11px]">{previewUrl}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  title="In externem Browser öffnen"
                  onClick={() => window.open(previewUrl, '_blank')}
                  className="p-1 rounded hover:bg-white/10 text-white/50 hover:text-white"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </button>
                <button
                  title="Neu laden"
                  onClick={() => {
                    const iframe = document.getElementById('preview-iframe') as HTMLIFrameElement;
                    if (iframe) iframe.src = previewUrl;
                  }}
                  className="p-1 rounded hover:bg-white/10 text-white/50 hover:text-white"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
                <button title="Schließen" onClick={() => setPreviewVisible(false)} className="p-1 rounded hover:bg-white/10">
                  <X className="h-4 w-4 text-white/50" />
                </button>
              </div>
            </div>
            <iframe
              id="preview-iframe"
              src={previewUrl}
              className="flex-1 w-full bg-white"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
              title="Web Preview"
            />
          </div>
        </div>
      )}

      {/* ── Status Bar ────────────────────────────────────────────────── */}
      <div className="h-7 flex items-center px-2 md:px-4 text-[10px] md:text-[11px] text-white shrink-0 z-20 relative" style={{ backgroundColor: accent }}>
        <div className="flex items-center gap-2 md:gap-3">
          <span className="flex items-center gap-1 font-medium">
            <GitBranch className="h-3 w-3" />
            <span className="hidden sm:inline">{gitInfo?.is_git ? gitInfo.branch : 'kein git'}</span>
          </span>
          {gitInfo?.dirty && (
            <span className="text-white/80 text-[10px] hidden md:inline">{gitInfo.change_count} Änderung{gitInfo.change_count !== 1 ? 'en' : ''}</span>
          )}
          {currentTab && (
            <>
              <span className="text-white/60 hidden sm:inline">·</span>
              <span className="text-white/80 hidden sm:inline">{currentTab.language}</span>
            </>
          )}
          {currentTab?.dirty && <span className="text-white/70 flex items-center gap-1">● unsaved</span>}
          {/* Error/Warning count */}
          {diagnostics.length > 0 && (
            <button onClick={() => setErrorsVisible(!errorsVisible)} className="flex items-center gap-1 text-white/90 hover:text-white transition-colors">
              <span className="text-white/60">·</span>
              <XCircle className="h-3 w-3" />
              <span>{diagnostics.filter(d => d.severity === 'error').length}</span>
              <AlertTriangle className="h-3 w-3" />
              <span>{diagnostics.filter(d => d.severity === 'warning').length}</span>
            </button>
          )}
        </div>
        <div className="flex-1" />
        {/* Coder toggles */}
        <div className="hidden md:flex items-center gap-2 mr-3">
          <button
            onClick={() => { toggleCoderSetting('autocomplete', !coderAutocomplete); setCoderAutocomplete(!coderAutocomplete); }}
            className={`flex items-center gap-1 transition-colors ${coderAutocomplete ? 'text-white' : 'text-white/40'}`}
            title={coderAutocomplete ? 'Autocomplete AN' : 'Autocomplete AUS'}
          >
            <Sparkles className="h-3 w-3" />
            <span className="text-[10px]">AC</span>
            {coderAutocomplete ? <ToggleRight className="h-3 w-3" /> : <ToggleLeft className="h-3 w-3" />}
          </button>
          <button
            onClick={() => { toggleCoderSetting('lint', !coderLint); setCoderLint(!coderLint); }}
            className={`flex items-center gap-1 transition-colors ${coderLint ? 'text-white' : 'text-white/40'}`}
            title={coderLint ? 'Lint AN' : 'Lint AUS'}
          >
            <Bug className="h-3 w-3" />
            <span className="text-[10px]">Lint</span>
            {coderLint ? <ToggleRight className="h-3 w-3" /> : <ToggleLeft className="h-3 w-3" />}
          </button>
          {coderLoaded && <span className="text-[9px] text-white/50">Qwen</span>}
          {chatBusy && <span className="text-[9px] text-white/50 animate-pulse">Ailey…</span>}
          {lintBusy && <Loader2 className="h-3 w-3 animate-spin" />}
        </div>
        {/* System stats compact */}
        {sysStats && (
          <button onClick={() => setShowStats(!showStats)} className="hidden lg:flex items-center gap-2 mr-3 text-white/70 hover:text-white transition-colors" title="System Stats">
            <span className="text-[10px]">CPU {sysStats.cpu.percent}%</span>
            <span className="text-[10px]">RAM {sysStats.ram.percent}%</span>
            {sysStats.temperature?.cpu_temp_c != null && <span className="text-[10px]">{sysStats.temperature.cpu_temp_c}°C</span>}
          </button>
        )}
        <span className="text-white/60 hidden sm:inline">A!LEY CODE v2.6</span>
        {/* Mobile quick-access buttons in status bar */}
        {isMobile && (
          <div className="flex items-center gap-2">
            <button onClick={() => setTermVisible(!termVisible)} className="p-1 rounded hover:bg-white/10 transition-colors" title="Terminal">
              <TermIcon className={`h-3 w-3 ${termVisible ? 'text-white' : 'text-white/50'}`} />
            </button>
            {chatBusy && <span className="text-[9px] text-white/50 animate-pulse">Ailey…</span>}
          </div>
        )}
      </div>

      {/* ── System Stats Popup ─────────────────────────────────────────── */}
      {showStats && sysStats && (
        <div className="absolute bottom-8 right-4 z-50 bg-[#1e1e1e] border border-white/10 rounded-lg shadow-2xl p-4 w-72 text-[11px] text-white/80 space-y-3">
          <div className="flex justify-between items-center">
            <span className="font-semibold text-white text-[12px]">System Monitor</span>
            <button onClick={() => setShowStats(false)} title="Schließen" className="text-white/40 hover:text-white"><X className="h-3.5 w-3.5" /></button>
          </div>
          <div className="space-y-2">
            <div>
              <div className="flex justify-between"><span>CPU</span><span className="font-mono">{sysStats.cpu.percent}%</span></div>
              <div className="h-1.5 bg-white/10 rounded-full overflow-hidden mt-1">
                <div className={`h-full rounded-full transition-all ${sysStats.cpu.percent > 80 ? 'bg-red-500' : sysStats.cpu.percent > 50 ? 'bg-yellow-500' : 'bg-emerald-500'}`} style={{ width: `${sysStats.cpu.percent}%` }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between"><span>RAM</span><span className="font-mono">{sysStats.ram.used_gb}/{sysStats.ram.total_gb} GB ({sysStats.ram.percent}%)</span></div>
              <div className="h-1.5 bg-white/10 rounded-full overflow-hidden mt-1">
                <div className={`h-full rounded-full transition-all ${sysStats.ram.percent > 85 ? 'bg-red-500' : sysStats.ram.percent > 60 ? 'bg-yellow-500' : 'bg-emerald-500'}`} style={{ width: `${sysStats.ram.percent}%` }} />
              </div>
            </div>
            {sysStats.temperature?.cpu_temp_c != null && (
              <div className="flex justify-between"><span>Temperatur</span><span className="font-mono">{sysStats.temperature.cpu_temp_c}°C ({sysStats.temperature.thermal_pressure})</span></div>
            )}
            <div className="flex justify-between"><span>Thermal Level</span><span className={`font-mono ${sysStats.thermal_level >= 3 ? 'text-red-400' : sysStats.thermal_level >= 2 ? 'text-orange-400' : sysStats.thermal_level >= 1 ? 'text-yellow-400' : 'text-emerald-400'}`}>{['Nominal','Leicht','Moderat','Kritisch'][sysStats.thermal_level] || sysStats.thermal_level}</span></div>
            <div className="flex justify-between"><span>Modell</span><span className="font-mono">{sysStats.model.status}</span></div>
            <div className="flex justify-between"><span>IdleThinker</span><span className="font-mono">{sysStats.idle_thinker.enabled ? 'pausiert (Code Mode)' : 'pausiert'}</span></div>
          </div>
          <div className="text-[9px] text-white/30">Auto-Refresh 10s</div>
        </div>
      )}
    </div>
  );
}
