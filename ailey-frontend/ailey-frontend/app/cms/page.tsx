"use client";
import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import {
  Globe, Plus, X, Trash2, ChevronLeft, ChevronUp, ChevronDown, Eye, Download,
  ExternalLink, FileText, Layers, ArrowLeft, Moon, Sun, Sparkles, PanelLeft, PanelRight,
  ImageIcon, Upload, Link, Type, Settings, Scale, Navigation, Footprints, Search,
  Wand2, Copy, RotateCcw
} from 'lucide-react';

// ── Constants ────────────────────────────────────────────────────────────
const API_BASE = typeof window !== 'undefined'
  ? (() => {
      const h = window.location.hostname;
      if (!h || h === 'tauri.localhost' || h === 'localhost' || h === '127.0.0.1') return 'http://127.0.0.1:5502';
      return `http://${h}:5502`;
    })()
  : '';

// ══════════════════════════════════════════════════════════════════════════
// AILEY CMS MODE — AI-powered Page Builder
// ══════════════════════════════════════════════════════════════════════════
export default function CmsModePage() {
  const router = useRouter();

  // ── Theme (synced with main app) ─────────────────────────────────────
  const [uiTheme, setUiTheme] = useState<'dark'|'cyber'|'light'|'rainbowpunk'|'ailey'>(() => {
    if (typeof window !== 'undefined') {
      const v = localStorage.getItem('ailey-ui-theme');
      if (v && ['dark','light','cyber','rainbowpunk','ailey'].includes(v)) return v as any;
    }
    return 'dark';
  });
  useEffect(() => {
    document.documentElement.classList.toggle('dark', uiTheme !== 'light');
    document.documentElement.classList.toggle('cyber', uiTheme === 'cyber');
    document.documentElement.classList.toggle('rainbowpunk', uiTheme === 'rainbowpunk');
    document.documentElement.classList.remove('ailey-mood');
    document.documentElement.removeAttribute('data-ailey-mood');
  }, [uiTheme]);
  const toggleTheme = () => {
    const order: ('dark'|'light'|'cyber'|'rainbowpunk'|'ailey')[] = ['dark','light','cyber','rainbowpunk','ailey'];
    const next = order[(order.indexOf(uiTheme)+1) % order.length];
    setUiTheme(next);
    localStorage.setItem('ailey-ui-theme', next);
  };

  // ── CMS State ────────────────────────────────────────────────────────
  const [projects, setProjects] = useState<any[]>([]);
  const [currentProject, setCurrentProject] = useState<string|null>(null);
  const [site, setSite] = useState<any>(null);
  const [activePage, setActivePage] = useState('/');
  const [selectedSection, setSelectedSection] = useState<string|null>(null);
  const [templates, setTemplates] = useState<any>({});
  const [categories, setCategories] = useState<any>({});
  const [previewHtml, setPreviewHtml] = useState('');
  const [showAddSection, setShowAddSection] = useState(false);
  const [showAddPage, setShowAddPage] = useState(false);
  const [newPageTitle, setNewPageTitle] = useState('');
  const [newProjectTitle, setNewProjectTitle] = useState('');
  const [showNewProject, setShowNewProject] = useState(false);
  const [cmsLoading, setCmsLoading] = useState(false);
  const [previewMode, setPreviewMode] = useState<'desktop'|'tablet'|'mobile'>('desktop');
  const [mediaFiles, setMediaFiles] = useState<any[]>([]);
  const [exportResult, setExportResult] = useState<any>(null);
  const [cmsPanel, setCmsPanel] = useState<'pages'|'preview'|'props'>('preview');
  const [rightTab, setRightTab] = useState<'section'|'design'|'meta'|'nav'|'footer'|'legal'|'ai'>('design');
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState('');
  const previewRef = useRef<HTMLIFrameElement>(null);

  // ── API helpers ──────────────────────────────────────────────────────
  const loadProjects = async () => {
    try { const r = await fetch(`${API_BASE}/api/cms/projects`); const j = await r.json(); if (j.success) setProjects(j.projects); } catch (e) { console.warn('CMS load projects:', e); }
  };
  const loadTemplates = async () => {
    try { const r = await fetch(`${API_BASE}/api/cms/templates`); const j = await r.json(); if (j.success) { setTemplates(j.templates); setCategories(j.categories); } } catch (e) { console.warn('CMS templates:', e); }
  };
  const loadProject = async (slug: string) => {
    setCmsLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/cms/projects/${slug}`); const j = await r.json();
      if (j.success) { setSite(j.site); setCurrentProject(slug); setActivePage('/'); setSelectedSection(null); refreshPreview(j.site, '/'); }
    } catch (e) { console.warn('CMS load:', e); } finally { setCmsLoading(false); }
  };
  const createProject = async () => {
    if (!newProjectTitle.trim()) return;
    try {
      const r = await fetch(`${API_BASE}/api/cms/projects`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: newProjectTitle }) });
      const j = await r.json();
      if (j.success) { setShowNewProject(false); setNewProjectTitle(''); loadProjects(); loadProject(j.slug); }
    } catch (e) { console.warn('CMS create:', e); }
  };
  const deleteProject = async (slug: string) => {
    if (!confirm('Projekt wirklich löschen?')) return;
    try { await fetch(`${API_BASE}/api/cms/projects/${slug}`, { method: 'DELETE' }); if (currentProject === slug) { setCurrentProject(null); setSite(null); } loadProjects(); } catch (e) { console.warn(e); }
  };
  const saveSite = async () => {
    if (!currentProject || !site) return;
    try { await fetch(`${API_BASE}/api/cms/projects/${currentProject}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ site }) }); } catch (e) { console.warn(e); }
  };
  const refreshPreview = async (s?: any, pg?: string) => {
    const siteData = s || site; const pageSlug = pg || activePage;
    if (!siteData) return;
    try {
      const r = await fetch(`${API_BASE}/api/cms/preview-live`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ site: siteData, pageSlug }) });
      const html = await r.text(); setPreviewHtml(html);
    } catch (e) { console.warn('Preview:', e); }
  };
  const addSection = async (type: string) => {
    if (!currentProject) return;
    try {
      const r = await fetch(`${API_BASE}/api/cms/projects/${currentProject}/sections`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pageSlug: activePage, type }) });
      const j = await r.json(); if (j.success) { setShowAddSection(false); loadProject(currentProject); }
    } catch (e) { console.warn(e); }
  };
  const removeSection = async (sectionId: string) => {
    if (!currentProject || !confirm('Section löschen?')) return;
    try {
      await fetch(`${API_BASE}/api/cms/projects/${currentProject}/sections/${sectionId}`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pageSlug: activePage }) });
      loadProject(currentProject); setSelectedSection(null);
    } catch (e) { console.warn(e); }
  };
  const moveSection = async (sectionId: string, newIndex: number) => {
    if (!currentProject) return;
    try {
      await fetch(`${API_BASE}/api/cms/projects/${currentProject}/sections/${sectionId}/move`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pageSlug: activePage, newIndex }) });
      loadProject(currentProject);
    } catch (e) { console.warn(e); }
  };
  const updateSectionProps = async (sectionId: string, updates: any) => {
    if (!currentProject) return;
    try {
      await fetch(`${API_BASE}/api/cms/projects/${currentProject}/sections/${sectionId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pageSlug: activePage, updates }) });
      loadProject(currentProject);
    } catch (e) { console.warn(e); }
  };
  const addPage = async () => {
    if (!currentProject || !newPageTitle.trim()) return;
    try {
      const r = await fetch(`${API_BASE}/api/cms/projects/${currentProject}/pages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: newPageTitle }) });
      const j = await r.json(); if (j.success) { setShowAddPage(false); setNewPageTitle(''); loadProject(currentProject); }
    } catch (e) { console.warn(e); }
  };
  const removePage = async (slug: string) => {
    if (!currentProject || slug === '/' || !confirm('Seite löschen?')) return;
    try {
      await fetch(`${API_BASE}/api/cms/projects/${currentProject}/pages${slug}`, { method: 'DELETE' });
      if (activePage === slug) setActivePage('/'); loadProject(currentProject);
    } catch (e) { console.warn(e); }
  };
  const exportProject = async () => {
    if (!currentProject) return; setCmsLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/cms/projects/${currentProject}/export`, { method: 'POST' });
      const j = await r.json(); setExportResult(j);
    } catch (e) { console.warn(e); } finally { setCmsLoading(false); }
  };
  const loadMedia = async () => {
    if (!currentProject) return;
    try { const r = await fetch(`${API_BASE}/api/cms/projects/${currentProject}/media`); const j = await r.json(); if (j.success) setMediaFiles(j.files); } catch (e) { console.warn(e); }
  };
  const uploadMedia = async (file: File): Promise<string|null> => {
    if (!currentProject) return null;
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await fetch(`${API_BASE}/api/cms/projects/${currentProject}/media`, { method: 'POST', body: fd });
      const j = await r.json();
      if (j.success) { loadMedia(); return `${API_BASE}${j.url}`; }
    } catch (e) { console.warn(e); }
    return null;
  };
  const generateWithAI = async () => {
    if (!aiPrompt.trim() || aiBusy) return;
    setAiBusy(true); setAiError('');
    try {
      const r = await fetch(`${API_BASE}/api/cms/ai/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: aiPrompt, projectSlug: currentProject || undefined })
      });
      const j = await r.json();
      if (j.success && j.slug) {
        setAiPrompt('');
        loadProjects();
        loadProject(j.slug);
      } else {
        setAiError(j.error || 'AI-Generierung fehlgeschlagen');
      }
    } catch (e: any) { setAiError(e.message || 'Netzwerkfehler'); }
    finally { setAiBusy(false); }
  };

  useEffect(() => { loadProjects(); loadTemplates(); }, []);
  useEffect(() => { if (site) refreshPreview(); }, [activePage]);

  const currentPage = site?.pages?.find((p: any) => p.slug === activePage);
  const sections = currentPage?.sections || [];

  // Category labels
  const catLabels: Record<string, string> = { navigation: '🧭 Navigation', hero: '🎬 Hero', about: '👤 Über Uns', services: '⚙️ Leistungen', portfolio: '🖼️ Portfolio', testimonials: '⭐ Testimonials', content: '📄 Content', cta: '📢 CTA', features: '✅ Features', contact: '📬 Kontakt', blog: '📰 Blog', footer: '🦶 Footer', special: '🎯 Spezial' };

  // ── No project selected → Project List ────────────────────────────────
  if (!currentProject) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        {/* Header */}
        <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-sm">
          <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => router.push('/')} className="flex items-center gap-2 text-xs text-foreground/60 hover:text-foreground transition-colors" title="Zurück zu Ailey">
                <ArrowLeft className="h-3.5 w-3.5" /> Zurück zu Ailey
              </button>
              <div className="w-px h-5 bg-border" />
              <Globe className="h-5 w-5 text-emerald-500" />
              <h1 className="text-lg font-bold">CMS Mode</h1>
            </div>
            <Button variant="outline" size="icon" onClick={toggleTheme} className="h-8 w-8" title="Theme wechseln">
              {uiTheme === 'dark' ? <Moon className="h-3.5 w-3.5" /> : uiTheme === 'cyber' ? <Sparkles className="h-3.5 w-3.5 text-teal-400" /> : uiTheme === 'rainbowpunk' ? <span className="text-sm leading-none">🌈</span> : uiTheme === 'ailey' ? <span className="text-sm leading-none">🎭</span> : <Sun className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </header>

        <div className="max-w-4xl mx-auto px-3 sm:px-4 py-6 sm:py-8">
          <div className="flex items-center justify-between mb-6 sm:mb-8 gap-3">
            <div className="min-w-0">
              <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2 sm:gap-3"><Globe className="h-6 w-6 sm:h-8 sm:w-8 text-emerald-500 shrink-0" />CMS Mode</h1>
              <p className="text-muted-foreground mt-1 text-sm">Aileys AI-gestützter Page Builder</p>
            </div>
            <Button onClick={() => setShowNewProject(true)} className="gap-2"><Plus className="h-4 w-4" />Neues Projekt</Button>
          </div>

          {showNewProject && (
            <Card className="p-4 mb-6 border-primary/30">
              <div className="flex gap-2">
                <Input placeholder="Projektname (z.B. Friseur Berlin)" value={newProjectTitle} onChange={e => setNewProjectTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') createProject(); }} />
                <Button onClick={createProject}>Erstellen</Button>
                <Button variant="ghost" onClick={() => setShowNewProject(false)}><X className="h-4 w-4" /></Button>
              </div>
            </Card>
          )}

          {projects.length === 0 ? (
            <Card className="p-12 text-center border-dashed">
              <Globe className="h-16 w-16 mx-auto text-muted-foreground/30 mb-4" />
              <h2 className="text-xl font-semibold mb-2">Noch keine Projekte</h2>
              <p className="text-muted-foreground text-sm mb-4">Erstelle dein erstes Website-Projekt oder sag Ailey im Chat:<br /><span className="italic">&ldquo;Bau mir eine Website für...&rdquo;</span></p>
              <Button onClick={() => setShowNewProject(true)} className="gap-2"><Plus className="h-4 w-4" />Erstes Projekt erstellen</Button>
            </Card>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {projects.map((p: any) => (
                <Card key={p.slug} className="p-4 hover:border-primary/50 cursor-pointer transition-colors group" onClick={() => loadProject(p.slug)}>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-lg group-hover:text-primary transition-colors">{p.title}</h3>
                      <p className="text-xs text-muted-foreground mt-1">{p.pageCount} Seiten · {p.sectionCount} Sections</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">/{p.slug}</p>
                    </div>
                    <button onClick={e => { e.stopPropagation(); deleteProject(p.slug); }} className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 className="h-4 w-4" /></button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Page Builder ─────────────────────────────────────────────────────
  return (
    <div className="h-screen flex flex-col bg-background text-foreground">
      {/* Top Bar */}
      <header className="h-12 border-b border-border bg-background/80 backdrop-blur-sm flex items-center px-3 gap-2 shrink-0 z-50">
        <button onClick={() => { setCurrentProject(null); setSite(null); }} className="flex items-center gap-1.5 text-xs text-foreground/60 hover:text-foreground transition-colors" title="Zurück zu Projekten">
          <ChevronLeft className="h-3.5 w-3.5" />Projekte
        </button>
        <div className="w-px h-5 bg-border" />
        <Globe className="h-4 w-4 text-emerald-500 shrink-0" />
        <span className="text-sm font-semibold truncate flex-1">{site?.meta?.title || 'Projekt'}</span>

        {/* Mobile panel switcher */}
        <div className="lg:hidden flex items-center gap-1">
          {([{ id: 'pages' as const, label: 'Seiten', icon: PanelLeft }, { id: 'preview' as const, label: 'Preview', icon: Eye }, { id: 'props' as const, label: 'Edit', icon: PanelRight }] as const).map(p => (
            <button key={p.id} onClick={() => setCmsPanel(p.id)} className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs transition-colors ${cmsPanel === p.id ? 'bg-primary/15 text-primary font-medium' : 'hover:bg-primary/5 text-muted-foreground'}`}>
              <p.icon className="h-3 w-3" />{p.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => refreshPreview()} className="p-1.5 rounded hover:bg-primary/10 text-muted-foreground" title="Preview aktualisieren"><Eye className="h-3.5 w-3.5" /></button>
          <button onClick={exportProject} className="p-1.5 rounded hover:bg-primary/10 text-muted-foreground" title="Exportieren"><Download className="h-3.5 w-3.5" /></button>
          <Button variant="outline" size="icon" onClick={toggleTheme} className="h-7 w-7" title="Theme wechseln">
            {uiTheme === 'dark' ? <Moon className="h-3 w-3" /> : uiTheme === 'cyber' ? <Sparkles className="h-3 w-3 text-teal-400" /> : uiTheme === 'rainbowpunk' ? <span className="text-xs leading-none">🌈</span> : uiTheme === 'ailey' ? <span className="text-xs leading-none">🎭</span> : <Sun className="h-3 w-3" />}
          </Button>
          <button onClick={() => router.push('/')} className="p-1.5 rounded hover:bg-primary/10 text-muted-foreground" title="Zurück zu Ailey"><ArrowLeft className="h-3.5 w-3.5" /></button>
        </div>
      </header>

      {/* Main 3-panel layout */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left Panel: Pages + Sections */}
        <div className={`${cmsPanel === 'pages' ? 'flex' : 'hidden'} lg:flex w-full lg:w-64 border-r border-border bg-card/50 flex-col overflow-y-auto shrink-0 flex-1 lg:flex-none`}>
          {/* Pages */}
          <div className="p-3 border-b border-border">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Seiten</span>
              <button onClick={() => setShowAddPage(true)} className="p-0.5 rounded hover:bg-primary/10"><Plus className="h-3 w-3" /></button>
            </div>
            {showAddPage && (
              <div className="flex gap-1 mb-2">
                <Input className="h-7 text-xs" placeholder="Seitenname" value={newPageTitle} onChange={e => setNewPageTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') addPage(); }} />
                <button onClick={addPage} className="px-2 py-1 text-xs bg-primary text-primary-foreground rounded">+</button>
              </div>
            )}
            {site?.pages?.map((p: any) => (
              <div key={p.slug} className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs cursor-pointer transition-colors ${activePage === p.slug ? 'bg-primary/15 text-primary font-medium' : 'hover:bg-primary/5'}`} onClick={() => setActivePage(p.slug)}>
                <FileText className="h-3 w-3 shrink-0" />
                <span className="truncate flex-1">{p.title}</span>
                {p.slug !== '/' && <button onClick={e => { e.stopPropagation(); removePage(p.slug); }} className="p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-destructive/10"><X className="h-2.5 w-2.5" /></button>}
              </div>
            ))}
          </div>

          {/* Sections on current page */}
          <div className="flex-1 p-3 overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Sections</span>
              <button onClick={() => setShowAddSection(true)} className="p-0.5 rounded hover:bg-primary/10"><Plus className="h-3 w-3" /></button>
            </div>
            {sections.length === 0 && !showAddSection && (
              <div className="text-center py-6 text-muted-foreground">
                <Layers className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-xs">Keine Sections</p>
                <button onClick={() => setShowAddSection(true)} className="text-xs text-primary hover:underline mt-1">+ Section hinzufügen</button>
              </div>
            )}
            {sections.map((s: any, i: number) => {
              const tpl = templates[s.type];
              return (
                <div key={s.id} className={`flex items-center gap-1.5 px-2 py-1.5 rounded text-xs cursor-pointer transition-colors mb-0.5 group ${selectedSection === s.id ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'hover:bg-primary/5'}`} onClick={() => { setSelectedSection(s.id); setRightTab('section'); }}>
                  <span className="text-sm">{tpl?.icon || '📦'}</span>
                  <span className="truncate flex-1">{tpl?.label || s.type}</span>
                  <div className="flex gap-0.5 opacity-0 group-hover:opacity-100">
                    {i > 0 && <button onClick={e => { e.stopPropagation(); moveSection(s.id, i - 1); }} className="p-0.5 rounded hover:bg-primary/10"><ChevronUp className="h-3 w-3" /></button>}
                    {i < sections.length - 1 && <button onClick={e => { e.stopPropagation(); moveSection(s.id, i + 1); }} className="p-0.5 rounded hover:bg-primary/10"><ChevronDown className="h-3 w-3" /></button>}
                    <button onClick={e => { e.stopPropagation(); removeSection(s.id); }} className="p-0.5 rounded hover:bg-destructive/10 text-destructive"><Trash2 className="h-3 w-3" /></button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Export result */}
          {exportResult && (
            <div className={`p-3 border-t border-border text-xs ${exportResult.success ? 'text-emerald-400' : 'text-red-400'}`}>
              {exportResult.success ? `✓ Exportiert: ${exportResult.file_count} Dateien` : `✗ ${exportResult.error}`}
              <button onClick={() => setExportResult(null)} className="ml-2 underline">OK</button>
            </div>
          )}
        </div>

        {/* Center: Live Preview */}
        <div className={`${cmsPanel === 'preview' ? 'flex' : 'hidden'} lg:flex flex-1 flex-col bg-muted/30 min-w-0`}>
          {/* Preview toolbar */}
          <div className="flex items-center justify-between px-2 sm:px-3 py-2 border-b border-border bg-card/50">
            <div className="flex items-center gap-1">
              {(['desktop', 'tablet', 'mobile'] as const).map(mode => {
                const icons = { desktop: '💻', tablet: '📲', mobile: '📱' };
                return <button key={mode} onClick={() => setPreviewMode(mode)} className={`px-2 py-1 rounded text-xs ${previewMode === mode ? 'bg-primary/15 text-primary' : 'hover:bg-primary/5 text-muted-foreground'}`}>{icons[mode]}</button>;
              })}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-muted-foreground">{site?.meta?.title}</span>
              <button onClick={() => { if (currentProject) window.open(`${API_BASE}/api/cms/projects/${currentProject}/preview?page=${activePage}`, '_blank'); }} className="p-1 rounded hover:bg-primary/10 text-muted-foreground" title="In neuem Tab öffnen"><ExternalLink className="h-3.5 w-3.5" /></button>
            </div>
          </div>
          {/* iframe */}
          <div className="flex-1 flex justify-center p-2 sm:p-4 overflow-auto">
            <div style={{ width: previewMode === 'desktop' ? '100%' : previewMode === 'tablet' ? '768px' : '375px', maxWidth: '100%', transition: 'width 0.3s' }} className="h-full">
              <iframe ref={previewRef} srcDoc={previewHtml} className="w-full h-full bg-white rounded-lg shadow-lg border border-border" sandbox="allow-scripts allow-same-origin" />
            </div>
          </div>
        </div>

        {/* Right Panel: Properties — Tabbed */}
        <div className={`${cmsPanel === 'props' ? 'flex flex-col' : 'hidden'} lg:flex lg:flex-col w-full lg:w-80 border-l border-border bg-card/50 shrink-0 flex-1 lg:flex-none`}>
          {/* Tab bar */}
          <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-border overflow-x-auto shrink-0 bg-card/80">
            {([
              { id: 'section' as const, label: '📝', tip: 'Section' },
              { id: 'design' as const, label: '🎨', tip: 'Design' },
              { id: 'meta' as const, label: '🔍', tip: 'SEO/Meta' },
              { id: 'nav' as const, label: '🧭', tip: 'Navigation' },
              { id: 'footer' as const, label: '🦶', tip: 'Footer' },
              { id: 'legal' as const, label: '⚖️', tip: 'Legal' },
              { id: 'ai' as const, label: '✨', tip: 'AI' },
            ]).map(t => (
              <button key={t.id} title={t.tip} onClick={() => { setRightTab(t.id); if (t.id !== 'section') setSelectedSection(null); }}
                className={`px-2 py-1 rounded text-xs whitespace-nowrap transition-colors ${rightTab === t.id ? 'bg-primary/15 text-primary font-medium' : 'hover:bg-primary/5 text-muted-foreground'}`}>
                {t.label} <span className="hidden sm:inline">{t.tip}</span>
              </button>
            ))}
          </div>

          {/* Tab content — scrollable */}
          <div className="flex-1 overflow-y-auto">

          {/* ═══ SECTION TAB ═══ */}
          {(rightTab === 'section' || (selectedSection && rightTab !== 'ai')) && (() => {
            const sec = sections.find((s: any) => s.id === selectedSection);
            if (!sec) return (
              <div className="p-4 text-center text-muted-foreground">
                <Layers className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-xs">Wähle eine Section links</p>
              </div>
            );
            const tpl = templates[sec.type];
            return (
              <div className="p-3 space-y-4">
                {/* Header */}
                <div className="flex items-center gap-2">
                  <span className="text-xl">{tpl?.icon || '📦'}</span>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-sm truncate">{tpl?.label || sec.type}</h3>
                    <p className="text-[10px] text-muted-foreground">{sec.id}</p>
                  </div>
                  <button title="Deselect" onClick={() => setSelectedSection(null)} className="ml-auto p-1 rounded hover:bg-primary/10 text-muted-foreground"><X className="h-3 w-3" /></button>
                </div>

                {/* Variant selector */}
                {tpl?.variants?.length > 0 && (
                  <div>
                    <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1 block">Variante</label>
                    <div className="flex flex-wrap gap-1">
                      {tpl.variants.map((v: string) => (
                        <button key={v} onClick={() => updateSectionProps(sec.id, { variant: v })} className={`px-2 py-1 rounded text-xs border transition-colors ${sec.variant === v ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:border-primary/30'}`}>{v}</button>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Props Editor (full: strings, objects, arrays, images) ── */}
                <div>
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">📝 Inhalte</label>
                  {Object.entries(sec.props || {}).map(([key, val]) => {
                    // String props
                    if (typeof val === 'string') {
                      return (
                        <div key={key} className="mb-2">
                          <label className="text-[10px] text-muted-foreground block mb-0.5">{key}</label>
                          {val.length > 80 ? (
                            <textarea className="w-full px-2 py-1.5 text-xs rounded border border-border bg-background resize-y" rows={3} defaultValue={val} placeholder={key} onBlur={e => updateSectionProps(sec.id, { props: { [key]: e.target.value } })} />
                          ) : (
                            <Input className="h-7 text-xs" defaultValue={val} onBlur={e => updateSectionProps(sec.id, { props: { [key]: e.target.value } })} />
                          )}
                        </div>
                      );
                    }
                    // Boolean props
                    if (typeof val === 'boolean') {
                      return (
                        <div key={key} className="mb-2 flex items-center gap-2">
                          <input type="checkbox" checked={val} onChange={e => updateSectionProps(sec.id, { props: { [key]: e.target.checked } })} />
                          <label className="text-xs text-muted-foreground">{key}</label>
                        </div>
                      );
                    }
                    // Number props
                    if (typeof val === 'number') {
                      return (
                        <div key={key} className="mb-2">
                          <label className="text-[10px] text-muted-foreground block mb-0.5">{key}</label>
                          <Input className="h-7 text-xs" type="number" defaultValue={val} onBlur={e => updateSectionProps(sec.id, { props: { [key]: Number(e.target.value) } })} />
                        </div>
                      );
                    }
                    // CTA / link objects {text, href, ...}
                    if (typeof val === 'object' && val && !Array.isArray(val) && ('text' in val || 'href' in val)) {
                      return (
                        <div key={key} className="mb-2 p-2 rounded border border-border/50">
                          <label className="text-[10px] text-muted-foreground font-medium block mb-1">🔗 {key}</label>
                          {Object.entries(val as Record<string, any>).filter(([, v2]) => typeof v2 === 'string').map(([k2, v2]) => (
                            <div key={k2} className="mb-1">
                              <label className="text-[10px] text-muted-foreground/70">{k2}</label>
                              <Input className="h-6 text-xs" defaultValue={String(v2)} onBlur={e => updateSectionProps(sec.id, { props: { [key]: { ...(val as any), [k2]: e.target.value } } })} />
                            </div>
                          ))}
                        </div>
                      );
                    }
                    // Image objects {src, alt, ...}
                    if (typeof val === 'object' && val && !Array.isArray(val) && ('src' in val || 'alt' in val)) {
                      const imgObj = val as Record<string, any>;
                      return (
                        <div key={key} className="mb-2 p-2 rounded border border-border/50">
                          <label className="text-[10px] text-muted-foreground font-medium block mb-1">🖼️ {key}</label>
                          {imgObj.src && <img src={imgObj.src} alt={imgObj.alt || ''} className="w-full h-20 object-cover rounded mb-1" />}
                          <div className="mb-1">
                            <label className="text-[10px] text-muted-foreground/70">src (URL)</label>
                            <Input className="h-6 text-xs" defaultValue={imgObj.src || ''} placeholder="https://... oder Upload" onBlur={e => updateSectionProps(sec.id, { props: { [key]: { ...imgObj, src: e.target.value } } })} />
                          </div>
                          <div className="mb-1">
                            <label className="text-[10px] text-muted-foreground/70">alt</label>
                            <Input className="h-6 text-xs" defaultValue={imgObj.alt || ''} onBlur={e => updateSectionProps(sec.id, { props: { [key]: { ...imgObj, alt: e.target.value } } })} />
                          </div>
                          <label className="flex items-center gap-1 text-[10px] text-primary cursor-pointer hover:underline mt-1">
                            <Upload className="h-3 w-3" /> Bild hochladen
                            <input type="file" accept="image/*" className="hidden" onChange={async e2 => {
                              const f = e2.target.files?.[0]; if (!f) return;
                              const url = await uploadMedia(f);
                              if (url) updateSectionProps(sec.id, { props: { [key]: { ...imgObj, src: url, alt: imgObj.alt || f.name } } });
                            }} />
                          </label>
                        </div>
                      );
                    }
                    // Generic object (colors, info, etc.)
                    if (typeof val === 'object' && val && !Array.isArray(val)) {
                      return (
                        <div key={key} className="mb-2 p-2 rounded border border-border/50">
                          <label className="text-[10px] text-muted-foreground font-medium block mb-1">⚙️ {key}</label>
                          {Object.entries(val as Record<string, any>).filter(([, v2]) => typeof v2 === 'string' || typeof v2 === 'number').map(([k2, v2]) => (
                            <div key={k2} className="mb-1">
                              <label className="text-[10px] text-muted-foreground/70">{k2}</label>
                              <Input className="h-6 text-xs" defaultValue={String(v2)} onBlur={e => {
                                const newVal = typeof v2 === 'number' ? Number(e.target.value) : e.target.value;
                                updateSectionProps(sec.id, { props: { [key]: { ...(val as any), [k2]: newVal } } });
                              }} />
                            </div>
                          ))}
                        </div>
                      );
                    }
                    // ── ARRAY props (items, members, stats, fields, plans, logos, images, posts, links) ──
                    if (Array.isArray(val)) {
                      const arr = val as any[];
                      return (
                        <div key={key} className="mb-3">
                          <div className="flex items-center justify-between mb-1">
                            <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">📋 {key} ({arr.length})</label>
                            <button title={`${key} hinzufügen`} onClick={() => {
                              const template = arr.length > 0 ? Object.fromEntries(Object.entries(arr[0]).map(([k,v]) => [k, typeof v === 'string' ? '' : typeof v === 'number' ? 0 : typeof v === 'boolean' ? false : Array.isArray(v) ? [] : typeof v === 'object' && v ? Object.fromEntries(Object.entries(v).map(([k2]) => [k2, ''])) : ''])) : { text: '' };
                              const newArr = [...arr, template];
                              updateSectionProps(sec.id, { props: { [key]: newArr } });
                            }} className="p-0.5 rounded hover:bg-primary/10 text-primary"><Plus className="h-3 w-3" /></button>
                          </div>
                          {arr.map((item, idx) => (
                            <div key={idx} className="mb-2 p-2 rounded border border-border/30 bg-background/50 relative group/item">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-[10px] text-muted-foreground font-medium">#{idx + 1}</span>
                                <div className="flex gap-0.5 opacity-0 group-hover/item:opacity-100 transition-opacity">
                                  {idx > 0 && <button title="Nach oben" onClick={() => { const a = [...arr]; [a[idx-1],a[idx]] = [a[idx],a[idx-1]]; updateSectionProps(sec.id, { props: { [key]: a } }); }} className="p-0.5 rounded hover:bg-primary/10"><ChevronUp className="h-2.5 w-2.5" /></button>}
                                  {idx < arr.length - 1 && <button title="Nach unten" onClick={() => { const a = [...arr]; [a[idx],a[idx+1]] = [a[idx+1],a[idx]]; updateSectionProps(sec.id, { props: { [key]: a } }); }} className="p-0.5 rounded hover:bg-primary/10"><ChevronDown className="h-2.5 w-2.5" /></button>}
                                  <button title="Duplizieren" onClick={() => { const a = [...arr]; a.splice(idx+1, 0, JSON.parse(JSON.stringify(item))); updateSectionProps(sec.id, { props: { [key]: a } }); }} className="p-0.5 rounded hover:bg-primary/10"><Copy className="h-2.5 w-2.5" /></button>
                                  <button title="Löschen" onClick={() => { const a = arr.filter((_: any, i: number) => i !== idx); updateSectionProps(sec.id, { props: { [key]: a } }); }} className="p-0.5 rounded hover:bg-destructive/10 text-destructive"><Trash2 className="h-2.5 w-2.5" /></button>
                                </div>
                              </div>
                              {typeof item === 'string' ? (
                                <Input className="h-6 text-xs" defaultValue={item} onBlur={e => { const a = [...arr]; a[idx] = e.target.value; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                              ) : typeof item === 'object' && item ? (
                                Object.entries(item).map(([ik, iv]) => {
                                  if (typeof iv === 'string') {
                                    return (
                                      <div key={ik} className="mb-1">
                                        <label className="text-[10px] text-muted-foreground/70">{ik}</label>
                                        {iv.length > 60 ? (
                                          <textarea className="w-full px-1.5 py-1 text-xs rounded border border-border bg-background resize-y" rows={2} defaultValue={iv} placeholder={ik}
                                            onBlur={e => { const a = [...arr]; a[idx] = { ...item, [ik]: e.target.value }; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                                        ) : (
                                          <Input className="h-6 text-xs" defaultValue={iv}
                                            onBlur={e => { const a = [...arr]; a[idx] = { ...item, [ik]: e.target.value }; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                                        )}
                                      </div>
                                    );
                                  }
                                  if (typeof iv === 'number') {
                                    return (
                                      <div key={ik} className="mb-1">
                                        <label className="text-[10px] text-muted-foreground/70">{ik}</label>
                                        <Input className="h-6 text-xs" type="number" defaultValue={iv}
                                          onBlur={e => { const a = [...arr]; a[idx] = { ...item, [ik]: Number(e.target.value) }; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                                      </div>
                                    );
                                  }
                                  if (typeof iv === 'boolean') {
                                    return (
                                      <div key={ik} className="mb-1 flex items-center gap-1.5">
                                        <input type="checkbox" checked={iv} onChange={e => { const a = [...arr]; a[idx] = { ...item, [ik]: e.target.checked }; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                                        <label className="text-[10px] text-muted-foreground/70">{ik}</label>
                                      </div>
                                    );
                                  }
                                  if (Array.isArray(iv)) {
                                    return (
                                      <div key={ik} className="mb-1">
                                        <label className="text-[10px] text-muted-foreground/70">{ik} (komma-getrennt)</label>
                                        <Input className="h-6 text-xs" defaultValue={(iv as string[]).join(', ')}
                                          onBlur={e => { const a = [...arr]; a[idx] = { ...item, [ik]: e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean) }; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                                      </div>
                                    );
                                  }
                                  // Nested image object inside array item
                                  if (typeof iv === 'object' && iv && ('src' in iv || 'alt' in iv)) {
                                    const iObj = iv as Record<string, any>;
                                    return (
                                      <div key={ik} className="mb-1 p-1.5 rounded border border-border/30">
                                        <label className="text-[10px] text-muted-foreground/70">🖼️ {ik}</label>
                                        {iObj.src && <img src={iObj.src} alt={iObj.alt || ''} className="w-full h-14 object-cover rounded my-0.5" />}
                                        <Input className="h-6 text-xs mb-0.5" defaultValue={iObj.src || ''} placeholder="URL"
                                          onBlur={e => { const a = [...arr]; a[idx] = { ...item, [ik]: { ...iObj, src: e.target.value } }; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                                        <label className="flex items-center gap-1 text-[10px] text-primary cursor-pointer hover:underline">
                                          <Upload className="h-2.5 w-2.5" /> Upload
                                          <input type="file" accept="image/*" className="hidden" onChange={async e2 => {
                                            const f = e2.target.files?.[0]; if (!f) return;
                                            const url = await uploadMedia(f);
                                            if (url) { const a = [...arr]; a[idx] = { ...item, [ik]: { ...iObj, src: url } }; updateSectionProps(sec.id, { props: { [key]: a } }); }
                                          }} />
                                        </label>
                                      </div>
                                    );
                                  }
                                  // Nested CTA object inside array item
                                  if (typeof iv === 'object' && iv && ('text' in iv || 'href' in iv)) {
                                    const cObj = iv as Record<string, any>;
                                    return (
                                      <div key={ik} className="mb-1 p-1.5 rounded border border-border/30">
                                        <label className="text-[10px] text-muted-foreground/70">🔗 {ik}</label>
                                        {Object.entries(cObj).filter(([,cv]) => typeof cv === 'string').map(([ck, cv]) => (
                                          <div key={ck} className="mb-0.5">
                                            <label className="text-[9px] text-muted-foreground/50">{ck}</label>
                                            <Input className="h-5 text-xs" defaultValue={String(cv)}
                                              onBlur={e => { const a = [...arr]; a[idx] = { ...item, [ik]: { ...cObj, [ck]: e.target.value } }; updateSectionProps(sec.id, { props: { [key]: a } }); }} />
                                          </div>
                                        ))}
                                      </div>
                                    );
                                  }
                                  return null;
                                })
                              ) : null}
                            </div>
                          ))}
                        </div>
                      );
                    }
                    return null;
                  })}
                </div>

                {/* Style */}
                <div>
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">🎨 Style</label>
                  <div className="mb-2">
                    <label className="text-[10px] text-muted-foreground">Custom ID</label>
                    <Input className="h-7 text-xs" defaultValue={sec.style?.customId || ''} onBlur={e => updateSectionProps(sec.id, { style: { customId: e.target.value } })} />
                  </div>
                  <div className="mb-2">
                    <label className="text-[10px] text-muted-foreground">Custom Classes</label>
                    <Input className="h-7 text-xs" defaultValue={sec.style?.customClasses || ''} onBlur={e => updateSectionProps(sec.id, { style: { customClasses: e.target.value } })} />
                  </div>
                  <div className="mb-2">
                    <label className="text-[10px] text-muted-foreground">Custom CSS</label>
                    <textarea className="w-full px-2 py-1.5 text-xs rounded border border-border bg-background font-mono resize-y" rows={3} defaultValue={sec.style?.customCSS || ''} placeholder="#my-section { ... }" onBlur={e => updateSectionProps(sec.id, { style: { customCSS: e.target.value } })} />
                  </div>
                </div>

                {/* Visibility */}
                <div>
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">📱 Sichtbarkeit</label>
                  <div className="flex gap-2">
                    {(['desktop', 'tablet', 'mobile'] as const).map(device => (
                      <label key={device} className="flex items-center gap-1 text-xs">
                        <input type="checkbox" checked={sec.visibility?.[device] !== false} onChange={e => updateSectionProps(sec.id, { visibility: { [device]: e.target.checked } })} />
                        {device === 'desktop' ? '💻' : device === 'tablet' ? '📲' : '📱'}
                      </label>
                    ))}
                  </div>
                </div>

                {/* Animation */}
                <div>
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">✨ Animation</label>
                  <div className="flex flex-wrap gap-1">
                    {['none', 'fade-up', 'slide-left', 'zoom-in'].map(a => (
                      <button key={a} onClick={() => updateSectionProps(sec.id, { animation: { type: a } })} className={`px-2 py-1 rounded text-xs border ${sec.animation?.type === a ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:border-primary/30'}`}>{a}</button>
                    ))}
                  </div>
                </div>
              </div>
            );
          })()}

          {/* ═══ DESIGN TAB ═══ */}
          {rightTab === 'design' && !selectedSection && (
            <div className="p-3 space-y-4">
              <h3 className="font-semibold text-sm">🎨 Design</h3>

              {/* Colors */}
              {site?.design?.colors && (
                <div>
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Farben</label>
                  {Object.entries(site.design.colors).map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2 mb-1">
                      <input type="color" title={key} value={String(val)} onChange={e => {
                        const newSite = { ...site, design: { ...site.design, colors: { ...site.design.colors, [key]: e.target.value } } };
                        setSite(newSite);
                      }} className="w-6 h-6 rounded border border-border cursor-pointer" />
                      <span className="text-xs text-muted-foreground flex-1">{key}</span>
                      <span className="text-[10px] font-mono text-muted-foreground/60">{String(val)}</span>
                    </div>
                  ))}
                  <Button size="sm" variant="outline" className="mt-2 text-xs h-7 w-full" onClick={() => { saveSite(); setTimeout(() => refreshPreview(), 300); }}>Farben anwenden</Button>
                </div>
              )}

              {/* Fonts */}
              {site?.design?.fonts && (
                <div>
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Schriften</label>
                  {Object.entries(site.design.fonts).map(([key, fconf]: [string, any]) => (
                    <div key={key} className="mb-2">
                      <label className="text-[10px] text-muted-foreground block mb-0.5">{key} ({fconf.weight})</label>
                      <Input className="h-7 text-xs" defaultValue={fconf.family || ''} placeholder="z.B. Inter, Poppins, Playfair Display" onBlur={e => {
                        const newFonts = { ...site.design.fonts, [key]: { ...fconf, family: e.target.value } };
                        const newSite = { ...site, design: { ...site.design, fonts: newFonts } };
                        setSite(newSite);
                      }} />
                    </div>
                  ))}
                  <Button size="sm" variant="outline" className="mt-1 text-xs h-7 w-full" onClick={() => { saveSite(); setTimeout(() => refreshPreview(), 300); }}>Schriften anwenden</Button>
                </div>
              )}

              {/* Spacing */}
              {site?.design?.sizes && (
                <div>
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Größen</label>
                  {Object.entries(site.design.sizes).map(([key, val]) => (
                    <div key={key} className="mb-1 flex items-center gap-2">
                      <label className="text-[10px] text-muted-foreground w-10 shrink-0">{key}</label>
                      <Input className="h-6 text-xs" defaultValue={String(val)} onBlur={e => {
                        const newSizes = { ...site.design.sizes, [key]: e.target.value };
                        setSite({ ...site, design: { ...site.design, sizes: newSizes } });
                      }} />
                    </div>
                  ))}
                </div>
              )}

              {/* Border Radius + Max Width */}
              <div>
                <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Layout</label>
                <div className="mb-1">
                  <label className="text-[10px] text-muted-foreground">Border Radius</label>
                  <Input className="h-7 text-xs" defaultValue={site?.design?.borderRadius || '0.5rem'} onBlur={e => setSite({ ...site, design: { ...site.design, borderRadius: e.target.value } })} />
                </div>
                <div className="mb-1">
                  <label className="text-[10px] text-muted-foreground">Max Width</label>
                  <Input className="h-7 text-xs" defaultValue={site?.design?.maxWidth || '1280px'} onBlur={e => setSite({ ...site, design: { ...site.design, maxWidth: e.target.value } })} />
                </div>
              </div>

              {/* Global CSS */}
              <div>
                <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Globales CSS</label>
                <textarea className="w-full px-2 py-1.5 text-xs rounded border border-border bg-background font-mono resize-y" rows={4} defaultValue={site?.design?.globalCSS || ''} placeholder="/* Eigenes CSS */" onBlur={e => {
                  setSite({ ...site, design: { ...site.design, globalCSS: e.target.value } });
                  saveSite();
                }} />
              </div>

              <Button size="sm" className="w-full text-xs h-8" onClick={() => { saveSite(); setTimeout(() => refreshPreview(), 300); }}>💾 Design speichern & Preview</Button>
            </div>
          )}

          {/* ═══ META / SEO TAB ═══ */}
          {rightTab === 'meta' && !selectedSection && (
            <div className="p-3 space-y-4">
              <h3 className="font-semibold text-sm">🔍 SEO & Meta</h3>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">Seitentitel</label>
                <Input className="h-7 text-xs" defaultValue={site?.meta?.title || ''} onBlur={e => {
                  setSite({ ...site, meta: { ...site.meta, title: e.target.value } });
                }} />
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">Beschreibung</label>
                <textarea className="w-full px-2 py-1.5 text-xs rounded border border-border bg-background resize-y" rows={3} defaultValue={site?.meta?.description || ''} placeholder="SEO-Beschreibung für Google" onBlur={e => {
                  setSite({ ...site, meta: { ...site.meta, description: e.target.value } });
                }} />
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">Sprache</label>
                <Input className="h-7 text-xs" defaultValue={site?.meta?.language || 'de'} onBlur={e => setSite({ ...site, meta: { ...site.meta, language: e.target.value } })} />
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">Favicon URL</label>
                <Input className="h-7 text-xs" defaultValue={site?.meta?.favicon || ''} placeholder="https://..." onBlur={e => setSite({ ...site, meta: { ...site.meta, favicon: e.target.value } })} />
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">OG Image URL</label>
                <Input className="h-7 text-xs" defaultValue={site?.meta?.ogImage || ''} placeholder="Social-Media Vorschaubild" onBlur={e => setSite({ ...site, meta: { ...site.meta, ogImage: e.target.value } })} />
              </div>
              <Button size="sm" className="w-full text-xs h-8" onClick={() => { saveSite(); setTimeout(() => refreshPreview(), 300); }}>💾 Meta speichern</Button>
            </div>
          )}

          {/* ═══ NAV TAB ═══ */}
          {rightTab === 'nav' && !selectedSection && (
            <div className="p-3 space-y-4">
              <h3 className="font-semibold text-sm">🧭 Navigation</h3>

              {/* Logo */}
              <div>
                <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Logo</label>
                <div className="mb-1">
                  <label className="text-[10px] text-muted-foreground">Logo URL</label>
                  <Input className="h-7 text-xs" defaultValue={site?.nav?.logo?.src || ''} placeholder="https://..." onBlur={e => {
                    setSite({ ...site, nav: { ...site.nav, logo: { ...site.nav?.logo, src: e.target.value } } });
                  }} />
                </div>
                <div className="mb-1">
                  <label className="text-[10px] text-muted-foreground">Alt-Text</label>
                  <Input className="h-7 text-xs" defaultValue={site?.nav?.logo?.alt || ''} onBlur={e => {
                    setSite({ ...site, nav: { ...site.nav, logo: { ...site.nav?.logo, alt: e.target.value } } });
                  }} />
                </div>
                <label className="flex items-center gap-1 text-[10px] text-primary cursor-pointer hover:underline mt-1">
                  <Upload className="h-3 w-3" /> Logo hochladen
                  <input type="file" accept="image/*" className="hidden" onChange={async e2 => {
                    const f = e2.target.files?.[0]; if (!f) return;
                    const url = await uploadMedia(f);
                    if (url) setSite({ ...site, nav: { ...site.nav, logo: { ...site.nav?.logo, src: url } } });
                  }} />
                </label>
              </div>

              {/* Nav Links */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Links</label>
                  <button title="Link hinzufügen" onClick={() => {
                    const links = [...(site?.nav?.links || []), { label: 'Neuer Link', href: '#' }];
                    setSite({ ...site, nav: { ...site.nav, links } });
                  }} className="p-0.5 rounded hover:bg-primary/10 text-primary"><Plus className="h-3 w-3" /></button>
                </div>
                {(site?.nav?.links || []).map((lnk: any, i: number) => (
                  <div key={i} className="mb-2 p-2 rounded border border-border/30 bg-background/50 group/navlnk relative">
                    <div className="flex gap-1 mb-1">
                      <Input className="h-6 text-xs flex-1" defaultValue={lnk.label} placeholder="Label" onBlur={e => {
                        const links = [...(site?.nav?.links || [])]; links[i] = { ...links[i], label: e.target.value };
                        setSite({ ...site, nav: { ...site.nav, links } });
                      }} />
                      <Input className="h-6 text-xs flex-1" defaultValue={lnk.href} placeholder="href" onBlur={e => {
                        const links = [...(site?.nav?.links || [])]; links[i] = { ...links[i], href: e.target.value };
                        setSite({ ...site, nav: { ...site.nav, links } });
                      }} />
                      <button title="Löschen" onClick={() => {
                        const links = (site?.nav?.links || []).filter((_: any, j: number) => j !== i);
                        setSite({ ...site, nav: { ...site.nav, links } });
                      }} className="p-0.5 rounded hover:bg-destructive/10 text-destructive"><Trash2 className="h-3 w-3" /></button>
                    </div>
                  </div>
                ))}
              </div>

              {/* CTA */}
              <div>
                <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">CTA Button</label>
                <div className="mb-1">
                  <label className="text-[10px] text-muted-foreground">Text</label>
                  <Input className="h-7 text-xs" defaultValue={site?.nav?.cta?.text || ''} placeholder="z.B. Kontakt" onBlur={e => {
                    const cta = e.target.value ? { ...(site?.nav?.cta || {}), text: e.target.value } : null;
                    setSite({ ...site, nav: { ...site.nav, cta } });
                  }} />
                </div>
                <div className="mb-1">
                  <label className="text-[10px] text-muted-foreground">href</label>
                  <Input className="h-7 text-xs" defaultValue={site?.nav?.cta?.href || ''} placeholder="#contact" onBlur={e => {
                    if (site?.nav?.cta) setSite({ ...site, nav: { ...site.nav, cta: { ...site.nav.cta, href: e.target.value } } });
                  }} />
                </div>
              </div>

              <Button size="sm" className="w-full text-xs h-8" onClick={() => { saveSite(); setTimeout(() => refreshPreview(), 300); }}>💾 Navigation speichern</Button>
            </div>
          )}

          {/* ═══ FOOTER TAB ═══ */}
          {rightTab === 'footer' && !selectedSection && (
            <div className="p-3 space-y-4">
              <h3 className="font-semibold text-sm">🦶 Footer</h3>

              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">Copyright</label>
                <Input className="h-7 text-xs" defaultValue={site?.footer?.copyright || ''} placeholder="© {year} Firma" onBlur={e => setSite({ ...site, footer: { ...site.footer, copyright: e.target.value } })} />
              </div>

              {/* Footer columns */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Spalten</label>
                  <button title="Spalte hinzufügen" onClick={() => {
                    const cols = [...(site?.footer?.columns || []), { title: 'Neue Spalte', links: [{ label: 'Link', href: '/' }] }];
                    setSite({ ...site, footer: { ...site.footer, columns: cols } });
                  }} className="p-0.5 rounded hover:bg-primary/10 text-primary"><Plus className="h-3 w-3" /></button>
                </div>
                {(site?.footer?.columns || []).map((col: any, ci: number) => (
                  <div key={ci} className="mb-2 p-2 rounded border border-border/30 bg-background/50">
                    <div className="flex items-center gap-1 mb-1">
                      <Input className="h-6 text-xs flex-1" defaultValue={col.title || ''} placeholder="Titel" onBlur={e => {
                        const cols = [...(site?.footer?.columns || [])]; cols[ci] = { ...cols[ci], title: e.target.value };
                        setSite({ ...site, footer: { ...site.footer, columns: cols } });
                      }} />
                      <button title="Spalte löschen" onClick={() => {
                        const cols = (site?.footer?.columns || []).filter((_: any, j: number) => j !== ci);
                        setSite({ ...site, footer: { ...site.footer, columns: cols } });
                      }} className="p-0.5 rounded hover:bg-destructive/10 text-destructive"><Trash2 className="h-3 w-3" /></button>
                    </div>
                    {col.html !== undefined ? (
                      <textarea className="w-full px-1.5 py-1 text-xs rounded border border-border bg-background resize-y" rows={2} defaultValue={col.html || ''} placeholder="HTML-Content"
                        onBlur={e => { const cols = [...(site?.footer?.columns || [])]; cols[ci] = { ...cols[ci], html: e.target.value }; setSite({ ...site, footer: { ...site.footer, columns: cols } }); }} />
                    ) : (
                      <>
                        {(col.links || []).map((lnk: any, li: number) => (
                          <div key={li} className="flex gap-1 mb-0.5">
                            <Input className="h-5 text-xs flex-1" defaultValue={lnk.label} placeholder="Label" onBlur={e => {
                              const cols = [...(site?.footer?.columns || [])]; const links = [...(cols[ci].links || [])]; links[li] = { ...links[li], label: e.target.value }; cols[ci] = { ...cols[ci], links };
                              setSite({ ...site, footer: { ...site.footer, columns: cols } });
                            }} />
                            <Input className="h-5 text-xs flex-1" defaultValue={lnk.href} placeholder="href" onBlur={e => {
                              const cols = [...(site?.footer?.columns || [])]; const links = [...(cols[ci].links || [])]; links[li] = { ...links[li], href: e.target.value }; cols[ci] = { ...cols[ci], links };
                              setSite({ ...site, footer: { ...site.footer, columns: cols } });
                            }} />
                            <button title="Löschen" onClick={() => {
                              const cols = [...(site?.footer?.columns || [])]; cols[ci] = { ...cols[ci], links: (cols[ci].links || []).filter((_: any, j: number) => j !== li) };
                              setSite({ ...site, footer: { ...site.footer, columns: cols } });
                            }} className="p-0.5 rounded hover:bg-destructive/10 text-destructive"><X className="h-2.5 w-2.5" /></button>
                          </div>
                        ))}
                        <button onClick={() => {
                          const cols = [...(site?.footer?.columns || [])]; cols[ci] = { ...cols[ci], links: [...(cols[ci].links || []), { label: 'Neuer Link', href: '#' }] };
                          setSite({ ...site, footer: { ...site.footer, columns: cols } });
                        }} className="text-[10px] text-primary hover:underline mt-0.5">+ Link</button>
                      </>
                    )}
                  </div>
                ))}
              </div>

              {/* Legal links */}
              <div>
                <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1 block">Legal-Links</label>
                {(site?.footer?.legalLinks || []).map((lnk: any, i: number) => (
                  <div key={i} className="flex gap-1 mb-0.5">
                    <Input className="h-6 text-xs flex-1" defaultValue={lnk.label} onBlur={e => {
                      const ll = [...(site?.footer?.legalLinks || [])]; ll[i] = { ...ll[i], label: e.target.value };
                      setSite({ ...site, footer: { ...site.footer, legalLinks: ll } });
                    }} />
                    <Input className="h-6 text-xs flex-1" defaultValue={lnk.href} onBlur={e => {
                      const ll = [...(site?.footer?.legalLinks || [])]; ll[i] = { ...ll[i], href: e.target.value };
                      setSite({ ...site, footer: { ...site.footer, legalLinks: ll } });
                    }} />
                  </div>
                ))}
              </div>

              <Button size="sm" className="w-full text-xs h-8" onClick={() => { saveSite(); setTimeout(() => refreshPreview(), 300); }}>💾 Footer speichern</Button>
            </div>
          )}

          {/* ═══ LEGAL TAB ═══ */}
          {rightTab === 'legal' && !selectedSection && (
            <div className="p-3 space-y-4">
              <h3 className="font-semibold text-sm">⚖️ Impressum & Datenschutz</h3>
              <p className="text-[10px] text-muted-foreground">Diese Daten werden für die automatische Generierung von Impressum und Datenschutzerklärung verwendet.</p>

              <div>
                <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Impressum</label>
                {(['companyName', 'address', 'phone', 'email', 'ceo', 'registration', 'vatId'] as const).map(field => {
                  const labels: Record<string, string> = { companyName: 'Firmenname', address: 'Adresse', phone: 'Telefon', email: 'E-Mail', ceo: 'Geschäftsführer', registration: 'Registereintrag', vatId: 'USt-IdNr.' };
                  return (
                    <div key={field} className="mb-1.5">
                      <label className="text-[10px] text-muted-foreground">{labels[field]}</label>
                      <Input className="h-7 text-xs" defaultValue={site?.legal?.impressum?.[field] || ''} placeholder={labels[field]} onBlur={e => {
                        setSite({ ...site, legal: { ...site.legal, impressum: { ...site.legal?.impressum, [field]: e.target.value } } });
                      }} />
                    </div>
                  );
                })}
              </div>

              <div>
                <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">Datenschutz</label>
                <div className="mb-1.5">
                  <label className="text-[10px] text-muted-foreground">Kontakt-E-Mail</label>
                  <Input className="h-7 text-xs" defaultValue={site?.legal?.datenschutz?.contactEmail || ''} onBlur={e => {
                    setSite({ ...site, legal: { ...site.legal, datenschutz: { ...site.legal?.datenschutz, contactEmail: e.target.value } } });
                  }} />
                </div>
                <div className="mb-1.5">
                  <label className="text-[10px] text-muted-foreground">Analytics</label>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {['none', 'google-analytics', 'matomo', 'plausible'].map(a => (
                      <button key={a} onClick={() => setSite({ ...site, legal: { ...site.legal, datenschutz: { ...site.legal?.datenschutz, analytics: a } } })}
                        className={`px-2 py-1 rounded text-xs border ${site?.legal?.datenschutz?.analytics === a ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:border-primary/30'}`}>{a}</button>
                    ))}
                  </div>
                </div>
                <div className="mb-1.5">
                  <label className="text-[10px] text-muted-foreground">Cookies</label>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {['none', 'essential-only', 'full'].map(c => (
                      <button key={c} onClick={() => setSite({ ...site, legal: { ...site.legal, datenschutz: { ...site.legal?.datenschutz, cookies: c } } })}
                        className={`px-2 py-1 rounded text-xs border ${site?.legal?.datenschutz?.cookies === c ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:border-primary/30'}`}>{c}</button>
                    ))}
                  </div>
                </div>
              </div>

              <Button size="sm" className="w-full text-xs h-8" onClick={async () => {
                await saveSite();
                if (currentProject) {
                  try {
                    const r = await fetch(`${API_BASE}/api/cms/projects/${currentProject}/legal`, { method: 'POST' });
                    const j = await r.json();
                    if (j.success) { alert('✅ Impressum & Datenschutz generiert!'); }
                  } catch (e) { console.warn(e); }
                }
              }}>⚖️ Legal-Seiten generieren</Button>
            </div>
          )}

          {/* ═══ AI TAB ═══ */}
          {rightTab === 'ai' && (
            <div className="p-3 space-y-4">
              <h3 className="font-semibold text-sm">✨ AI Website-Generator</h3>
              <p className="text-[10px] text-muted-foreground">Beschreibe die Website die du brauchst — Ailey generiert Struktur, Texte und Design.</p>

              <div>
                <textarea className="w-full px-2 py-2 text-xs rounded border border-border bg-background resize-y" rows={5}
                  value={aiPrompt} onChange={e => setAiPrompt(e.target.value)}
                  placeholder={"z.B.:\n• Erstelle eine Website für einen Friseur in Berlin-Kreuzberg\n• Landingpage für ein SaaS-Produkt namens 'CloudSync'\n• Portfolio-Seite für eine Fotografin"}
                  onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) generateWithAI(); }}
                />
              </div>
              {aiError && <p className="text-xs text-red-400">{aiError}</p>}
              <Button size="sm" className="w-full text-xs h-8 gap-2" onClick={generateWithAI} disabled={aiBusy || !aiPrompt.trim()}>
                {aiBusy ? <><RotateCcw className="h-3 w-3 animate-spin" /> Ailey denkt nach...</> : <><Wand2 className="h-3 w-3" /> Website generieren</>}
              </Button>
              <p className="text-[10px] text-muted-foreground">⌘+Enter zum Absenden</p>
            </div>
          )}

          </div>
        </div>
      </div>

      {/* Add Section Modal */}
      {showAddSection && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddSection(false)}>
          <div className="bg-card rounded-t-xl sm:rounded-xl border border-border shadow-2xl w-full sm:w-[600px] max-h-[85vh] sm:max-h-[80vh] overflow-y-auto p-4 sm:p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold flex items-center gap-2"><Layers className="h-5 w-5" />Section hinzufügen</h2>
              <button onClick={() => setShowAddSection(false)} className="p-1 rounded hover:bg-primary/10"><X className="h-5 w-5" /></button>
            </div>
            {Object.entries(categories).map(([cat, items]) => (
              <div key={cat} className="mb-4">
                <h3 className="text-sm font-semibold mb-2">{catLabels[cat] || cat}</h3>
                <div className="grid grid-cols-2 gap-2">
                  {(items as any[]).map((t: any) => (
                    <button key={t.type} onClick={() => addSection(t.type)} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:border-primary hover:bg-primary/5 transition-colors text-left">
                      <span className="text-lg">{t.icon}</span>
                      <div>
                        <div className="text-xs font-medium">{t.label}</div>
                        {t.variants?.length > 0 && <div className="text-[10px] text-muted-foreground">{t.variants.length} Varianten</div>}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
