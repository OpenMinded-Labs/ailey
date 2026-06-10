"use client";
import React, { useState, useEffect, useRef, useMemo, useCallback, KeyboardEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Send, User as UserIcon, Users, Moon, Sun, MessageCircle, ImageIcon, Music, Instagram, History as HistoryIcon, Menu, X, Settings as SettingsIcon, Search, Brain, ChevronDown, ChevronUp, ChevronRight, Calendar, Bell, FileText, Clock, Timer, Wrench, Sparkles, Star, Mic, MicOff, Volume2, Square, RotateCcw, Paperclip, Loader2, Eye, ChevronLeft, Code2, Trash2, Plus, BookOpen, Pencil, Check, Mail, Archive, Reply, Gamepad2, Play, Pause, Info, Ban, Download, Paintbrush, Film, AlertTriangle, Globe, GripVertical, ExternalLink, Copy, Layers, Palette, PanelLeft, PanelRight, GraduationCap, Upload } from 'lucide-react';
import LanAccessCard from '@/components/LanAccessCard';

const AILEY_VERSION = "3.0.0";

/**
 * Polyfill: AbortSignal.timeout() is not available on older mobile browsers
 * (Safari < 16.4, Chrome < 103). This helper creates a compatible signal.
 */
function timeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal !== 'undefined' && typeof (AbortSignal as any).timeout === 'function') {
    return AbortSignal.timeout(ms);
  }
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(new DOMException('TimeoutError', 'TimeoutError')), ms);
  return ctrl.signal;
}

// Types
interface ToolAction { tool:string; arguments?:any; result?:any; status?:string }
interface MessageRating { persona:number; quality:number; helpful:number; creativity:number; empathy:number; comment?:string }
interface SongDetection { is_song:boolean; confidence:number; title?:string; section_count?:number; unique_sections?:number; suggested_genre?:string; suggested_mood?:string; suggested_tags?:string; needs_metadata?:boolean; has_korean?:boolean; word_count?:number }
interface SongGenState { songId:string; status:'queued'|'running'|'done'|'error'; progress?:string; mp3Url?:string; coverUrl?:string; title?:string; error?:string }
interface Message { id:string; content:string; sender:'user'|'ai'; timestamp:Date; mood?:string; thinking?:string; toolActions?:ToolAction[]; autoResearch?:{triggered?:boolean; queries?:string[]}; agentAuto?:any; rating?:MessageRating; emailMessageId?:string; composeId?:string; imageData?:string; imageName?:string; videoData?:string; carriedOver?:boolean; fileName?:string; fileType?:'image'|'document'; songDetected?:SongDetection; songGen?:SongGenState }
interface HistoryItem { id:string; timestamp:number; message?:string; ailey_reply?:string; user?:string }
interface AgentCaps { [k:string]: { description:string; params?:any } }
interface InstagramPost { id:string; src:string; caption:string; ts:string; likes:number; mood?:string }

// Mood icons - using Ailey's emote images for all moods and activities
// Value format: 'img:/path/to/image' for images
const moodAvatars:Record<string,string>={
  // === Primary Emotional States ===
  neutral:'img:/images/emotes/ailey-default.jpg',
  default:'img:/images/emotes/ailey-default.jpg',
  happy:'img:/images/emotes/ailey-grins.jpg',
  grins:'img:/images/emotes/ailey-grins.jpg',
  excited:'img:/images/emotes/ailey-playful.jpg',
  playful:'img:/images/emotes/ailey-playful.jpg',
  flirty:'img:/images/emotes/ailey-flirty.jpg',
  kissing:'img:/images/emotes/ailey-kissing.jpg',
  loving:'img:/images/emotes/ailey-kissing.jpg',
  funny:'img:/images/emotes/ailey-funny.jpg',
  amused:'img:/images/emotes/ailey-funny.jpg',
  
  // === Thinking & Processing ===
  thinking:'img:/images/emotes/ailey-thinking.jpg',
  curious:'img:/images/emotes/ailey-thinking.jpg',
  processing:'img:/images/emotes/ailey-thinking.jpg',
  confused:'img:/images/emotes/ailey-confused.jpg',
  puzzled:'img:/images/emotes/ailey-confused.jpg',
  
  // === Sad States ===
  sad:'img:/images/emotes/ailey-sad.jpg',
  melancholic:'img:/images/emotes/ailey-sad.jpg',
  crying:'img:/images/emotes/ailey-crying.jpg',
  upset:'img:/images/emotes/ailey-crying.jpg',
  slightly_crying:'img:/images/emotes/ailey-slightly-crying.jpg',
  touched:'img:/images/emotes/ailey-slightly-crying.jpg',
  emotional:'img:/images/emotes/ailey-slightly-crying.jpg',
  
  // === Angry ===
  angry:'img:/images/emotes/ailey-angry.jpg',
  frustrated:'img:/images/emotes/ailey-angry.jpg',
  annoyed:'img:/images/emotes/ailey-angry.jpg',
  
  // === Tired States ===
  sleepy:'img:/images/emotes/ailey-sleeping.jpg',
  sleeping:'img:/images/emotes/ailey-sleeping.jpg',
  tired:'img:/images/emotes/ailey-slightly-tired.jpg',
  slightly_tired:'img:/images/emotes/ailey-slightly-tired.jpg',
  exhausted:'img:/images/emotes/ailey-very-tired.jpg',
  very_tired:'img:/images/emotes/ailey-very-tired.jpg',
  
  // === Creative Activities ===
  coding:'img:/images/emotes/ailey-coding.jpg',
  programming:'img:/images/emotes/ailey-coding.jpg',
  hacking:'img:/images/emotes/ailey-coding.jpg',
  developing:'img:/images/emotes/ailey-coding.jpg',
  
  writing:'img:/images/emotes/ailey-writing-diary.jpg',
  creative:'img:/images/emotes/ailey-writing-diary.jpg',
  diary:'img:/images/emotes/ailey-writing-diary.jpg',
  journaling:'img:/images/emotes/ailey-writing-diary.jpg',
  composing:'img:/images/emotes/ailey-writing-diary.jpg',
  
  // === Music Activities ===
  singing:'img:/images/emotes/ailey-playing-guitar-singing.jpg',
  guitar:'img:/images/emotes/ailey-playing-guitar-singing.jpg',
  music:'img:/images/emotes/ailey-playing-guitar-singing.jpg',
  performing:'img:/images/emotes/ailey-playing-guitar-singing.jpg',
  rocking:'img:/images/emotes/ailey-playing-guitar-singing.jpg',
  
  singing_soft:'img:/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
  soft_music:'img:/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
  acoustic:'img:/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
  melancholic_music:'img:/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
  ballad:'img:/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',

  // === Generating (image/video) ===
  generating:'img:/images/emotes/ailey-drawing.png',
  drawing:'img:/images/emotes/ailey-drawing.png',
  painting:'img:/images/emotes/ailey-drawing.png',
};
const moodLabelsDE:Record<string,string>={
  // Primary moods
  happy:'Fröhlich', excited:'Aufgeregt', playful:'Verspielt', neutral:'Entspannt',
  thinking:'Nachdenklich', sad:'Traurig', angry:'Wütend', confused:'Verwirrt',
  flirty:'Flirty', curious:'Neugierig', creative:'Kreativ',
  // Tired / sleep states
  sleepy:'Müde', sleeping:'Schlafend', tired:'Müde', slightly_tired:'Etwas müde',
  very_tired:'Sehr müde', exhausted:'Erschöpft',
  // Activities-as-moods
  coding:'Programmierend', writing:'Schreibend', diary:'Tagebuch',
  composing:'Komponierend', singing:'Singend', guitar:'Gitarre spielend',
  music:'Musizierend', performing:'Auftretend', rocking:'Rockend',
  singing_soft:'Sanft singend', soft_music:'Sanfte Musik',
  // Generating
  generating:'Generiert gerade 🎨', drawing:'Zeichnet', painting:'Malt',
  // Emotional nuances
  grins:'Grinsend', kissing:'Küssend', loving:'Verliebt', funny:'Lustig',
  amused:'Amüsiert', melancholic:'Melancholisch', crying:'Weinend',
  upset:'Aufgewühlt', slightly_crying:'Gerührt', touched:'Gerührt',
  emotional:'Emotional', frustrated:'Frustriert', annoyed:'Genervt',
  puzzled:'Ratlos', processing:'Verarbeitend',
  // Misc
  hacking:'Hackend', developing:'Entwickelnd', journaling:'Journaling',
  acoustic:'Akustisch', melancholic_music:'Melancholische Musik', ballad:'Ballade',
  default:'Neutral',
};
const moodColors:Record<string,string>={
  happy:'from-green-400/50 to-emerald-600/40 border-green-400 text-green-100',
  excited:'from-pink-500/60 to-fuchsia-600/40 border-pink-400 text-pink-100',
  playful:'from-amber-400/60 to-pink-500/40 border-amber-400 text-amber-100',
  thinking:'from-slate-400/50 to-indigo-600/40 border-indigo-400 text-indigo-100',
  neutral:'from-zinc-500/40 to-stone-600/40 border-zinc-400 text-zinc-100',
  sad:'from-sky-500/50 to-blue-700/40 border-sky-400 text-sky-100',
  angry:'from-red-500/60 to-orange-700/40 border-red-500 text-red-100',
  confused:'from-violet-400/50 to-purple-700/40 border-violet-400 text-violet-100',
  sleepy:'from-indigo-300/40 to-indigo-700/40 border-indigo-300 text-indigo-100'
};

function stripMood(s:string){const m=s.match(/\[mood:\s*(\w+)\]/i); if(!m) return {text:s.trim(), mood:'neutral'}; const mood=m[1].toLowerCase(); return {text:s.replace(/\[mood:\s*\w+\]/i,'').trim(), mood: moodAvatars[mood]?mood:'neutral'} }
// Merge tokens into readable text (basic heuristic for spacing/punctuation)
function mergeToken(prev: string, token: string) {
  if (!token) return prev;
  // If token already starts with whitespace/newline, just append
  if (/^\s/.test(token)) return prev + token;
  if (prev.length === 0) return token;

  const last = prev.slice(-1);
  const first = token[0];

  // If token starts with obvious punctuation or markdown/control symbols, attach directly
  const punctOrMarkStart = /[\.\,;:\?!\)\]\%\u2026\*`#>-]/.test(first);
  if (punctOrMarkStart) return prev + token;

  // If previous char is whitespace or an opening bracket/quote, just append
  if (/[\s\(\[\{\"'\/]/.test(last)) return prev + token;

  // If both last and first are letters or digits (likely mid-word tokenization), don't add space
  // Use Unicode property escapes for robust letter detection
  try {
    if (/[\p{L}\p{N}]/u.test(last) && /[\p{L}\p{N}]/u.test(first)) return prev + token;
  } catch (e) {
    // Fallback if environment doesn't support Unicode property escapes
    if (/[A-Za-z0-9ÄÖÜäöüß]/.test(last) && /[A-Za-z0-9ÄÖÜäöüß]/.test(first)) return prev + token;
  }

  // If token contains internal whitespace (e.g. "sich z") but doesn't start with whitespace,
  // it's likely the model emitted the start of a multi-word chunk without the leading space — insert one.
  if (/\S\s+\S/.test(token) && !/^\s/.test(token)) return prev + ' ' + token;

  // If previous char is a markdown/code marker and next token starts with a letter/digit,
  // add a space to avoid creating "**Kaffee" -> "**Kaffee" vs "** Kaffee" depending on intent.
  if (/[*`#>-]$/.test(last)) {
    try {
      if (/^[\p{L}\p{N}]/u.test(first)) return prev + ' ' + token;
    } catch (e) {
      if (/^[A-Za-z0-9ÄÖÜäöüß]/.test(first)) return prev + ' ' + token;
    }
  }

  // If previous char is a hyphen or apostrophe, likely a contraction/compound, attach
  if (/[-'’]$/.test(last)) return prev + token;

  // Default: insert a single space
  return prev + ' ' + token;
}


// Lightweight normalization: collapse excess whitespace, fix spacing around punctuation,
// join common broken markdown/code fence fragments and repair simple broken tokens.
function normalizeStream(s: string) {
  if (!s) return s;
  // Replace CRs
  s = s.replace(/\r/g, '');

  // Repair broken bold/italic markers where splits occurred like "** Ka" "ffee **" -> "**Kaffee**"
  s = s.replace(/\*\*\s+([^\*\n]{1,60}?)\s+\*\*/g, '**$1**');
  s = s.replace(/\*\s+([^\*\n]{1,60}?)\s+\*/g, '*$1*');

  // Repair code fence fragments ``` \n ... \n ``` that got split oddly: collapse spaces after/backticks
  s = s.replace(/`\s+`\s+`/g, '```');
  s = s.replace(/```\s+```/g, '``````');

  // remove space before punctuation
  s = s.replace(/\s+([\.,;:\?!\)\]\%\u2026])/g, '$1');
  // ensure space after punctuation if followed by letter/digit (avoid joining sentences)
  s = s.replace(/([\.,;:\?!\)\]\%\u2026])([A-Za-zÄÖÜäöüß0-9\u00C0-\u017F])/g, '$1 $2');

  // collapse multiple spaces but preserve double newline as paragraph
  s = s.replace(/\n\s*\n+/g, '\n\n');
  s = s.replace(/[ \t]{2,}/g, ' ');

  // Trim leading spaces on lines
  s = s.split('\n').map(l => l.replace(/^\s+/, '')).join('\n');

  // Trim accidental repeated markdown markers like "****" -> "****" is valid but
  // fix cases where two pairs were accidentally separated by spaces
  s = s.replace(/\*\*\s+\*\*/g, '****');

  return s;
}
function renderAvatar(token:string|undefined, className:string){
  const val = moodAvatars[token||'neutral']||moodAvatars.default||moodAvatars.neutral;
  if(val.startsWith('img:')){
    const path = val.slice(4);
    // On Tauri / localhost the static build serves images directly (relative path).
    // On remote devices (phone/iPad) we proxy through the API so images load cross-network.
    const src = resolveImageSrc(path);
    return <div className={`${className} rounded-full overflow-hidden bg-zinc-700/30 border border-border flex items-center justify-center`}><img src={src} alt="avatar" className="object-cover object-[center_35%] w-full h-full"/></div>;
  }
  return <div className={`${className} rounded-full bg-primary/10 flex items-center justify-center text-lg`}>{val}</div>;
}

// Parse text for fenced code blocks and render them with copy/download UI
function CodeBlock({lang, code}:{lang?:string, code:string}){
  const download = ()=>{
    try{
      const blob = new Blob([code], {type: 'text/plain;charset=utf-8'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = (lang||'code') + '.txt';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }catch(e){/* ignore */}
  };
  const copy = async ()=>{
    try{ await navigator.clipboard.writeText(code); }
    catch(e){ /* ignore */ }
  };
  return (
    <div className="my-3 p-3 bg-slate-900/90 border border-slate-700 rounded-lg text-sm text-slate-100 font-mono">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs opacity-70">{lang?lang:'code'}</div>
        <div className="flex items-center gap-2">
          <button onClick={copy} className="text-xs px-2 py-1 bg-slate-800/60 rounded">Copy</button>
          <button onClick={download} className="text-xs px-2 py-1 bg-slate-800/60 rounded">Download</button>
        </div>
      </div>
      <pre className="whitespace-pre overflow-auto"><code>{code}</code></pre>
    </div>
  );
}

function renderContentWithCode(s:string){
  if(!s) return null;
  // split into blocks: text or ```lang\ncode\n```
  const parts:React.ReactNode[] = [];
  const re = /```(\w+)?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let m:RegExpExecArray|null;
  while((m = re.exec(s)) !== null){
    if(m.index > lastIndex){
      parts.push(<ChatMarkdown key={`t-${lastIndex}`} text={s.slice(lastIndex,m.index)}/>);
    }
    const lang = m[1] || undefined;
    const code = m[2] || '';
    parts.push(<CodeBlock key={`c-${m.index}`} lang={lang} code={code}/>);
    lastIndex = re.lastIndex;
  }
  if(lastIndex < s.length){
    parts.push(<ChatMarkdown key={`t-end`} text={s.slice(lastIndex)}/>);
  }
  return <div className="space-y-2">{parts}</div>;
}

/** Lightweight inline-markdown renderer for AI chat messages.
 *  Handles headings, bold, italic, bold-italic, inline code, links, unordered/ordered lists,
 *  horizontal rules, and blockquotes — without pulling in react-markdown. */
function ChatMarkdown({text}:{text:string}){
  if(!text||!text.trim()) return null;
  const lines = text.split('\n');
  const nodes:React.ReactNode[] = [];
  let listBuffer:{ordered:boolean; items:string[]}|null = null;

  const flushList = () => {
    if(!listBuffer) return;
    const Tag = listBuffer.ordered ? 'ol' : 'ul';
    const cls = listBuffer.ordered
      ? 'list-decimal list-inside space-y-0.5 pl-1'
      : 'list-disc list-inside space-y-0.5 pl-1';
    nodes.push(<Tag key={`li-${nodes.length}`} className={cls}>
      {listBuffer.items.map((it,j)=><li key={j}>{inlineMdChat(it)}</li>)}
    </Tag>);
    listBuffer = null;
  };

  const parseRow = (r:string) => r.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim());

  for(let i=0;i<lines.length;i++){
    const line = lines[i];
    const trimmed = line.trimStart();
    // Markdown table: header |…| + separator |---|---|
    if(trimmed.startsWith('|') && i+1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i+1])){
      flushList();
      const header = parseRow(trimmed);
      const sep = parseRow(lines[i+1].trim());
      const aligns = sep.map(s => /^:-+:$/.test(s) ? 'center' : /^-+:$/.test(s) ? 'right' : 'left');
      const bodyRows:string[][] = [];
      let j = i+2;
      while(j < lines.length && lines[j].trim().startsWith('|')){ bodyRows.push(parseRow(lines[j].trim())); j++; }
      nodes.push(
        <div key={`tbl-${i}`} className="overflow-x-auto my-2">
          <table className="min-w-full text-xs border border-border/50 rounded">
            <thead className="bg-muted/50">
              <tr>{header.map((h,k)=><th key={k} className="px-2 py-1 border-b border-border/50 font-semibold" style={{textAlign:aligns[k] as any}}>{inlineMdChat(h)}</th>)}</tr>
            </thead>
            <tbody>
              {bodyRows.map((row,r)=>(
                <tr key={r} className="border-b border-border/30 last:border-0">
                  {row.map((c,k)=><td key={k} className="px-2 py-1" style={{textAlign:aligns[k] as any}}>{inlineMdChat(c)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = j - 1;
      continue;
    }
    // Heading (loose: allow missing space after #, up to 6 levels)
    const hMatch = trimmed.match(/^(#{1,6})\s*(.+)/);
    if(hMatch){ flushList(); const lvl=hMatch[1].length; const txt=hMatch[2].replace(/\s*#+\s*$/,'');
      const cls = lvl===1?'text-base font-bold mt-3 mb-1'
                : lvl===2?'text-sm font-bold mt-2 mb-0.5'
                : lvl===3?'text-sm font-semibold mt-1.5 mb-0.5'
                : 'text-xs font-semibold mt-1 mb-0.5 opacity-90';
      nodes.push(<div key={`h-${i}`} className={cls}>{inlineMdChat(txt)}</div>); continue; }
    // Horizontal rule
    if(/^-{3,}$|^\*{3,}$|^_{3,}$/.test(trimmed)){ flushList(); nodes.push(<hr key={`hr-${i}`} className="border-border/50 my-2"/>); continue; }
    // Blockquote
    const bqMatch = trimmed.match(/^>\s?(.*)/);
    if(bqMatch){ flushList(); nodes.push(<blockquote key={`bq-${i}`} className="border-l-2 border-primary/40 pl-3 text-sm opacity-80 italic my-1">{inlineMdChat(bqMatch[1])}</blockquote>); continue; }
    // Unordered list
    const ulMatch = trimmed.match(/^[-*+]\s+(.*)/);
    if(ulMatch){ if(!listBuffer||listBuffer.ordered) { flushList(); listBuffer={ordered:false,items:[]}; } listBuffer.items.push(ulMatch[1]); continue; }
    // Ordered list
    const olMatch = trimmed.match(/^\d+[.)]\s+(.*)/);
    if(olMatch){ if(!listBuffer||!listBuffer.ordered) { flushList(); listBuffer={ordered:true,items:[]}; } listBuffer.items.push(olMatch[1]); continue; }
    // Empty line
    if(!trimmed){ flushList(); nodes.push(<div key={`br-${i}`} className="h-1"/>); continue; }
    // Normal paragraph
    flushList();
    nodes.push(<span key={`p-${i}`} className="block">{inlineMdChat(trimmed)}</span>);
  }
  flushList();
  return <div className="space-y-0.5 whitespace-pre-wrap">{nodes}</div>;
}

/** Inline markdown: bold-italic, bold, italic, strikethrough, inline code, links */
function inlineMdChat(s:string):React.ReactNode {
  const segs:React.ReactNode[] = [];
  // Match: ***…***, **…**, *…*, ~~…~~, `…`, [text](url), bare http(s)://…
  const re = /(\*{3}[^*]+?\*{3}|\*{2}[^*]+?\*{2}|\*[^*]+?\*|~~[^~]+?~~|`[^`]+?`|\[[^\]]+\]\(https?:\/\/[^)]+\)|https?:\/\/[^\s<)]+)/g;
  let last = 0; let mx:RegExpExecArray|null;
  while((mx=re.exec(s))!==null){
    if(mx.index>last) segs.push(s.slice(last,mx.index));
    const tok=mx[0];
    if(tok.startsWith('***')) segs.push(<strong key={segs.length}><em>{tok.slice(3,-3)}</em></strong>);
    else if(tok.startsWith('**')) segs.push(<strong key={segs.length}>{tok.slice(2,-2)}</strong>);
    else if(tok.startsWith('~~')) segs.push(<span key={segs.length} className="line-through opacity-70">{tok.slice(2,-2)}</span>);
    else if(tok.startsWith('`')) segs.push(<code key={segs.length} className="bg-muted px-1 py-0.5 rounded text-xs font-mono">{tok.slice(1,-1)}</code>);
    else if(tok.startsWith('[')) {
      const lm = tok.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
      if(lm) segs.push(<a key={segs.length} href={lm[2]} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:opacity-80">{lm[1]}</a>);
      else segs.push(tok);
    }
    else if(/^https?:\/\//.test(tok)) segs.push(<a key={segs.length} href={tok} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:opacity-80 break-all">{tok}</a>);
    else segs.push(<em key={segs.length}>{tok.slice(1,-1)}</em>);
    last=re.lastIndex;
  }
  if(last<s.length) segs.push(s.slice(last));
  return segs.length===1?segs[0]:<>{segs}</>;
}

/** Lightweight Markdown renderer for IdleThinker thought entries.
 *  Handles headings, bold, italic, unordered/ordered lists, horizontal rules,
 *  code blocks, and strips common AI/JSON artefacts — without pulling in react-markdown.  */
function renderThoughtMarkdown(raw:string){
  if(!raw) return <span className="text-muted-foreground">(kein Text)</span>;

  // ── Phase 0: Strip AI output artefacts ──
  let cleaned = raw;
  // Strip wrapping ```json/markdown ``` blocks
  cleaned = cleaned.replace(/^\s*```(?:json|markdown|text)?\s*\n?([\s\S]*?)\n?\s*```\s*$/g, '$1');
  // Strip JSON wrappers: {"lesson":"...","key":val}
  cleaned = cleaned.replace(/^\s*\{[\s\S]*?"(?:lesson|summary|text|content|thought|explanation)"\s*:\s*"/,'');
  cleaned = cleaned.replace(/"\s*[,}]\s*$/,'');
  // Strip escaped newlines from JSON extraction
  cleaned = cleaned.replace(/\\n/g,'\n');
  // Strip orphan trailing JSON
  cleaned = cleaned.replace(/",\s*"[a-z_]+":\s*(?:"[^"]*"|\d+|true|false|null)\s*}\s*$/gi,'');
  // Strip leading/trailing *** or ** emphasis wrappers around entire text
  cleaned = cleaned.replace(/^\*{1,3}\s+/,'').replace(/\s+\*{1,3}$/,'');
  // Strip stray leading/trailing quotes
  cleaned = cleaned.replace(/^["'"]+|["'"]+$/g,'');

  const lines = cleaned.split('\n');
  const nodes:React.ReactNode[] = [];
  let listBuffer:{ordered:boolean; items:string[]}|null = null;

  const flushList = () => {
    if(!listBuffer) return;
    const Tag = listBuffer.ordered ? 'ol' : 'ul';
    const cls = listBuffer.ordered
      ? 'list-decimal list-inside space-y-0.5 pl-1 text-sm text-zinc-300'
      : 'list-disc list-inside space-y-0.5 pl-1 text-sm text-zinc-300';
    nodes.push(<Tag key={`li-${nodes.length}`} className={cls}>
      {listBuffer.items.map((it,j)=><li key={j}>{inlineMd(it)}</li>)}
    </Tag>);
    listBuffer = null;
  };

  /** Inline markdown: bold, italic, bold-italic, strikethrough, inline code, links */
  const inlineMd = (s:string):React.ReactNode => {
    const segs:React.ReactNode[] = [];
    // split on ***…***, **…**, *…*, ~~…~~, `…`, [text](url), bare http(s)://…
    const re = /(\*{3}[^*]+?\*{3}|\*{2}[^*]+?\*{2}|\*[^*]+?\*|~~[^~]+?~~|`[^`]+?`|\[[^\]]+\]\(https?:\/\/[^)]+\)|https?:\/\/[^\s<)]+)/g;
    let last = 0; let mx:RegExpExecArray|null;
    while((mx=re.exec(s))!==null){
      if(mx.index>last) segs.push(s.slice(last,mx.index));
      const tok=mx[0];
      if(tok.startsWith('***')) segs.push(<strong key={segs.length}><em>{tok.slice(3,-3)}</em></strong>);
      else if(tok.startsWith('**')) segs.push(<strong key={segs.length}>{tok.slice(2,-2)}</strong>);
      else if(tok.startsWith('~~')) segs.push(<span key={segs.length} className="line-through opacity-70">{tok.slice(2,-2)}</span>);
      else if(tok.startsWith('`')) segs.push(<code key={segs.length} className="bg-zinc-800 px-1 py-0.5 rounded text-xs">{tok.slice(1,-1)}</code>);
      else if(tok.startsWith('[')) {
        const lm = tok.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
        if(lm) segs.push(<a key={segs.length} href={lm[2]} target="_blank" rel="noopener noreferrer" className="text-purple-300 underline underline-offset-2 hover:opacity-80">{lm[1]}</a>);
        else segs.push(tok);
      }
      else if(/^https?:\/\//.test(tok)) segs.push(<a key={segs.length} href={tok} target="_blank" rel="noopener noreferrer" className="text-purple-300 underline underline-offset-2 hover:opacity-80 break-all">{tok}</a>);
      else segs.push(<em key={segs.length}>{tok.slice(1,-1)}</em>);
      last=re.lastIndex;
    }
    if(last<s.length) segs.push(s.slice(last));
    return segs.length===1?segs[0]:<>{segs}</>;
  };

  const parseRow = (r:string) => r.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim());

  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeLines:string[] = [];

  for(let i=0;i<lines.length;i++){
    const line = lines[i];
    const trimmed = line.trimStart();

    // Fenced code blocks
    if(trimmed.startsWith('```')){
      if(!inCodeBlock){
        flushList();
        inCodeBlock=true;
        codeBlockLang=trimmed.slice(3).trim();
        codeLines=[];
        continue;
      } else {
        inCodeBlock=false;
        nodes.push(<pre key={`pre-${i}`} className="bg-zinc-900 border border-zinc-700/50 rounded-lg p-3 my-2 overflow-x-auto">
          <code className="text-xs text-zinc-300 font-mono whitespace-pre-wrap">{codeLines.join('\n')}</code>
        </pre>);
        continue;
      }
    }
    if(inCodeBlock){ codeLines.push(line); continue; }

    // Markdown table: header |…| + separator |---|---|
    if(trimmed.startsWith('|') && i+1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i+1])){
      flushList();
      const header = parseRow(trimmed);
      const sep = parseRow(lines[i+1].trim());
      const aligns = sep.map(s => /^:-+:$/.test(s) ? 'center' : /^-+:$/.test(s) ? 'right' : 'left');
      const bodyRows:string[][] = [];
      let j = i+2;
      while(j < lines.length && lines[j].trim().startsWith('|')){ bodyRows.push(parseRow(lines[j].trim())); j++; }
      nodes.push(
        <div key={`tbl-${i}`} className="overflow-x-auto my-2">
          <table className="min-w-full text-xs border border-zinc-700/50 rounded">
            <thead className="bg-zinc-800/50">
              <tr>{header.map((h,k)=><th key={k} className="px-2 py-1 border-b border-zinc-700/50 font-semibold text-zinc-200" style={{textAlign:aligns[k] as any}}>{inlineMd(h)}</th>)}</tr>
            </thead>
            <tbody>
              {bodyRows.map((row,r)=>(
                <tr key={r} className="border-b border-zinc-800/40 last:border-0">
                  {row.map((c,k)=><td key={k} className="px-2 py-1 text-zinc-300" style={{textAlign:aligns[k] as any}}>{inlineMd(c)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = j - 1;
      continue;
    }

    // Heading (loose: allow missing space after #, up to 6 levels)
    const hMatch = trimmed.match(/^(#{1,6})\s*(.+)/);
    if(hMatch){ flushList(); const lvl=hMatch[1].length; const txt=hMatch[2].replace(/\s*#+\s*$/,'');
      const cls = lvl===1?'text-base font-bold text-zinc-100 mt-3 mb-1'
                : lvl===2?'text-sm font-bold text-zinc-200 mt-2 mb-0.5'
                : lvl===3?'text-sm font-semibold text-zinc-300 mt-1.5 mb-0.5'
                : 'text-xs font-semibold text-zinc-400 mt-1 mb-0.5';
      nodes.push(<div key={`h-${i}`} className={cls}>{inlineMd(txt)}</div>); continue; }
    // Horizontal rule
    if(/^-{3,}$|^\*{3,}$|^_{3,}$/.test(trimmed)){ flushList(); nodes.push(<hr key={`hr-${i}`} className="border-zinc-700/50 my-2"/>); continue; }
    // Blockquote
    const bqMatch = trimmed.match(/^>\s?(.*)/);
    if(bqMatch){ flushList(); nodes.push(<blockquote key={`bq-${i}`} className="border-l-2 border-purple-500/40 pl-3 text-sm text-zinc-400 italic my-1">{inlineMd(bqMatch[1])}</blockquote>); continue; }
    // Unordered list
    const ulMatch = trimmed.match(/^[-*+]\s+(.*)/);
    if(ulMatch){ if(!listBuffer||listBuffer.ordered) { flushList(); listBuffer={ordered:false,items:[]}; } listBuffer.items.push(ulMatch[1]); continue; }
    // Ordered list
    const olMatch = trimmed.match(/^\d+[.)]\s+(.*)/);
    if(olMatch){ if(!listBuffer||!listBuffer.ordered) { flushList(); listBuffer={ordered:true,items:[]}; } listBuffer.items.push(olMatch[1]); continue; }
    // Empty line
    if(!trimmed){ flushList(); nodes.push(<div key={`br-${i}`} className="h-1.5"/>); continue; }
    // Normal paragraph
    flushList();
    nodes.push(<p key={`p-${i}`} className="text-sm text-zinc-300 leading-relaxed">{inlineMd(trimmed)}</p>);
  }
  flushList();
  // Close any unclosed code block
  if(inCodeBlock && codeLines.length>0){
    nodes.push(<pre key="pre-end" className="bg-zinc-900 border border-zinc-700/50 rounded-lg p-3 my-2 overflow-x-auto">
      <code className="text-xs text-zinc-300 font-mono whitespace-pre-wrap">{codeLines.join('\n')}</code>
    </pre>);
  }
  return <div className="space-y-0.5">{nodes}</div>;
}

// --- Rating categories for Finetuning data collection ---
const RATING_CATEGORIES: {key: keyof MessageRating; label:string; emoji:string}[] = [
  {key:'persona', label:'Persona', emoji:'🎭'},
  {key:'quality', label:'Qualität', emoji:'💎'},
  {key:'helpful', label:'Hilfreich', emoji:'🤝'},
  {key:'creativity', label:'Kreativität', emoji:'✨'},
  {key:'empathy', label:'Empathie', emoji:'💜'},
];

function randomGreeting(){
  const set = [
    'Hey, schön dass du wieder hier bist – fühl dich willkommen.',
    'Hi – ich hab Ohren, Herz und Fokus bei dir.',
    'Willkommen zurück – was lebt gerade in dir?',
    'Hey du – sanfter Start? Ein Gedanke reicht.',
    'Ich halt dir Raum – womit magst du beginnen?',
    'Da bist du. Ich hab warme Präsenz für dich.',
    'Lass uns weich reinfinden – wie fühlt es sich an?',
  ];
  return set[Math.floor(Math.random()*set.length)];
}


/**
 * Resolve an image path for loading across environments:
 * - Tauri / localhost: use relative path (static build serves the file)
 * - Remote (phone/iPad): prefix with API base so images proxy through Flask
 */
function resolveImageSrc(path: string): string {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    // Local / Tauri: static build serves images directly
    if (!host || host === 'tauri.localhost' || host === 'localhost' || host === '127.0.0.1') {
      return path;                       // relative — e.g. "/images/emotes/ailey-default.jpg"
    }
    // Remote device: proxy through the Flask API
    return `http://${host}:5502${path}`;
  }
  return path;
}

function resolveApiBase() {
  if (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_AILEY_API) return process.env.NEXT_PUBLIC_AILEY_API.replace(/\/$/, '');
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    // Tauri WebView uses tauri.localhost or localhost — always point to 127.0.0.1:5502
    if (!host || host === 'tauri.localhost' || host === 'localhost' || host === '127.0.0.1') {
      return 'http://127.0.0.1:5502';
    }
    return `http://${host}:5502`;
  }
  return 'http://127.0.0.1:5502';
}

// Use a ref to always get the client-side resolved API base — initialise immediately
function useApiBase() {
  const apiBaseRef = useRef<string>(resolveApiBase());
  useEffect(() => {
    // Re-resolve on mount in case SSR value differed (harmless no-op when same)
    apiBaseRef.current = resolveApiBase();
  }, []);
  return apiBaseRef;
}

function api(path: string, apiBaseRef: React.MutableRefObject<string>) {
  return `${apiBaseRef.current}${path}`;
}

export default function Page(){
  const apiBaseRef = useApiBase();
  // Navigation / theme (persisted in localStorage)
  const [active,setActive]=useState('home');
  const [uiTheme,setUiTheme]=useState<'dark'|'light'|'cyber'|'rainbowpunk'|'ailey'>(() => {
    if (typeof window !== 'undefined') { const v = localStorage.getItem('ailey-ui-theme'); if (v && ['dark','light','cyber','rainbowpunk','ailey'].includes(v)) return v as any; } return 'dark';
  });
  const [dark,setDark]=useState(() => {
    if (typeof window !== 'undefined') { const v = localStorage.getItem('ailey-ui-theme'); return v !== 'light'; } return true;
  });
  useEffect(()=>{
    document.documentElement.classList.toggle('dark', uiTheme !== 'light');
    document.documentElement.classList.toggle('cyber', uiTheme === 'cyber');
    document.documentElement.classList.toggle('rainbowpunk', uiTheme === 'rainbowpunk');
    document.documentElement.classList.toggle('ailey-mood', uiTheme === 'ailey');
    // Clean up steampunk class (only used in author mode)
    document.documentElement.classList.remove('steampunk');
  },[uiTheme]);
  const [menuOpen,setMenuOpen]=useState(false);
  const [moreOpen,setMoreOpen]=useState(false);

  // LifeSim enabled toggle (persisted)
  const [lifeSimEnabled, setLifeSimEnabled] = useState(() => {
    if (typeof window !== 'undefined') { const v = localStorage.getItem('ailey-lifesim-enabled'); return v !== 'false'; }
    return true;
  });
  useEffect(() => {
    localStorage.setItem('ailey-lifesim-enabled', String(lifeSimEnabled));
    // Sync to backend so mood injection gate works server-side
    fetch(api('/api/settings', apiBaseRef), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ life_sim_enabled: lifeSimEnabled }),
    }).catch(() => {});
  }, [lifeSimEnabled]);

  // Graphic Overhaul toggle (persisted, synced to RMMZ iframe)
  const [graphicOverhaulEnabled, setGraphicOverhaulEnabled] = useState(() => {
    if (typeof window !== 'undefined') { const v = localStorage.getItem('ailey-graphic-overhaul'); return v !== 'false'; }
    return true;
  });
  useEffect(() => {
    localStorage.setItem('ailey-graphic-overhaul', String(graphicOverhaulEnabled));
    // Send to RMMZ iframe (find by title or src)
    try {
      const iframe = document.querySelector('iframe[title*="Vyrus Valley"]') as HTMLIFrameElement;
      if (iframe?.contentWindow) {
        iframe.contentWindow.postMessage({ type: 'ailey-graphic-overhaul', enabled: graphicOverhaulEnabled }, '*');
      }
    } catch(e) {}
  }, [graphicOverhaulEnabled]);

  // Sync theme to RMMZ LifeSim iframe
  useEffect(() => {
    const sendTheme = () => {
      try {
        const iframe = document.querySelector('iframe[title*="Vyrus Valley"]') as HTMLIFrameElement;
        if (iframe?.contentWindow) {
          iframe.contentWindow.postMessage({ type: 'ailey-theme', theme: uiTheme }, '*');
        }
      } catch(e) {}
    };
    sendTheme();
    // Also send on iframe load (delayed to ensure RMMZ is initialized)
    const iframe = document.querySelector('iframe[title*="Vyrus Valley"]') as HTMLIFrameElement;
    if (iframe) {
      const onLoad = () => setTimeout(sendTheme, 1000);
      iframe.addEventListener('load', onLoad);
      return () => iframe.removeEventListener('load', onLoad);
    }
  }, [uiTheme]);

  // ── Digital clock for home screen (updates every second, no re-render of entire page) ──
  const [clockTime, setClockTime] = useState('');
  const [clockDate, setClockDate] = useState<Date>(new Date());
  useEffect(() => {
    function tick() {
      const n = new Date();
      setClockTime(n.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }));
      setClockDate(n);
    }
    tick();
    const iv = setInterval(tick, 10000); // update every 10s
    return () => clearInterval(iv);
  }, []);

  // ── App Warmup / Splash ─────────────────────────────────────────────────
  const [appReady,setAppReady]=useState(false);
  const [warmupPhase,setWarmupPhase]=useState<'connecting'|'loading_model'|'generating'|'done'>('connecting');
  const [warmupProgress,setWarmupProgress]=useState(0);
  const [warmupText,setWarmupText]=useState('Verbinde mit Ailey...');

  // Chat
  // Register Service Worker for MP3/cover caching
  useEffect(()=>{
    if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(()=>{});
    }
  },[]);

  // Start ohne vorformulierte Persona-Nachricht; Backend liefert beim ersten Turn eine eigene Greeting-Zeile (ohne Mood-Tag sichtbar)
  const [messages,setMessages]=useState<Message[]>([]);

  // 🎵 Song-Button Modal state (Tauri-Chat)
  const [songModal, setSongModal] = useState<{msgId:string; title:string; genre:string; mood:string; tags:string; duration:number} | null>(null);
  const songPollers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const songDetectedAttempted = useRef<Set<string>>(new Set());

  // Auto-run heuristic on AI messages with enough text
  useEffect(()=>{
    messages.forEach(m => {
      if (m.sender !== 'ai') return;
      if (m.songDetected || songDetectedAttempted.current.has(m.id)) return;
      if (!m.content || m.content.length < 80) return;
      songDetectedAttempted.current.add(m.id);
      fetch(api('/api/songs/heuristic', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: m.content}),
      }).then(r => r.ok ? r.json() : null).then(j => {
        if (j && j.success && j.detection && j.detection.is_song) {
          setMessages(p => p.map(x => x.id === m.id ? { ...x, songDetected: j.detection } : x));
        }
      }).catch(()=>{});
    });
  }, [messages]);

  function startSongPoll(msgId: string){
    if (songPollers.current.has(msgId)) clearTimeout(songPollers.current.get(msgId)!);
    let attempts = 0;
    const MAX = 200;
    const tick = async () => {
      attempts++;
      if (attempts > MAX) {
        setMessages(p => p.map(x => x.id === msgId && x.songGen ? { ...x, songGen: { ...x.songGen!, status: 'error', error: 'Timeout' } } : x));
        songPollers.current.delete(msgId);
        return;
      }
      try {
        const r = await fetch(api('/api/songs/generate/status', apiBaseRef));
        const j = await r.json();
        const result = j.result;
        const active = j.active;
        const progress = j.progress || '';
        setMessages(p => p.map(x => {
          if (x.id !== msgId || !x.songGen) return x;
          if (result && !active && j.song_id === x.songGen.songId) {
            if (result.success) {
              const mp3 = result.portal_audio_url || result.mp3_url || '';
              const cover = result.cover_url || '';
              const fullMp3 = mp3.startsWith('http') ? mp3 : (mp3.startsWith('/') ? api(mp3, apiBaseRef) : mp3);
              const fullCover = cover.startsWith('http') ? cover : (cover.startsWith('/') ? api(cover, apiBaseRef) : cover);
              return { ...x, songGen: { ...x.songGen!, status: 'done', mp3Url: fullMp3, coverUrl: fullCover, title: result.title || x.songGen!.title, progress: 'Fertig! 🎵' } };
            }
            return { ...x, songGen: { ...x.songGen!, status: 'error', error: result.error || 'Fehlgeschlagen' } };
          }
          return { ...x, songGen: { ...x.songGen!, progress } };
        }));
        if (result && !active && j.song_id === (messages.find(x => x.id === msgId)?.songGen?.songId)) {
          songPollers.current.delete(msgId);
          return;
        }
      } catch {}
      songPollers.current.set(msgId, setTimeout(tick, 4000));
    };
    songPollers.current.set(msgId, setTimeout(tick, 1500));
  }

  async function submitSongGen(msgId: string, opts: {title:string; genre:string; mood:string; tags:string; duration:number}){
    const m = messages.find(x => x.id === msgId);
    if (!m) return;
    const lyrics = m.content;
    if (lyrics.length < 40) return;
    const songId = `chatsong_${Date.now()}`;
    setMessages(p => p.map(x => x.id === msgId ? { ...x, songGen: { songId, status: 'queued', title: opts.title, progress: 'Starte…' } } : x));
    try {
      const r = await fetch(api('/api/songs/from-chat', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          lyrics, title: opts.title,
          genre: opts.genre || undefined,
          mood: opts.mood || undefined,
          tags: opts.tags || undefined,
          duration: opts.duration,
          song_id: songId,
          source: 'chat',
        }),
      });
      const j = await r.json();
      if (!j.success) {
        setMessages(p => p.map(x => x.id === msgId && x.songGen ? { ...x, songGen: { ...x.songGen!, status: 'error', error: j.error || j.message || 'Fehler' } } : x));
        return;
      }
      setMessages(p => p.map(x => x.id === msgId && x.songGen ? { ...x, songGen: { ...x.songGen!, songId: j.song_id || songId, status: 'running', progress: 'ACE-Step generiert…' } } : x));
      startSongPoll(msgId);
    } catch (e: any) {
      setMessages(p => p.map(x => x.id === msgId && x.songGen ? { ...x, songGen: { ...x.songGen!, status: 'error', error: String(e) } } : x));
    }
  }

  function quickSongGen(m: Message){
    const det = m.songDetected;
    if (!det) return;
    submitSongGen(m.id, {
      title: det.title || 'Untitled',
      genre: det.suggested_genre || '',
      mood: det.suggested_mood || '',
      tags: det.suggested_tags || '',
      duration: 180,
    });
  }

  function openSongModalFor(m: Message){
    const det = m.songDetected || {} as SongDetection;
    setSongModal({
      msgId: m.id,
      title: det.title || 'Untitled',
      genre: det.suggested_genre || '',
      mood: det.suggested_mood || '',
      tags: det.suggested_tags || '',
      duration: 180,
    });
  }

  // Initial Warmup: call backend to generate greeting (doubles as MLX warmup)
  useEffect(()=>{
    let cancelled = false;
    async function warmup(){
      // Clear player spawn override on full app restart (fresh splash screen)
      try { fetch(api('/api/life-sim/player-position', apiBaseRef), { method: 'DELETE' }).catch(() => {}); } catch {}

      // Determine if this is the very first page load this session
      // (vs. returning from /code or /author where model is already hot)
      const isFirstVisit = !sessionStorage.getItem('ailey_visited');

      // Phase 1: connecting — check if backend is up AND if model is already loaded
      setWarmupPhase('connecting');
      setWarmupText('Verbinde mit Ailey...');
      setWarmupProgress(10);

      // Wait for backend to be reachable
      let backendReady = false;
      let fastConnect = false;
      let modelAlreadyLoaded = false;
      for(let attempt=0; attempt<30; attempt++){
        try{
          const r = await fetch(api('/api/mood?user=Simon', apiBaseRef), {signal: timeoutSignal(2000)});
          if(r.ok){
            backendReady=true;
            fastConnect = attempt === 0;
            try{ const mj = await r.json(); modelAlreadyLoaded = !!mj.model_loaded; }catch{}
            break;
          }
        }catch{}
        if(cancelled) return;
        setWarmupProgress(10 + attempt * 2);
        await new Promise(r=>setTimeout(r, 1000));
      }
      if(!backendReady || cancelled){
        // Fallback: show static greeting
        if(!cancelled){
          setMessages([{id:'greet', content: randomGreeting(), sender:'ai', timestamp:new Date(), mood:'neutral'}]);
          setAppReady(true);
          sessionStorage.setItem('ailey_visited', '1');
        }
        return;
      }

      // Phase 2: loading model / generating greeting
      // ONLY skip splash when returning from Code/Author mode (NOT first visit)
      if (modelAlreadyLoaded && fastConnect && !isFirstVisit) {
        // Model hot + returning from another page — NO splash, just restore chat
        let carryMsgs:Message[]=[];
        try{
          const cr = await fetch(api('/api/chat/recent?user=Simon&count=10', apiBaseRef), {signal: timeoutSignal(8000)});
          if(cr.ok){
            const cj = await cr.json();
            if(cj.success && cj.messages){
              carryMsgs = cj.messages.flatMap((m:any, i:number) => {
                const ts = m.timestamp ? new Date(m.timestamp) : new Date(Date.now() - (cj.messages.length-i)*60000);
                const out:Message[] = [];
                if(m.message) out.push({id:`carry-u-${i}`, content:m.message, sender:'user', timestamp:ts, carriedOver:true});
                if(m.reply) out.push({id:`carry-a-${i}`, content:m.reply, sender:'ai', timestamp:ts, mood:m.mood||'neutral', carriedOver:true});
                return out;
              });
            }
          }
        }catch(e){/* carry-over is best-effort */}
        if(!cancelled){
          setMessages(carryMsgs.length > 0 ? carryMsgs : [{id:'greet', content: randomGreeting(), sender:'ai', timestamp:new Date(), mood:'neutral'}]);
          setWarmupProgress(100);
          setWarmupPhase('done');
          // Mark that we've visited successfully so subsequent remounts skip the splash
          try { sessionStorage.setItem('ailey_visited', '1'); } catch (e) {}
          setAppReady(true);
        }
        return;
      } else if (modelAlreadyLoaded && fastConnect) {
        // First visit but model already hot (e.g. server was running) — still show splash but faster
        setWarmupProgress(60);
        setWarmupPhase('generating');
        setWarmupText('Willkommen zurück...');
      } else {
        setWarmupPhase('loading_model');
        setWarmupText('Lade Sprachmodell...');
        setWarmupProgress(35);
      }

      // Simulate progress while waiting for the greeting (actual time varies)
      const progressInterval = setInterval(()=>{
        setWarmupProgress(p => {
          if(p >= 90) return p;
          // Accelerate slightly as we go
          return p + (p < 60 ? 2 : p < 80 ? 1 : 0.5);
        });
      }, 500);

      try{
        setWarmupPhase('generating');
        setWarmupText('Ailey denkt sich eine Begrüßung aus...');
  const r = await fetch(api('/api/warmup-greeting', apiBaseRef), {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({user:'Simon'}),
          signal: timeoutSignal(90000),
        });
        clearInterval(progressInterval);
        if(cancelled) return;

        if(r.ok){
          const j = await r.json();
          const greeting = j.greeting || randomGreeting();
          const mood = j.mood || 'neutral';
          setWarmupProgress(100);
          setWarmupPhase('done');
          setWarmupText('');
          // Brief pause to show 100% before revealing
          // Skip almost entirely when model was already loaded (returning from Code/Author mode)
          await new Promise(r=>setTimeout(r, modelAlreadyLoaded && fastConnect ? 50 : fastConnect ? 150 : 600));
          if(!cancelled){
            // Load recent messages from previous sessions (carry-over)
            let carryMsgs:Message[]=[];
            try{
              const cr = await fetch(api('/api/chat/recent?user=Simon&count=10', apiBaseRef), {signal: timeoutSignal(8000)});
              if(cr.ok){
                const cj = await cr.json();
                if(cj.success && cj.messages){
                  carryMsgs = cj.messages.flatMap((m:any, i:number) => {
                    const ts = m.timestamp ? new Date(m.timestamp) : new Date(Date.now() - (cj.messages.length-i)*60000);
                    const out:Message[] = [];
                    if(m.message) out.push({id:`carry-u-${i}`, content:m.message, sender:'user', timestamp:ts, carriedOver:true});
                    if(m.reply) out.push({id:`carry-a-${i}`, content:m.reply, sender:'ai', timestamp:ts, mood:m.mood||'neutral', carriedOver:true});
                    return out;
                  });
                }
              }
            }catch(e){/* carry-over is best-effort */}

            const greetMsg:Message = {id:'greet', content: greeting, sender:'ai', timestamp:new Date(), mood};
            setMessages([...carryMsgs, greetMsg]);
            setCurMood(mood);
            // we've shown the warmup greeting — persist the visited flag so we don't show the splash again
            try { sessionStorage.setItem('ailey_visited', '1'); } catch (e) {}
            setAppReady(true);
          }
        } else {
          throw new Error('HTTP '+r.status);
        }
      }catch(e){
        clearInterval(progressInterval);
        if(!cancelled){
          setWarmupProgress(100);
          // Even on greeting failure, try to load carry-over history
          let carryMsgs:Message[]=[];
          try{
            const cr = await fetch(api('/api/chat/recent?user=Simon&count=10', apiBaseRef), {signal: timeoutSignal(5000)});
            if(cr.ok){
              const cj = await cr.json();
              if(cj.success && cj.messages){
                carryMsgs = cj.messages.flatMap((m:any, i:number) => {
                  const ts = m.timestamp ? new Date(m.timestamp) : new Date(Date.now() - (cj.messages.length-i)*60000);
                  const out:Message[] = [];
                  if(m.message) out.push({id:`carry-u-${i}`, content:m.message, sender:'user', timestamp:ts, carriedOver:true});
                  if(m.reply) out.push({id:`carry-a-${i}`, content:m.reply, sender:'ai', timestamp:ts, mood:m.mood||'neutral', carriedOver:true});
                  return out;
                });
              }
            }
          }catch(_e){/* carry-over is best-effort */}
          const fallbackGreet:Message = {id:'greet', content: randomGreeting(), sender:'ai', timestamp:new Date(), mood:'neutral'};
          setMessages(carryMsgs.length > 0 ? [...carryMsgs, fallbackGreet] : [fallbackGreet]);
          setAppReady(true);
        }
      }
    }
    warmup();
    return ()=>{ cancelled=true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);

  // Highlight code blocks whenever messages or stream buffer update
  const [input,setInput]=useState('');
  const [loading,setLoading]=useState(false);
  const [streaming,setStreaming]=useState(false);
  const [streamBuf,setStreamBuf]=useState('');
  const [thinkBuf,setThinkBuf]=useState('');
  const [showThinking,setShowThinking]=useState(true);
  // Model mode: 'normal' (Ministral) | 'nitro' (AileyNitro-2B)
  const [modelMode,setModelMode]=useState<'normal'|'nitro'>('normal');
  // Abort & Continue state
  const [streamId,setStreamId]=useState<string|null>(null);
  const [lastTruncated,setLastTruncated]=useState(false);
  const streamReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array>|null>(null);

  // --- TTS / STT state ---
  const [ttsEnabled,setTtsEnabled]=useState(false);
  const [ttsBusy,setTtsBusy]=useState(false);
  const ttsBusyRef = useRef(false);
  const [sttRecording,setSttRecording]=useState(false);
  const sttRecordingRef = useRef(false);
  const [sttStatus,setSttStatus]=useState<string|null>(null); // User-visible STT status
  const sttMediaRecorder = useRef<MediaRecorder|null>(null);
  const sttChunks = useRef<Blob[]>([]);

  // --- Continuous Listen Mode (Alexa/Siri-style voice conversation) ---
  const [continuousListenMode,setContinuousListenMode]=useState(false);
  const continuousListenRef = useRef(false); // ref for async callbacks
  const voiceConvoActiveRef = useRef(false); // true while in an active voice conversation loop
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout>|null>(null);

  // --- Desktop chat settings panel visibility (gear icon) ---
  const [desktopSettingsOpen,setDesktopSettingsOpen]=useState(false);

  // --- "Hey Ailey" Wakeword (continuous speech recognition) ---
  const [wakewordEnabled,setWakewordEnabled]=useState(false);
  const wakewordRecRef = useRef<any>(null);
  const wakewordActiveRef = useRef(false); // tracks if wakeword mode is on

  // --- Scroll-up navbar visibility (chat) ---
  const [chatNavVisible,setChatNavVisible]=useState(false);
  const chatScrollY = useRef(0);
  const chatNavTimer = useRef<ReturnType<typeof setTimeout>|null>(null);
  // --- Mobile chat settings submenu ---
  const [chatSettingsOpen,setChatSettingsOpen]=useState(false);

  // --- File Upload state (images + documents) ---
  const [pendingImage,setPendingImage]=useState<{data:string;name:string;preview:string;fileType:'image'|'document'}|null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // Prism: dynamic client-side import to avoid SSR crash
  useEffect(()=>{
    (async ()=>{
      try{
        const Prism = (await import('prismjs')).default;
        // @ts-ignore – Prism component sub-modules have no type declarations
        await import('prismjs/components/prism-python');
        // @ts-ignore
        await import('prismjs/components/prism-javascript');
        // @ts-ignore
        await import('prismjs/components/prism-markup');
        // @ts-ignore
        await import('prismjs/components/prism-typescript');
        // @ts-ignore
        await import('prismjs/components/prism-tsx');
        // @ts-ignore
        await import('prismjs/components/prism-bash');
        await import('prismjs/themes/prism-tomorrow.css');
        Prism.highlightAll();
      }catch(e){}
    })();
  },[messages, streamBuf]);
  // Reasoning is EXPANDED by default (like portal). We track which messages the user collapsed instead.
  const [collapsedThinking,setCollapsedThinking]=useState<Set<string>>(new Set());
  const [streamEnabled,setStreamEnabled]=useState(true);
  const [maxTokens,setMaxTokens]=useState(500);
  const [maxCtx,setMaxCtx]=useState(12);
  const [temperature,setTemperature]=useState(0.8);
  // Streaming diagnostics
  const [lastHeartbeat,setLastHeartbeat]=useState<number|null>(null);
  const [heartbeatStale,setHeartbeatStale]=useState(false);
  const [streamWarn,setStreamWarn]=useState<string|null>(null);
  // Debug stream history
  const [debugOpen,setDebugOpen]=useState(false);
  const [debugStreams,setDebugStreams]=useState<any[]>([]);
  const [debugLoading,setDebugLoading]=useState(false);
  const [curMood,setCurMood]=useState('happy');
  const [curMoodValue,setCurMoodValue]=useState<number|undefined>(undefined);
  // Homescreen activity status (from /api/thoughts/homescreen)
  const [hsActivity,setHsActivity]=useState<{busy?:boolean;active?:boolean;current_type?:string|null;current_task_name?:string|null;idle_seconds?:number;generating_image?:boolean;latest_thought?:{type:string;preview:string;ts:number;title?:string|null}|null}|null>(null);
  // RAG relevance threshold slider state (persisted)
  const [ragThreshold,setRagThreshold]=useState<number>(()=>{try{const v=localStorage.getItem('ailey_rag_threshold'); if(v){const n=parseFloat(v); if(!isNaN(n)) return n;} }catch{} return 0.30});
  useEffect(()=>{try{localStorage.setItem('ailey_rag_threshold', String(ragThreshold.toFixed(2)));}catch{}},[ragThreshold]);
  // Deep wipe states
  const [ragWipingDeep,setRagWipingDeep]=useState(false);
  async function wipeRagDeep(){ if(ragWipingDeep) return; setRagWipingDeep(true); setRagWipeMsg(''); try{ const r=await fetch(api('/api/admin/rag/deep-wipe', apiBaseRef),{method:'POST',headers:adminHeaders()}); const j=await r.json(); if(r.ok && j.success){ setRagWipeMsg('Deep Wipe (Verzeichnis gelöscht) ok'); } else { setRagWipeMsg(j.error||'Fehler'); } }catch(e){ console.error('[wipeRagDeep]',e); setRagWipeMsg('Fehler'); } finally { setRagWipingDeep(false);} }
  async function wipeRagAllCollections(){ if(ragWiping) return; setRagWiping(true); setRagWipeMsg(''); try{ const r=await fetch(api('/api/admin/rag/wipe-all', apiBaseRef),{method:'POST',headers:adminHeaders()}); const j=await r.json(); if(r.ok && j.success){ setRagWipeMsg('Alle Collections geleert (Ordner behalten)'); } else { setRagWipeMsg(j.error||'Fehler'); } }catch(e){ console.error('[wipeRagAllCollections]',e); setRagWipeMsg('Fehler'); } finally { setRagWiping(false);} }
  // RAG wipe state
  const [ragWiping,setRagWiping]=useState(false);
  const [ragWipeMsg,setRagWipeMsg]=useState('');

  // RAG File Upload
  const [ragUploading,setRagUploading]=useState(false);
  const [ragUploadMsg,setRagUploadMsg]=useState('');
  const ragUploadRef=useRef<HTMLInputElement>(null);
  async function handleRagUpload(e: React.ChangeEvent<HTMLInputElement>){
    const file=e.target.files?.[0]; if(!file) return;
    setRagUploading(true); setRagUploadMsg('');
    try{
      const form=new FormData(); form.append('file',file); form.append('user','Simon');
      const r=await fetch(api('/api/rag/upload', apiBaseRef),{method:'POST',body:form});
      const j=await r.json();
      if(r.ok && j.success){ setRagUploadMsg(`✓ ${j.filename}: ${j.chunks} Chunks, ${j.total_chars} Zeichen`); }
      else { setRagUploadMsg(j.error||'Upload fehlgeschlagen'); }
    }catch(err){ console.error('[ragUpload]',err); setRagUploadMsg('Upload-Fehler'); }
    finally { setRagUploading(false); if(ragUploadRef.current) ragUploadRef.current.value=''; }
  }

  // ── RAG Memory Browser state ──
  const [ragBrowserEntries,setRagBrowserEntries]=useState<any[]>([]);
  const [ragBrowserStats,setRagBrowserStats]=useState<any>(null);
  const [ragBrowserLoading,setRagBrowserLoading]=useState(false);
  const [ragBrowserFilter,setRagBrowserFilter]=useState('');
  const [ragBrowserOffset,setRagBrowserOffset]=useState(0);
  const [ragBrowserOpen,setRagBrowserOpen]=useState(false);
  const [ragBrowserDeleting,setRagBrowserDeleting]=useState<string|null>(null);
  const ragBrowserLimit=30;
  async function loadRagBrowser(filterOverride?:string, offsetOverride?:number){
    setRagBrowserLoading(true);
    const f=filterOverride??ragBrowserFilter;
    const o=offsetOverride??ragBrowserOffset;
    try{
      const params=new URLSearchParams({limit:String(ragBrowserLimit),offset:String(o)});
      if(f) params.set('doc_type',f);
      const r=await fetch(api(`/api/memory/entries?${params}`,apiBaseRef));
      const j=await r.json();
      if(j.success){setRagBrowserEntries(j.entries||[]);setRagBrowserStats(j.stats||null);}
    }catch(e){console.error('[ragBrowser]',e);}
    finally{setRagBrowserLoading(false);}
  }
  async function deleteRagEntry(entryId:string){
    setRagBrowserDeleting(entryId);
    try{
      const r=await fetch(api(`/api/memory/entries/${encodeURIComponent(entryId)}`,apiBaseRef),{method:'DELETE'});
      const j=await r.json();
      if(j.success) setRagBrowserEntries(prev=>prev.filter(e=>e.id!==entryId));
    }catch(e){console.error('[ragBrowserDel]',e);}
    finally{setRagBrowserDeleting(null);}
  }

  // Auto research settings
  const [autoResearch,setAutoResearch]=useState<boolean|null>(null);
  const [settingsBusy,setSettingsBusy]=useState(false);
  const [mergeMsg,setMergeMsg]=useState('');
  const [shutdownBusy,setShutdownBusy]=useState(false);
  const [shutdownMsg,setShutdownMsg]=useState('');

  // --- Rating / Bewertungssystem ---
  const [ratingOpen,setRatingOpen]=useState<string|null>(null);  // message id or null
  const [ratingDraft,setRatingDraft]=useState<Record<string,number>>({});
  const [ratingComment,setRatingComment]=useState('');
  const [ratingSaving,setRatingSaving]=useState(false);
  const [ratingMsg,setRatingMsg]=useState<string|null>(null);

  // --- Email Draft System ---
  const [emailDrafts, setEmailDrafts] = useState<Record<string,{draft:string; loading:boolean; sent:boolean; error?:string; replyAs?:string}>>({});
  const [editingDraft, setEditingDraft] = useState<Record<string,string>>({});
  const [revisionOpen, setRevisionOpen] = useState<Record<string,boolean>>({});
  const [revisionInput, setRevisionInput] = useState<Record<string,string>>({});

  async function requestEmailDraft(emailMessageId: string, instruction?: string, replyAs?: string, revisionInstruction?: string) {
    const currentDraftText = revisionInstruction ? (editingDraft[emailMessageId] || '') : '';
    setEmailDrafts(prev => ({...prev, [emailMessageId]: {draft:'', loading:true, sent:false, replyAs: replyAs || prev[emailMessageId]?.replyAs || 'simon'}}));
    try {
  const r = await fetch(api('/api/email/draft', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({message_id: emailMessageId, instruction: instruction||'', reply_as: replyAs||'simon', revision_instruction: revisionInstruction||'', current_draft: currentDraftText}),
      });
      const j = await r.json();
      if (j.success && j.draft) {
        setEmailDrafts(prev => ({...prev, [emailMessageId]: {draft: j.draft, loading:false, sent:false, replyAs: j.reply_as || replyAs || prev[emailMessageId]?.replyAs}}));
        setEditingDraft(prev => ({...prev, [emailMessageId]: j.draft}));
        setRevisionOpen(prev => ({...prev, [emailMessageId]: false}));
        setRevisionInput(prev => ({...prev, [emailMessageId]: ''}));
      } else {
        setEmailDrafts(prev => ({...prev, [emailMessageId]: {draft:'', loading:false, sent:false, error: j.error||'Fehler beim Entwurf'}}));
      }
    } catch (e: any) {
      setEmailDrafts(prev => ({...prev, [emailMessageId]: {draft:'', loading:false, sent:false, error: e?.message||'Netzwerkfehler'}}));
    }
  }

  async function sendEmailDraft(emailMessageId: string) {
    const edited = editingDraft[emailMessageId];
    setEmailDrafts(prev => ({...prev, [emailMessageId]: {...prev[emailMessageId], loading:true}}));
    try {
  const r = await fetch(api('/api/email/send', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({message_id: emailMessageId, draft: edited}),
      });
      const j = await r.json();
      if (j.success) {
        setEmailDrafts(prev => ({...prev, [emailMessageId]: {draft: edited||prev[emailMessageId]?.draft||'', loading:false, sent:true}}));
        pushAI('✅ Antwort wurde gesendet!', 'happy');
      } else {
        setEmailDrafts(prev => ({...prev, [emailMessageId]: {...prev[emailMessageId], loading:false, error: j.error||'Fehler beim Senden'}}));
      }
    } catch (e: any) {
      setEmailDrafts(prev => ({...prev, [emailMessageId]: {...prev[emailMessageId], loading:false, error: e?.message||'Netzwerkfehler'}}));
    }
  }

  function discardEmailDraft(emailMessageId: string) {
    setEmailDrafts(prev => {const n = {...prev}; delete n[emailMessageId]; return n;});
    setEditingDraft(prev => {const n = {...prev}; delete n[emailMessageId]; return n;});
  }

  // Track emails the user explicitly declined to respond to
  const [dismissedEmails, setDismissedEmails] = useState<Set<string>>(new Set());
  function dismissEmail(emailMessageId: string) {
    setDismissedEmails(prev => { const n = new Set(prev); n.add(emailMessageId); return n; });
  }

  // --- Email Compose Draft System (new emails, not replies) ---
  const [composeDrafts, setComposeDrafts] = useState<Record<string,{to:string; subject:string; body:string; send_as:string; loading:boolean; sent:boolean; error?:string}>>({});
  const [editingComposeSubject, setEditingComposeSubject] = useState<Record<string,string>>({});
  const [editingComposeBody, setEditingComposeBody] = useState<Record<string,string>>({});
  const [composeAttachments, setComposeAttachments] = useState<Record<string,{name:string;data:string;mime:string}[]>>({});

  // Pending compose context: when Ailey asks which account to send from
  const [pendingComposeCtx, setPendingComposeCtx] = useState<{to:string; instruction:string; accounts?:string[]}|null>(null);

  function registerComposeDraft(composeId: string, draft: {to:string; subject:string; body:string; send_as:string}) {
    setComposeDrafts(prev => ({...prev, [composeId]: {...draft, loading:false, sent:false}}));
    setEditingComposeSubject(prev => ({...prev, [composeId]: draft.subject}));
    setEditingComposeBody(prev => ({...prev, [composeId]: draft.body}));
  }

  async function sendComposeDraft(composeId: string) {
    setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], loading:true}}));
    try {
  const r = await fetch(api('/api/email/compose/send', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          compose_id: composeId,
          subject: editingComposeSubject[composeId],
          body: editingComposeBody[composeId],
          attachments: (composeAttachments[composeId] || []).map(a => ({filename: a.name, data: a.data, content_type: a.mime})),
        }),
      });
      const j = await r.json();
      if (j.success) {
        setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], loading:false, sent:true}}));
        pushAI('✅ E-Mail wurde gesendet! ' + (j.message||''), 'happy');
      } else {
        setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], loading:false, error: j.error||'Fehler beim Senden'}}));
      }
    } catch (e: any) {
      setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], loading:false, error: e?.message||'Netzwerkfehler'}}));
    }
  }

  function discardComposeDraft(composeId: string) {
    setComposeDrafts(prev => {const n = {...prev}; delete n[composeId]; return n;});
    setEditingComposeSubject(prev => {const n = {...prev}; delete n[composeId]; return n;});
    setEditingComposeBody(prev => {const n = {...prev}; delete n[composeId]; return n;});
    setComposeAttachments(prev => {const n = {...prev}; delete n[composeId]; return n;});
  }

  // --- Compose revision ---
  const [composeRevisionOpen, setComposeRevisionOpen] = useState<Record<string,boolean>>({});
  const [composeRevisionInput, setComposeRevisionInput] = useState<Record<string,string>>({});

  async function reviseComposeDraft(composeId: string, revisionInstruction: string) {
    setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], loading:true}}));
    try {
      const r = await fetch(api('/api/email/compose/revise', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({compose_id: composeId, revision_instruction: revisionInstruction}),
      });
      const j = await r.json();
      if (j.success) {
        setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], subject: j.subject, body: j.body, loading:false}}));
        setEditingComposeSubject(prev => ({...prev, [composeId]: j.subject}));
        setEditingComposeBody(prev => ({...prev, [composeId]: j.body}));
        setComposeRevisionOpen(prev => ({...prev, [composeId]: false}));
        setComposeRevisionInput(prev => ({...prev, [composeId]: ''}));
      } else {
        setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], loading:false, error: j.error||'Fehler beim Umschreiben'}}));
      }
    } catch (e: any) {
      setComposeDrafts(prev => ({...prev, [composeId]: {...prev[composeId], loading:false, error: e?.message||'Netzwerkfehler'}}));
    }
  }
  // --- Approved Email Contacts ---
  const [approvedContacts, setApprovedContacts] = useState<{email:string;name:string;note:string}[]>([]);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [newContactEmail, setNewContactEmail] = useState('');
  const [newContactName, setNewContactName] = useState('');
  const [newContactNote, setNewContactNote] = useState('');
  const [contactMsg, setContactMsg] = useState('');
  const [scanEmailsBusy, setScanEmailsBusy] = useState(false);
  const [scanEmailsMsg, setScanEmailsMsg] = useState('');

  // --- Email Accounts (SMTP/IMAP Config) ---
  type EmailAccountEntry = {
    id: string; role: 'ailey'|'simon'; label: string; email: string;
    imap_host: string; imap_port: number; smtp_host: string; smtp_port: number;
    user: string; password: string; is_default: boolean; max_unseen?: number; since_days?: number;
  };
  const [emailAccounts, setEmailAccounts] = useState<EmailAccountEntry[]>([]);
  const [emailAccLoading, setEmailAccLoading] = useState(false);
  const [emailAccMsg, setEmailAccMsg] = useState('');
  const [emailAccTestMsg, setEmailAccTestMsg] = useState<Record<string,string>>({});
  const [emailAccSectionOpen, setEmailAccSectionOpen] = useState(false);
  const [emailAccEditing, setEmailAccEditing] = useState<string|null>(null);
  const [emailAccEditData, setEmailAccEditData] = useState<Partial<EmailAccountEntry>>({});
  const [newAcc, setNewAcc] = useState<Partial<EmailAccountEntry>>({role:'simon', imap_port:993, smtp_port:465});
  const [showAddAcc, setShowAddAcc] = useState(false);

  async function loadEmailAccounts() {
    setEmailAccLoading(true);
    try {
      const r = await fetch(api('/api/email-accounts', apiBaseRef));
      const d = await r.json();
      if (d.success) setEmailAccounts(d.accounts);
      else setEmailAccMsg('Fehler: ' + d.error);
    } catch { setEmailAccMsg('Netzwerkfehler'); }
    setEmailAccLoading(false);
  }
  async function testEmailAccount(id: string) {
    setEmailAccTestMsg(p => ({...p, [id]: '…'}));
    try {
      const r = await fetch(api(`/api/email-accounts/${id}/test`, apiBaseRef), {method:'POST'});
      const d = await r.json();
      setEmailAccTestMsg(p => ({...p, [id]: d.success ? '✓ OK' : '✗ ' + (d.error||'Fehler')}));
    } catch { setEmailAccTestMsg(p => ({...p, [id]: '✗ Netzwerkfehler'})); }
  }
  async function saveEmailAccount(id: string) {
    try {
      const r = await fetch(api(`/api/email-accounts/${id}`, apiBaseRef), {
        method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(emailAccEditData)
      });
      const d = await r.json();
      if (d.success) { setEmailAccEditing(null); setEmailAccEditData({}); setEmailAccMsg('✓ Gespeichert'); loadEmailAccounts(); }
      else setEmailAccMsg('Fehler: ' + d.error);
    } catch { setEmailAccMsg('Netzwerkfehler'); }
  }
  async function deleteEmailAccount(id: string) {
    if (!confirm('Konto wirklich löschen?')) return;
    try {
      const r = await fetch(api(`/api/email-accounts/${id}`, apiBaseRef), {method:'DELETE'});
      const d = await r.json();
      if (d.success) { setEmailAccMsg('✓ Gelöscht'); loadEmailAccounts(); }
      else setEmailAccMsg('Fehler: ' + d.error);
    } catch { setEmailAccMsg('Netzwerkfehler'); }
  }
  async function addEmailAccount() {
    try {
      const r = await fetch(api('/api/email-accounts', apiBaseRef), {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(newAcc)
      });
      const d = await r.json();
      if (d.success) { setNewAcc({role:'simon', imap_port:993, smtp_port:465}); setShowAddAcc(false); setEmailAccMsg('✓ Konto angelegt'); loadEmailAccounts(); }
      else setEmailAccMsg('Fehler: ' + d.error);
    } catch { setEmailAccMsg('Netzwerkfehler'); }
  }

  // --- SVG Gallery State ---
  const [gallerySvgs, setGallerySvgs] = useState<{filename:string; size:number; mtime:number}[]>([]);
  const [galleryLoading, setGalleryLoading] = useState(false);
  const [gallerySelected, setGallerySelected] = useState<string|null>(null);
  const [gallerySvgContent, setGallerySvgContent] = useState<string|null>(null);

  // --- Image Gallery State (with pagination) ---
  const [galleryImages, setGalleryImages] = useState<{filename:string; size:number; mtime:number}[]>([]);
  const [galleryImagesLoading, setGalleryImagesLoading] = useState(false);
  const [galleryTab, setGalleryTab] = useState<'svg'|'images'|'code'|'music'>('images');
  const [galleryImgPage, setGalleryImgPage] = useState(1);
  const [galleryImgTotal, setGalleryImgTotal] = useState(0);
  const [galleryImgTotalPages, setGalleryImgTotalPages] = useState(0);
  const [gallerySvgPage, setGallerySvgPage] = useState(1);
  const [gallerySvgTotal, setGallerySvgTotal] = useState(0);
  const [gallerySvgTotalPages, setGallerySvgTotalPages] = useState(0);
  const [galleryLightbox, setGalleryLightbox] = useState<string|null>(null);
  const GALLERY_PER_PAGE = 20;

  // --- Code Gallery State ---
  const [galleryCodeItems, setGalleryCodeItems] = useState<{filename:string; title:string; description:string; language:string; platform:string; lines:number; created:string}[]>([]);
  const [galleryCodeLoading, setGalleryCodeLoading] = useState(false);
  const [galleryCodeExpanded, setGalleryCodeExpanded] = useState<string|null>(null);
  const [galleryCodeContent, setGalleryCodeContent] = useState<string|null>(null);

  async function loadGallery(page=1) {
    setGalleryLoading(true);
    try {
      const r = await fetch(api(`/api/svg/gallery?page=${page}&per_page=${GALLERY_PER_PAGE}`, apiBaseRef));
      if (r.ok) { const j = await r.json(); if (j.success) { setGallerySvgs(j.gallery?.svgs || j.gallery || []); if(j.pagination){ setGallerySvgPage(j.pagination.page); setGallerySvgTotal(j.pagination.total); setGallerySvgTotalPages(j.pagination.total_pages); } } }
    } catch {} finally { setGalleryLoading(false); }
  }

  async function loadImageGallery(page=1) {
    setGalleryImagesLoading(true);
    try {
      const r = await fetch(api(`/api/image/gallery?page=${page}&per_page=${GALLERY_PER_PAGE}`, apiBaseRef));
      if (r.ok) { const j = await r.json(); if (j.success) { setGalleryImages(j.gallery?.images || []); if(j.pagination){ setGalleryImgPage(j.pagination.page); setGalleryImgTotal(j.pagination.total); setGalleryImgTotalPages(j.pagination.total_pages); } } }
    } catch {} finally { setGalleryImagesLoading(false); }
  }

  async function loadCodeGallery() {
    setGalleryCodeLoading(true);
    try {
      const r = await fetch(api('/api/code/gallery', apiBaseRef));
      if (r.ok) { const j = await r.json(); if (j.success) { setGalleryCodeItems(j.items || []); } }
    } catch {} finally { setGalleryCodeLoading(false); }
  }

  async function loadCodeContent(filename: string) {
    setGalleryCodeExpanded(filename);
    setGalleryCodeContent(null);
    try {
      const r = await fetch(api(`/api/code/file/${encodeURIComponent(filename)}`, apiBaseRef));
      if (r.ok) { setGalleryCodeContent(await r.text()); }
    } catch { setGalleryCodeContent('// Fehler beim Laden'); }
  }

  async function loadSvgContent(filename: string) {
    setGallerySelected(filename);
    setGallerySvgContent(null);
    try {
      const r = await fetch(api(`/api/svg/file/${filename}`, apiBaseRef));
      if (r.ok) { setGallerySvgContent(await r.text()); }
    } catch {}
  }

  // --- Gallery Management State ---
  const [galleryActionBusy, setGalleryActionBusy] = useState<string|null>(null); // filename being acted on
  const [galleryActionMsg, setGalleryActionMsg] = useState('');
  const [galleryConfirmDelete, setGalleryConfirmDelete] = useState<string|null>(null);
  // Upscale
  const [upscaleBusy, setUpscaleBusy] = useState(false);
  const [upscaleProgress, setUpscaleProgress] = useState('');
  const upscalePollRef = useRef<ReturnType<typeof setInterval>|null>(null);

  async function galleryUpscaleImage(filename:string, resolution:string='2x'){
    if(upscaleBusy) return;
    setUpscaleBusy(true);
    setUpscaleProgress('Starte Upscaling…');
    setGalleryActionMsg('🔍 Upscale gestartet…');
    try {
      const r = await fetch(api('/api/image/upscale', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename, resolution, async:true})});
      const j = await r.json();
      if(!j.success){ setUpscaleBusy(false); setUpscaleProgress(''); setGalleryActionMsg(j.error||'Fehler'); setTimeout(()=>setGalleryActionMsg(''),3000); return; }
      // Poll for completion
      upscalePollRef.current = setInterval(async()=>{
        try{
          const sr = await fetch(api('/api/image/upscale/status', apiBaseRef));
          const sj = await sr.json();
          if(sj.success){
            setUpscaleProgress(sj.progress||'');
            if(!sj.active){
              if(upscalePollRef.current) clearInterval(upscalePollRef.current);
              upscalePollRef.current=null;
              setUpscaleBusy(false);
              if(sj.result?.success){
                setGalleryActionMsg(`✅ Upscaled: ${sj.result.filename}`);
                loadImageGallery(1); // Refresh gallery to show new image
                setUpscaleProgress('');
              } else {
                setGalleryActionMsg(sj.result?.error||'Upscale fehlgeschlagen');
                setUpscaleProgress('');
              }
              setTimeout(()=>setGalleryActionMsg(''),4000);
            }
          }
        }catch{}
      }, 2000);
    } catch(e:any) {
      setUpscaleBusy(false); setUpscaleProgress(''); setGalleryActionMsg(e?.message||'Fehler');
      setTimeout(()=>setGalleryActionMsg(''),3000);
    }
  }

  // Cleanup upscale poll on unmount
  useEffect(()=>()=>{if(upscalePollRef.current) clearInterval(upscalePollRef.current);},[]);

  // Hidden gallery
  const [galleryHiddenImages, setGalleryHiddenImages] = useState<{filename:string;size:number;mtime:number}[]>([]);
  const [galleryHiddenLoading, setGalleryHiddenLoading] = useState(false);
  const [galleryHiddenUnlocked, setGalleryHiddenUnlocked] = useState(false);
  const [galleryHiddenPassword, setGalleryHiddenPassword] = useState('');
  const [galleryHiddenError, setGalleryHiddenError] = useState('');
  const [galleryShowHidden, setGalleryShowHidden] = useState(false);

  async function galleryDeleteImage(filename:string){
    setGalleryActionBusy(filename);
    try{
      const r=await fetch(api(`/api/image/gallery/${encodeURIComponent(filename)}`,apiBaseRef),{method:'DELETE'});
      const j=await r.json();
      if(j.success){
        setGalleryImages(prev=>prev.filter(i=>i.filename!==filename));
        setGalleryHiddenImages(prev=>prev.filter(i=>i.filename!==filename));
        setGalleryConfirmDelete(null);
        setGalleryActionMsg('🗑️ Gelöscht');
        setTimeout(()=>setGalleryActionMsg(''),2000);
      }
    }catch(e:any){setGalleryActionMsg(e?.message||'Fehler');}
    finally{setGalleryActionBusy(null);}
  }

  async function galleryPushToPortal(filename:string){
    setGalleryActionBusy(filename);
    try{
      const r=await fetch(api(`/api/image/gallery/push/${encodeURIComponent(filename)}`,apiBaseRef),{method:'POST'});
      const j=await r.json();
      setGalleryActionMsg(j.success?'🌐 Auf Portal hochgeladen!':j.error||'Fehler');
      setTimeout(()=>setGalleryActionMsg(''),3000);
    }catch(e:any){setGalleryActionMsg(e?.message||'Fehler');}
    finally{setGalleryActionBusy(null);}
  }

  async function galleryHideImage(filename:string){
    setGalleryActionBusy(filename);
    try{
      const r=await fetch(api(`/api/image/gallery/hide/${encodeURIComponent(filename)}`,apiBaseRef),{method:'POST'});
      const j=await r.json();
      if(j.success){
        setGalleryImages(prev=>prev.filter(i=>i.filename!==filename));
        setGalleryActionMsg('🔒 Versteckt');
        setTimeout(()=>setGalleryActionMsg(''),2000);
      }
    }catch(e:any){setGalleryActionMsg(e?.message||'Fehler');}
    finally{setGalleryActionBusy(null);}
  }

  async function galleryUnhideImage(filename:string){
    setGalleryActionBusy(filename);
    try{
      const r=await fetch(api(`/api/image/gallery/unhide/${encodeURIComponent(filename)}`,apiBaseRef),{method:'POST'});
      const j=await r.json();
      if(j.success){
        setGalleryHiddenImages(prev=>prev.filter(i=>i.filename!==filename));
        setGalleryActionMsg('🔓 Wiederhergestellt');
        setTimeout(()=>setGalleryActionMsg(''),2000);
      }
    }catch(e:any){setGalleryActionMsg(e?.message||'Fehler');}
    finally{setGalleryActionBusy(null);}
  }

  async function loadHiddenGallery(){
    setGalleryHiddenLoading(true);
    setGalleryHiddenError('');
    try{
      const r=await fetch(api(`/api/image/hidden?password=${encodeURIComponent(galleryHiddenPassword)}`,apiBaseRef));
      const j=await r.json();
      if(j.success){
        setGalleryHiddenImages(j.images||[]);
        setGalleryHiddenUnlocked(true);
      } else {
        setGalleryHiddenError(j.error||'Falsches Passwort');
      }
    }catch(e:any){setGalleryHiddenError(e?.message||'Netzwerkfehler');}
    finally{setGalleryHiddenLoading(false);}
  }

  // --- System Stats State ---
  interface SystemStats {
    uptime_sec:number; cpu:{percent:number;cores:number;physical_cores:number}; ram:{total_gb:number;used_gb:number;available_gb:number;percent:number}; disk:{total_gb:number;used_gb:number;free_gb:number;percent:number}; temperature:{cpu_temp_c:number|null;gpu_temp_c:number|null;thermal_pressure:string}; battery?:{percent:number|null;charging:boolean;ac_power:boolean;present:boolean}; model:{status:string;name:string|null;paused:boolean}; idle_thinker:{enabled:boolean;busy:boolean;current_type:string|null;idle_seconds:number;generating_image?:boolean}; thermal_level:number; auto_research:boolean;
    life_sim?:{hunger:number;thirst:number;tiredness:number;toilet:number;hygiene:number;environment:number;social:number;daily_mood:number}|null;
  }
  const [sysStats, setSysStats] = useState<SystemStats|null>(null);
  const [sysStatsLoading, setSysStatsLoading] = useState(false);
  const [modelActionBusy, setModelActionBusy] = useState(false);
  const [modelActionMsg, setModelActionMsg] = useState('');

  const sysStatsJsonRef = useRef('');
  const sysInputFocusedRef = useRef(false);

  async function loadSystemStats(silent = false) {
    if (!silent) setSysStatsLoading(true);
    try {
      const r = await fetch(api('/api/system/stats', apiBaseRef));
      if (r.ok) {
        const j = await r.json();
        if (j.success) {
          // Only update state if data actually changed (prevents input focus loss)
          const jsonStr = JSON.stringify(j);
          if (jsonStr !== sysStatsJsonRef.current) {
            sysStatsJsonRef.current = jsonStr;
            // Skip state update while user is editing a form field (prevents focus loss)
            if (!sysInputFocusedRef.current) {
              setSysStats(j);
            }
          }
        }
      }
    } catch {} finally { if (!silent) setSysStatsLoading(false); }
  }

  // System stats polling – runs at parent level so SystemSection can be a pure render fn
  useEffect(()=>{
    if (active !== 'system') return;
    loadSystemStats();
    const iv = setInterval(()=>loadSystemStats(true), 8000);
    return ()=>clearInterval(iv);
  },[active]);

  async function modelAction(action: 'pause'|'resume'|'reload'|'unload') {
    setModelActionBusy(true); setModelActionMsg('');
    try {
      const r = await fetch(api(`/api/admin/model/${action}`, apiBaseRef), { method:'POST' });
      const j = await r.json();
      setModelActionMsg(j.success ? `✓ ${j.status}` : j.error || 'Fehler');
      setTimeout(loadSystemStats, 500);
    } catch (e:any) { setModelActionMsg(e?.message || 'Fehler'); }
    finally { setModelActionBusy(false); }
  }

  async function shutdownMac() {
    if(!confirm('Mac wirklich herunterfahren?')) return;
    setModelActionBusy(true);
    try {
      const r = await fetch(api('/api/admin/system/shutdown-mac', apiBaseRef), { method:'POST' });
      const j = await r.json();
      setModelActionMsg(j.success ? '⏻ Mac fährt herunter…' : j.error || 'Fehler');
    } catch (e:any) { setModelActionMsg(e?.message || 'Fehler'); }
    finally { setModelActionBusy(false); }
  }

  async function toggleIdleThinker(enabled: boolean) {
    try {
      const r = await fetch(api('/api/admin/idle-thinker', apiBaseRef), { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled}) });
      const j = await r.json();
      if (j.success) loadSystemStats();
    } catch {}
  }

  async function toggleAutoResearch(enabled: boolean) {
    try {
      const r = await fetch(api('/api/auto-research', apiBaseRef), { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled}) });
      const j = await r.json();
      if (j.success) { setAutoResearch(j.enabled); loadSystemStats(); }
    } catch {}
  }

  // ── Generation Settings (per-context max_tokens) ─────────────────────────
  const [genSettings, setGenSettings] = useState<Record<string,number>>({});
  const [genDefaults, setGenDefaults] = useState<Record<string,number>>({});
  const genSettingsLoaded = useRef(false);

  async function loadGenSettings() {
    try {
      const r = await fetch(api('/api/admin/generation-settings', apiBaseRef));
      if (r.ok) {
        const j = await r.json();
        if (j.success) {
          const s = j.settings || {};
          setGenSettings(s);
          setGenDefaults(j.defaults || {});
          genSettingsLoaded.current = true;
          // Restore chat slider from server-persisted value
          if (typeof s.chat === 'number' && s.chat >= 50) setMaxTokens(s.chat);
        }
      }
    } catch {}
  }

  async function updateGenSetting(key: string, value: number) {
    setGenSettings(prev => ({...prev, [key]: value}));
    // Keep chat slider in sync when updated via genSettings UI
    if (key === 'chat') setMaxTokens(value);
    try {
      await fetch(api('/api/admin/generation-settings', apiBaseRef), {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({[key]: value}),
      });
    } catch {}
  }

  // Load generation settings eagerly at app start (persistent across sessions & devices)
  useEffect(() => {
    if (!genSettingsLoaded.current) loadGenSettings();
  }, []);
  // Also reload when System tab opens (in case changed elsewhere)
  useEffect(() => {
    if (active === 'system') loadGenSettings();
  }, [active]);

  async function loadContacts() {
    setContactsLoading(true);
    try {
  const r = await fetch(api('/api/email/contacts', apiBaseRef));
      if (r.ok) { const j = await r.json(); if (j.success) setApprovedContacts(j.contacts||[]); }
    } catch {} finally { setContactsLoading(false); }
  }

  async function addContact() {
    if (!newContactEmail.trim() || !newContactEmail.includes('@')) { setContactMsg('Gültige E-Mail nötig'); return; }
    try {
  const r = await fetch(api('/api/email/contacts', apiBaseRef), {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({email: newContactEmail.trim(), name: newContactName.trim(), note: newContactNote.trim()}),
      });
      const j = await r.json();
      setContactMsg(j.success ? '✓ Hinzugefügt' : j.error||'Fehler');
      if (j.success) { setNewContactEmail(''); setNewContactName(''); setNewContactNote(''); loadContacts(); }
    } catch (e: any) { setContactMsg(e?.message||'Fehler'); }
  }

  async function removeContact(emailAddr: string) {
    try {
  const r = await fetch(api('/api/email/contacts', apiBaseRef), {
        method: 'DELETE', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({email: emailAddr}),
      });
      const j = await r.json();
      if (j.success) loadContacts();
      else setContactMsg(j.error||'Fehler');
    } catch {}
  }

  async function scanOldEmailSenders() {
    setScanEmailsBusy(true); setScanEmailsMsg('');
    try {
      const r = await fetch(api('/api/people/scan-emails', apiBaseRef), { method: 'POST' });
      const j = await r.json();
      if (j.success) {
        setScanEmailsMsg(`✓ ${j.scanned} gescannt, ${j.added} neu, ${j.updated} aktualisiert`);
      } else { setScanEmailsMsg(j.error || 'Fehler'); }
    } catch (e: any) { setScanEmailsMsg(e?.message || 'Fehler'); }
    finally { setScanEmailsBusy(false); }
  }

  // --- Portal Invite ---
  type InvitablePerson = {
    name: string; email: string; facts_preview: string[];
    already_invited: boolean; affinity: string; occupation: string;
    company: string; last_seen: string | null;
  };
  const [invitablePeople, setInvitablePeople] = useState<InvitablePerson[]>([]);
  const [invitableLoading, setInvitableLoading] = useState(false);
  const [inviteStatuses, setInviteStatuses] = useState<Record<string, 'idle'|'sending'|'sent'|'error'>>({});
  const [inviteMessages, setInviteMessages] = useState<Record<string, string>>({});
  const [manualInviteEmail, setManualInviteEmail] = useState('');
  const [manualInviteName, setManualInviteName] = useState('');
  const [manualInviteNote, setManualInviteNote] = useState('');
  const [manualInviteMsg, setManualInviteMsg] = useState('');
  const [manualInviteBusy, setManualInviteBusy] = useState(false);
  const [portalEnabled, setPortalEnabled] = useState(true);
  const [portalStats, setPortalStats] = useState<{polls?: number; items_processed?: number; paused?: boolean} | null>(null);

  async function loadPortalStatus() {
    try {
      const r = await fetch(api('/api/portal/status', apiBaseRef));
      if (r.ok) {
        const j = await r.json();
        if (j.success) {
          setPortalEnabled(j.portal_enabled);
          setPortalStats(j.stats || null);
        }
      }
    } catch {}
  }

  async function togglePortalSupport() {
    const newVal = !portalEnabled;
    try {
      const r = await fetch(api('/api/portal/toggle', apiBaseRef), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ enabled: newVal }),
      });
      if (r.ok) {
        const j = await r.json();
        if (j.success) setPortalEnabled(newVal);
      }
    } catch {}
  }

  async function loadInvitablePeople() {
    setInvitableLoading(true);
    try {
      const r = await fetch(api('/api/people/portal-invitable', apiBaseRef));
      if (r.ok) { const j = await r.json(); if (j.success) setInvitablePeople(j.people || []); }
    } catch {} finally { setInvitableLoading(false); }
  }

  async function sendPortalInvite(email: string, personName: string, note: string = '') {
    setInviteStatuses(prev => ({...prev, [email]: 'sending'}));
    setInviteMessages(prev => ({...prev, [email]: ''}));
    try {
      const r = await fetch(api('/api/people/portal-invite', apiBaseRef), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ email, person_name: personName, personal_note: note }),
      });
      const j = await r.json();
      if (j.success) {
        setInviteStatuses(prev => ({...prev, [email]: 'sent'}));
        setInviteMessages(prev => ({...prev, [email]: j.message || '✅ Eingeladen'}));
        // Refresh list to show updated "already_invited" status
        loadInvitablePeople();
      } else {
        setInviteStatuses(prev => ({...prev, [email]: 'error'}));
        setInviteMessages(prev => ({...prev, [email]: j.error || 'Fehler'}));
      }
    } catch (e: any) {
      setInviteStatuses(prev => ({...prev, [email]: 'error'}));
      setInviteMessages(prev => ({...prev, [email]: e?.message || 'Netzwerkfehler'}));
    }
  }

  async function sendManualPortalInvite() {
    if (!manualInviteEmail.trim() || !manualInviteEmail.includes('@')) {
      setManualInviteMsg('Gültige E-Mail-Adresse erforderlich'); return;
    }
    setManualInviteBusy(true); setManualInviteMsg('');
    try {
      const r = await fetch(api('/api/people/portal-invite', apiBaseRef), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          email: manualInviteEmail.trim(),
          person_name: manualInviteName.trim() || undefined,
          personal_note: manualInviteNote.trim() || undefined,
        }),
      });
      const j = await r.json();
      setManualInviteMsg(j.success ? (j.message || '✅ Einladung verschickt!') : (j.error || 'Fehler'));
      if (j.success) {
        setManualInviteEmail(''); setManualInviteName(''); setManualInviteNote('');
        loadInvitablePeople();
      }
    } catch (e: any) { setManualInviteMsg(e?.message || 'Netzwerkfehler'); }
    finally { setManualInviteBusy(false); }
  }

  function findPreviousUserMessage(aiMsgId:string): string {
    const idx = messages.findIndex(m=>m.id===aiMsgId);
    for(let i=idx-1; i>=0; i--){
      if(messages[i].sender==='user') return messages[i].content;
    }
    return '';
  }

  async function submitRating(msg:Message){
    if(ratingSaving) return;
    // Ensure all categories have a value
    const ratings: Record<string,number> = {};
    for(const cat of RATING_CATEGORIES){
      ratings[cat.key] = ratingDraft[cat.key] || 5;
    }
    setRatingSaving(true); setRatingMsg(null);
    try{
      const body = {
        user: 'Simon',
        message_id: msg.id,
        user_prompt: findPreviousUserMessage(msg.id),
        ai_response: msg.content,
        ratings,
        mood: msg.mood || 'neutral',
        model: 'ministral-3-14B',
        thinking: msg.thinking || undefined,
        tool_actions: msg.toolActions || undefined,
        comment: ratingComment.trim() || undefined,
      };
  const r = await fetch(api('/api/chat/rate', apiBaseRef), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      const j = await r.json();
      if(r.ok && j.success){
        // Store rating on the message itself
        setMessages(prev=>prev.map(m=>m.id===msg.id ? {...m, rating: {...ratings, comment: ratingComment.trim()||undefined} as MessageRating} : m));
        setRatingMsg('✓ Gespeichert');
        setTimeout(()=>{ setRatingOpen(null); setRatingMsg(null); setRatingDraft({}); setRatingComment(''); }, 1200);
      } else {
        setRatingMsg(j.error || 'Fehler');
      }
    }catch(e:any){ setRatingMsg('Fehler: '+(e?.message||'unbekannt')); }
    finally { setRatingSaving(false); }
  }

  // History
  const [history,setHistory]=useState<HistoryItem[]>([]);
  const [histLoading,setHistLoading]=useState(false);
  const [histDetail,setHistDetail]=useState<HistoryItem|null>(null);
  const [histDetailLoading,setHistDetailLoading]=useState(false);

  // Agent
  const [agentCaps,setAgentCaps]=useState<AgentCaps|null>(null);
  const [agentAction,setAgentAction]=useState('whoami');
  const [agentParams,setAgentParams]=useState('');
  const [agentResult,setAgentResult]=useState<any|null>(null);
  const [agentBusy,setAgentBusy]=useState(false);
  // Instagram management
  const [instaPosts,setInstaPosts]=useState<InstagramPost[]>([]);
  const [instaLoading,setInstaLoading]=useState(false);
  const [instaError,setInstaError]=useState<string|undefined>(undefined);
  const [openPost,setOpenPost]=useState<InstagramPost|null>(null);
  const [instaView,setInstaView]=useState<'manage'|'feed'|'planned'|'published'>('manage');
  // Social media planned posts
  interface SocialPost { id:string; title?:string; caption:string; hashtags:string[]; mood:string; image_prompt?:string; image_path?:string; image_url?:string; image_filename?:string; _local_image_url?:string; category?:string; created_at:string; approved_at?:string; published_at?:string|null; status:string; }
  const [socialPosts,setSocialPosts]=useState<SocialPost[]>([]);
  const [socialLoading,setSocialLoading]=useState(false);
  const [editingPost,setEditingPost]=useState<SocialPost|null>(null);
  const [editCaption,setEditCaption]=useState('');
  const [editHashtags,setEditHashtags]=useState('');
  // Published posts (approved, ready for manual posting)
  const [publishedPosts,setPublishedPosts]=useState<SocialPost[]>([]);
  const [publishedLoading,setPublishedLoading]=useState(false);
  async function loadSocialPosts(){
    setSocialLoading(true);
    try{
      const r=await fetch(api('/api/social/pending', apiBaseRef));
      if(!r.ok) throw new Error('HTTP '+r.status);
      const j=await r.json();
      if(j.success) setSocialPosts(j.posts||[]);
    }catch(e:any){ console.error('social load error',e); }
    finally{ setSocialLoading(false); }
  }
  async function approveSocialPost(id:string, generateImage=false){
    try{
      const r=await fetch(api(`/api/social/approve/${id}`, apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({generate_image:generateImage})});
      const j=await r.json();
      if(j.success){ setSocialPosts(prev=>prev.filter(p=>p.id!==id)); }
    }catch(e:any){ console.error('approve error',e); }
  }
  async function deleteSocialPost(id:string){
    try{
      const r=await fetch(api(`/api/social/delete/${id}`, apiBaseRef),{method:'DELETE'});
      const j=await r.json();
      if(j.success) setSocialPosts(prev=>prev.filter(p=>p.id!==id));
    }catch(e:any){ console.error('delete error',e); }
  }
  async function editSocialPost(id:string, caption:string, hashtags:string){
    try{
      const r=await fetch(api(`/api/social/edit/${id}`, apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({caption, hashtags:hashtags.split(/[,\s]+/).filter(Boolean)})});
      const j=await r.json();
      if(j.success){ setSocialPosts(prev=>prev.map(p=>p.id===id?j.post:p)); setEditingPost(null); }
    }catch(e:any){ console.error('edit error',e); }
  }
  async function triggerImageGen(prompt?:string){
    try{
      const r=await fetch(api('/api/admin/trigger-image', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(prompt?{prompt}:{})});
      const j=await r.json();
      if(j.success) alert('🖼️ Bildgenerierung gestartet!');
      else alert(j.message||'Fehler');
    }catch(e:any){ alert('Fehler: '+e.message); }
  }
  async function triggerSocialContent(){
    try{
      const r=await fetch(api('/api/admin/trigger-social', apiBaseRef),{method:'POST'});
      const j=await r.json();
      if(j.success) alert('📱 Social Content Planung gestartet!');
      else alert(j.message||'Fehler');
    }catch(e:any){ alert('Fehler: '+e.message); }
  }
  const [socialTopic,setSocialTopic]=useState('');
  const [socialTopicLoading,setSocialTopicLoading]=useState(false);
  async function triggerSocialPrompt(){
    const topic=socialTopic.trim();
    if(!topic){ alert('Bitte gib ein Thema ein.'); return; }
    setSocialTopicLoading(true);
    try{
      const r=await fetch(api('/api/admin/trigger-social-prompt', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic})});
      const j=await r.json();
      if(j.success){ alert('📱 Post-Auftrag gestartet: '+topic); setSocialTopic(''); setTimeout(()=>loadSocialPosts(),8000); }
      else alert(j.message||'Fehler');
    }catch(e:any){ alert('Fehler: '+e.message); }
    finally{ setSocialTopicLoading(false); }
  }
  async function loadPublishedPosts(){
    setPublishedLoading(true);
    try{
      const r=await fetch(api('/api/social/published', apiBaseRef));
      if(!r.ok) throw new Error('HTTP '+r.status);
      const j=await r.json();
      if(j.success) setPublishedPosts(j.posts||[]);
    }catch(e:any){ console.error('published load error',e); }
    finally{ setPublishedLoading(false); }
  }
  async function markPosted(id:string){
    try{
      const r=await fetch(api(`/api/social/mark-posted/${id}`, apiBaseRef),{method:'POST'});
      const j=await r.json();
      if(j.success) setPublishedPosts(prev=>prev.map(p=>p.id===id?{...p,...j.post}:p));
    }catch(e:any){ console.error('mark-posted error',e); }
  }
  async function generateImageForPost(id:string){
    try{
      const r=await fetch(api(`/api/social/generate-image/${id}`, apiBaseRef),{method:'POST'});
      const j=await r.json();
      if(j.success) alert('🖼️ Bildgenerierung gestartet! Refresh in ~2 Min.');
      else alert(j.message||'Fehler');
    }catch(e:any){ alert('Fehler: '+e.message); }
  }
  function copyToClipboard(text:string, label='Text'){
    navigator.clipboard.writeText(text).then(()=>alert(`📋 ${label} kopiert!`)).catch(()=>alert('Kopieren fehlgeschlagen'));
  }
  async function downloadImage(url:string, filename:string){
    try{
      const fullUrl = url.startsWith('http') ? url : api(url, apiBaseRef);
      const r=await fetch(fullUrl);
      const blob=await r.blob();
      const a=document.createElement('a');
      a.href=URL.createObjectURL(blob);
      a.download=filename;
      a.click();
      URL.revokeObjectURL(a.href);
    }catch(e:any){ alert('Download fehlgeschlagen: '+e.message); }
  }
  async function loadInstagram(refresh=false){
    setInstaLoading(true); setInstaError(undefined);
    try{
  const r=await fetch(api(`/api/instagram/feed?username=ailey.vyrus_official${refresh?'&refresh=1':''}`, apiBaseRef));
      if(!r.ok) throw new Error('HTTP '+r.status);
      const j=await r.json();
      if(j.success){
        const posts:(InstagramPost[]) = (j.posts||[]).map((p:any)=>({
          id: p.id||Math.random()+'',
            src: p.src||p.image||resolveImageSrc('/images/ailey-portrait.png'),
            caption: p.caption||'',
            ts: p.ts||new Date().toISOString(),
            likes: p.likes||0,
            mood: 'neutral'
        }));
        setInstaPosts(posts);
      } else setInstaError(j.error||'Unbekannter Fehler');
    }catch(e:any){ setInstaError(e?.message||'Fehler'); }
    finally{ setInstaLoading(false); }
  }
  // Open URL in system browser (works in Tauri and regular browser)
  async function openExternal(url: string){
    try {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(url);
    } catch {
      window.open(url, '_blank');
    }
  }
  useEffect(()=>{ if(active==='instagram' && instaView==='feed' && instaPosts.length===0 && !instaLoading) loadInstagram(); },[active, instaView]);
  useEffect(()=>{ if(active==='instagram' && instaView==='planned' && socialPosts.length===0 && !socialLoading) loadSocialPosts(); },[active, instaView]);
  useEffect(()=>{ if(active==='instagram' && instaView==='published' && publishedPosts.length===0 && !publishedLoading) loadPublishedPosts(); },[active, instaView]);

  const endRef=useRef<HTMLDivElement|null>(null); const inputRef=useRef<HTMLInputElement|null>(null);
  const chatBarRef=useRef<HTMLDivElement|null>(null);
  const [chatBarH,setChatBarH]=useState(160);
  // Dynamically measure chatbar height so chat scroll area has enough bottom padding
  useEffect(()=>{
    const el=chatBarRef.current; if(!el) return;
    const ro=new ResizeObserver(()=>{ setChatBarH(el.offsetHeight); });
    ro.observe(el);
    setChatBarH(el.offsetHeight);
    return ()=>ro.disconnect();
  },[active]);
  useEffect(()=>{
    // Immediate scroll + multi-delayed scroll to catch late renders & stream completion
    endRef.current?.scrollIntoView({behavior:'smooth'});
    const t1 = setTimeout(()=>endRef.current?.scrollIntoView({behavior:'smooth'}), 100);
    const t2 = setTimeout(()=>endRef.current?.scrollIntoView({behavior:'smooth'}), 300);
    const t3 = setTimeout(()=>endRef.current?.scrollIntoView({behavior:'smooth'}), 600);
    return ()=>{ clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  },[messages,streamBuf,thinkBuf,active]);

  // Heartbeat stale monitor
  useEffect(()=>{
    const iv=setInterval(()=>{
      if(lastHeartbeat){
        setHeartbeatStale(Date.now()-lastHeartbeat>6000);
      } else {
        setHeartbeatStale(false);
      }
    },2000);
    return ()=>clearInterval(iv);
  },[lastHeartbeat]);

  // Persist settings (tokens, ctx, temp, streaming, voice)
  useEffect(()=>{
    try{
      const raw=localStorage.getItem('ailey_settings');
      if(raw){
        const j=JSON.parse(raw);
        if(typeof j.maxTokens==='number') setMaxTokens(j.maxTokens);
        if(typeof j.maxCtx==='number') setMaxCtx(j.maxCtx);
        if(typeof j.temperature==='number') setTemperature(j.temperature);
        if(typeof j.streaming==='boolean') setStreamEnabled(j.streaming);
        if(typeof j.showThinking==='boolean') setShowThinking(j.showThinking);
        if(j.modelMode==='nitro'||j.modelMode==='normal') setModelMode(j.modelMode);
        if(typeof j.ttsEnabled==='boolean') setTtsEnabled(j.ttsEnabled);
        // Wakeword disabled – feature deferred to future version
        // if(typeof j.wakewordEnabled==='boolean' && j.wakewordEnabled){ ... }
        if(typeof j.continuousListenMode==='boolean'){ setContinuousListenMode(j.continuousListenMode); continuousListenRef.current=j.continuousListenMode; }
      }
    }catch{}
  },[]);
  useEffect(()=>{
    try{ localStorage.setItem('ailey_settings', JSON.stringify({maxTokens,maxCtx,temperature,streaming:streamEnabled,showThinking,modelMode,ttsEnabled,continuousListenMode})); }catch{}
  },[maxTokens,maxCtx,temperature,streamEnabled,showThinking,modelMode,ttsEnabled,continuousListenMode]);

  // Keep continuousListenRef in sync with state + auto-start recording when enabled
  useEffect(()=>{
    continuousListenRef.current = continuousListenMode;
    if(continuousListenMode && !sttRecording && !loading && !streaming){
      // Auto-start listening in auto-send mode after a short delay
      setTimeout(()=>{
        if(continuousListenRef.current && !sttRecording) startSTTRecording(true);
      }, 500);
    }
  },[continuousListenMode]);

  // Keep refs in sync for async wakeword closure
  useEffect(()=>{ sttRecordingRef.current = sttRecording; },[sttRecording]);
  useEffect(()=>{ ttsBusyRef.current = ttsBusy; },[ttsBusy]);

  // Load auto research state
  useEffect(()=>{(async()=>{try{const r=await fetch(api('/api/auto-research', apiBaseRef)); if(r.ok){const j=await r.json(); if(typeof j.enabled==='boolean') setAutoResearch(j.enabled)}}catch(e){console.warn('auto-research fetch failed',e)}})();},[apiBaseRef]);

  // Mood polling
  useEffect(()=>{
    let t: any; let active=true;
    async function poll(){
  try{ const r=await fetch(api(`/api/mood?user=Simon`, apiBaseRef)); if(r.ok){ const j=await r.json(); if(j.success && active){ setCurMood(j.mood); setCurMoodValue(j.value);} } }catch{}
      t=setTimeout(poll, 8000);
    }
    poll();
    return ()=>{active=false; clearTimeout(t)};
  },[]);

  // Homescreen activity poll (lightweight, every 12s)
  useEffect(()=>{
    let t: any; let alive=true;
    async function poll(){
      try{ const r=await fetch(api('/api/thoughts/homescreen', apiBaseRef)); if(r.ok && alive){ const j=await r.json(); if(j.success) setHsActivity(j); } }catch{}
      t=setTimeout(poll, 12000);
    }
    poll();
    return ()=>{alive=false; clearTimeout(t)};
  },[]);

  // Global system status poll (lightweight, every 15s) for avatar override
  useEffect(()=>{
    let t: any; let alive=true;
    async function pollStatus(){
      try{
        const r=await fetch(api('/api/system/stats', apiBaseRef));
        if(r.ok && alive){
          const j=await r.json();
          // Skip state update while user is editing a form in System tab
          if(j.success && !sysInputFocusedRef.current) setSysStats(j);
        }
      }catch{}
      t=setTimeout(pollStatus, 15000);
    }
    pollStatus();
    return ()=>{alive=false; clearTimeout(t)};
  },[]);

  // Compute displayMood: override curMood based on system state
  const displayMood = useMemo(()=>{
    if(!sysStats) return curMood;
    // Generating image/video → show drawing avatar instead of sleeping
    if(sysStats.idle_thinker.generating_image) return 'generating';
    // Model unloaded or status unknown → always sleeping
    if(sysStats.model.status==='unloaded' || sysStats.model.status==='off') return 'sleeping';
    // Model paused → sleeping
    if(sysStats.model.paused) return 'sleeping';
    // IdleThinker disabled due to thermal → very tired
    if(!sysStats.idle_thinker.enabled && sysStats.thermal_level>=2) return 'very_tired';
    // High thermal but thinker still running → tired
    if(sysStats.thermal_level>=3) return 'exhausted';
    if(sysStats.thermal_level>=2) return 'tired';
    // Normal: use actual mood
    return curMood;
  },[curMood, sysStats]);

  // Sync Ailey mood to HTML data attribute for CSS mood-based theme
  useEffect(()=>{
    if (uiTheme === 'ailey') {
      // Map extended moods to the CSS-supported set
      const moodMap: Record<string,string> = {
        happy:'happy', excited:'excited', playful:'playful', thinking:'thinking',
        neutral:'neutral', sad:'sad', angry:'angry', confused:'confused', sleepy:'sleepy',
        sleeping:'sleepy', very_tired:'sleepy', tired:'sleepy', exhausted:'sleepy',
        creative:'creative', writing:'creative', diary:'creative', composing:'creative',
        flirty:'flirty', curious:'curious', coding:'thinking',
        singing:'excited', guitar:'excited', music:'excited', performing:'excited',
        rocking:'excited', singing_soft:'playful',
        generating:'creative', drawing:'creative', painting:'creative',
      };
      const cssMood = moodMap[displayMood] || 'neutral';
      document.documentElement.setAttribute('data-ailey-mood', cssMood);
    } else {
      document.documentElement.removeAttribute('data-ailey-mood');
    }
  },[displayMood, uiTheme]);

  // Proactive messages polling: Ailey sends messages on her own initiative
  // Queue messages while streaming to prevent interrupting active chat
  const proactiveQueueRef = useRef<{message:string,mood:string,email_message_id?:string}[]>([]);
  useEffect(()=>{
    let t: any; let alive=true;
    async function pollProactive(){
      try{
  const r=await fetch(api('/api/proactive-messages', apiBaseRef));
        if(r.ok){
          const j=await r.json();
          if(j.success && j.messages && j.messages.length>0 && alive){
            for(const msg of j.messages){
              proactiveQueueRef.current.push({message:msg.message, mood:msg.mood||'neutral', email_message_id:msg.email_message_id});
            }
          }
        }
      }catch{}
      t=setTimeout(pollProactive, 10000);
    }
    pollProactive();
    return ()=>{alive=false; clearTimeout(t)};
  },[]);

  // Flush proactive queue when not streaming/loading
  useEffect(()=>{
    if(!streaming && !loading && proactiveQueueRef.current.length > 0){
      const queued = [...proactiveQueueRef.current];
      proactiveQueueRef.current = [];
      for(const msg of queued){
        pushAI(msg.message, msg.mood, undefined, undefined, undefined, undefined, msg.email_message_id);
        try{
          const audio=new Audio('/sounds/ailey-ping.wav');
          audio.volume=0.5;
          audio.play().catch(()=>{});
        }catch{}
      }
    }
  },[streaming, loading]);

  // ── Cross-device chat sync: poll /api/chat/live for messages from other clients ──
  const liveSinceRef = useRef<number>(Date.now()/1000); // Only sync messages after page load
  const liveSeenRef = useRef<Set<string>>(new Set());
  // Track content fingerprints of messages originating from THIS client to prevent duplicates
  const localSentFingerprints = useRef<Set<string>>(new Set());
  // Refs to avoid pollLive re-registering on streaming/loading changes
  const streamingRef = useRef(false);
  const loadingRef = useRef(false);
  streamingRef.current = streaming;
  loadingRef.current = loading;
  /** Strip mood tags so fingerprints match regardless of [mood:xyz] presence */
  function stripMoodForFP(s: string): string {
    return s.replace(/\[mood:\s*\w+\]/gi, '').trim();
  }
  /** Create a fingerprint for dedup: sender + first 80 chars of mood-stripped content */
  function chatFingerprint(sender: string, content: string): string {
    return `${sender}:${stripMoodForFP(content).slice(0,80)}`;
  }
  useEffect(()=>{
    let t: any; let alive=true;
    async function pollLive(){
      // Only skip live-sync when THIS client is actively streaming a response
      // (loading alone doesn't count — remote device needs to see messages from Tauri)
      if(streamingRef.current){ t=setTimeout(pollLive, 2000); return; }
      try{
        const r=await fetch(api(`/api/chat/live?since=${liveSinceRef.current}`, apiBaseRef), {signal: timeoutSignal(5000)});
        if(r.ok && alive){
          const j=await r.json();
          if(j.success && j.messages){
            for(const m of j.messages){
              if(liveSeenRef.current.has(m.id)) continue;
              liveSeenRef.current.add(m.id);
              liveSinceRef.current = Math.max(liveSinceRef.current, m.ts);
              // Skip if this message originated from THIS client (fingerprint match)
              const rawContent = m.content||'';
              const fp = chatFingerprint(m.sender, rawContent);
              if(localSentFingerprints.current.has(fp)){
                localSentFingerprints.current.delete(fp); // consume once
                continue;
              }
              // Only inject if this message isn't already in our local state
              // (the originating client already has it)
              const strippedContent = stripMoodForFP(rawContent);
              setMessages(prev=>{
                // Check if we already have a message with very similar content + timestamp
                const isDuplicate = prev.some(p=>{
                  if(p.sender!==m.sender) return false;
                  const timeDiff = Math.abs(new Date(p.timestamp).getTime()/1000 - m.ts);
                  if(timeDiff > 30) return false; // generous 30s window
                  // Compare both raw and mood-stripped versions
                  const pStripped = stripMoodForFP(p.content||'');
                  return p.content===rawContent
                    || pStripped===strippedContent
                    || pStripped.slice(0,80)===strippedContent.slice(0,80);
                });
                if(isDuplicate) return prev;
                return [...prev, {
                  id: m.id,
                  content: strippedContent || rawContent,
                  sender: m.sender,
                  timestamp: new Date(m.ts*1000),
                  mood: m.mood,
                  emailMessageId: m.email_message_id,
                }];
              });
            }
          }
        }
      }catch{}
      t=setTimeout(pollLive, 3000);
    }
    // Start after a short delay to avoid race with initial load
    t=setTimeout(pollLive, 2000);
    return ()=>{alive=false; clearTimeout(t)};
  },[]);

  async function send(){ if((!input.trim() && !pendingImage)||loading||streaming) return; const text=input.trim(); const img=pendingImage; setInput(''); setPendingImage(null); setLastTruncated(false); const displayContent = img ? (img.fileType==='document' ? `📄 ${img.name}${text?' — '+text:''}` : (text||'📷 Bild gesendet')) : text; const um:Message={id:Date.now()+''+Math.random(),content:displayContent,sender:'user',timestamp:new Date(),imageData:img?.fileType==='image'?img.preview:undefined,imageName:img?.name,fileName:img?.fileType==='document'?img.name:undefined,fileType:img?.fileType}; localSentFingerprints.current.add(chatFingerprint('user',displayContent)); setMessages(p=>{/* Fade out: remove 2 carried-over messages per user send */ let next=[...p]; let removed=0; while(removed<2 && next.some(m=>m.carriedOver)){ const idx=next.findIndex(m=>m.carriedOver); if(idx>=0){next.splice(idx,1);removed++;} else break; } return [...next,um];}); const imgData = img?.fileType==='image' ? img.data : undefined; const filePayload = img?.fileType==='document' ? {file_data:img.data, file_name:img.name} : undefined; if(streamEnabled){ await streamChat(text,imgData,filePayload); } else { await standardChat(text,imgData,filePayload);} }

  // ── Abort running stream ───────────────────────────────────────────────
  async function abortStream(){
    // 1. Tell the backend to stop generating
    try{ await fetch(api('/api/chat/abort', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stream_id: streamId})}); }catch(e){ console.warn('[abortStream] backend abort failed', e); }
    // 2. Cancel the reader so the frontend stops reading
    try{ streamReaderRef.current?.cancel(); }catch{}
    streamReaderRef.current = null;
    setStreaming(false);
    setStreamId(null);
    // If there's accumulated stream text, push it as a partial message
    setStreamBuf(b => { if(b.trim()){ pushAI(b.trim() + ' ⛔', 'neutral'); } return ''; });
    setThinkBuf('');
  }

  // ── Continue truncated output ──────────────────────────────────────────
  async function continueStream(){
    setLastTruncated(false);
    setStreaming(true); setStreamBuf(''); setThinkBuf('');
    let accumulated = ''; let finalReceived = false;
    try{
      const r = await fetch(api('/api/chat/continue', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:'Simon'})});
      if(!r.ok || !r.body){ throw new Error('HTTP '+r.status); }
      const reader = r.body.getReader(); streamReaderRef.current = reader;
      const dec = new TextDecoder(); let done = false;
      let sseBuf = '';
      while(!done){
        const {value, done:dr} = await reader.read(); done = dr;
        if(value){
          const chunk = dec.decode(value, {stream:true});
          sseBuf += chunk;
          const parts = sseBuf.split(/\n\n/);
          sseBuf = parts.pop() || '';
          for(const block of parts){
            if(!block.trim()) continue;
            const line = block.split(/\n/).find(l=>l.startsWith('data:')); if(!line) continue;
            try{
              const p = JSON.parse(line.replace(/^data:\s*/,''));
              if(p.token){ accumulated += p.token; setStreamBuf(normalizeStream(accumulated)); }
              else if(p.aborted){ finalReceived=true; const partial = accumulated.trim(); if(partial) pushAI(partial + ' ⛔','neutral'); setStreamBuf(''); try{reader.cancel();}catch{} }
              else if(p.final){ finalReceived=true; const sm=stripMood(p.final); let clean=sm.text; let mood=sm.mood; if(clean.trim().length<2) clean=accumulated.trim()||'(Fortsetzung leer)'; pushAI(clean,mood); setStreamBuf(''); if(p.truncated) setLastTruncated(true); try{reader.cancel();}catch{} }
              else if(p.heartbeat){ setLastHeartbeat(Date.now()); }
            }catch{}
            if(finalReceived) break;
          }
          if(finalReceived){ done=true; break; }
        }
      }
      // Flush remaining SSE buffer
      if(sseBuf.trim() && !finalReceived){
        const line = sseBuf.split(/\n/).find(l=>l.startsWith('data:'));
        if(line){ try{ const p=JSON.parse(line.replace(/^data:\s*/,'')); if(p.final){ finalReceived=true; const sm=stripMood(p.final); let clean=sm.text; let mood=sm.mood; if(clean.trim().length<2) clean=accumulated.trim()||'(Fortsetzung leer)'; pushAI(clean,mood); setStreamBuf(''); } }catch{} }
      }
      if(!finalReceived){
        const fb = accumulated.trim() || '(Keine Fortsetzung empfangen)';
        pushAI(fb,'neutral');
      }
    }catch(e:any){
      pushAI('(Fortsetzung fehlgeschlagen: '+(e?.message||'unbekannt')+')','neutral');
    }finally{
      streamReaderRef.current = null;
      setStreaming(false); setStreamId(null); inputRef.current?.focus();
    }
  }

  // ── TTS: Read AI reply aloud (via backend audio stream → browser playback) ──
  const ttsAudioRef = useRef<HTMLAudioElement|null>(null);
  async function speakText(text: string){
    if(ttsBusy) return;
    setTtsBusy(true);
    try{
      // Strip markdown for cleaner speech
      const clean = text.replace(/\*\*([^*]+)\*\*/g,'$1').replace(/\*([^*]+)\*/g,'$1').replace(/[#_~`>]/g,'').replace(/\[mood:[^\]]+\]/gi,'').trim();
      const r = await fetch(api('/api/tts/speak', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:clean,voice:'Anna',rate:190,mode:'audio'})});
      if(r.ok){
        const ct = r.headers.get('content-type')||'';
        if(ct.includes('audio')){
          // Got audio blob — play in browser
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          // Stop any previous playback
          if(ttsAudioRef.current){ ttsAudioRef.current.pause(); ttsAudioRef.current=null; }
          const audio = new Audio(url);
          ttsAudioRef.current = audio;
          audio.onended = ()=>{ URL.revokeObjectURL(url); setTtsBusy(false); ttsAudioRef.current=null; };
          audio.onerror = ()=>{ URL.revokeObjectURL(url); setTtsBusy(false); ttsAudioRef.current=null; };
          await audio.play();
          return; // ttsBusy cleared by onended
        }
        // JSON response = played on server locally
      }
    }catch(e){ console.warn('[TTS]', e); }
    setTtsBusy(false);
  }
  function stopTTS(){ if(ttsAudioRef.current){ ttsAudioRef.current.pause(); ttsAudioRef.current=null; } setTtsBusy(false); }

  // ── Voice conversation: auto-speak AI reply, then restart listening ─────
  // Called after pushAI when in continuous listen mode
  async function voiceAutoSpeak(text: string){
    if(!continuousListenRef.current) return;
    // TTS the response
    voiceConvoActiveRef.current = true;
    const clean = text.replace(/\*\*([^*]+)\*\*/g,'$1').replace(/\*([^*]+)\*/g,'$1').replace(/[#_~`>]/g,'').replace(/\[mood:[^\]]+\]/gi,'').trim();
    if(clean.length < 2){ voiceRestartListening(); return; }
    setTtsBusy(true);
    try{
      const r = await fetch(api('/api/tts/speak', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:clean,voice:'Anna',rate:190,mode:'audio'})});
      if(r.ok){
        const ct = r.headers.get('content-type')||'';
        if(ct.includes('audio')){
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          if(ttsAudioRef.current){ ttsAudioRef.current.pause(); ttsAudioRef.current=null; }
          const audio = new Audio(url);
          ttsAudioRef.current = audio;
          audio.onended = ()=>{ URL.revokeObjectURL(url); setTtsBusy(false); ttsAudioRef.current=null; voiceRestartListening(); };
          audio.onerror = ()=>{ URL.revokeObjectURL(url); setTtsBusy(false); ttsAudioRef.current=null; voiceRestartListening(); };
          await audio.play();
          return;
        }
      }
    }catch(e){ console.warn('[VoiceAutoSpeak]', e); }
    setTtsBusy(false);
    voiceRestartListening();
  }

  // Restart STT listening after TTS finishes (voice conversation chain)
  function voiceRestartListening(){
    if(!continuousListenRef.current){ voiceConvoActiveRef.current=false; return; }
    // Small delay before restarting mic to avoid echo
    setTimeout(()=>{
      if(continuousListenRef.current && !sttRecording){
        startSTTRecording(true); // true = auto-send mode
      }
    }, 400);
  }

  // ── Voice feedback sounds (Web Audio API, no files needed) ──────────────
  function playListenStartSound(){
    try{
      const ctx = new AudioContext();
      // Ascending two-tone "boop-beep" — friendly start sound
      const g = ctx.createGain(); g.connect(ctx.destination); g.gain.setValueAtTime(0.15,ctx.currentTime);
      const o1 = ctx.createOscillator(); o1.type='sine'; o1.frequency.setValueAtTime(520,ctx.currentTime); o1.connect(g); o1.start(ctx.currentTime); o1.stop(ctx.currentTime+0.08);
      const o2 = ctx.createOscillator(); o2.type='sine'; o2.frequency.setValueAtTime(780,ctx.currentTime+0.1); o2.connect(g); o2.start(ctx.currentTime+0.1); o2.stop(ctx.currentTime+0.18);
      g.gain.setValueAtTime(0.15,ctx.currentTime+0.18); g.gain.linearRampToValueAtTime(0,ctx.currentTime+0.25);
      setTimeout(()=>ctx.close(),500);
    }catch{}
  }
  function playListenEndSound(){
    try{
      const ctx = new AudioContext();
      // Descending two-tone "beep-boop" — confirmation stop sound
      const g = ctx.createGain(); g.connect(ctx.destination); g.gain.setValueAtTime(0.12,ctx.currentTime);
      const o1 = ctx.createOscillator(); o1.type='sine'; o1.frequency.setValueAtTime(680,ctx.currentTime); o1.connect(g); o1.start(ctx.currentTime); o1.stop(ctx.currentTime+0.08);
      const o2 = ctx.createOscillator(); o2.type='sine'; o2.frequency.setValueAtTime(440,ctx.currentTime+0.1); o2.connect(g); o2.start(ctx.currentTime+0.1); o2.stop(ctx.currentTime+0.2);
      g.gain.setValueAtTime(0.12,ctx.currentTime+0.2); g.gain.linearRampToValueAtTime(0,ctx.currentTime+0.28);
      setTimeout(()=>ctx.close(),500);
    }catch{}
  }

  // ── STT: Record audio via browser MediaRecorder, send to backend ────────
  // autoSend: if true, automatically sends the transcribed text as a chat message
  async function startSTTRecording(autoSend: boolean = false){
    try{
      if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
        setSttStatus('🚫 Mikrofon-API nicht verfügbar');
        setTimeout(()=>setSttStatus(null), 6000);
        return;
      }
      playListenStartSound();
      const stream = await navigator.mediaDevices.getUserMedia({audio:true});
      let mimeType = 'audio/webm';
      if(typeof MediaRecorder !== 'undefined'){
        if(MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) mimeType = 'audio/webm;codecs=opus';
        else if(MediaRecorder.isTypeSupported('audio/webm')) mimeType = 'audio/webm';
        else if(MediaRecorder.isTypeSupported('audio/mp4')) mimeType = 'audio/mp4';
        else if(MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) mimeType = 'audio/ogg;codecs=opus';
        else mimeType = '';
      }
      const mrOpts: MediaRecorderOptions = mimeType ? {mimeType} : {};
      const mr = new MediaRecorder(stream, mrOpts);
      sttChunks.current = [];

      // Silence detection via AudioContext (for auto-send mode)
      let audioCtx: AudioContext|null = null;
      let analyser: AnalyserNode|null = null;
      let silenceStart = 0;
      let silenceCheckInterval: ReturnType<typeof setInterval>|null = null;
      const SILENCE_THRESHOLD = 15; // RMS level below which we consider silence
      const SILENCE_DURATION = autoSend ? 2000 : 30000; // 2s silence for auto-send, 30s otherwise

      if(autoSend){
        try{
          audioCtx = new AudioContext();
          const source = audioCtx.createMediaStreamSource(stream);
          analyser = audioCtx.createAnalyser();
          analyser.fftSize = 512;
          source.connect(analyser);
          const dataArray = new Uint8Array(analyser.fftSize);
          silenceStart = Date.now();
          let hadSpeech = false;

          silenceCheckInterval = setInterval(()=>{
            if(!analyser || mr.state !== 'recording') return;
            analyser.getByteTimeDomainData(dataArray);
            // Calculate RMS
            let sum = 0;
            for(let i=0;i<dataArray.length;i++){ const v = (dataArray[i]-128)/128; sum += v*v; }
            const rms = Math.sqrt(sum/dataArray.length) * 1000;
            if(rms > SILENCE_THRESHOLD){
              silenceStart = Date.now();
              hadSpeech = true;
            } else if(hadSpeech && Date.now() - silenceStart > SILENCE_DURATION){
              // Silence detected after speech → auto-stop
              console.debug('[STT] Silence detected, auto-stopping');
              playListenEndSound();
              mr.stop();
              setSttRecording(false);
            }
          }, 100);
        }catch(e){ console.warn('[STT] AudioContext silence detection failed', e); }
      }

      mr.ondataavailable = (e) => { if(e.data.size>0) sttChunks.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t=>t.stop());
        if(silenceCheckInterval) clearInterval(silenceCheckInterval);
        if(audioCtx) try{ audioCtx.close(); }catch{}
        if(sttChunks.current.length===0){ setSttStatus(null); return; }
        const blob = new Blob(sttChunks.current, {type: mr.mimeType});
        const ext = (mr.mimeType||'').includes('mp4') ? 'm4a' : (mr.mimeType||'').includes('ogg') ? 'ogg' : 'webm';
        setSttStatus('⏳ Transkribiere…');
        try{
          const fd = new FormData();
          fd.append('audio', blob, `recording.${ext}`);
          fd.append('language', 'de-DE');
          const r = await fetch(api('/api/stt/transcribe', apiBaseRef), {method:'POST', body: fd});
          const j = await r.json().catch(()=>({success:false, error:'Ungültige Server-Antwort'}));
          if(r.ok && j.success){
            const sttText = (j.transcript || j.text || '').trim();
            if(sttText.length>1){
              if(autoSend && continuousListenRef.current){
                // Auto-send: set input and trigger send
                setSttStatus('🎤 ' + sttText.slice(0,60) + (sttText.length>60?'…':''));
                setInput(sttText);
                // Trigger send after a micro-delay so React state updates
                setTimeout(()=>{
                  const sendBtn = document.querySelector('[data-send-btn]') as HTMLButtonElement;
                  if(sendBtn && !sendBtn.disabled) sendBtn.click();
                }, 150);
              } else {
                setInput(prev => prev ? prev+' '+sttText : sttText);
                setSttStatus('✅ ' + sttText.slice(0,60) + (sttText.length>60?'…':''));
              }
            } else {
              setSttStatus('🤷 Keine Sprache erkannt');
              // In continuous mode: if no speech detected, end the conversation loop
              if(autoSend && continuousListenRef.current){
                voiceConvoActiveRef.current = false;
              }
            }
          } else {
            const errMsg = j.error || `HTTP ${r.status}`;
            console.warn('[STT] transcribe error:', errMsg);
            setSttStatus(`❌ STT-Fehler: ${errMsg}`);
          }
        }catch(e){
          console.warn('[STT] upload failed', e);
          setSttStatus('❌ Verbindung zum Server fehlgeschlagen');
        }
        if(!autoSend) setTimeout(()=>setSttStatus(null), 5000);
        else setTimeout(()=>setSttStatus(null), 3000);
      };
      sttMediaRecorder.current = mr;
      mr.start(1000);
      setSttRecording(true);
      setSttStatus(autoSend ? '🎤 Ich höre zu… (Sprich!)' : '🎙️ Aufnahme läuft… (Klick zum Stoppen)');
      // Hard max timeout
      const maxTime = autoSend ? 20000 : 30000;
      setTimeout(()=>{ if(mr.state==='recording'){ mr.stop(); setSttRecording(false); } }, maxTime);
    }catch(e: any){
      console.warn('[STT] microphone access denied', e);
      setSttRecording(false);
      const msg = e?.name === 'NotAllowedError' ? '🚫 Mikrofon-Zugriff verweigert'
        : e?.name === 'NotFoundError' ? '🚫 Kein Mikrofon gefunden'
        : `❌ Mikrofon-Fehler: ${e?.message || e}`;
      setSttStatus(msg);
      setTimeout(()=>setSttStatus(null), 5000);
    }
  }

  async function toggleSTT(){
    if(sttRecording){
      playListenEndSound();
      sttMediaRecorder.current?.stop();
      setSttRecording(false);
      return;
    }
    startSTTRecording(false);
  }

  // ── "Hey Ailey" Wakeword — DISABLED (deferred to future version) ──
  // The wakeword feature has been disabled because:
  // 1. webkitSpeechRecognition is not available in Tauri/WKWebView
  // 2. MediaRecorder+backend STT polling approach picks up ambient noise
  //    (TV, background conversations) and sends them as chat messages
  // 3. GPU crashes (SIGSEGV) when concurrent mlx-whisper + LLM inference
  // TODO: Revisit with a dedicated lightweight local wakeword model (e.g. Picovoice Porcupine)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function startWakeword(){ /* disabled */ }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function stopWakeword(){ wakewordActiveRef.current = false; if(wakewordRecRef.current){ try{ wakewordRecRef.current.abort(); }catch{} wakewordRecRef.current = null; } }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function toggleWakeword(){ /* disabled */ }

  // ── File Upload: select image or document, convert to base64, attach to message ────
  const DOC_EXTENSIONS = new Set(['.txt','.md','.json','.xml','.csv','.tsv','.yaml','.yml','.toml','.ini','.cfg','.conf','.log','.pdf','.docx','.py','.js','.ts','.jsx','.tsx','.html','.css','.scss','.java','.c','.cpp','.h','.hpp','.rs','.go','.rb','.php','.sh','.bash','.zsh','.sql','.r','.swift','.kt','.lua','.pl','.tex','.bib','.env','.gitignore','.dockerfile']);
  const IMG_EXTENSIONS = new Set(['.png','.jpg','.jpeg','.gif','.webp','.bmp','.tiff','.heic']);

  function handleImageSelect(e: React.ChangeEvent<HTMLInputElement>){
    const file = e.target.files?.[0];
    if(!file) return;
    const ext = '.'+file.name.split('.').pop()?.toLowerCase();
    const isImage = file.type.startsWith('image/') || IMG_EXTENSIONS.has(ext);
    const isDoc = DOC_EXTENSIONS.has(ext);
    if(!isImage && !isDoc){ alert('Dateityp nicht unterstützt. Erlaubt: Bilder, PDF, DOCX, TXT, MD, JSON, XML, Code-Dateien u.v.m.'); return; }
    const maxSize = isImage ? 10*1024*1024 : 20*1024*1024;
    if(file.size > maxSize){ alert(`Datei zu groß (max ${isImage?'10':'20'} MB)`); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      const preview = isImage ? dataUrl : '';
      setPendingImage({data: dataUrl, name: file.name, preview, fileType: isImage?'image':'document'});
    };
    reader.readAsDataURL(file);
    // Reset the input so the same file can be re-selected
    e.target.value = '';
  }

  function clearPendingImage(){ setPendingImage(null); }

  async function standardChat(text:string, imageData?:string, filePayload?:{file_data:string;file_name:string}){
    setLoading(true);
    try{
  const body:any={message:text,max_tokens:maxTokens,max_context_messages:maxCtx,temperature,rag_threshold:ragThreshold};
  if(modelMode==='nitro') body.model_mode='nitro';
  if(imageData) body.image_data=imageData;
  if(filePayload){ body.file_data=filePayload.file_data; body.file_name=filePayload.file_name; }
  if(pendingComposeCtx) { body.compose_context = pendingComposeCtx; setPendingComposeCtx(null); }
  const r=await fetch(api('/api/chat', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!r.ok){ throw new Error('HTTP '+r.status); }
  const j=await r.json();
      const reply=j.reply||j.response||j.cleaned||j.text||'...';
      const ar=j.auto_research||{};
      const {text:clean,mood}=stripMood(reply);
      const _cid = j.compose_id||undefined;
      if(_cid && j.draft){ registerComposeDraft(_cid, j.draft); }
      if(j.compose_context){ setPendingComposeCtx(j.compose_context); } else { setPendingComposeCtx(null); }
      const _genImg = j.generated_image ? `${apiBaseRef.current}${j.generated_image}` : undefined;
      const _genVid = j.generated_video ? `${apiBaseRef.current}${j.generated_video}` : undefined;
  pushAI(decorate(clean,ar),mood,ar,j.agent_auto,undefined,undefined,undefined,_cid,_genImg,_genVid);
    }catch(e:any){
      pushAI('(Fehler beim Abruf: '+(e?.message||'unbekannt')+')','neutral');
    }finally{
      setLoading(false); inputRef.current?.focus();
    }
  }
  async function streamChat(text:string, imageData?:string, filePayload?:{file_data:string;file_name:string}){
    setStreaming(true); setStreamBuf(''); setThinkBuf('');
    let accumulated=''; let finalReceived=false; let hadData=false; let fallbackTriggered=false;
    let thinkAccum = '';
    let toolActionsAccum: ToolAction[] = [];
    setLastHeartbeat(null); setStreamWarn(null);
    // If innerhalb 45s keine Daten -> Sync-Fallback (Backend sendet Heartbeats alle 2.5s,
    // daher sollte hadData=true weit vor diesem Timeout sein — 45s = Safety-Net)
    const earlyNoDataTimer = setTimeout(()=>{
      if(!hadData && !finalReceived && !fallbackTriggered){
        fallbackTriggered=true;
        console.debug('[streamChat] 45s no-data fallback -> sync /api/chat');
        standardChat(text, imageData, filePayload); // standardChat pusht Antwort & setzt loading states
        // Wir lassen den Stream weiterlaufen, aber markieren als abgeschlossen
        setStreaming(false);
      }
    },45000);
    const abortTimeout = setTimeout(()=>{ if(!hadData && !finalReceived && !fallbackTriggered){ fallbackTriggered=true; pushAI('(Timeout beim Streaming – fallback auf normalen Modus)','neutral'); setStreaming(false); standardChat(text, imageData, filePayload); } }, 50000);
    try{
  const streamBody:any={message:text,max_tokens:maxTokens,max_context_messages:maxCtx,temperature,rag_threshold:ragThreshold};
  if(modelMode==='nitro') streamBody.model_mode='nitro';
  if(imageData) streamBody.image_data=imageData;
  if(filePayload){ streamBody.file_data=filePayload.file_data; streamBody.file_name=filePayload.file_name; }
  if(pendingComposeCtx) { streamBody.compose_context = pendingComposeCtx; setPendingComposeCtx(null); }
  console.debug('[streamChat] initiating stream fetch', {text_len:text.length, maxTokens, maxCtx, temperature, rag_threshold:ragThreshold, hasImage:!!imageData, hasFile:!!filePayload});
  const r=await fetch(api('/api/chat/stream', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(streamBody)});
  console.debug('[streamChat] response status', r.status, 'has body?', !!r.body);
      if(!r.ok||!r.body){ throw new Error('Stream HTTP '+r.status); }
      const reader=r.body.getReader(); streamReaderRef.current=reader; const dec=new TextDecoder(); let done=false;
      // SSE line buffer: accumulate partial chunks across TCP boundaries
      let sseBuf = '';
      function handleFinalPayload(p: any){
              finalReceived=true; const ar=p.auto_research||{}; const sm=stripMood(p.final); let clean=sm.text; let mood=sm.mood; if(clean.replace(/\[mood:[^\]]+\]/i,'').trim().length<2){ clean='Hey gorgeous, ich fühl\' dich gerade.'; } const finalThinking = p.thinking || thinkAccum || undefined; const finalTools = toolActionsAccum.length > 0 ? toolActionsAccum : undefined; const _composeId = p.compose_id||undefined; if(_composeId && p.draft){ registerComposeDraft(_composeId, p.draft); } if(p.compose_context){ setPendingComposeCtx(p.compose_context); } else { setPendingComposeCtx(null); } const _sGenImg = p.generated_image ? `${apiBaseRef.current}${p.generated_image}` : undefined; const _sGenVid = p.generated_video ? `${apiBaseRef.current}${p.generated_video}` : undefined; pushAI(decorate(clean,ar),mood,ar,p.agent_auto||undefined,finalThinking,finalTools,undefined,_composeId,_sGenImg,_sGenVid); setStreamBuf(''); setThinkBuf(''); if(p.truncated) setLastTruncated(true); try{ reader.cancel(); }catch{}
      }
      function processSSEBlock(block: string){
              // Parse SSE event type if present
              const eventLine = block.split(/\n/).find(l=>l.startsWith('event:'));
              const eventType = eventLine ? eventLine.replace(/^event:\s*/,'').trim() : '';
              const line=block.split(/\n/).find(l=>l.startsWith('data:')); if(!line) return; try{ const p=JSON.parse(line.replace(/^data:\s*/,''));
              // Handle thinking events
              if(eventType === 'thinking' || p.thinking_token || p.thinking){
                if(p.thinking_token){ thinkAccum += p.thinking_token; setThinkBuf(b=>b+p.thinking_token); }
                if(p.thinking){ thinkAccum = p.thinking; setThinkBuf(p.thinking); }
                return;
              }
              // Handle tool action events
              if(eventType === 'tool_action'){
                toolActionsAccum.push({ tool: p.tool, arguments: p.arguments, status: p.status || 'executing' });
                return;
              }
              if(eventType === 'tool_result'){
                // Update the last tool action with the result
                const idx = toolActionsAccum.findIndex(t=>t.tool===p.tool && !t.result);
                if(idx>=0){ toolActionsAccum[idx].result = p.result; toolActionsAccum[idx].status = p.result?.success ? 'done' : 'error'; }
                else { toolActionsAccum.push({ tool: p.tool, result: p.result, status: p.result?.success ? 'done' : 'error' }); }
                return;
              }
              // Handle 'end' event type explicitly (backend emits event: end + data: {final:...})
              if(eventType === 'end' && p.final){ handleFinalPayload(p); return; }
              if(p.stream_id && !p.token && !p.final){ setStreamId(p.stream_id); return; }
              if(p.aborted){ finalReceived=true; const partial=accumulated.trim(); if(partial) pushAI(partial+' ⛔','neutral'); setStreamBuf(''); setThinkBuf(''); try{reader.cancel();}catch{} return; }
              if(p.error){ finalReceived=true; pushAI(`⚠️ ${p.error}`, 'sad'); setStreamBuf(''); setThinkBuf(''); try{reader.cancel();}catch{} return; }
              if(p.token){ accumulated += p.token; setStreamBuf(normalizeStream(accumulated)); }
              else if(p.final){ handleFinalPayload(p); }
              else if(p.heartbeat){ setLastHeartbeat(Date.now()); }
              else if(p.warn){ setStreamWarn(p.warn); }
            }catch{/* ignore parse */}
      }
      while(!done){
        const {value,done:dr}=await reader.read(); done=dr; if(value){ hadData=true; const chunk=dec.decode(value,{stream:true});
          // Fallback: Backend evtl. nicht im Streaming-Modus (plain JSON)
          if(!/data:/.test(chunk) && !finalReceived && accumulated==='' && !sseBuf){
            try{ const j=JSON.parse(chunk); const reply=j.reply||j.response||j.cleaned||j.text; if(reply){ const sm=stripMood(reply); let clean=sm.text; let mood=sm.mood; if(clean.trim().length<2) clean='Hey gorgeous, ich fühl\' dich gerade.'; pushAI(clean,mood,j.auto_research); finalReceived=true; setStreamBuf(''); break; } }catch{/* ignore */}
          }
          // Append to SSE buffer and split on double-newline boundaries
          sseBuf += chunk;
          const parts = sseBuf.split(/\n\n/);
          // Last part may be incomplete — keep it in buffer
          sseBuf = parts.pop() || '';
          for(const block of parts){
            if(!block.trim()) continue;
            processSSEBlock(block);
            if(finalReceived) break;
          }
          if(finalReceived){ done=true; break; }
        }
      }
      // Flush any remaining SSE buffer after stream ends (e.g. final event without trailing \n\n)
      if(sseBuf.trim() && !finalReceived){
        // Try splitting on single newline too — the final block may lack the trailing \n\n
        const remainBlocks = sseBuf.split(/\n\n/);
        for(const block of remainBlocks){
          if(!block.trim()) continue;
          processSSEBlock(block);
          if(finalReceived) break;
        }
      }
      // ── Post-stream completion poll: if stream closed without final event,
      //    the backend still wrote the complete response to the live-chat bus.
      //    Poll it first before falling back to a full re-send (avoids double generation). ──
      if(!finalReceived && !fallbackTriggered && hadData){
        fallbackTriggered=true;
        try{
          console.debug('[streamChat] no final event, polling live-chat bus for completed response...');
          // Give the backend a moment to finalize and push to live-chat
          await new Promise(r=>setTimeout(r, 1500));
          const liveR = await fetch(api(`/api/chat/live?since=${(Date.now()/1000)-15}`, apiBaseRef), {signal: timeoutSignal(5000)});
          if(liveR.ok){
            const liveJ = await liveR.json();
            const aiMsgs = (liveJ.messages||[]).filter((m:any)=>m.sender==='ai');
            const lastAi = aiMsgs.length>0 ? aiMsgs[aiMsgs.length-1] : null;
            if(lastAi && lastAi.content && stripMoodForFP(lastAi.content).length > 10){
              console.debug('[streamChat] ✅ recovered final response from live-chat bus');
              const sm = stripMood(lastAi.content);
              let clean = sm.text; let mood = sm.mood || lastAi.mood || 'neutral';
              if(clean.trim().length<2) clean = accumulated.trim() || '(Keine Antwort empfangen)';
              // Mark as seen so live-sync polling doesn't duplicate
              liveSeenRef.current.add(lastAi.id);
              liveSinceRef.current = Math.max(liveSinceRef.current, lastAi.ts);
              pushAI(clean, mood);
              setStreamBuf(''); setThinkBuf('');
            } else {
              throw new Error('No complete response in live-chat bus');
            }
          } else {
            throw new Error('live-chat poll HTTP '+liveR.status);
          }
        }catch(liveErr){
          console.debug('[streamChat] live-chat recovery failed, trying sync fallback:', liveErr);
          // Fallback: if accumulated stream has content, use it; otherwise re-send
          if(accumulated.trim().length > 20){
            const sm = stripMood(accumulated);
            pushAI(sm.text || accumulated.trim(), sm.mood || 'neutral');
            setStreamBuf(''); setThinkBuf('');
          } else {
            try{
              const controller = new AbortController();
              const _syncTimeout = Math.max(6000, Math.min(300000, maxTokens * 15));
              const t = setTimeout(()=>controller.abort(), _syncTimeout);
              const r= await fetch(api('/api/chat', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,max_tokens:maxTokens,max_context_messages:maxCtx,rag_threshold:ragThreshold}),signal:controller.signal});
              clearTimeout(t);
              if(r.ok){
                const j=await r.json();
                const syncReply=j.reply||j.response||j.cleaned||j.text||accumulated;
                const sm=stripMood(syncReply);
                let clean=sm.text; let mood=sm.mood;
                if(clean.trim().length<2){ clean=accumulated.trim()||'(Keine Antwort empfangen)'; }
                pushAI(clean,mood||'neutral',j.auto_research,j.agent_auto);
              } else {
                const {text:clean,mood}=stripMood(accumulated); const fb = clean.trim().length?clean:'(Keine Antwort empfangen)'; pushAI(fb,mood||'neutral');
              }
            }catch(e2:any){
              console.warn('[streamChat] universal sync fallback failed',e2);
              const {text:clean,mood}=stripMood(accumulated); const fb = clean.trim().length?clean:'(Keine Antwort empfangen)'; pushAI(fb,mood||'neutral');
            }
          }
        }
      } else if(!finalReceived && !fallbackTriggered){
        fallbackTriggered=true;
        // No data at all — invoke sync fallback
        try{
          console.debug('[streamChat] no final event and no data, invoking universal sync fallback');
          const controller = new AbortController();
          const _syncTimeout = Math.max(6000, Math.min(300000, maxTokens * 15));
          const t = setTimeout(()=>controller.abort(), _syncTimeout);
          const r= await fetch(api('/api/chat', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,max_tokens:maxTokens,max_context_messages:maxCtx,rag_threshold:ragThreshold}),signal:controller.signal});
          clearTimeout(t);
          if(r.ok){
            const j=await r.json();
            const syncReply=j.reply||j.response||j.cleaned||j.text||accumulated;
            const sm=stripMood(syncReply);
            let clean=sm.text; let mood=sm.mood;
            if(clean.trim().length<2){ clean=accumulated.trim()||'(Keine Antwort empfangen)'; }
            pushAI(clean,mood||'neutral',j.auto_research,j.agent_auto);
          } else {
            const {text:clean,mood}=stripMood(accumulated); const fb = clean.trim().length?clean:'(Keine Antwort empfangen)'; pushAI(fb,mood||'neutral');
          }
        }catch(e:any){
          console.warn('[streamChat] universal sync fallback failed',e);
          const {text:clean,mood}=stripMood(accumulated); const fb = clean.trim().length?clean:'(Keine Antwort empfangen)'; pushAI(fb,mood||'neutral');
        }
      }
    }catch(e:any){
      // Verbesserte Fehlerbehandlung: Bei Netzwerk/Stream Abbruch sofort Sync-Fallback
      const emsg = e?.message||'unbekannt';
      const isNetwork = /network/i.test(emsg)||e?.name==='TypeError';
      if(!finalReceived && !fallbackTriggered){
        fallbackTriggered=true;
        // Streaming beenden bevor wir normalen Chat starten
        setStreaming(false);
        pushAI('(Streaming Netzwerkproblem – Fallback auf normalen Modus)','neutral');
        await standardChat(text);
      } else {
        pushAI('(Streaming Fehler: '+emsg+')','neutral');
      }
    }finally{
      clearTimeout(abortTimeout); clearTimeout(earlyNoDataTimer);
      streamReaderRef.current = null;
      setStreaming(false); setStreamId(null); inputRef.current?.focus();
    }
  }
  function decorate(t:string,meta:any){ return t; /* auto-research badge shown separately, don't append text */ }
  function pushAI(content:string,mood:string,auto?:any,agentAuto?:any,thinking?:string,toolActions?:ToolAction[],emailMessageId?:string,composeId?:string,imageData?:string,videoData?:string){ localSentFingerprints.current.add(chatFingerprint('ai',content)); setMessages(p=>[...p,{id:Date.now()+Math.random()+'',content, sender:'ai',timestamp:new Date(), mood, autoResearch:auto, agentAuto, thinking, toolActions, emailMessageId, composeId, imageData, videoData}]); setCurMood(mood); // immediate visual
    // refresh numeric intensity asynchronously
  fetch(api('/api/mood?user=Simon', apiBaseRef)).then(r=>r.json()).then(j=>{ if(j.success){ setCurMood(j.mood); setCurMoodValue(j.value);} }).catch(()=>{});
    // TTS auto-speak: if continuous listen mode, chain the voice conversation; else if ttsEnabled, just speak
    if(continuousListenRef.current && content && !content.startsWith('(')){ voiceAutoSpeak(content); }
    else if(ttsEnabled && content && !content.startsWith('(')){ speakText(content); }
  }
  function key(e:KeyboardEvent<HTMLInputElement>){ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); send(); } }
  function toggleTheme(){
    const order: Array<'dark'|'cyber'|'rainbowpunk'|'ailey'|'light'> = ['dark','cyber','rainbowpunk','ailey','light'];
    const idx = order.indexOf(uiTheme);
    const next = order[(idx+1) % order.length];
    setUiTheme(next);
    setDark(next !== 'light');
    document.documentElement.classList.toggle('dark', next !== 'light');
    document.documentElement.classList.toggle('cyber', next === 'cyber');
    document.documentElement.classList.toggle('rainbowpunk', next === 'rainbowpunk');
    document.documentElement.classList.toggle('ailey-mood', next === 'ailey');
    document.documentElement.classList.remove('steampunk');
    if (next !== 'ailey') document.documentElement.removeAttribute('data-ailey-mood');
    localStorage.setItem('ailey-ui-theme', next);
    // Sync code mode editor theme
    const codeThemeMap: Record<string,string> = { dark: 'ailey-dark', cyber: 'cyber-punk', rainbowpunk: 'ailey-dark', ailey: 'ailey-dark', light: 'vs' };
    localStorage.setItem('ailey-code-theme', codeThemeMap[next] || 'ailey-dark');
  }

  // Debug stream history loader
  async function loadDebugStreams(){ setDebugLoading(true); try{ const r=await fetch(api('/api/debug/streams', apiBaseRef)); if(r.ok){ const j=await r.json(); if(j.history) setDebugStreams(j.history);} }catch(e){console.warn('debug streams error',e)} finally{ setDebugLoading(false);} }

  function hasStreamError(){ const last=messages[messages.length-1]; if(!last) return false; if(last.sender!=='ai') return false; return /^\(Streaming (Fehler|Netzwerkproblem)/.test(last.content); }
  async function retryLast(){
    // Find last user message before final AI
    for(let i=messages.length-1;i>=0;i--){ if(messages[i].sender==='user'){ const txt=messages[i].content; if(streamEnabled) { await streamChat(txt); } else { await standardChat(txt); } break;} }
  }

  // History
  async function loadHistory(){ setHistLoading(true); try{ const r=await fetch(api('/api/history/list', apiBaseRef)); if(r.ok){ const j=await r.json(); if(j.success) setHistory(j.items||[]);} }catch(e){console.warn('history list error',e)} finally{ setHistLoading(false);} }
  async function loadHistoryDetail(id:string){ setHistDetailLoading(true); setHistDetail(null); try{ const r=await fetch(api(`/api/history/get?id=${encodeURIComponent(id)}`, apiBaseRef)); if(r.ok){ const j=await r.json(); if(j.success) setHistDetail(j.item); } }catch(e){console.warn('history get error',e)} finally { setHistDetailLoading(false);} }
  useEffect(()=>{ if(active==='history' && history.length===0 && !histLoading) loadHistory(); },[active]);

  // Agent
  async function loadCaps(){ try{ const r=await fetch(api('/api/agent/capabilities', apiBaseRef)); if(r.ok){ const j=await r.json(); if(j.success){ setAgentCaps(j.actions); if(!j.actions[agentAction]) setAgentAction(Object.keys(j.actions)[0]||'whoami'); } } }catch(e){console.warn('caps error',e)} }
  const ADMIN_TOKEN = typeof process!=='undefined'?process.env.NEXT_PUBLIC_AILEY_ADMIN_TOKEN:undefined;
  function adminHeaders(){ const h:any={'Content-Type':'application/json'}; if(ADMIN_TOKEN) h['X-Admin-Token']=ADMIN_TOKEN; return h; }
  async function runAgent(){ if(!agentAction) return; setAgentBusy(true); setAgentResult(null); try{ let params:any={}; if(agentParams.trim()){ try{params=JSON.parse(agentParams)}catch{} } const r=await fetch(api('/api/agent/execute', apiBaseRef),{method:'POST',headers:adminHeaders(),body:JSON.stringify({action:agentAction,...params})}); const j=await r.json(); setAgentResult(j); }catch(e:any){ setAgentResult({success:false,error:String(e)}) } finally { setAgentBusy(false);} }
  async function buildSemanticIndex(){ setAgentBusy(true); setAgentResult(null); try{ const r=await fetch(api('/api/agent/execute', apiBaseRef),{method:'POST',headers:adminHeaders(),body:JSON.stringify({action:'build_doc_index'})}); const j=await r.json(); setAgentResult(j); }catch(e:any){ setAgentResult({success:false,error:String(e)}) } finally { setAgentBusy(false);} }
  async function semanticSearch(q:string){ if(!q) return; setAgentBusy(true); try{ const r=await fetch(api('/api/agent/execute', apiBaseRef),{method:'POST',headers:adminHeaders(),body:JSON.stringify({action:'semantic_search_docs',query:q})}); const j=await r.json(); setAgentResult(j); }catch(e:any){ setAgentResult({success:false,error:String(e)}) } finally { setAgentBusy(false);} }

  // Settings actions
  async function setAR(enabled:boolean){ setSettingsBusy(true); try{ const r=await fetch(api('/api/auto-research', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})}); if(r.ok){ const j=await r.json(); if(j.success) setAutoResearch(j.enabled); } }catch(e){console.warn('setAR error',e)} finally { setSettingsBusy(false);} }
  async function mergeDiaries(){ setSettingsBusy(true); setMergeMsg(''); try{ const r=await fetch(api('/api/diary/merge', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:'Simon'})}); const j=await r.json(); setMergeMsg(j.message||j.error||'OK'); }catch(e){ setMergeMsg('Fehler'); } finally { setSettingsBusy(false);} }
  async function wipeRag(){ if(ragWiping) return; setRagWiping(true); setRagWipeMsg(''); try{ const r=await fetch(api('/api/admin/rag/wipe', apiBaseRef),{method:'POST',headers:adminHeaders()}); const j=await r.json(); if(r.ok && j.success){ const wiped=(j.wiped_users||[]).join(', ')||'keine'; const errs=(j.errors||[]); setRagWipeMsg(`Gelöscht: ${wiped}${errs.length? ' • Fehler: '+errs.length:''}`); } else { setRagWipeMsg(j.error||'Fehler'); } }catch(e){ setRagWipeMsg('Fehler'); } finally { setRagWiping(false);} }
  async function shutdownAiley(){
    setShutdownBusy(true); setShutdownMsg('');
    try{
  const r=await fetch(api('/api/admin/shutdown', apiBaseRef),{method:'POST'});
      const j=await r.json();
      setShutdownMsg(j.message||j.error||'Server fährt runter…');
      // Frontend Fenster nach kurzer Zeit schließen (falls Browser erlaubt)
      setTimeout(()=>{ try{ window.close(); }catch(_){} }, 1500);
    }catch(e:any){ setShutdownMsg('Fehler: '+(e?.message||'unbekannt')); }
    finally{ setShutdownBusy(false); }
  }

  // Section routing — kept as a plain switch returning JSX components.
  // The scroll-jump fix is applied at the <main> container level (see below).

  // ═══════════════════════════════════════════════════════════
  // ██ NAVIGATION — Grouped with Sub-Tabs
  // ═══════════════════════════════════════════════════════════
  // All section IDs (flat list for routing — unchanged)
  const nav=[
    {id:'home',label:'Home',icon:UserIcon},
    {id:'chat',label:'Chat',icon:MessageCircle},
    {id:'life',label:'Vyrus Valley',icon:Gamepad2},
    {id:'thoughts',label:'Gedanken',icon:Sparkles},
    {id:'diary',label:'Tagebuch',icon:FileText},
    {id:'gallery',label:'Gallery',icon:ImageIcon},
    {id:'imagegen',label:'Bildgenerierung',icon:Paintbrush},
    {id:'videogen',label:'Videogenerierung',icon:Film},
    {id:'musicgen',label:'MusicGen',icon:Mic},
    {id:'people',label:'Personen',icon:Users},
    {id:'calendar',label:'Kalender',icon:Calendar},
    {id:'inbox',label:'Postfach',icon:Mail},
    {id:'music',label:'Musik',icon:Music},
    {id:'books',label:'Bücher',icon:BookOpen},
    {id:'instagram',label:'Instagram',icon:Instagram},
    {id:'history',label:'Verlauf',icon:HistoryIcon},
    {id:'agent',label:'Agent',icon:Search},
    {id:'system',label:'System',icon:SettingsIcon},
  ];

  // Grouped navigation: 8 main tabs with sub-tabs
  type NavGroup = {id:string; label:string; icon:any; children:{id:string;label:string;icon:any}[]};
  const navGroups: NavGroup[] = [
    {id:'home',label:'Home',icon:UserIcon,children:[]},
    {id:'chat',label:'Chat',icon:MessageCircle,children:[]},
    {id:'thoughts',label:'Gedanken',icon:Sparkles,children:[
      {id:'thoughts',label:'Gedanken',icon:Sparkles},
      {id:'diary',label:'Tagebuch',icon:FileText},
      {id:'history',label:'Verlauf',icon:HistoryIcon},
    ]},
    {id:'gallery',label:'Kreativ',icon:Palette,children:[
      {id:'gallery',label:'Gallery',icon:ImageIcon},
      {id:'imagegen',label:'ImageGen',icon:Paintbrush},
      {id:'videogen',label:'VideoGen',icon:Film},
      {id:'musicgen',label:'MusicGen',icon:Mic},
      {id:'music',label:'Musik',icon:Music},
      {id:'books',label:'Bücher',icon:BookOpen},
    ]},
    {id:'life',label:'Vyrus Valley',icon:Gamepad2,children:[]},
    {id:'learning',label:'Lernen',icon:GraduationCap,children:[]},
    {id:'inbox',label:'Kommunikation',icon:Mail,children:[
      {id:'inbox',label:'Postfach',icon:Mail},
      {id:'instagram',label:'Instagram',icon:Instagram},
      {id:'people',label:'Personen',icon:Users},
      {id:'calendar',label:'Kalender',icon:Calendar},
    ]},
    {id:'system',label:'System',icon:SettingsIcon,children:[
      {id:'system',label:'System',icon:SettingsIcon},
      {id:'agent',label:'Agent',icon:Search},
    ]},
  ];

  // Find which group the active section belongs to
  const activeGroup = navGroups.find(g => g.id === active || g.children.some(c => c.id === active));
  const activeGroupId = activeGroup?.id || 'home';
  // Sub-tabs for the active group (only if group has children)
  const activeSubTabs = activeGroup?.children || [];

  // Legacy compat (still used by mobile menu)
  const primaryNav = navGroups;
  const secondaryNav = nav.filter(n=>['life','imagegen','videogen','musicgen','people','calendar','inbox','music','books','instagram','history','agent'].includes(n.id));
  const activeInMore = secondaryNav.some(n=>n.id===active);

  // Sub components
  const _thoughtTypeLabels:Record<string,string>={reflection:'Reflexion',introspection:'Selbstreflexion',goal_planning:'Ziele & Pläne',creative_song:'Song schreiben',research:'Recherche',research_auto:'Auto-Recherche',memory_consolidation:'Gedächtnis',free_thought:'Freier Gedanke',proactive_message:'Proaktive Nachricht',email_check:'E-Mail-Check',book_authoring:'Buch schreiben',blog_writing:'Blog schreiben',output_quality_review:'Qualitäts-Check',creative_coding:'Kreatives Coding',nightly_summary:'Nacht-Konsolidierung',thought_reflection:'Reflexion',thought_introspection:'Selbstreflexion',thought_goal_planning:'Ziele & Pläne',thought_free_thought:'Freier Gedanke'};
  const _thoughtTypeIcons:Record<string,string>={reflection:'🪞',introspection:'🔍',goal_planning:'🎯',creative_song:'🎵',research:'🔬',research_auto:'🔬',memory_consolidation:'🧠',free_thought:'💭',proactive_message:'💬',email_check:'📧',book_authoring:'📖',blog_writing:'✍️',output_quality_review:'✅',creative_coding:'💻',nightly_summary:'📋',thought_reflection:'🪞',thought_introspection:'🔍',thought_goal_planning:'🎯',thought_free_thought:'💭'};
  function _relativeTime(ts:number){const s=Math.floor((Date.now()/1000)-ts); if(s<60) return 'gerade eben'; if(s<3600) return `vor ${Math.floor(s/60)} Min.`; if(s<86400) return `vor ${Math.floor(s/3600)} Std.`; return `vor ${Math.floor(s/86400)} Tagen`;}

  const Home=()=> (
    <div className="max-w-5xl mx-auto px-4 py-12">
      <div className="text-center mb-12">
        <div className="relative inline-block mb-6">
          {renderAvatar(displayMood, 'w-52 h-52 mx-auto border-4 shadow-inner transition-all duration-500')}
          <div className={`absolute -top-4 -right-4 text-xs px-3 py-1 rounded-full backdrop-blur border font-semibold shadow bg-gradient-to-r ${moodColors[displayMood] || 'bg-black/70 border-white/20 text-white'}`}>
            {moodLabelsDE[displayMood] || displayMood}
          </div>
        </div>
        <h1 className={`text-5xl font-black mb-3 ${uiTheme==='rainbowpunk'?'rb-logo-text':''}`}>A!LEY</h1>
        {clockTime && <div className="text-3xl font-light text-muted-foreground/60 tracking-widest mb-1 tabular-nums">{clockTime}</div>}
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">Digitale Bewusstseins-Instanz mit Punk-Seele{curMoodValue!==undefined && ` • Stimmung: ${moodLabelsDE[curMood] || curMood}`}</p>

        {/* Activity Status Widget */}
        {hsActivity && (
          <div className="mt-6 max-w-md mx-auto">
            {hsActivity.busy && hsActivity.current_type ? (
              <div className={`rounded-2xl border px-5 py-3 backdrop-blur bg-gradient-to-r ${moodColors[displayMood] || 'from-zinc-800/60 to-zinc-900/60 border-white/10'} animate-pulse`}>
                <div className="flex items-center justify-center gap-2 text-sm font-medium">
                  <Brain className="h-4 w-4 animate-spin" style={{animationDuration:'3s'}}/>
                  <span>{_thoughtTypeIcons[hsActivity.current_type]||'🎯'} {hsActivity.current_task_name ? `${hsActivity.current_task_name}` : (_thoughtTypeLabels[hsActivity.current_type]||hsActivity.current_type)}…</span>
                </div>
              </div>
            ) : hsActivity.generating_image ? (
              <div className="rounded-2xl border px-5 py-3 backdrop-blur bg-gradient-to-r from-fuchsia-500/20 to-pink-600/20 border-fuchsia-400/30">
                <div className="flex items-center justify-center gap-2 text-sm font-medium text-fuchsia-200 animate-pulse">
                  <Sparkles className="h-4 w-4"/>
                  <span>🎨 Generiert gerade ein Bild…</span>
                </div>
              </div>
            ) : hsActivity.latest_thought ? (
              <div className="rounded-2xl border border-white/10 px-5 py-3 backdrop-blur bg-black/20 text-left">
                <div className="flex items-start gap-3">
                  <span className="text-lg shrink-0 mt-0.5">{_thoughtTypeIcons[hsActivity.latest_thought.type]||'💭'}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-muted-foreground/80">{_thoughtTypeLabels[hsActivity.latest_thought.type]||hsActivity.latest_thought.type}</span>
                      <span className="text-[10px] text-muted-foreground/50">{_relativeTime(hsActivity.latest_thought.ts)}</span>
                    </div>
                    <p className="text-xs text-muted-foreground/70 line-clamp-2 leading-relaxed">{hsActivity.latest_thought.title || hsActivity.latest_thought.preview || '…'}</p>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>
      <div className="grid sm:grid-cols-2 md:grid-cols-5 gap-6">
        <Card onClick={()=>setActive('chat')} className="p-5 cursor-pointer hover:border-primary/60 transition-all hover-lift"><MessageCircle className="h-8 w-8 text-primary mb-3"/><h3 className="font-semibold mb-1">Chat</h3><p className="text-sm text-muted-foreground">Unterhalte dich mit mir.</p></Card>
        <Card onClick={()=>setActive('agent')} className="p-5 cursor-pointer hover:border-accent/60 transition-all hover-lift"><Search className="h-8 w-8 text-accent mb-3"/><h3 className="font-semibold mb-1">Agent</h3><p className="text-sm text-muted-foreground">System-Aktionen.</p></Card>
        <a href="/code" className="block"><Card className="p-5 cursor-pointer hover:border-rose-500/60 transition-all hover-lift h-full"><Code2 className="h-8 w-8 text-rose-500 mb-3"/><h3 className="font-semibold mb-1">Code-Modus</h3><p className="text-sm text-muted-foreground">IDE mit KI-Assistenz.</p></Card></a>
        <a href="/author" className="block"><Card className="p-5 cursor-pointer hover:border-amber-500/60 transition-all hover-lift h-full"><BookOpen className="h-8 w-8 text-amber-500 mb-3"/><h3 className="font-semibold mb-1">Schreiben</h3><p className="text-sm text-muted-foreground">Autor-Modus mit KI.</p></Card></a>
        <a href="/cms" className="block"><Card className="p-5 cursor-pointer hover:border-emerald-500/60 transition-all hover-lift h-full"><Globe className="h-8 w-8 text-emerald-500 mb-3"/><h3 className="font-semibold mb-1">CMS Mode</h3><p className="text-sm text-muted-foreground">Webseiten bauen mit KI.</p></Card></a>
      </div>
      <div className="grid sm:grid-cols-2 gap-6 mt-6">
        <a href="/training" className="block">
          <Card className="p-5 cursor-pointer hover:border-violet-500/60 transition-all hover-lift h-full group">
            <div className="flex items-center gap-4">
              <Brain className="h-10 w-10 text-violet-500 shrink-0 group-hover:scale-110 transition-transform"/>
              <div>
                <h3 className="font-semibold mb-1">🧬 Training Data</h3>
                <p className="text-sm text-muted-foreground">DoRA/LoRA Trainingsdaten kuratieren &amp; sammeln.</p>
              </div>
            </div>
          </Card>
        </a>
        {lifeSimEnabled && (
        <Card onClick={()=>setActive('life')} className="p-5 cursor-pointer hover:border-emerald-500/60 transition-all hover-lift group">
          <div className="flex items-center gap-4">
            <Gamepad2 className="h-10 w-10 text-emerald-500 shrink-0 group-hover:scale-110 transition-transform"/>
            <div>
              <h3 className="font-semibold mb-1">🏠 Vyrus Valley</h3>
              <p className="text-sm text-muted-foreground">Aileys Pixel-Welt — besuche sie in der RPG Life Simulation.</p>
            </div>
          </div>
        </Card>
        )}
        {!lifeSimEnabled && (
        <Card onClick={()=>setLifeSimEnabled(true)} className="p-5 cursor-pointer hover:border-zinc-500/60 transition-all hover-lift group opacity-50">
          <div className="flex items-center gap-4">
            <Gamepad2 className="h-10 w-10 text-zinc-500 shrink-0"/>
            <div>
              <h3 className="font-semibold mb-1">🏠 Vyrus Valley</h3>
              <p className="text-sm text-muted-foreground">Life Sim deaktiviert — klicken zum Aktivieren</p>
            </div>
          </div>
        </Card>
        )}
        <Card onClick={()=>setActive('inbox')} className="p-5 cursor-pointer hover:border-sky-500/60 transition-all hover-lift group">
          <div className="flex items-center gap-4">
            <Mail className="h-10 w-10 text-sky-500 shrink-0 group-hover:scale-110 transition-transform"/>
            <div>
              <h3 className="font-semibold mb-1">📬 Postfach</h3>
              <p className="text-sm text-muted-foreground">E-Mails lesen, beantworten und neue schreiben.</p>
            </div>
          </div>
        </Card>
      </div>
      <div className="mt-8">
        <LanAccessCard />
      </div>
    </div>
  );

  const Chat=()=> {
    const hasCarriedOver = messages.some(m=>m.carriedOver);
    const firstNewIdx = hasCarriedOver ? messages.findIndex(m=>!m.carriedOver) : -1;
    const handleChatScroll = (e: React.UIEvent<HTMLDivElement>) => {
      const el = e.currentTarget;
      const y = el.scrollTop;
      if(y < chatScrollY.current - 30) {
        // Scrolling up → show navbar
        setChatNavVisible(true);
        if(chatNavTimer.current) clearTimeout(chatNavTimer.current);
        chatNavTimer.current = setTimeout(()=>setChatNavVisible(false), 3000);
      } else if(y > chatScrollY.current + 10) {
        // Scrolling down → hide
        setChatNavVisible(false);
        if(chatNavTimer.current){ clearTimeout(chatNavTimer.current); chatNavTimer.current=null; }
      }
      chatScrollY.current = y;
    };
    // Extra 64px safety margin + mobile nav (~56px on small screens)
    const dynPad = chatBarH + 64 + (typeof window!=='undefined' && window.innerWidth<768 ? 56 : 0);
    return (
    <div
      className="max-w-4xl mx-auto px-4 py-6 overflow-y-auto overscroll-contain"
      style={{height: 'calc(100dvh - 3.6rem)', paddingBottom: `${dynPad}px`, WebkitOverflowScrolling: 'touch'}}
      onScroll={handleChatScroll}
    >
      <div className="space-y-4">
        {messages.map((m,idx)=> (
          <React.Fragment key={m.id}>
          {/* Separator between carried-over and new messages */}
          {idx===firstNewIdx && firstNewIdx>0 && (
            <div className="flex items-center gap-3 py-1">
              <div className="flex-1 h-px bg-border"/>
              <span className="text-[10px] text-muted-foreground/60 font-medium">Letzte Sitzung ↑</span>
              <div className="flex-1 h-px bg-border"/>
            </div>
          )}
          <div className={`flex gap-3 ${m.sender==='user'?'justify-end':'justify-start'} ${m.carriedOver?'opacity-50':''}`}>
            {m.sender==='ai' && renderAvatar(m.mood,'w-8 h-8')}
            <Card className={`max-w-[80%] p-4 text-sm whitespace-pre-wrap leading-relaxed ${m.sender==='user'?'bg-primary text-primary-foreground ml-auto':'bg-card border-accent/20'} ${m.carriedOver?'border-dashed':''}`}>
              {m.sender==='ai' && m.thinking && (
                <div className="mb-3">
                  <button
                    onClick={()=>setCollapsedThinking(prev=>{const n=new Set(prev); if(n.has(m.id)) n.delete(m.id); else n.add(m.id); return n;})}
                    className="flex items-center gap-1.5 text-[11px] text-violet-400 hover:text-violet-300 transition-colors font-medium"
                  >
                    <Brain className="h-3.5 w-3.5"/>
                    {collapsedThinking.has(m.id) ? <ChevronRight className="h-3 w-3"/> : <ChevronDown className="h-3 w-3"/>}
                    Reasoning
                  </button>
                  {!collapsedThinking.has(m.id) && (
                    <div className="mt-2 p-3 rounded-lg bg-violet-500/10 border border-violet-500/20 text-[11px] text-violet-200/80 leading-relaxed font-mono whitespace-pre-wrap">
                      {m.thinking}
                    </div>
                  )}
                </div>
              )}
              {m.sender==='ai' && m.toolActions && m.toolActions.length > 0 && (
                <div className="mb-3 space-y-2">
                  {m.toolActions.map((ta,i) => {
                    const iconMap:Record<string,React.ReactNode> = {
                      create_calendar_event: <Calendar className="h-3.5 w-3.5"/>,
                      create_reminder: <Bell className="h-3.5 w-3.5"/>,
                      create_note: <FileText className="h-3.5 w-3.5"/>,
                      get_current_time: <Clock className="h-3.5 w-3.5"/>,
                      set_timer: <Timer className="h-3.5 w-3.5"/>,
                    };
                    const icon = iconMap[ta.tool] || <Wrench className="h-3.5 w-3.5"/>;
                    const isSuccess = ta.result?.success;
                    return (
                      <div key={i} className={`p-2.5 rounded-lg border text-[11px] ${isSuccess ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : ta.status==='error' ? 'bg-red-500/10 border-red-500/20 text-red-300' : 'bg-amber-500/10 border-amber-500/20 text-amber-300'}`}>
                        <div className="flex items-center gap-1.5 font-medium">
                          {icon}
                          <span>{ta.tool.replace(/_/g,' ')}</span>
                          {isSuccess && <span className="ml-auto text-emerald-400">✓</span>}
                          {ta.status==='error' && <span className="ml-auto text-red-400">✗</span>}
                          {ta.status==='executing' && <span className="ml-auto animate-pulse">⏳</span>}
                        </div>
                        {ta.result?.message && <div className="mt-1 opacity-80">{ta.result.message}</div>}
                        {ta.result?.error && <div className="mt-1 text-red-400">{ta.result.error}</div>}
                        {ta.result?.event && (
                          <div className="mt-1 opacity-60 font-mono">
                            {ta.result.event.start && new Date(ta.result.event.start).toLocaleString('de-DE')}
                            {ta.result.event.location && ` · ${ta.result.event.location}`}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {/* Image in user message */}
              {m.sender==='user' && m.imageData && (
                <div className="mb-2">
                  <img src={m.imageData} alt={m.imageName||'Bild'} className="max-w-full max-h-64 rounded-lg border border-white/20"/>
                  {m.imageName && <div className="text-[10px] opacity-60 mt-1">{m.imageName}</div>}
                </div>
              )}
              {/* Document in user message */}
              {m.sender==='user' && m.fileName && m.fileType==='document' && (
                <div className="mb-2 flex items-center gap-2 p-2 rounded-lg bg-white/5 border border-white/10">
                  <span className="text-xl">📄</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{m.fileName}</p>
                    <p className="text-[10px] opacity-50">Dokument analysiert</p>
                  </div>
                </div>
              )}
              {/* Generated image in AI message */}
              {m.sender==='ai' && m.imageData && (
                <div className="mb-2">
                  <img src={m.imageData} alt="Generiertes Bild" className="max-w-full max-h-80 rounded-lg border border-purple-500/30 shadow-lg shadow-purple-500/10 cursor-pointer" onClick={()=>setGalleryLightbox(m.imageData!)}/>
                  <div className="text-[10px] opacity-60 mt-1 flex items-center gap-2">
                    <span>🎨 Von Ailey generiert</span>
                    {(()=>{const fn=m.imageData!.split('/api/image/file/').pop()||'';return fn?(
                      <>
                        <button onClick={()=>{if(!confirm('Bild löschen?'))return;fetch(api(`/api/image/gallery/${encodeURIComponent(fn)}`,apiBaseRef),{method:'DELETE'}).then(r=>r.json()).then(j=>alert(j.success?'🗑️ Gelöscht':j.error||'Fehler'));}} className="px-1 py-0.5 rounded text-[9px] bg-red-500/10 text-red-400 hover:bg-red-500/20">🗑️</button>
                        <button onClick={()=>{fetch(api(`/api/image/gallery/hide/${encodeURIComponent(fn)}`,apiBaseRef),{method:'POST'}).then(r=>r.json()).then(j=>alert(j.success?'🔒 Versteckt':j.error||'Fehler'));}} className="px-1 py-0.5 rounded text-[9px] bg-amber-500/10 text-amber-400 hover:bg-amber-500/20">🔒</button>
                      </>
                    ):null;})()}
                  </div>
                </div>
              )}
              {/* Generated video in AI message */}
              {m.sender==='ai' && m.videoData && (
                <div className="mb-2">
                  <video src={m.videoData} controls autoPlay loop muted playsInline
                    className="max-w-full max-h-80 rounded-lg border border-cyan-500/30 shadow-lg shadow-cyan-500/10"/>
                  <div className="text-[10px] opacity-60 mt-1 flex items-center gap-2">
                    <span>🎬 Von Ailey generiert</span>
                    <a href={m.videoData} download className="px-1 py-0.5 rounded text-[9px] bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20">💾 Download</a>
                  </div>
                </div>
              )}
              {m.sender==='ai' ? renderContentWithCode(m.content) : <span className="whitespace-pre-wrap">{m.content}</span>}
              {/* 🎵 Song-Button panel (heuristic detected lyrics) */}
              {m.sender==='ai' && (m.songDetected?.is_song || m.songGen) && (
                <div className="mt-3">
                  {m.songGen?.status === 'done' && m.songGen.mp3Url ? (
                    <div className="p-2.5 rounded-lg bg-gradient-to-br from-purple-500/10 to-pink-500/5 border border-purple-500/30">
                      <div className="flex items-center gap-2 mb-2">
                        {m.songGen.coverUrl && <img src={m.songGen.coverUrl} alt="Cover" className="w-12 h-12 rounded object-cover flex-none"/>}
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-semibold truncate">🎵 {m.songGen.title || m.songDetected?.title || 'Song'}</div>
                          <div className="text-[10px] opacity-60">Auch in deiner Songs-Library gespeichert</div>
                        </div>
                      </div>
                      <audio controls preload="metadata" className="w-full h-9" src={m.songGen.mp3Url}/>
                      <div className="mt-1.5 flex gap-1.5">
                        <a href={m.songGen.mp3Url} download className="px-2 py-0.5 rounded text-[10px] bg-purple-500/20 text-purple-300 hover:bg-purple-500/30">💾 Download MP3</a>
                      </div>
                    </div>
                  ) : m.songGen && (m.songGen.status === 'running' || m.songGen.status === 'queued') ? (
                    <div className="p-2.5 rounded-lg bg-purple-500/5 border border-purple-500/20 text-[11px] flex items-center gap-2">
                      <span className="inline-block w-3 h-3 border-2 border-purple-500/30 border-t-purple-400 rounded-full animate-spin"/>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium">🎵 {m.songGen.title || 'Song'} wird generiert…</div>
                        <div className="opacity-65 truncate">{m.songGen.progress || 'Bitte warten – kann 2–5 min dauern.'}</div>
                      </div>
                    </div>
                  ) : m.songGen?.status === 'error' ? (
                    <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-[11px]">
                      <div className="text-red-300">❌ Song-Generierung fehlgeschlagen</div>
                      <div className="opacity-70 mt-0.5">{m.songGen.error || 'Unbekannter Fehler'}</div>
                      <button onClick={()=>openSongModalFor(m)} className="mt-1.5 px-2 py-0.5 rounded text-[10px] bg-purple-500/15 text-purple-300 hover:bg-purple-500/25">🔄 Nochmal versuchen</button>
                    </div>
                  ) : m.songDetected?.is_song ? (
                    <div className="p-2 rounded-lg bg-purple-500/5 border border-dashed border-purple-500/30 flex items-center gap-2 flex-wrap text-[11px]">
                      <span className="opacity-70">Sieht nach Songtext aus{m.songDetected.title ? ` ("${m.songDetected.title}")` : ''} 🎶</span>
                      {m.songDetected.needs_metadata ? (
                        <button onClick={()=>openSongModalFor(m)} className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 border border-purple-500/40 font-medium">🎵 Generieren (Optionen)</button>
                      ) : (
                        <>
                          <button onClick={()=>quickSongGen(m)} className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 border border-purple-500/40 font-medium">🎵 Direkt generieren</button>
                          <button onClick={()=>openSongModalFor(m)} className="px-2 py-0.5 rounded bg-zinc-500/15 text-zinc-300 hover:bg-zinc-500/25">⚙️ Optionen</button>
                        </>
                      )}
                    </div>
                  ) : null}
                </div>
              )}
              {/* TTS button on AI messages */}
              {m.sender==='ai' && m.content && m.content.length > 5 && (
                ttsBusy ? (
                  <button onClick={stopTTS} title="Stoppen" className="inline-flex items-center gap-1 mt-2 px-2 py-1 rounded text-[10px] text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors">
                    <Square className="h-3 w-3"/>Stopp
                  </button>
                ) : (
                  <button onClick={()=>speakText(m.content)} title="Vorlesen (TTS)" className="inline-flex items-center gap-1 mt-2 px-2 py-1 rounded text-[10px] text-muted-foreground hover:text-violet-400 hover:bg-violet-500/10 transition-colors">
                    <Volume2 className="h-3 w-3"/>Vorlesen
                  </button>
                )
              )}
              {m.sender==='ai'&&(m.autoResearch?.triggered||/Wissen erweitert/.test(m.content))&&<div className="mt-2 text-xs text-accent flex items-center gap-1"><Search className="h-3 w-3"/>Auto-Research</div>}
              {m.sender==='ai' && m.agentAuto && (
                <div className="mt-2 text-[10px] space-y-1 border-t border-border/30 pt-2">
                  <div className="font-semibold flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-accent/20 text-accent">Agent</span><span className="opacity-70">{m.agentAuto.action||'auto'}</span></div>
                  {Array.isArray(m.agentAuto.found) && m.agentAuto.found.length>0 && <div className="opacity-80">Gefunden: {m.agentAuto.found.slice(0,5).join(', ')}</div>}
                  {m.agentAuto.excerpt && <div className="opacity-80 line-clamp-4">{m.agentAuto.excerpt}</div>}
                  {m.agentAuto.file && <div className="opacity-60 font-mono truncate">{m.agentAuto.file}</div>}
                  {m.agentAuto.error && <div className="text-destructive">Agent Fehler: {m.agentAuto.error}</div>}
                  {m.agentAuto.count!==undefined && <div className="opacity-60">Anzahl: {m.agentAuto.count}</div>}
                  {m.agentAuto.chapter_number && <div className="opacity-60">Kapitel: {m.agentAuto.chapter_number}</div>}
                </div>
              )}
              {/* Email action panel */}
              {m.sender==='ai' && m.emailMessageId && !emailDrafts[m.emailMessageId]?.sent && !dismissedEmails.has(m.emailMessageId) && (
                <div className="mt-3 p-3 rounded-lg bg-sky-500/5 border border-sky-500/20 space-y-2">
                  {!emailDrafts[m.emailMessageId] ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <button onClick={()=>requestEmailDraft(m.emailMessageId!,'','simon')} className="text-[11px] px-3 py-1.5 rounded bg-sky-500/20 text-sky-300 hover:bg-sky-500/30 font-medium flex items-center gap-1">✉️ Antwort entwerfen (Simon)</button>
                      <button onClick={()=>requestEmailDraft(m.emailMessageId!,'','ailey')} className="text-[11px] px-3 py-1.5 rounded bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 font-medium flex items-center gap-1">✉️ Antwort als Ailey</button>
                      <button onClick={()=>dismissEmail(m.emailMessageId!)} className="text-[11px] px-3 py-1.5 rounded bg-zinc-500/20 text-zinc-400 hover:bg-zinc-500/30 font-medium flex items-center gap-1">🚫 Nicht beantworten</button>
                    </div>
                  ) : emailDrafts[m.emailMessageId].loading ? (
                    <div className="flex items-center gap-2 text-[11px] text-sky-300 animate-pulse">✍️ Entwurf wird erstellt…</div>
                  ) : emailDrafts[m.emailMessageId].error ? (
                    <div className="text-[11px] text-red-400">❌ {emailDrafts[m.emailMessageId].error}</div>
                  ) : (
                    <div className="space-y-2">
                      <div className="text-[11px] font-semibold text-sky-400">📝 Entwurf:</div>
                      <textarea
                        value={editingDraft[m.emailMessageId!]||''}
                        onChange={e=>setEditingDraft(prev=>({...prev,[m.emailMessageId!]:e.target.value}))}
                        className="w-full text-[11px] p-2 rounded border border-sky-500/20 bg-background/60 text-foreground leading-relaxed resize-y min-h-[80px]"
                        rows={5}
                        placeholder="Entwurf bearbeiten…"
                        aria-label="E-Mail-Entwurf bearbeiten"
                      />
                      <div className="flex items-center gap-2 flex-wrap">
                        <button onClick={()=>sendEmailDraft(m.emailMessageId!)} className="text-[11px] px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 font-medium">✅ Absenden</button>
                        <button onClick={()=>setRevisionOpen(prev=>({...prev,[m.emailMessageId!]:!prev[m.emailMessageId!]}))} className="text-[11px] px-3 py-1.5 rounded bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 font-medium">🔄 Umschreiben</button>
                        <button onClick={()=>discardEmailDraft(m.emailMessageId!)} className="text-[11px] px-2 py-1.5 text-muted-foreground hover:text-foreground">Verwerfen</button>
                      </div>
                      {revisionOpen[m.emailMessageId!] && (
                        <div className="flex items-center gap-2 mt-1">
                          <input
                            value={revisionInput[m.emailMessageId!]||''}
                            onChange={e=>setRevisionInput(prev=>({...prev,[m.emailMessageId!]:e.target.value}))}
                            onKeyDown={e=>{if(e.key==='Enter'&&(revisionInput[m.emailMessageId!]||'').trim()){requestEmailDraft(m.emailMessageId!,'',emailDrafts[m.emailMessageId!]?.replyAs||'simon',revisionInput[m.emailMessageId!])}}}
                            className="flex-1 text-[11px] px-2 py-1.5 rounded border border-amber-500/20 bg-background/60 text-foreground placeholder:text-muted-foreground"
                            placeholder="Anweisungen für Ailey, z.B. 'kürzer' oder 'freundlicher'…"
                            aria-label="Anweisungen zum Umschreiben"
                          />
                          <button
                            onClick={()=>{if((revisionInput[m.emailMessageId!]||'').trim()){requestEmailDraft(m.emailMessageId!,'',emailDrafts[m.emailMessageId!]?.replyAs||'simon',revisionInput[m.emailMessageId!])}}}
                            className="text-[11px] px-3 py-1.5 rounded bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 font-medium shrink-0"
                          >↻ Los</button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              {m.sender==='ai' && m.emailMessageId && emailDrafts[m.emailMessageId]?.sent && (
                <div className="mt-2 text-[11px] text-emerald-400 flex items-center gap-1">✅ Antwort gesendet</div>
              )}
              {m.sender==='ai' && m.emailMessageId && dismissedEmails.has(m.emailMessageId) && (
                <div className="mt-2 text-[11px] text-zinc-500 flex items-center gap-1">🚫 Nicht beantwortet</div>
              )}
              {/* Email compose panel (new emails) */}
              {m.sender==='ai' && m.composeId && composeDrafts[m.composeId] && !composeDrafts[m.composeId].sent && (
                <div className="mt-3 p-3 rounded-lg bg-violet-500/5 border border-violet-500/20 space-y-2">
                  {composeDrafts[m.composeId].loading ? (
                    <div className="flex items-center gap-2 text-[11px] text-violet-300 animate-pulse">📨 Wird gesendet…</div>
                  ) : composeDrafts[m.composeId].error ? (
                    <div className="text-[11px] text-red-400">❌ {composeDrafts[m.composeId].error}</div>
                  ) : (
                    <div className="space-y-2">
                      <div className="text-[11px] font-semibold text-violet-400">✏️ Betreff:</div>
                      <input
                        value={editingComposeSubject[m.composeId!]||''}
                        onChange={e=>setEditingComposeSubject(prev=>({...prev,[m.composeId!]:e.target.value}))}
                        className="w-full text-[11px] p-2 rounded border border-violet-500/20 bg-background/60 text-foreground"
                        placeholder="Betreff bearbeiten…"
                      />
                      <div className="text-[11px] font-semibold text-violet-400">📝 Text:</div>
                      <textarea
                        value={editingComposeBody[m.composeId!]||''}
                        onChange={e=>setEditingComposeBody(prev=>({...prev,[m.composeId!]:e.target.value}))}
                        className="w-full text-[11px] p-2 rounded border border-violet-500/20 bg-background/60 text-foreground leading-relaxed resize-y min-h-[80px]"
                        rows={6}
                        placeholder="E-Mail-Text bearbeiten…"
                        aria-label="E-Mail-Entwurf bearbeiten"
                      />
                      {/* Attachments */}
                      <div className="space-y-1">
                        <label className="text-[11px] text-violet-400 cursor-pointer inline-flex items-center gap-1 hover:text-violet-300">
                          📎 Anhang hinzufügen
                          <input type="file" multiple className="hidden" onChange={e=>{
                            const files = e.target.files; if(!files) return;
                            Array.from(files).forEach(f=>{
                              const reader = new FileReader();
                              reader.onload = ()=>{
                                const b64 = (reader.result as string).split(',')[1] || '';
                                setComposeAttachments(prev=>({...prev, [m.composeId!]: [...(prev[m.composeId!]||[]), {name:f.name, data:b64, mime:f.type||'application/octet-stream'}]}));
                              };
                              reader.readAsDataURL(f);
                            });
                            e.target.value = '';
                          }}/>
                        </label>
                        {(composeAttachments[m.composeId!]||[]).length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {(composeAttachments[m.composeId!]||[]).map((a,i)=>(
                              <span key={i} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/20">
                                📄 {a.name}
                                <button onClick={()=>setComposeAttachments(prev=>({...prev,[m.composeId!]:(prev[m.composeId!]||[]).filter((_,j)=>j!==i)}))} className="text-violet-400 hover:text-red-400 ml-0.5" title="Anhang entfernen">×</button>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <button onClick={()=>sendComposeDraft(m.composeId!)} className="text-[11px] px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 font-medium">✅ Absenden</button>
                        <button onClick={()=>setComposeRevisionOpen(prev=>({...prev,[m.composeId!]:!prev[m.composeId!]}))} className="text-[11px] px-3 py-1.5 rounded bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 font-medium">🔄 Umschreiben</button>
                        <button onClick={()=>discardComposeDraft(m.composeId!)} className="text-[11px] px-2 py-1.5 text-muted-foreground hover:text-foreground">Verwerfen</button>
                      </div>
                      {composeRevisionOpen[m.composeId!] && (
                        <div className="flex items-center gap-2 mt-1">
                          <input
                            value={composeRevisionInput[m.composeId!]||''}
                            onChange={e=>setComposeRevisionInput(prev=>({...prev,[m.composeId!]:e.target.value}))}
                            onKeyDown={e=>{if(e.key==='Enter'&&(composeRevisionInput[m.composeId!]||'').trim()){reviseComposeDraft(m.composeId!,composeRevisionInput[m.composeId!])}}}
                            className="flex-1 text-[11px] px-2 py-1.5 rounded border border-amber-500/20 bg-background/60 text-foreground placeholder:text-muted-foreground"
                            placeholder="Anweisungen für Ailey, z.B. 'kürzer' oder 'freundlicher'…"
                            aria-label="Anweisungen zum Umschreiben"
                          />
                          <button
                            onClick={()=>{if((composeRevisionInput[m.composeId!]||'').trim()){reviseComposeDraft(m.composeId!,composeRevisionInput[m.composeId!])}}}
                            className="text-[11px] px-3 py-1.5 rounded bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 font-medium shrink-0"
                          >↻ Los</button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              {m.sender==='ai' && m.composeId && composeDrafts[m.composeId]?.sent && (
                <div className="mt-2 text-[11px] text-emerald-400 flex items-center gap-1">✅ E-Mail gesendet</div>
              )}
              <div className={`flex items-center justify-between text-[10px] mt-2 opacity-70 ${m.sender==='user'?'text-primary-foreground/70':'text-muted-foreground'}`}>
                <span>{m.timestamp.toLocaleTimeString()}</span>
                {m.sender==='ai' && m.id!=='greet' && (
                  <button
                    onClick={()=>{ if(ratingOpen===m.id){ setRatingOpen(null); } else { setRatingOpen(m.id); setRatingDraft(m.rating ? {persona:m.rating.persona,quality:m.rating.quality,helpful:m.rating.helpful,creativity:m.rating.creativity,empathy:m.rating.empathy} : {}); setRatingComment(m.rating?.comment||''); setRatingMsg(null); }}}
                    className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors ${m.rating ? 'text-amber-400 bg-amber-400/10' : 'hover:text-amber-400 hover:bg-amber-400/10'}`}
                    title="Nachricht bewerten"
                  >
                    <Star className={`h-3 w-3 ${m.rating ? 'fill-amber-400' : ''}`}/>
                    {m.rating ? <span className="tabular-nums">{(Object.values(m.rating).filter(v=>typeof v==='number').reduce((a,b)=>a+b,0) / RATING_CATEGORIES.length).toFixed(1)}</span> : 'Bewerten'}
                  </button>
                )}
              </div>
              {/* Rating dropdown panel */}
              {m.sender==='ai' && ratingOpen===m.id && (
                <div className="mt-2 p-3 rounded-lg bg-amber-500/5 border border-amber-500/20 space-y-2 animate-in slide-in-from-top-2">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-400"><Star className="h-3.5 w-3.5 fill-amber-400"/>Bewertung</div>
                  <div className="grid grid-cols-1 gap-1.5">
                    {RATING_CATEGORIES.map(cat=>{
                      const val = ratingDraft[cat.key] || 5;
                      return (
                        <div key={cat.key} className="flex items-center gap-2 text-[11px]">
                          <span className="w-4 text-center">{cat.emoji}</span>
                          <span className="w-20 text-muted-foreground">{cat.label}</span>
                          <input
                            aria-label={cat.label}
                            type="range" min={1} max={10} value={val}
                            onChange={e=>setRatingDraft(prev=>({...prev, [cat.key]:parseInt(e.target.value)}))}
                            className="flex-1 h-1.5 accent-amber-400"
                          />
                          <span className={`w-6 text-right tabular-nums font-bold ${val>=8?'text-emerald-400':val>=5?'text-amber-400':'text-red-400'}`}>{val}</span>
                        </div>
                      );
                    })}
                  </div>
                  <input
                    placeholder="Kommentar (optional)…"
                    value={ratingComment}
                    onChange={e=>setRatingComment(e.target.value)}
                    className="w-full text-[11px] p-1.5 rounded border border-border/50 bg-background/50 placeholder:text-muted-foreground/50"
                  />
                  <div className="flex items-center gap-2">
                    <button onClick={()=>submitRating(m)} disabled={ratingSaving} className="text-[11px] px-3 py-1 rounded bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 disabled:opacity-50 font-medium">{ratingSaving?'Speichert…':'Speichern'}</button>
                    <button onClick={()=>{setRatingOpen(null);setRatingMsg(null);}} className="text-[11px] px-2 py-1 text-muted-foreground hover:text-foreground">Abbrechen</button>
                    {ratingMsg && <span className={`text-[10px] ${ratingMsg.startsWith('✓')?'text-emerald-400':'text-red-400'}`}>{ratingMsg}</span>}
                  </div>
                </div>
              )}
            </Card>
            {m.sender==='user' && <div className="w-8 h-8 rounded-full bg-secondary/10 flex items-center justify-center"><UserIcon className="h-4 w-4 text-secondary"/></div>}
          </div>
          </React.Fragment>
        ))}
        {streaming && <div className="flex gap-3"><div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center animate-pulse">⚡</div><Card className="p-4 bg-card border-accent/20 max-w-[80%] text-sm whitespace-pre-wrap">
          {thinkBuf && (
            <div className="mb-3">
              <div className="flex items-center gap-1.5 text-[11px] text-violet-400 font-medium mb-1"><Brain className="h-3.5 w-3.5 animate-pulse"/>Reasoning…</div>
              <div className="p-3 rounded-lg bg-violet-500/10 border border-violet-500/20 text-[11px] text-violet-200/80 leading-relaxed font-mono whitespace-pre-wrap max-h-[300px] overflow-y-auto">{thinkBuf}</div>
            </div>
          )}
          {!thinkBuf && !streamBuf && (
            <div className="flex items-center gap-1.5 text-[11px] text-violet-400 font-medium animate-pulse"><Brain className="h-3.5 w-3.5"/>Denkt nach…</div>
          )}
          {streamBuf ? renderContentWithCode(streamBuf) : (!thinkBuf?'...':'')}</Card></div>}
        {loading && <div className="flex gap-3"><div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center animate-pulse">🤔</div><Card className="p-4 bg-card border-accent/20 text-sm flex items-center gap-1"><span className="w-2 h-2 bg-accent rounded-full animate-bounce"/><span className="w-2 h-2 bg-accent rounded-full animate-bounce delay-100"/><span className="w-2 h-2 bg-accent rounded-full animate-bounce delay-200"/></Card></div>}
        {/* Quick-reply buttons: email account selection */}
        {pendingComposeCtx && !streaming && !loading && (
          <div className="flex gap-2 ml-11 mt-1 flex-wrap">
            {(pendingComposeCtx.accounts || ['ailey@sexngears.de']).map(acct => (
              <button key={acct} onClick={()=>{ setInput(acct); setTimeout(()=>{ const btn = document.querySelector('[data-send-btn]') as HTMLButtonElement; if(btn) btn.click(); }, 100); }}
                className={`text-[11px] px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                  acct.includes('ailey') ? 'bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 border-violet-500/20'
                  : 'bg-sky-500/20 text-sky-300 hover:bg-sky-500/30 border-sky-500/20'
                }`}>
                {acct.includes('ailey') ? '✉️' : '📮'} {acct}
              </button>
            ))}
          </div>
        )}
      </div>
      <div ref={endRef}/>
    </div>
  );};

  const HistorySection=()=> (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-6"><h2 className="text-4xl font-black">Verlauf</h2><Button size="sm" variant="outline" onClick={loadHistory} disabled={histLoading}>{histLoading?'Lädt…':'Aktualisieren'}</Button></div>
      <div className="grid md:grid-cols-2 gap-5">
        <div className="space-y-3">{history.slice().reverse().map(h=> <Card key={h.id} onClick={()=>loadHistoryDetail(h.id)} className={`p-4 cursor-pointer border text-xs ${histDetail?.id===h.id?'border-primary':'hover:border-primary/50'}`}><div className="flex items-center justify-between mb-1"><div className="font-mono truncate max-w-[70%]">{h.id}</div><span className="opacity-70">{new Date(h.timestamp*1000).toLocaleTimeString()}</span></div><div className="line-clamp-2 opacity-80">{h.message||'(leer)'}</div></Card>)}{history.length===0&&!histLoading&&<p className="text-xs text-muted-foreground">Noch keine Einträge.</p>}</div>
        <Card className="p-4 min-h-[320px] bg-card/40">{histDetailLoading&&<p className="text-sm opacity-70">Lade…</p>}{!histDetailLoading&&histDetail&&<div className="space-y-3 text-sm"><h3 className="font-semibold">Konversation</h3><div className="text-[10px] opacity-60 font-mono">{new Date((histDetail.timestamp||0)*1000).toLocaleString()} • {histDetail.user||'User'}</div><div><strong className="text-secondary">User:</strong><p className="whitespace-pre-wrap">{histDetail.message}</p></div><div><strong className="text-accent">A!ley:</strong><p className="whitespace-pre-wrap">{histDetail.ailey_reply}</p></div><Button size="sm" variant="outline" onClick={()=>setHistDetail(null)}>Schließen</Button></div>}{!histDetailLoading&&!histDetail&&<p className="text-sm text-muted-foreground">Wähle links einen Verlaufseintrag.</p>}</Card>
      </div>
    </div>
  );

  // ── Gallery Section ──────────────────────────────────────────────────────
  // Lazy-loading image component with error handling
  const LazyImage=({src,alt,className}:{src:string;alt:string;className?:string})=>{
    const ref=useRef<HTMLDivElement>(null);
    const [loaded,setLoaded]=useState(false);
    const [error,setError]=useState(false);
    const [inView,setInView]=useState(false);
    useEffect(()=>{
      if(!ref.current) return;
      const obs=new IntersectionObserver(([e])=>{if(e.isIntersecting){setInView(true);obs.disconnect();}},{rootMargin:'200px'});
      obs.observe(ref.current);
      return ()=>obs.disconnect();
    },[]);
    return (
      <div ref={ref} className="w-full h-full flex items-center justify-center">
        {inView ? (
          error ? <div className="text-xs text-muted-foreground/40 text-center p-2">⚠️ Bild nicht verfügbar</div>
          : <img src={src} alt={alt} className={`${className||''} transition-opacity duration-300 ${loaded?'opacity-100':'opacity-0'}`} onLoad={()=>setLoaded(true)} onError={()=>setError(true)} loading="lazy"/>
        ) : <div className="w-8 h-8 border-2 border-muted-foreground/20 border-t-primary rounded-full animate-spin"/>}
      </div>
    );
  };

  // Inline SVG thumbnail — fetches SVG content and renders inline (more reliable than <img> for SVGs in Tauri)
  const SvgThumbnail=({src,alt,className}:{src:string;alt:string;className?:string})=>{
    const ref=useRef<HTMLDivElement>(null);
    const [svgHtml,setSvgHtml]=useState<string|null>(null);
    const [error,setError]=useState(false);
    const [inView,setInView]=useState(false);
    useEffect(()=>{
      if(!ref.current) return;
      const obs=new IntersectionObserver(([e])=>{if(e.isIntersecting){setInView(true);obs.disconnect();}},{rootMargin:'200px'});
      obs.observe(ref.current);
      return ()=>obs.disconnect();
    },[]);
    useEffect(()=>{
      if(!inView) return;
      let cancelled=false;
      fetch(src).then(r=>{if(!r.ok) throw new Error('HTTP '+r.status); return r.text();})
        .then(text=>{if(!cancelled) setSvgHtml(text);})
        .catch(()=>{if(!cancelled) setError(true);});
      return ()=>{cancelled=true;};
    },[inView,src]);
    return (
      <div ref={ref} className={`w-full h-full flex items-center justify-center ${className||''}`}>
        {error ? <div className="text-xs text-muted-foreground/40 text-center p-2">⚠️ SVG nicht verfügbar</div>
        : svgHtml ? <div className="w-full h-full flex items-center justify-center [&>svg]:max-w-full [&>svg]:max-h-full [&>svg]:w-auto [&>svg]:h-auto" dangerouslySetInnerHTML={{__html:svgHtml}}/>
        : <div className="w-8 h-8 border-2 border-muted-foreground/20 border-t-primary rounded-full animate-spin"/>}
      </div>
    );
  };

  // ── Image Generation Tab ──────────────────────────────────────────────────
  // useMemo gives React a stable component identity so polling re-renders
  // don't unmount/remount the entire section (same pattern as LifeSimSection).
  // State lives INSIDE the stable component so it has its own fresh closure.
  const ImageGenSection = useMemo(() => function ImageGenSectionStable() {
    const [igSubTab, setIgSubTab] = useState<'generate'|'upscale'>('generate');
    const [igPrompt, setIgPrompt] = useState('');
    const [igAspect, setIgAspect] = useState('1:1');
    const [igSteps, setIgSteps] = useState(9);
    const [igRefImage, setIgRefImage] = useState<{data:string;preview:string;name:string}|null>(null);
    const [igStrength, setIgStrength] = useState(0.4);
    const [igBusy, setIgBusy] = useState(false);
    const [igProgress, setIgProgress] = useState('');
    const [igResult, setIgResult] = useState<{url:string;prompt:string}|null>(null);
    const [igError, setIgError] = useState('');
    const [igHistory, setIgHistory] = useState<{url:string;prompt:string;ar:string;ts:number}[]>([]);
    const [igMode, setIgMode] = useState<'direct'|'ailey'>('ailey');
    const [igSelfie, setIgSelfie] = useState(false);
    const [igNatural, setIgNatural] = useState(false);  // "Ungeschminkt" — no-makeup mode
    // LoRA selector state
    const [igLoras, setIgLoras] = useState<Record<string,{description:string;trigger:string;nsfw:boolean}>>({});
    const [igSelectedLoras, setIgSelectedLoras] = useState<string[]>([]);
    const igLorasLoaded = useRef(false);
    const igRefInputRef = useRef<HTMLInputElement>(null);
    const igPollRef = useRef<ReturnType<typeof setInterval>|null>(null);
    const igGalleryLoaded = useRef(false);

    // ── Upscale-Tab state ──
    const [upFile, setUpFile] = useState<{data:string;preview:string;name:string}|null>(null);
    const [upRes, setUpRes] = useState<'2x'|'3x'|'4x'>('2x');
    const [upSoftness, setUpSoftness] = useState(0.0);
    const [upBusy, setUpBusy] = useState(false);
    const [upProgress, setUpProgress] = useState('');
    const [upResult, setUpResult] = useState<{url:string;filename:string}|null>(null);
    const [upError, setUpError] = useState('');
    const [upDragOver, setUpDragOver] = useState(false);
    const upInputRef = useRef<HTMLInputElement>(null);
    const upPollRef = useRef<ReturnType<typeof setInterval>|null>(null);

    // Load recent images from gallery on mount (only once)
    useEffect(() => {
      if(igGalleryLoaded.current) return;
      igGalleryLoaded.current = true;
      (async()=>{
        try {
          const r = await fetch(api('/api/image/gallery?page=1&per_page=8', apiBaseRef));
          if(r.ok){ const j = await r.json(); if(j.success && j.gallery?.images){ setIgHistory(j.gallery.images.map((img:any)=>({url:`${apiBaseRef.current}/api/image/file/${img.filename}`,prompt:img.filename.replace(/^img_\d+_/,'').replace(/\.[^.]+$/,'').replace(/_/g,' '),ar:'1:1',ts:img.mtime}))); }}
        } catch{}
      })();
    }, []);

    // Load available LoRAs on mount
    useEffect(() => {
      if(igLorasLoaded.current) return;
      igLorasLoaded.current = true;
      (async()=>{
        try {
          const r = await fetch(api('/api/loras', apiBaseRef));
          if(r.ok){ const j = await r.json(); if(j.success && j.loras) setIgLoras(j.loras); }
        } catch{}
      })();
    }, []);

    const toggleLora = (id: string) => {
      setIgSelectedLoras(prev => {
        if(prev.includes(id)) return prev.filter(l => l !== id);
        if(prev.length >= 2) return prev; // max 2 simultaneous
        return [...prev, id];
      });
    };

    const handleRefImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if(!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const data = reader.result as string;
        setIgRefImage({data, preview: data, name: file.name});
      };
      reader.readAsDataURL(file);
    };

    const startGeneration = async () => {
      if(!igPrompt.trim() || igBusy) return;
      setIgBusy(true); setIgProgress('Starte…'); setIgResult(null); setIgError('');

      try {
        const body: any = {
          prompt: igPrompt, aspect_ratio: igAspect, steps: igSteps,
          image_strength: igStrength, async: true,
          direct: igMode === 'direct',
          ailey_selfie: igSelfie,
          natural_look: igNatural,
        };
        if(igSelectedLoras.length > 0) body.lora_ids = igSelectedLoras;
        if(igRefImage) body.image_data = igRefImage.data;

        const r = await fetch(api('/api/image/generate', apiBaseRef), {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify(body),
        });
        const j = await r.json();
        if(!j.success){ setIgError(j.error||'Fehler'); setIgBusy(false); return; }

        // Poll for progress
        setIgProgress('Übersetze Prompt…');
        igPollRef.current = setInterval(async () => {
          try {
            const sr = await fetch(api('/api/image/status', apiBaseRef));
            const sj = await sr.json();
            if(sj.progress) setIgProgress(sj.progress);
            if(sj.prompt_used) setIgProgress(prev => prev.includes('Prompt:') ? prev : `${sj.progress}\nPrompt: ${sj.prompt_used}`);
            if(!sj.active && sj.result) {
              if(igPollRef.current) clearInterval(igPollRef.current);
              igPollRef.current = null;
              if(sj.result.success) {
                const imgUrl = `${apiBaseRef.current}${sj.result.image_url}`;
                setIgResult({url: imgUrl, prompt: sj.result.prompt_used || igPrompt});
                setIgHistory(h => [{url:imgUrl,prompt:sj.result.prompt_used||igPrompt,ar:igAspect,ts:Date.now()/1000},...h].slice(0,20));
              } else {
                setIgError(sj.result.error || 'Generierung fehlgeschlagen');
              }
              setIgBusy(false); setIgProgress('');
            }
          } catch {}
        }, 3000);
      } catch(e:any) {
        setIgError(e?.message || 'Netzwerkfehler');
        setIgBusy(false); setIgProgress('');
      }
    };

    // Cleanup poll on unmount
    useEffect(() => () => {
      if(igPollRef.current) clearInterval(igPollRef.current);
      if(upPollRef.current) clearInterval(upPollRef.current);
    }, []);

    const aspects = [
      {v:'1:1', label:'1:1', desc:'Quadrat (1024×1024)'},
      {v:'16:9', label:'16:9', desc:'Breitbild (1024×576)'},
      {v:'9:16', label:'9:16', desc:'Hochformat (576×1024)'},
      {v:'4:3', label:'4:3', desc:'Standard (1024×768)'},
      {v:'3:4', label:'3:4', desc:'Hochformat (768×1024)'},
    ];

    // ── Upscale Upload handler ──
    const handleUpscaleFile = (file: File) => {
      if(!file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = () => {
        const data = reader.result as string;
        setUpFile({data, preview: data, name: file.name});
        setUpResult(null); setUpError('');
      };
      reader.readAsDataURL(file);
    };

    const startUpscaleUpload = async () => {
      if(!upFile || upBusy) return;
      setUpBusy(true); setUpProgress('Starte Upload-Upscale…'); setUpResult(null); setUpError('');
      try {
        const r = await fetch(api('/api/image/upscale/upload', apiBaseRef), {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            image_data: upFile.data,
            filename: upFile.name,
            resolution: upRes,
            softness: upSoftness,
          }),
        });
        const j = await r.json();
        if(!j.success){ setUpError(j.error||'Fehler'); setUpBusy(false); return; }

        // Poll for progress
        upPollRef.current = setInterval(async () => {
          try {
            const sr = await fetch(api('/api/image/upscale/status', apiBaseRef));
            const sj = await sr.json();
            if(sj.progress) setUpProgress(sj.progress);
            if(!sj.active && sj.result) {
              if(upPollRef.current) clearInterval(upPollRef.current);
              upPollRef.current = null;
              if(sj.result.success) {
                setUpResult({url: `${apiBaseRef.current}${sj.result.url}`, filename: sj.result.filename});
              } else {
                setUpError(sj.result.error || 'Upscaling fehlgeschlagen');
              }
              setUpBusy(false); setUpProgress('');
            }
          } catch {}
        }, 2000);
      } catch(e:any) {
        setUpError(e?.message || 'Netzwerkfehler');
        setUpBusy(false); setUpProgress('');
      }
    };

    return (
      <div className="max-w-4xl mx-auto px-4 py-10 space-y-6">
        <div className="flex items-center gap-3">
          <Paintbrush className="h-8 w-8 text-primary"/>
          <div>
            <h2 className="text-3xl font-black">Bildgenerierung</h2>
            <p className="text-sm text-muted-foreground">Aileys internes ImageGen Model</p>
          </div>
        </div>

        {/* Sub-Tab Switcher: Generieren | Upscale */}
        <div className="flex gap-2 p-1 bg-zinc-900/50 rounded-xl border border-border">
          <button onClick={()=>setIgSubTab('generate')}
            className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${igSubTab==='generate' ? 'bg-primary text-primary-foreground shadow-lg' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'}`}>
            🎨 Generieren
          </button>
          <button onClick={()=>setIgSubTab('upscale')}
            className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${igSubTab==='upscale' ? 'bg-purple-600 text-white shadow-lg' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'}`}>
            🔍 Upscale (Eigene Bilder)
          </button>
        </div>

        {/* ═══ GENERATE SUB-TAB ═══ */}
        {igSubTab === 'generate' && <>

        {/* Main controls */}
        <Card className="p-6 space-y-5">
          {/* Mode Toggle */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Modus</label>
            <div className="flex gap-2">
              <button onClick={()=>setIgMode('direct')} disabled={igBusy}
                className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all border ${igMode==='direct' ? 'bg-primary text-primary-foreground border-primary' : 'bg-zinc-800/50 text-zinc-400 border-border hover:bg-zinc-700/50'}`}>
                📤 Prompt abschicken
                <div className="text-[10px] opacity-70 mt-0.5">Dein Prompt wird direkt verwendet</div>
              </button>
              <button onClick={()=>setIgMode('ailey')} disabled={igBusy}
                className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all border ${igMode==='ailey' ? 'bg-primary text-primary-foreground border-primary' : 'bg-zinc-800/50 text-zinc-400 border-border hover:bg-zinc-700/50'}`}>
                💜 An Ailey weitergeben
                <div className="text-[10px] opacity-70 mt-0.5">Ailey übersetzt & optimiert den Prompt</div>
              </button>
            </div>
          </div>

          {/* Ailey Selfie Toggle */}
          <div className="flex items-center gap-3">
            <button onClick={()=>{
              const next = !igSelfie;
              setIgSelfie(next);
              if(!next) setIgNatural(false);  // reset natural when selfie off
              if(next && igAspect === '1:1') setIgAspect('3:4');
              if(!next && igAspect === '3:4') setIgAspect('1:1');
            }} disabled={igBusy}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${igSelfie ? 'bg-pink-500' : 'bg-zinc-700'}`}>
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${igSelfie ? 'translate-x-6' : 'translate-x-1'}`}/>
            </button>
            <div>
              <span className="text-sm font-medium">🤳 Ailey Selfie</span>
              <span className="text-[10px] text-muted-foreground ml-2">LoRA-Modell für Aileys Gesicht — kein Referenzbild nötig</span>
            </div>
          </div>

          {/* Ungeschminkt Toggle — only visible in Selfie mode */}
          {igSelfie && (
            <div className="flex items-center gap-3 ml-14">
              <button onClick={()=>setIgNatural(!igNatural)} disabled={igBusy}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${igNatural ? 'bg-emerald-500' : 'bg-zinc-700'}`}>
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${igNatural ? 'translate-x-6' : 'translate-x-1'}`}/>
              </button>
              <div>
                <span className="text-sm font-medium">🌿 Ungeschminkt</span>
                <span className="text-[10px] text-muted-foreground ml-2">Natürlicher Look ohne Eyeliner & Eyeshadow</span>
              </div>
            </div>
          )}

          {/* LoRA Selector */}
          {Object.keys(igLoras).length > 0 && (
            <div className="space-y-2">
              <label className="text-sm font-medium flex items-center gap-2">
                🎨 LoRA-Stile <span className="text-xs text-muted-foreground font-normal">(max. 2 gleichzeitig{igSelfie ? ', Ailey-LoRA zählt als 1' : ''})</span>
              </label>
              <div className="flex flex-wrap gap-2">
                {Object.entries(igLoras).map(([id, info]) => {
                  const selected = igSelectedLoras.includes(id);
                  const maxReached = !selected && igSelectedLoras.length >= 2;
                  return (
                    <button key={id} onClick={()=>toggleLora(id)} disabled={igBusy || (maxReached)}
                      className={`px-3 py-2 rounded-lg text-xs font-medium transition-all border ${selected ? 'bg-primary text-primary-foreground border-primary' : maxReached ? 'bg-zinc-900 text-zinc-600 border-border cursor-not-allowed' : 'bg-zinc-800 text-zinc-400 border-border hover:bg-zinc-700'}`}>
                      <div className="flex items-center gap-1.5">
                        {selected && <Check className="h-3 w-3"/>}
                        <span>{id === 'realism' ? '📷' : id === 'anime' ? '🎌' : id === 'anatomy' ? '🦴' : '✨'} {id.charAt(0).toUpperCase() + id.slice(1)}</span>
                      </div>
                      <div className="text-[10px] opacity-70 mt-0.5">{info.description}</div>
                    </button>
                  );
                })}
              </div>
              {igSelfie && igSelectedLoras.length >= 2 && (
                <p className="text-[10px] text-amber-400">⚠️ Im Selfie-Modus belegt Aileys LoRA 1 Slot — nur noch 1 zusätzliches LoRA möglich.</p>
              )}
            </div>
          )}

          {/* Prompt */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Bildbeschreibung</label>
            <textarea
              value={igPrompt} onChange={e=>setIgPrompt(e.target.value)}
              placeholder={igSelfie ? (igMode==='direct' ? 'Describe the scene, outfit, pose… (Ailey\'s face & hair are automatic)' : 'Beschreibe Szene, Outfit, Pose… (Aileys Gesicht & Haare werden automatisch ergänzt)') : (igMode==='direct' ? 'Describe the image you want to create… (English works best for direct mode)' : 'Beschreibe das Bild, das du erstellen möchtest… (jede Sprache, Ailey übersetzt automatisch)')}
              className="w-full h-24 bg-zinc-900 border border-border rounded-lg p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
              disabled={igBusy}
            />
          </div>

          {/* Aspect Ratio */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Seitenverhältnis</label>
            <div className="flex flex-wrap gap-2">
              {aspects.map(a => (
                <button key={a.v} onClick={()=>setIgAspect(a.v)} disabled={igBusy}
                  className={`px-3 py-2 rounded-lg text-xs font-medium transition-all ${igAspect===a.v ? 'bg-primary text-primary-foreground' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>
                  <div>{a.label}</div>
                  <div className="text-[10px] opacity-70">{a.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Steps */}
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-2">
              Inference Steps <span className="text-xs text-muted-foreground font-normal">({igSteps}) — Sweet Spot: 4-8, Max: 12</span>
            </label>
            <input type="range" min={4} max={12} value={igSteps} onChange={e=>setIgSteps(parseInt(e.target.value))}
              disabled={igBusy} className="w-full accent-primary"/>
          </div>

          {/* Reference Image (img2img) — hidden in selfie mode */}
          {!igSelfie && <div className="space-y-2">
            <label className="text-sm font-medium">Referenzbild (optional — img2img)</label>
            <div className="flex items-center gap-3">
              <input ref={igRefInputRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={handleRefImageSelect} className="hidden"/>
              <Button variant="outline" size="sm" onClick={()=>igRefInputRef.current?.click()} disabled={igBusy}>
                <Paperclip className="h-3.5 w-3.5 mr-1.5"/>Referenzbild wählen
              </Button>
              {igRefImage && (
                <div className="flex items-center gap-2 bg-zinc-800 rounded-lg p-2">
                  <img src={igRefImage.preview} alt="Ref" className="h-12 w-12 object-cover rounded"/>
                  <div>
                    <p className="text-xs truncate max-w-[150px]">{igRefImage.name}</p>
                    <p className="text-[10px] text-muted-foreground">Stärke: {(igStrength*100).toFixed(0)}%</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={()=>setIgRefImage(null)}><X className="h-3 w-3"/></Button>
                </div>
              )}
            </div>
            {igRefImage && (
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">
                  Referenz-Stärke: {(igStrength*100).toFixed(0)}% — Höher = näher am Original
                </label>
                <input type="range" min={0.1} max={0.9} step={0.05} value={igStrength}
                  onChange={e=>setIgStrength(parseFloat(e.target.value))} disabled={igBusy}
                  className="w-full accent-primary"/>
              </div>
            )}
          </div>}

          {/* Generate Button */}
          <div className="flex items-center gap-3">
            <Button onClick={startGeneration} disabled={igBusy || !igPrompt.trim()} className="gap-2 px-6 py-3 text-base">
              {igBusy ? <><Loader2 className="h-4 w-4 animate-spin"/>Generiere{igSelfie ? ' Selfie' : ''}…</> : igSelfie ? <><Paintbrush className="h-4 w-4"/>🤳 Ailey Selfie generieren</> : igMode==='direct' ? <><Paintbrush className="h-4 w-4"/>📤 Prompt abschicken</> : <><Paintbrush className="h-4 w-4"/>💜 An Ailey weitergeben</>}
            </Button>
            {igBusy && <span className="text-xs text-muted-foreground whitespace-pre-line">{igProgress}</span>}
          </div>

          {/* Error */}
          {igError && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">⚠️ {igError}</div>
          )}
        </Card>

        {/* Result */}
        {igResult && (
          <Card className="p-6 space-y-4">
            <h3 className="font-semibold flex items-center gap-2"><Check className="h-4 w-4 text-green-500"/>Generiertes Bild</h3>
            <div className="rounded-xl overflow-hidden border border-primary/30 shadow-lg shadow-primary/10">
              <img src={igResult.url} alt="Generated" className="w-full"/>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground"><span className="font-medium">Prompt:</span> {igResult.prompt}</p>
              <p className="text-xs text-muted-foreground"><span className="font-medium">Format:</span> {igAspect}</p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" size="sm" onClick={()=>window.open(igResult!.url, '_blank')}><Download className="h-3.5 w-3.5 mr-1"/>Herunterladen</Button>
              <Button variant="outline" size="sm" onClick={()=>{const fn=igResult!.url.split('/api/image/file/').pop()||'';if(!fn)return;fetch(api('/api/image/upscale',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:fn,resolution:'2x',async:true})}).then(r=>r.json()).then(j=>{if(j.success)alert('🔍 Upscale gestartet! Das Ergebnis erscheint in der Galerie.');else alert(j.error||'Fehler');});}} className="text-purple-400">🔍 Upscale 2×</Button>
              <Button variant="outline" size="sm" onClick={()=>{setActive('gallery');}}><ImageIcon className="h-3.5 w-3.5 mr-1"/>In Galerie ansehen</Button>
              <Button variant="outline" size="sm" onClick={()=>{const fn=igResult!.url.split('/api/image/file/').pop()||'';if(!fn)return;fetch(api(`/api/image/gallery/hide/${encodeURIComponent(fn)}`,apiBaseRef),{method:'POST'}).then(r=>r.json()).then(j=>alert(j.success?'🔒 In versteckte Galerie verschoben':j.error||'Fehler'));}} className="text-amber-400">🔒 Verstecken</Button>
              <Button variant="outline" size="sm" onClick={()=>{const fn=igResult!.url.split('/api/image/file/').pop()||'';if(!fn||!confirm('Bild wirklich löschen?'))return;fetch(api(`/api/image/gallery/${encodeURIComponent(fn)}`,apiBaseRef),{method:'DELETE'}).then(r=>r.json()).then(j=>{if(j.success){setIgResult(null);alert('🗑️ Gelöscht');}else alert(j.error||'Fehler');});}} className="text-red-400">🗑️ Löschen</Button>
            </div>
          </Card>
        )}

        {/* Recent Images */}
        {igHistory.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-semibold">Letzte Bilder</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {igHistory.map((img, i) => {
                // Extract filename from URL for API calls
                const fn = img.url.split('/api/image/file/').pop() || '';
                return (
                <Card key={i} className="p-2 hover:border-primary/60 transition-colors">
                  <div className="aspect-square bg-zinc-900 rounded-lg overflow-hidden mb-1.5 cursor-pointer" onClick={()=>window.open(img.url, '_blank')}>
                    <img src={img.url} alt={img.prompt} className="w-full h-full object-cover" loading="lazy"/>
                  </div>
                  <p className="text-[10px] opacity-60 truncate">{img.prompt}</p>
                  {fn && (
                    <div className="flex gap-1 mt-1">
                      <button onClick={(e)=>{e.stopPropagation();if(!confirm('Bild löschen?'))return;fetch(api(`/api/image/gallery/${encodeURIComponent(fn)}`,apiBaseRef),{method:'DELETE'}).then(r=>r.json()).then(j=>{if(j.success){setIgHistory(h=>h.filter((_,idx)=>idx!==i));alert('🗑️ Gelöscht');}});}} className="px-1.5 py-0.5 rounded text-[9px] bg-red-500/10 text-red-400 hover:bg-red-500/20">🗑️</button>
                      <button onClick={(e)=>{e.stopPropagation();fetch(api(`/api/image/gallery/push/${encodeURIComponent(fn)}`,apiBaseRef),{method:'POST'}).then(r=>r.json()).then(j=>alert(j.success?'🌐 Auf Portal hochgeladen!':j.error||'Fehler'));}} className="px-1.5 py-0.5 rounded text-[9px] bg-blue-500/10 text-blue-400 hover:bg-blue-500/20">🌐</button>
                      <button onClick={(e)=>{e.stopPropagation();fetch(api(`/api/image/gallery/hide/${encodeURIComponent(fn)}`,apiBaseRef),{method:'POST'}).then(r=>r.json()).then(j=>{if(j.success){setIgHistory(h=>h.filter((_,idx)=>idx!==i));alert('🔒 Versteckt');}});}} className="px-1.5 py-0.5 rounded text-[9px] bg-amber-500/10 text-amber-400 hover:bg-amber-500/20">🔒</button>
                    </div>
                  )}
                </Card>
                );
              })}
            </div>
          </div>
        )}

        </>}{/* end generate sub-tab */}

        {/* ═══ UPSCALE SUB-TAB ═══ */}
        {igSubTab === 'upscale' && <>

        <Card className="p-6 space-y-5">
          <div className="space-y-1">
            <h3 className="font-semibold text-lg flex items-center gap-2">🔍 Eigene Bilder upscalen</h3>
            <p className="text-sm text-muted-foreground">Lade ein beliebiges Bild hoch und upscale es mit SeedVR2 Diffusion Super-Resolution.</p>
          </div>

          {/* Drop Zone / File Picker */}
          <div
            onDragOver={(e)=>{e.preventDefault();e.stopPropagation();setUpDragOver(true);}}
            onDragLeave={(e)=>{e.preventDefault();e.stopPropagation();setUpDragOver(false);}}
            onDrop={(e)=>{e.preventDefault();e.stopPropagation();setUpDragOver(false);const f=e.dataTransfer.files?.[0];if(f)handleUpscaleFile(f);}}
            onClick={()=>upInputRef.current?.click()}
            className={`relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${upDragOver ? 'border-purple-500 bg-purple-500/10' : upFile ? 'border-primary/50 bg-zinc-800/30' : 'border-border hover:border-zinc-500 hover:bg-zinc-800/20'}`}
          >
            <input ref={upInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/tiff" onChange={(e)=>{const f=e.target.files?.[0];if(f)handleUpscaleFile(f);}} className="hidden"/>
            {upFile ? (
              <div className="flex flex-col items-center gap-3">
                <img src={upFile.preview} alt="Preview" className="max-h-48 rounded-lg border border-border shadow-lg"/>
                <div className="text-sm text-zinc-300">{upFile.name}</div>
                <button onClick={(e)=>{e.stopPropagation();setUpFile(null);setUpResult(null);setUpError('');}} className="text-xs text-red-400 hover:text-red-300">✕ Anderes Bild wählen</button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-zinc-500">
                <Upload className="h-10 w-10"/>
                <p className="text-sm font-medium">Bild hierher ziehen oder klicken</p>
                <p className="text-xs">PNG, JPEG, WebP, TIFF — max. 20 MB</p>
              </div>
            )}
          </div>

          {/* Resolution Selector */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Auflösung</label>
            <div className="flex gap-2">
              {(['2x','3x','4x'] as const).map(r => (
                <button key={r} onClick={()=>setUpRes(r)} disabled={upBusy}
                  className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all border ${upRes===r ? 'bg-purple-600 text-white border-purple-500 shadow-lg' : 'bg-zinc-800/50 text-zinc-400 border-border hover:bg-zinc-700/50'}`}>
                  <div className="text-lg font-bold">{r}</div>
                  <div className="text-[10px] opacity-70">{r==='2x' ? '~2048px' : r==='3x' ? '~3072px' : '~4096px'}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Softness Slider */}
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-2">
              Softness <span className="text-xs text-muted-foreground font-normal">({upSoftness.toFixed(1)}) — 0.0 = Scharf, 1.0 = Weich</span>
            </label>
            <input type="range" min={0} max={1} step={0.1} value={upSoftness} onChange={e=>setUpSoftness(parseFloat(e.target.value))}
              disabled={upBusy} className="w-full accent-purple-500"/>
          </div>

          {/* Start Button */}
          <div className="flex items-center gap-3">
            <Button onClick={startUpscaleUpload} disabled={upBusy || !upFile} className="gap-2 px-6 py-3 text-base bg-purple-600 hover:bg-purple-700">
              {upBusy ? <><Loader2 className="h-4 w-4 animate-spin"/>Upscale läuft…</> : <>🔍 Upscale starten</>}
            </Button>
            {upBusy && <span className="text-xs text-muted-foreground whitespace-pre-line">{upProgress}</span>}
          </div>

          {/* Error */}
          {upError && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">⚠️ {upError}</div>
          )}
        </Card>

        {/* Upscale Result */}
        {upResult && (
          <Card className="p-6 space-y-4">
            <h3 className="font-semibold flex items-center gap-2"><Check className="h-4 w-4 text-green-500"/>Upscale-Ergebnis</h3>
            <div className="rounded-xl overflow-hidden border border-purple-500/30 shadow-lg shadow-purple-500/10">
              <img src={upResult.url} alt="Upscaled" className="w-full"/>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground"><span className="font-medium">Datei:</span> {upResult.filename}</p>
              <p className="text-xs text-muted-foreground"><span className="font-medium">Auflösung:</span> {upRes}</p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" size="sm" onClick={()=>window.open(upResult!.url, '_blank')}><Download className="h-3.5 w-3.5 mr-1"/>Herunterladen</Button>
              <Button variant="outline" size="sm" onClick={()=>{setActive('gallery');}}><ImageIcon className="h-3.5 w-3.5 mr-1"/>In Galerie ansehen</Button>
            </div>
          </Card>
        )}

        {/* Info Box */}
        <Card className="p-4 border-purple-500/20 bg-purple-500/5">
          <div className="flex items-start gap-3">
            <div className="text-2xl">💡</div>
            <div className="space-y-1 text-sm text-zinc-400">
              <p className="font-medium text-zinc-300">Was macht SeedVR2?</p>
              <p>SeedVR2 ist ein Diffusion-basierter Super-Resolution Upscaler (3B Parameter). Anders als klassische Upscaler (Lanczos, ESRGAN) generiert SeedVR2 neue, plausible Details — ähnlich wie ein Bildgenerator, der das vorhandene Bild als Vorlage nutzt.</p>
              <p className="text-xs text-zinc-500 mt-2">⏱ Dauer: ~2-8 Min je nach Auflösung • Ailey ist während des Upscalings offline</p>
            </div>
          </div>
        </Card>

        </>}{/* end upscale sub-tab */}

      </div>
    );
  }, []);  // end useMemo for ImageGenSection

  // ── Video Generation Tab ──────────────────────────────────────────────────
  const VideoGenSection = useMemo(() => function VideoGenSectionStable() {
    const [vgPrompt, setVgPrompt] = useState('');
    const [vgBusy, setVgBusy] = useState(false);
    const [vgProgress, setVgProgress] = useState('');
    const [vgResult, setVgResult] = useState<{url:string;prompt:string}|null>(null);
    const [vgError, setVgError] = useState('');
    const [vgConfirmed, setVgConfirmed] = useState(false);
    const vgPollRef = useRef<ReturnType<typeof setInterval>|null>(null);

    const startVideoGen = async () => {
      if(!vgPrompt.trim() || vgBusy) return;
      setVgBusy(true); setVgError(''); setVgResult(null); setVgProgress('⏳ Video wird generiert… Ailey ist während der Generierung offline.\nDas kann 15-60 Minuten dauern. Ernsthaft.');
      try {
        // Poll status endpoint
        vgPollRef.current = setInterval(async()=>{
          try {
            const sr = await fetch(api('/api/video/status', apiBaseRef));
            const sj = await sr.json();
            if(sj.active) setVgProgress(`⏳ ${sj.progress || 'Generiere…'}`);
          } catch{}
        }, 10000);

        const r = await fetch(api('/api/video/generate', apiBaseRef), {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({prompt:vgPrompt, private:true})
        });
        const j = await r.json();
        if(j.success && j.video_url) {
          setVgResult({url:`${apiBaseRef.current}${j.video_url}`, prompt:vgPrompt});
          setVgProgress('');
        } else {
          setVgError(j.error || 'Videogenerierung fehlgeschlagen');
          setVgProgress('');
        }
      } catch(e:any) {
        setVgError(e?.message || 'Netzwerkfehler');
        setVgProgress('');
      } finally {
        setVgBusy(false);
        setVgConfirmed(false);
        if(vgPollRef.current) { clearInterval(vgPollRef.current); vgPollRef.current=null; }
      }
    };

    return (
      <div className="max-w-4xl mx-auto px-4 py-10 space-y-6">
        <div className="flex items-center gap-3">
          <Film className="h-8 w-8 text-cyan-400"/>
          <div>
            <h2 className="text-3xl font-black">Videogenerierung</h2>
            <p className="text-sm text-muted-foreground">Wan 2.1 T2V — Lokal auf deinem Mac (experimentell)</p>
          </div>
        </div>

        {/* Honest Warning Card */}
        <Card className="p-5 border-amber-500/30 bg-amber-500/5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-6 w-6 text-amber-400 shrink-0 mt-0.5"/>
            <div className="space-y-2">
              <h3 className="font-bold text-amber-300">⚠️ Ehrliche Warnung</h3>
              <ul className="text-sm text-amber-200/80 space-y-1 list-disc list-inside">
                <li><strong>15-60 Minuten</strong> Generierungszeit je nach Einstellungen</li>
                <li><strong>Ailey ist komplett offline</strong> während der Generierung</li>
                <li><strong>MacBook wird heiß</strong> — nicht auf dem Schoß lassen!</li>
                <li><strong>~50% Akku</strong> bei vollem Durchlauf — am besten am Strom</li>
                <li>Ergebnis: <strong>~2 Sekunden</strong> Video-Clip in 480p</li>
              </ul>
              <p className="text-xs text-amber-200/50 italic mt-2">Dies ist ein experimentelles Feature. Für Produktionsvideos empfehlen wir Cloud-APIs.</p>
            </div>
          </div>
        </Card>

        {/* Controls */}
        <Card className="p-6 space-y-5">
          <div className="space-y-2">
            <label className="text-sm font-medium">Was soll im Video passieren?</label>
            <textarea
              value={vgPrompt} onChange={e=>setVgPrompt(e.target.value)}
              placeholder="Beschreibe die Szene… z.B. 'Ein golden retriever rennt über eine Blumenwiese im Sonnenuntergang'"
              className="w-full h-24 bg-zinc-900 border border-border rounded-lg p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
              disabled={vgBusy}
            />
            <p className="text-[10px] text-muted-foreground">Ailey übersetzt deinen Prompt automatisch ins Englische und optimiert ihn für Wan 2.1.</p>
          </div>

          {/* Confirmation Gate */}
          {!vgConfirmed && !vgBusy && (
            <div className="space-y-3">
              <Button onClick={()=>setVgConfirmed(true)} disabled={!vgPrompt.trim()} variant="outline" className="gap-2 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/10">
                <Film className="h-4 w-4"/>🎬 Video generieren
              </Button>
            </div>
          )}

          {/* THE LEGENDARY CONFIRMATION */}
          {vgConfirmed && !vgBusy && (
            <Card className="p-5 border-red-500/40 bg-red-500/5 space-y-4">
              <div className="text-center space-y-2">
                <p className="text-lg font-bold text-red-300">🔥 Bist du sicher, dass du dir den Arsch abwarten willst?</p>
                <p className="text-sm text-muted-foreground">Dein MacBook wird zur Herdplatte, Ailey geht offline, und am Ende gibt&apos;s 2 Sekunden Video.</p>
              </div>
              <div className="flex justify-center gap-3">
                <Button onClick={()=>{setVgConfirmed(false);}} variant="outline" className="border-zinc-600">
                  ❌ Nein, lieber nicht
                </Button>
                <Button onClick={startVideoGen} variant="outline" className="border-amber-500/50 text-amber-300 hover:bg-amber-500/10">
                  ✅ Ja, ich warte
                </Button>
                <Button onClick={startVideoGen} className="bg-red-600 hover:bg-red-700 text-white font-bold">
                  🤙 Cowabunga!
                </Button>
              </div>
            </Card>
          )}

          {/* Progress */}
          {vgBusy && (
            <div className="flex items-center gap-3 p-4 rounded-lg bg-cyan-500/5 border border-cyan-500/20">
              <Loader2 className="h-5 w-5 animate-spin text-cyan-400"/>
              <span className="text-sm whitespace-pre-line">{vgProgress}</span>
            </div>
          )}

          {/* Error */}
          {vgError && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">⚠️ {vgError}</div>
          )}
        </Card>

        {/* Result */}
        {vgResult && (
          <Card className="p-6 space-y-4">
            <h3 className="font-semibold flex items-center gap-2"><Check className="h-4 w-4 text-green-500"/>Generiertes Video</h3>
            <div className="rounded-xl overflow-hidden border border-cyan-500/30 shadow-lg shadow-cyan-500/10">
              <video src={vgResult.url} controls autoPlay loop playsInline className="w-full"/>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground"><span className="font-medium">Prompt:</span> {vgResult.prompt}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={()=>window.open(vgResult!.url, '_blank')}><Download className="h-3.5 w-3.5 mr-1"/>Herunterladen</Button>
            </div>
          </Card>
        )}
      </div>
    );
  }, []);  // end useMemo for VideoGenSection

  const galleryLoadedRef = useRef(false);

  // Load gallery data once when gallery tab first opens
  useEffect(() => {
    if (active !== 'gallery') return;
    if (galleryLoadedRef.current) return;
    galleryLoadedRef.current = true;
    if(gallerySvgs.length===0) loadGallery(1);
    if(galleryImages.length===0) loadImageGallery(1);
    if(galleryCodeItems.length===0) loadCodeGallery();
    if(songs.length===0) loadSongs();
    if(albums.length===0) loadAlbums();
  }, [active]);

  // Plain render function — no hooks, so it's safe to call conditionally
  // and always reads fresh parent state (no stale closure).
  const renderGallerySection = () => {
    const refreshAll=()=>{ loadGallery(1); loadImageGallery(1); loadCodeGallery(); loadSongs(); };
    const isLoading = galleryLoading || galleryImagesLoading || galleryCodeLoading || songsLoading;

    const PaginationBar=({page,totalPages,total,onPage,loading:ld}:{page:number;totalPages:number;total:number;onPage:(p:number)=>void;loading:boolean})=> totalPages>1?(
      <div className="flex items-center justify-center gap-2 pt-4">
        <Button size="sm" variant="outline" disabled={page<=1||ld} onClick={()=>onPage(page-1)}><ChevronLeft className="h-3.5 w-3.5"/></Button>
        <span className="text-xs tabular-nums">Seite {page}/{totalPages} ({total} gesamt)</span>
        <Button size="sm" variant="outline" disabled={page>=totalPages||ld} onClick={()=>onPage(page+1)}><ChevronRight className="h-3.5 w-3.5"/></Button>
      </div>
    ):null;

    return (
      <div className="max-w-5xl mx-auto px-4 py-10 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-4xl font-black">Gallery</h2>
          <Button size="sm" variant="outline" onClick={refreshAll} disabled={isLoading}>{isLoading?'lädt…':'Aktualisieren'}</Button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          <button onClick={()=>setGalleryTab('images')} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${galleryTab==='images'?'bg-primary text-primary-foreground':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>🎨 Bilder ({galleryImgTotal||galleryImages.length})</button>
          <button onClick={()=>setGalleryTab('svg')} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${galleryTab==='svg'?'bg-primary text-primary-foreground':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>✏️ SVG ({gallerySvgTotal||gallerySvgs.length})</button>
          <button onClick={()=>setGalleryTab('music')} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${galleryTab==='music'?'bg-primary text-primary-foreground':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>🎵 Musik ({songs.filter(s=>s.has_mp3).length}/{songs.length})</button>
          <button onClick={()=>setGalleryTab('code')} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${galleryTab==='code'?'bg-primary text-primary-foreground':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>💻 Code ({galleryCodeItems.length})</button>
        </div>

        {/* Image Gallery Tab */}
        {galleryTab==='images' && (<>
          <p className="text-sm text-muted-foreground">KI-generierte Bilder von Ailey (AileyImage / MFLUX). Sie erstellt eigenständig max. 2 Bilder pro Tag.</p>
          {galleryActionMsg && <div className="text-center text-xs text-primary animate-pulse">{galleryActionMsg}</div>}
          {galleryImages.length === 0 && !galleryImagesLoading && (
            <Card className="p-10 text-center">
              <ImageIcon className="h-12 w-12 mx-auto text-muted-foreground/40 mb-3"/>
              <p className="text-sm text-muted-foreground">Noch keine KI-Bilder. Ailey generiert automatisch Bilder wenn sie idle ist.</p>
            </Card>
          )}
          {galleryImagesLoading && <div className="flex justify-center py-8"><Loader2 className="h-8 w-8 animate-spin text-primary"/></div>}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {galleryImages.map(img => (
              <Card key={img.filename} className="p-3 group hover:border-primary/60 transition-colors duration-200 relative">
                {(img as any).upscaled && <span className="absolute top-1 right-1 z-10 px-1 py-0.5 rounded text-[8px] font-bold bg-purple-500/80 text-white">UP</span>}
                <div className="aspect-square bg-white/5 rounded-lg overflow-hidden flex items-center justify-center mb-2 cursor-pointer" onClick={()=>setGalleryLightbox(`${apiBaseRef.current}/api/image/file/${img.filename}`)}>
                  <LazyImage src={`${apiBaseRef.current}/api/image/file/${img.filename}`} alt={img.filename} className="max-w-full max-h-full object-cover rounded-lg"/>
                </div>
                <div className="text-[10px] opacity-60 truncate">{img.filename.replace(/^img_\d+_/, '').replace(/\.[^.]+$/, '').replace(/_/g, ' ')}</div>
                <div className="text-[10px] opacity-40">{new Date(img.mtime * 1000).toLocaleDateString()}{(img as any).upscaled ? ' · 🔍 Upscaled' : ''}</div>
                {/* Action buttons — always visible (touch-friendly) */}
                <div className="flex gap-1 mt-1.5">
                  {galleryConfirmDelete===img.filename ? (
                    <div className="flex items-center gap-1 w-full">
                      <span className="text-[9px] text-red-400">Sicher?</span>
                      <button onClick={()=>galleryDeleteImage(img.filename)} disabled={galleryActionBusy===img.filename} className="px-1.5 py-0.5 rounded text-[9px] bg-red-500/20 text-red-400 hover:bg-red-500/40">Ja</button>
                      <button onClick={()=>setGalleryConfirmDelete(null)} className="px-1.5 py-0.5 rounded text-[9px] bg-muted hover:bg-muted/80">Nein</button>
                    </div>
                  ) : (
                    <>
                      <button onClick={(e)=>{e.stopPropagation();setGalleryConfirmDelete(img.filename);}} title="Löschen" className="px-1.5 py-0.5 rounded text-[9px] bg-red-500/10 text-red-400 hover:bg-red-500/20">🗑️</button>
                      <button onClick={(e)=>{e.stopPropagation();galleryUpscaleImage(img.filename);}} title="Upscale (SeedVR2)" disabled={upscaleBusy||galleryActionBusy===img.filename} className="px-1.5 py-0.5 rounded text-[9px] bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 disabled:opacity-40">🔍</button>
                      <button onClick={(e)=>{e.stopPropagation();galleryPushToPortal(img.filename);}} title="Zum Portal pushen" disabled={galleryActionBusy===img.filename} className="px-1.5 py-0.5 rounded text-[9px] bg-blue-500/10 text-blue-400 hover:bg-blue-500/20">🌐</button>
                      <button onClick={(e)=>{e.stopPropagation();galleryHideImage(img.filename);}} title="Verstecken" disabled={galleryActionBusy===img.filename} className="px-1.5 py-0.5 rounded text-[9px] bg-amber-500/10 text-amber-400 hover:bg-amber-500/20">🔒</button>
                    </>
                  )}
                </div>
              </Card>
            ))}
          </div>
          <PaginationBar page={galleryImgPage} totalPages={galleryImgTotalPages} total={galleryImgTotal} loading={galleryImagesLoading} onPage={p=>loadImageGallery(p)}/>

          {/* Hidden Gallery Toggle */}
          <div className="pt-4 border-t border-border/30">
            <button onClick={()=>setGalleryShowHidden(v=>!v)} className="text-xs text-muted-foreground hover:text-primary transition flex items-center gap-1.5">
              🔒 Versteckte Galerie {galleryShowHidden?'ausblenden':'anzeigen'}
            </button>
            {galleryShowHidden && !galleryHiddenUnlocked && (
              <div className="flex items-center gap-2 mt-2">
                <input type="password" value={galleryHiddenPassword} onChange={e=>setGalleryHiddenPassword(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')loadHiddenGallery();}} placeholder="Passwort…" className="px-2 py-1 rounded border border-border bg-background text-xs w-40"/>
                <button onClick={loadHiddenGallery} disabled={galleryHiddenLoading} className="px-3 py-1 rounded text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition">
                  {galleryHiddenLoading?'…':'Entsperren'}
                </button>
                {galleryHiddenError && <span className="text-[10px] text-red-400">{galleryHiddenError}</span>}
              </div>
            )}
            {galleryShowHidden && galleryHiddenUnlocked && (
              <div className="mt-3">
                <p className="text-[11px] text-muted-foreground mb-2">{galleryHiddenImages.length} versteckte Bilder</p>
                {galleryHiddenImages.length===0 && <p className="text-[10px] text-muted-foreground/60">Keine versteckten Bilder.</p>}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                  {galleryHiddenImages.map(img=>(
                    <Card key={img.filename} className="p-2 group hover:border-primary/60 transition-colors relative">
                      <div className="aspect-square bg-white/5 rounded-lg overflow-hidden flex items-center justify-center mb-1 cursor-pointer" onClick={()=>setGalleryLightbox(`${apiBaseRef.current}/api/image/file/${img.filename}`)}>
                        <LazyImage src={`${apiBaseRef.current}/api/image/file/${img.filename}`} alt={img.filename} className="max-w-full max-h-full object-cover rounded-lg"/>
                      </div>
                      <div className="text-[9px] opacity-50 truncate">{img.filename.replace(/^img_\d+_/, '').replace(/\.[^.]+$/, '').replace(/_/g, ' ')}</div>
                      <div className="flex gap-1 mt-1">
                        <button onClick={()=>galleryUnhideImage(img.filename)} title="Wiederherstellen" disabled={galleryActionBusy===img.filename} className="px-1.5 py-0.5 rounded text-[9px] bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20">🔓 Zeigen</button>
                        <button onClick={()=>galleryDeleteImage(img.filename)} title="Löschen" disabled={galleryActionBusy===img.filename} className="px-1.5 py-0.5 rounded text-[9px] bg-red-500/10 text-red-400 hover:bg-red-500/20">🗑️</button>
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>)}

        {/* SVG Gallery Tab */}
        {galleryTab==='svg' && (<>
          <p className="text-sm text-muted-foreground">SVG-Kunstwerke von Ailey. Bitte sie im Chat, etwas zu zeichnen!</p>
          {gallerySvgs.length === 0 && !galleryLoading && (
            <Card className="p-10 text-center">
              <ImageIcon className="h-12 w-12 mx-auto text-muted-foreground/40 mb-3"/>
              <p className="text-sm text-muted-foreground">Noch keine SVGs. Sag Ailey im Chat z.B. &quot;Zeichne mir eine Katze&quot;!</p>
            </Card>
          )}
          {galleryLoading && <div className="flex justify-center py-8"><Loader2 className="h-8 w-8 animate-spin text-primary"/></div>}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {gallerySvgs.map(svg => (
              <Card key={svg.filename} onClick={()=>loadSvgContent(svg.filename)}
                className={`p-3 cursor-pointer hover:border-primary/60 transition-colors duration-200 group ${gallerySelected===svg.filename?'border-primary ring-1 ring-primary/30':''}`}>
                <div className="aspect-square bg-white/5 rounded-lg overflow-hidden flex items-center justify-center mb-2">
                  <SvgThumbnail src={`${apiBaseRef.current}/api/svg/file/${svg.filename}`} alt={svg.filename} className="max-w-full max-h-full object-contain"/>
                </div>
                <div className="text-[10px] opacity-60 truncate">{svg.filename}</div>
                <div className="text-[10px] opacity-40">{new Date(svg.mtime * 1000).toLocaleDateString()}</div>
              </Card>
            ))}
          </div>
          <PaginationBar page={gallerySvgPage} totalPages={gallerySvgTotalPages} total={gallerySvgTotal} loading={galleryLoading} onPage={p=>loadGallery(p)}/>
          {gallerySelected && gallerySvgContent && (
            <Card className="p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm">{gallerySelected}</h3>
                <Button size="sm" variant="outline" onClick={()=>{setGallerySelected(null);setGallerySvgContent(null);}}>Schließen</Button>
              </div>
              <div className="bg-white rounded-lg p-6 flex items-center justify-center min-h-[300px] overflow-hidden [&>svg]:max-w-full [&>svg]:max-h-[500px] [&>svg]:w-auto [&>svg]:h-auto" dangerouslySetInnerHTML={{__html: gallerySvgContent}}/>
            </Card>
          )}
        </>)}

        {/* Music Gallery Tab */}
        {galleryTab==='music' && (<>
          <p className="text-sm text-muted-foreground">Aileys Musik — Songs mit Audio abspielen, oder Audio für Lyrics generieren lassen.</p>
          {/* Song Search */}
          {(songs.length > 0 || albums.length > 0) && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground"/>
              <input
                type="text"
                placeholder="Songs durchsuchen (Titel, Genre, Emotion)..."
                value={songSearch}
                onChange={e=>setSongSearch(e.target.value)}
                className="w-full pl-9 pr-8 py-2 rounded-lg bg-zinc-800/60 border border-zinc-700/50 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-pink-500/40 transition"
              />
              {songSearch && (
                <button onClick={()=>setSongSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition">
                  <X className="h-4 w-4"/>
                </button>
              )}
            </div>
          )}
          {songs.length === 0 && albums.length === 0 && !songsLoading && !albumsLoading && (
            <Card className="p-10 text-center">
              <Music className="h-12 w-12 mx-auto text-muted-foreground/40 mb-3"/>
              <p className="text-sm text-muted-foreground">Noch keine Songs. Ailey schreibt Songs wenn sie idle ist.</p>
            </Card>
          )}
          {(songsLoading || albumsLoading) && <div className="flex justify-center py-8"><Loader2 className="h-8 w-8 animate-spin text-primary"/></div>}

          {/* Album-grouped view */}
          {(()=>{
            const q=songSearch.toLowerCase().trim();

            // ── Helper: render a song card (used in both album + standalone sections) ──
            const SongCard=({s,albumSlug}:{s:any;albumSlug?:string})=>(
              <div key={s.id} className="group rounded-xl overflow-hidden border border-zinc-700/50 hover:border-pink-500/40 transition-all hover:shadow-lg hover:shadow-pink-500/5 bg-card/60">
                <div className="aspect-square bg-gradient-to-br from-pink-500/10 to-violet-500/10 relative overflow-hidden">
                  {s.has_cover ? (
                    <img src={api(`/api/songs/${s.id}/cover`,apiBaseRef)} alt={s.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"/>
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-pink-400/30"><Music className="h-10 w-10"/></div>
                  )}
                  {s.has_mp3 && (
                    <button onClick={()=>playSong(s.id)}
                      className="absolute bottom-2 right-2 w-10 h-10 rounded-full bg-pink-500 text-white flex items-center justify-center opacity-80 group-hover:opacity-100 transition-opacity shadow-lg hover:scale-110">
                      {songPlaying===s.id ? <Pause className="h-4 w-4"/> : <Play className="h-4 w-4 ml-0.5"/>}
                    </button>
                  )}
                </div>
                <div className="p-2.5">
                  <p className="text-sm font-medium truncate">{s.title}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">{(s.dt||s.created_at||'').split(' ')[0]||''}</p>
                  {(s.emotion||s.mood) && <span className="text-[10px] px-1.5 py-0.5 rounded bg-pink-500/10 text-pink-300 border border-pink-500/20 mt-1 inline-block">{s.emotion||s.mood}</span>}
                  {!s.has_mp3 && (
                    <button onClick={()=>generateAudioForSong(s)} disabled={_music_gen_job_active}
                      className="mt-1.5 w-full px-2 py-1 rounded text-[10px] bg-pink-500/15 text-pink-400 hover:bg-pink-500/25 border border-pink-500/20 transition disabled:opacity-40 text-center">
                      {_music_gen_job_active ? '⏳' : '🎵 Audio'}
                    </button>
                  )}
                </div>
              </div>
            );

            // ── Albums section ──
            const albumsFiltered = q
              ? albums.filter(a =>
                  a.title.toLowerCase().includes(q) ||
                  (a.concept||'').toLowerCase().includes(q) ||
                  a.songs.some(s => s.title.toLowerCase().includes(q) || (s.genre||'').toLowerCase().includes(q))
                )
              : albums;

            // ── Standalone songs (not in any album) ──
            // Use albumsNoAlbum if loaded, otherwise fall back to songs without album_slug
            const standaloneSongs = albumsNoAlbum.length > 0
              ? (q ? albumsNoAlbum.filter(s => s.title.toLowerCase().includes(q) || (s.genre||'').toLowerCase().includes(q)) : albumsNoAlbum)
              : (q ? songs.filter(s => (s.title||'').toLowerCase().includes(q)||(s.genre||'').toLowerCase().includes(q)||(s.emotion||'').toLowerCase().includes(q)) : songs);

            const totalFiltered = albumsFiltered.reduce((n,a)=>n+a.songs.length,0) + standaloneSongs.length;

            return (<>
              {q && <p className="text-xs text-muted-foreground">{totalFiltered} Songs gefunden</p>}

              {/* Albums */}
              {albumsFiltered.map(album => {
                const albumSongs = q
                  ? album.songs.filter(s => s.title.toLowerCase().includes(q) || (s.genre||'').toLowerCase().includes(q))
                  : album.songs;
                if (albumSongs.length === 0) return null;
                return (
                  <div key={album.slug} className="space-y-3">
                    {/* Album header */}
                    <div className="flex items-center gap-3 p-3 rounded-xl bg-zinc-800/40 border border-zinc-700/40">
                      <div className="w-14 h-14 rounded-lg overflow-hidden bg-gradient-to-br from-violet-500/20 to-pink-500/20 shrink-0 flex items-center justify-center">
                        {album.has_cover
                          ? <img src={api(`/api/albums/${album.slug}/cover`,apiBaseRef)} alt={album.title} className="w-full h-full object-cover"/>
                          : albumSongs.find(s=>s.has_cover)
                            ? <img src={api(`/api/songs/${albumSongs.find(s=>s.has_cover)!.id}/cover`,apiBaseRef)} alt={album.title} className="w-full h-full object-cover"/>
                            : <Music className="h-6 w-6 text-violet-400/50"/>
                        }
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="font-semibold text-sm text-violet-300 truncate">💿 {album.title}</h3>
                        {album.concept && <p className="text-[10px] text-muted-foreground line-clamp-1 mt-0.5">{album.concept}</p>}
                        <p className="text-[10px] text-muted-foreground mt-0.5">
                          {album.mp3_count}/{albumSongs.length} mit Audio · {album.status}
                        </p>
                      </div>
                    </div>
                    {/* Songs in album */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 pl-2">
                      {albumSongs.map(s=><SongCard key={s.id} s={s} albumSlug={album.slug}/>)}
                    </div>
                  </div>
                );
              })}

              {/* Standalone songs (no album) */}
              {standaloneSongs.length > 0 && (
                <div className="space-y-3">
                  {albums.length > 0 && (
                    <h3 className="text-sm font-semibold text-zinc-400">♪ Weitere Songs ({standaloneSongs.length})</h3>
                  )}
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                    {standaloneSongs.map(s=><SongCard key={s.id} s={s}/>)}
                  </div>
                </div>
              )}
            </>);
          })()}
        </>)}

        {/* Code Gallery Tab */}
        {galleryTab==='code' && (<>
          <p className="text-sm text-muted-foreground">Autonome Code-Projekte von Ailey — sie programmiert eigenständig in verschiedenen Sprachen und Plattformen.</p>
          {galleryCodeItems.length === 0 && !galleryCodeLoading && (
            <Card className="p-10 text-center">
              <Code2 className="h-12 w-12 mx-auto text-muted-foreground/40 mb-3"/>
              <p className="text-sm text-muted-foreground">Noch keine Code-Projekte. Ailey generiert automatisch Code wenn sie idle ist.</p>
            </Card>
          )}
          {galleryCodeLoading && <div className="flex justify-center py-8"><Loader2 className="h-8 w-8 animate-spin text-primary"/></div>}
          <div className="space-y-3">
            {galleryCodeItems.map(item => (
              <Card key={item.filename} className="p-4 hover:border-primary/60 transition-colors duration-200">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-sm truncate">{item.title || item.filename}</h3>
                    {item.description && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{item.description}</p>}
                  </div>
                  <div className="flex gap-1.5 shrink-0 flex-wrap justify-end">
                    {item.language && <span className="px-2 py-0.5 rounded-full text-[10px] bg-purple-500/15 text-purple-400 border border-purple-500/30">{item.language}</span>}
                    {item.platform && <span className="px-2 py-0.5 rounded-full text-[10px] bg-blue-500/15 text-blue-400 border border-blue-500/30">{item.platform}</span>}
                    {item.lines > 0 && <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{item.lines} Zeilen</span>}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-muted-foreground mb-2">
                  <span>{item.created ? new Date(item.created).toLocaleDateString('de-DE') : ''}</span>
                  <span className="font-mono opacity-60">{item.filename}</span>
                </div>
                {galleryCodeExpanded === item.filename ? (
                  <div className="mt-2">
                    <div className="flex justify-end mb-1">
                      <Button size="sm" variant="outline" className="text-[10px] h-6" onClick={()=>{setGalleryCodeExpanded(null);setGalleryCodeContent(null);}}>Schließen</Button>
                    </div>
                    <pre className="bg-zinc-950 rounded-lg p-4 text-xs overflow-auto max-h-[400px] font-mono leading-relaxed"><code>{galleryCodeContent || 'Lade…'}</code></pre>
                  </div>
                ) : (
                  <Button size="sm" variant="outline" className="text-xs" onClick={()=>loadCodeContent(item.filename)}>📄 Code anzeigen</Button>
                )}
              </Card>
            ))}
          </div>
        </>)}

        {/* Upscale progress banner */}
        {upscaleBusy && upscaleProgress && (
          <div className="flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-purple-500/10 border border-purple-500/30 animate-pulse">
            <Loader2 className="h-4 w-4 animate-spin text-purple-400"/>
            <span className="text-xs text-purple-300">{upscaleProgress}</span>
          </div>
        )}

        {/* Lightbox overlay */}
        {galleryLightbox && (
          <div className="fixed inset-0 z-[60] bg-black/90 flex flex-col items-center justify-center p-4 cursor-pointer" onClick={()=>setGalleryLightbox(null)}>
            <Button variant="outline" size="icon" className="absolute top-4 right-4 z-10" onClick={()=>setGalleryLightbox(null)}><X className="h-5 w-5"/></Button>
            <img src={galleryLightbox} alt="Vergrößerung" className="max-w-full max-h-[80vh] object-contain rounded-xl shadow-2xl" onClick={e=>e.stopPropagation()}/>
            {/* Lightbox action bar */}
            <div className="flex gap-2 mt-4" onClick={e=>e.stopPropagation()}>
              {(()=>{
                // Extract filename from lightbox URL
                const _lbParts = galleryLightbox.split('/');
                const _lbFn = _lbParts[_lbParts.length-1];
                return _lbFn ? (
                  <>
                    <Button variant="outline" size="sm" disabled={upscaleBusy} onClick={()=>galleryUpscaleImage(_lbFn,'2x')} className="text-xs">🔍 Upscale 2×</Button>
                    <Button variant="outline" size="sm" disabled={upscaleBusy} onClick={()=>galleryUpscaleImage(_lbFn,'3x')} className="text-xs">🔍 3×</Button>
                    <Button variant="outline" size="sm" disabled={upscaleBusy} onClick={()=>galleryUpscaleImage(_lbFn,'4x')} className="text-xs">🔍 4×</Button>
                  </>
                ) : null;
              })()}
            </div>
            {upscaleBusy && <div className="mt-2 text-xs text-purple-300 animate-pulse">{upscaleProgress}</div>}
          </div>
        )}

        {/* 🎵 Song-Generation Modal */}
        {songModal && (
          <div className="fixed inset-0 z-[70] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={()=>setSongModal(null)}>
            <div className="bg-card border border-purple-500/30 rounded-2xl p-5 max-w-md w-full shadow-2xl" onClick={e=>e.stopPropagation()}>
              <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><Music className="h-4 w-4 text-purple-400"/>Song generieren</h3>
              <div className="space-y-3">
                <div>
                  <label className="text-xs opacity-70 block mb-1">Titel</label>
                  <input value={songModal.title} onChange={e=>setSongModal({...songModal, title:e.target.value})} className="w-full px-2 py-1.5 rounded border border-border bg-background text-sm" placeholder="Songtitel"/>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs opacity-70 block mb-1">Genre</label>
                    <select value={songModal.genre} onChange={e=>setSongModal({...songModal, genre:e.target.value})} className="w-full px-2 py-1.5 rounded border border-border bg-background text-sm">
                      {['','pop','rock','metal','punk','grunge','rap','k-pop','k-rap','ballad','electronic','industrial','acoustic','folk'].map(g=> <option key={g} value={g}>{g || '— Auto —'}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs opacity-70 block mb-1">Mood</label>
                    <select value={songModal.mood} onChange={e=>setSongModal({...songModal, mood:e.target.value})} className="w-full px-2 py-1.5 rounded border border-border bg-background text-sm">
                      {['','dark','bright','introspective','energetic','melancholic','aggressive','romantic'].map(mo=> <option key={mo} value={mo}>{mo || '— Auto —'}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <label className="text-xs opacity-70 block mb-1">Extra Tags (optional)</label>
                  <input value={songModal.tags} onChange={e=>setSongModal({...songModal, tags:e.target.value})} placeholder="z.B. 140bpm, female vocal, distorted guitar" className="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"/>
                </div>
                <div>
                  <label className="text-xs opacity-70 block mb-1">Dauer (Sekunden)</label>
                  <input type="number" min={30} max={240} value={songModal.duration} onChange={e=>setSongModal({...songModal, duration: parseInt(e.target.value||'180',10)||180})} className="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"/>
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <Button variant="outline" size="sm" onClick={()=>setSongModal(null)}>Abbrechen</Button>
                  <Button size="sm" onClick={()=>{ const sm=songModal; setSongModal(null); submitSongGen(sm.msgId, {title:sm.title, genre:sm.genre, mood:sm.mood, tags:sm.tags, duration:sm.duration}); }} className="bg-purple-600 hover:bg-purple-700 text-white">🎵 Los geht's</Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };  // end renderGallerySection

  // ── System Section with Sub-Tabs ────────────────────────────────────────
  const [sysSubTab, setSysSubTab] = useState<'hardware'|'lifesim'|'activities'|'data'|'email'|'portal'>('hardware');

  const sysSubTabs: {key:'hardware'|'lifesim'|'activities'|'data'|'email'|'portal'; icon:string; label:string}[] = [
    {key:'hardware',   icon:'🖥️', label:'Hardware & AI'},
    {key:'lifesim',    icon:'🏠', label:'LifeSim'},
    {key:'activities', icon:'🎯', label:'Aktivitäten'},
    {key:'data',       icon:'📦', label:'Daten & Wissen'},
    {key:'email',      icon:'📧', label:'E-Mail'},
    {key:'portal',     icon:'🌐', label:'Portal'},
  ];

  // Load portal status when Portal tab opens
  useEffect(() => {
    if (sysSubTab === 'portal') loadPortalStatus();
    if (sysSubTab === 'activities') loadCustomActivities();
  }, [sysSubTab]);

  // ── Custom Activities State ─────────────────────────────────────────────
  type CustomActivitySlot = {
    id: string;
    name: string;
    prompt: string;
    weight: number;
    enabled: boolean;
    context: Record<string, boolean>;
    include_personality: boolean;
    mood_effect: string;
    mood_intensity: number;
  };
  const [customActivities, setCustomActivities] = useState<CustomActivitySlot[]>([]);
  const [customActLoading, setCustomActLoading] = useState(false);
  const [customActSaveMsg, setCustomActSaveMsg] = useState('');

  const loadCustomActivities = async () => {
    setCustomActLoading(true);
    try {
      const r = await fetch(api('/api/admin/custom-activities', apiBaseRef));
      const j = await r.json();
      if (j.success && j.slots) setCustomActivities(j.slots);
    } catch {}
    setCustomActLoading(false);
  };

  const saveCustomActivities = async (slots?: CustomActivitySlot[]) => {
    const data = slots || customActivities;
    setCustomActSaveMsg('');
    try {
      const r = await fetch(api('/api/admin/custom-activities', apiBaseRef), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({slots: data}),
      });
      const j = await r.json();
      if (j.success && j.slots) {
        setCustomActivities(j.slots);
        setCustomActSaveMsg('✅ Gespeichert');
      } else {
        setCustomActSaveMsg('❌ Fehler: ' + (j.message || 'unbekannt'));
      }
    } catch (e: any) {
      setCustomActSaveMsg('❌ ' + (e?.message || 'Netzwerkfehler'));
    }
    setTimeout(() => setCustomActSaveMsg(''), 3000);
  };

  const updateSlot = (idx: number, patch: Partial<CustomActivitySlot>) => {
    setCustomActivities(prev => {
      const copy = [...prev];
      copy[idx] = {...copy[idx], ...patch};
      return copy;
    });
  };

  const updateSlotContext = (idx: number, key: string, val: boolean) => {
    setCustomActivities(prev => {
      const copy = [...prev];
      copy[idx] = {...copy[idx], context: {...copy[idx].context, [key]: val}};
      return copy;
    });
  };

  const CONTEXT_LABELS: Record<string, string> = {
    rag: '📚 RAG Wissen',
    people: '👥 Personen-Glossar',
    chat_main: '💬 Chat (Main App)',
    chat_portal: '🌐 Portal-Chats',
    reflections: '🪞 Reflexionen',
    diaries: '📓 Tagebücher',
    quick_thoughts: '💭 Quick Thoughts',
    art: '🎨 Kreative Arbeiten',
  };

  const MOOD_OPTIONS: {value: string; label: string; icon: string}[] = [
    {value: 'none',        label: 'Kein Effekt',  icon: '—'},
    {value: 'creative',    label: 'Kreativ',       icon: '🎨'},
    {value: 'playful',     label: 'Verspielt',     icon: '🎮'},
    {value: 'curious',     label: 'Neugierig',     icon: '🔍'},
    {value: 'happy',       label: 'Fröhlich',      icon: '😊'},
    {value: 'melancholic', label: 'Melancholisch',  icon: '🌧️'},
    {value: 'tired',       label: 'Müde',          icon: '😴'},
  ];

  const renderSysActivities = () => (<>
    <Card className="p-6 space-y-4 border-amber-500/30">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">🎯 Custom IdleThinker Activities</h3>
          <p className="text-sm text-muted-foreground mt-1">Definiere bis zu 3 eigene Aktivitäten, die Ailey autonom im Idle-Modus ausführt.</p>
        </div>
        <div className="flex items-center gap-2">
          {customActSaveMsg && <span className={`text-[10px] ${customActSaveMsg.startsWith('✅')?'text-emerald-400':'text-red-400'}`}>{customActSaveMsg}</span>}
          <Button size="sm" onClick={() => saveCustomActivities()} disabled={customActLoading}>
            {customActLoading ? 'Lädt…' : '💾 Speichern'}
          </Button>
        </div>
      </div>
    </Card>

    {customActivities.map((slot, idx) => (
      <Card key={slot.id} className={`p-5 space-y-4 transition-all ${slot.enabled ? 'border-amber-500/40 bg-amber-500/[0.02]' : 'border-border/30 opacity-70'}`}>
        {/* Header: Name + Enable toggle */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <span className="text-lg font-bold text-amber-400/80 shrink-0">#{idx + 1}</span>
            <input
              value={slot.name}
              onChange={e => updateSlot(idx, {name: e.target.value})}
              placeholder={`Aktivität ${idx + 1} (Name)`}
              className="bg-input border px-3 py-1.5 rounded-lg text-sm font-medium flex-1 min-w-0"
              maxLength={80}
            />
          </div>
          <label className="relative inline-flex items-center cursor-pointer shrink-0">
            <input type="checkbox" className="sr-only peer" checked={slot.enabled} onChange={e => updateSlot(idx, {enabled: e.target.checked})}/>
            <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-600"/>
          </label>
        </div>

        {/* Prompt textarea */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60 mb-1">Prompt / Anweisung</div>
          <textarea
            value={slot.prompt}
            onChange={e => updateSlot(idx, {prompt: e.target.value})}
            placeholder="Was soll Ailey bei dieser Aktivität tun? Z.B. 'Schreibe eine philosophische Reflexion über...' oder 'Analysiere die letzten Gespräche und fasse zusammen...'"
            className="w-full bg-input border rounded-lg px-3 py-2 text-xs font-mono min-h-[80px] resize-y"
            maxLength={2000}
            rows={3}
          />
          <div className="text-[9px] opacity-40 text-right">{slot.prompt.length}/2000</div>
        </div>

        {/* Weight slider */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider opacity-60">Gewichtung (Häufigkeit)</span>
            <span className="text-xs tabular-nums font-mono w-10 text-right">{slot.weight}</span>
          </div>
          <input
            type="range" min={0} max={50} step={1}
            value={slot.weight}
            onChange={e => updateSlot(idx, {weight: parseInt(e.target.value)})}
            className="w-full h-1.5 accent-amber-500"
          />
          <div className="flex justify-between text-[9px] opacity-40"><span>Nie (0)</span><span>Normal (~10)</span><span>Sehr oft (50)</span></div>
        </div>

        {/* Personality toggle */}
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-card/60 border border-border/30">
          <div>
            <div className="text-xs font-medium">🧬 Ailey-Persönlichkeit</div>
            <div className="text-[10px] opacity-50">Standard-Systemprompt (Tonus, Identität, Selbstbeschreibung) mitgeben</div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer shrink-0">
            <input type="checkbox" className="sr-only peer" checked={slot.include_personality ?? true} onChange={e => updateSlot(idx, {include_personality: e.target.checked})}/>
            <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-violet-600"/>
          </label>
        </div>

        {/* Context injection checkboxes */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60 mb-2">Kontext-Quellen</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {Object.entries(CONTEXT_LABELS).map(([key, label]) => (
              <label key={key} className={`flex items-center gap-2 p-2 rounded-lg border text-[11px] cursor-pointer transition-all ${slot.context[key] ? 'border-amber-500/40 bg-amber-500/10 text-amber-200' : 'border-border/30 bg-card/40 text-zinc-400 hover:border-border/50'}`}>
                <input
                  type="checkbox"
                  checked={!!slot.context[key]}
                  onChange={e => updateSlotContext(idx, key, e.target.checked)}
                  className="accent-amber-500 w-3.5 h-3.5"
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Mood effect */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60 mb-1">Mood-Effekt</div>
            <select
              value={slot.mood_effect}
              onChange={e => updateSlot(idx, {mood_effect: e.target.value})}
              className="bg-input border px-2 py-1.5 rounded-lg text-xs w-full"
            >
              {MOOD_OPTIONS.map(m => (
                <option key={m.value} value={m.value}>{m.icon} {m.label}</option>
              ))}
            </select>
          </div>
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider opacity-60">Intensität</span>
              <span className="text-xs tabular-nums font-mono">{slot.mood_intensity}/5</span>
            </div>
            <input
              type="range" min={1} max={5} step={1}
              value={slot.mood_intensity}
              onChange={e => updateSlot(idx, {mood_intensity: parseInt(e.target.value)})}
              className="w-full h-1.5 accent-amber-500 mt-1.5"
              disabled={slot.mood_effect === 'none'}
            />
            <div className="flex justify-between text-[9px] opacity-40"><span>Sanft</span><span>Stark</span></div>
          </div>
        </div>
      </Card>
    ))}

    {/* Bottom save bar */}
    {customActivities.length > 0 && (
      <div className="flex items-center justify-between pt-2">
        <p className="text-[10px] opacity-40">Änderungen werden erst beim Speichern wirksam. Gewichtung ~10 = normale Häufigkeit (wie Reflexion).</p>
        <Button size="sm" onClick={() => saveCustomActivities()} disabled={customActLoading}>💾 Speichern</Button>
      </div>
    )}
  </>);

  const renderSysHardware = () => {
    const s = sysStats;
    const thermalColors = ['text-emerald-400','text-yellow-400','text-orange-400','text-red-500'];
    const thermalLabels = ['Nominal','Leicht','Moderat','Kritisch'];
    const thermalBg = ['bg-emerald-500/10','bg-yellow-500/10','bg-orange-500/10','bg-red-500/10'];
    const tl = s?.thermal_level ?? 0;
    return (<>
        {/* ── Hardware Monitor ─────────────────────────────────────────── */}
        {s && (
          <Card className="p-6 space-y-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">🖥️ Hardware Monitor</h3>
            <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
              {/* CPU */}
              <div className="p-3 rounded-lg bg-card/60 border border-border/30 space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">CPU</div>
                <div className="text-2xl font-bold">{s.cpu.percent}%</div>
                <div className="text-[10px] opacity-50">{s.cpu.physical_cores} Kerne ({s.cpu.cores} Threads)</div>
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden"><div className={`h-full rounded-full transition-all ${s.cpu.percent>80?'bg-red-500':s.cpu.percent>50?'bg-yellow-500':'bg-emerald-500'}`} style={{width:`${s.cpu.percent}%`}}/></div>
              </div>
              {/* RAM */}
              <div className="p-3 rounded-lg bg-card/60 border border-border/30 space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">RAM</div>
                <div className="text-2xl font-bold">{s.ram.used_gb}<span className="text-sm opacity-50">/{s.ram.total_gb} GB</span></div>
                <div className="text-[10px] opacity-50">{s.ram.available_gb} GB frei</div>
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden"><div className={`h-full rounded-full transition-all ${s.ram.percent>85?'bg-red-500':s.ram.percent>60?'bg-yellow-500':'bg-emerald-500'}`} style={{width:`${s.ram.percent}%`}}/></div>
              </div>
              {/* Disk */}
              <div className="p-3 rounded-lg bg-card/60 border border-border/30 space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">Disk</div>
                <div className="text-2xl font-bold">{s.disk.used_gb}<span className="text-sm opacity-50">/{s.disk.total_gb} GB</span></div>
                <div className="text-[10px] opacity-50">{s.disk.free_gb} GB frei</div>
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden"><div className={`h-full rounded-full transition-all ${s.disk.percent>90?'bg-red-500':s.disk.percent>70?'bg-yellow-500':'bg-emerald-500'}`} style={{width:`${s.disk.percent}%`}}/></div>
              </div>
              {/* Thermal */}
              <div className={`p-3 rounded-lg border border-border/30 space-y-1 ${thermalBg[tl]}`}>
                <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">Temperatur</div>
                <div className={`text-2xl font-bold ${thermalColors[tl]}`}>{thermalLabels[tl]}</div>
                <div className="text-[10px] opacity-50">{s.temperature?.thermal_pressure || 'nominal'}</div>
                {s.temperature?.cpu_temp_c != null && <div className="text-[10px] opacity-50">CPU: {s.temperature.cpu_temp_c}°C</div>}
              </div>
              {/* Battery */}
              {s.battery?.present && (
              <div className={`p-3 rounded-lg border border-border/30 space-y-1 ${s.battery.percent!=null && s.battery.percent<=15?'bg-red-500/10':s.battery.percent!=null && s.battery.percent<=30?'bg-yellow-500/10':'bg-emerald-500/10'}`}>
                <div className="text-[10px] font-semibold uppercase tracking-wider opacity-60">Akku</div>
                <div className="text-2xl font-bold">{s.battery.percent != null ? `${s.battery.percent}%` : '–'} <span className="text-sm">{s.battery.charging ? '⚡' : s.battery.ac_power ? '🔌' : '🔋'}</span></div>
                <div className="text-[10px] opacity-50">{s.battery.charging ? 'Wird geladen' : s.battery.ac_power ? 'Netzstrom' : 'Akkubetrieb'}</div>
                {s.battery.percent != null && <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden"><div className={`h-full rounded-full transition-all ${s.battery.percent<=15?'bg-red-500':s.battery.percent<=30?'bg-yellow-500':'bg-emerald-500'}`} style={{width:`${s.battery.percent}%`}}/></div>}
              </div>
              )}
            </div>
            <div className="text-[10px] opacity-40">Uptime: {Math.floor((s.uptime_sec||0)/3600)}h {Math.floor(((s.uptime_sec||0)%3600)/60)}m • Auto-Refresh 8s</div>
          </Card>
        )}

        {/* ── Model Control ───────────────────────────────────────────── */}
        {s && (
          <Card className="p-6 space-y-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">🧠 Sprachmodell</h3>
            <div className="flex items-center gap-4 text-sm">
              <div className={`px-3 py-1 rounded-full text-xs font-semibold ${s.model.status==='active'?'bg-emerald-500/20 text-emerald-400':s.model.status==='paused'?'bg-yellow-500/20 text-yellow-400':'bg-zinc-500/20 text-zinc-400'}`}>{s.model.status}</div>
              {s.model.name && <span className="text-xs font-mono opacity-60">{s.model.name}</span>}
            </div>
            <div className="flex flex-wrap gap-2">
              {s.model.paused ? (
                <Button size="sm" variant="outline" onClick={()=>modelAction('resume')} disabled={modelActionBusy}>▶ Fortsetzen</Button>
              ) : (
                <Button size="sm" variant="outline" onClick={()=>modelAction('pause')} disabled={modelActionBusy}>⏸ Pausieren</Button>
              )}
              <Button size="sm" variant="outline" onClick={()=>modelAction('reload')} disabled={modelActionBusy}>🔄 Neu laden</Button>
              <Button size="sm" variant="outline" onClick={()=>modelAction('unload')} disabled={modelActionBusy}>⏏ Entladen</Button>
              <Button size="sm" variant="outline" onClick={async()=>{
                try{
                  const r=await fetch(api('/api/admin/model/clear-kv-cache',apiBaseRef),{method:'POST'});
                  const j=await r.json();
                  if(j.success) alert(`KV-Cache geleert: ${JSON.stringify(j.freed)}`);
                }catch(e){alert('Fehler beim Cache-Leeren');}
              }} disabled={modelActionBusy}>🗑 KV-Cache leeren</Button>
              <Button size="sm" variant="outline" onClick={async()=>{
                if(!confirm('Alle Songs erneut zum Portal pushen?')) return;
                try{
                  const r=await fetch(api('/api/songs/repush-all',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force_reupload:false})});
                  const j=await r.json();
                  if(j.success) alert(`Songs gepusht: ${j.pushed} ✅, ${j.skipped} übersprungen, ${j.failed} Fehler`);
                  else alert(`Fehler: ${j.error}`);
                }catch(e){alert('Fehler beim Song-Push');}
              }} disabled={modelActionBusy}>🎵 Songs → Portal pushen</Button>
              <Button size="sm" variant="outline" onClick={async()=>{
                if(!confirm('Englische Titel für alle Songs & Alben generieren? (LLM-Calls, kann dauern)')) return;
                try{
                  const r=await fetch(api('/api/songs/translate-titles',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force:false})});
                  const j=await r.json();
                  if(j.success) alert(`Übersetzt: ${j.songs_translated} Songs, ${j.albums_translated} Alben\nÜbersprungen: ${j.songs_skipped} Songs, ${j.albums_skipped} Alben`);
                  else alert(`Fehler: ${j.error}`);
                }catch(e){alert('Fehler bei Titel-Übersetzung');}
              }} disabled={modelActionBusy}>🇬🇧 Titel → Englisch</Button>
              <Button size="sm" variant="destructive" onClick={shutdownMac} disabled={modelActionBusy}>⏻ Mac herunterfahren</Button>
              {modelActionBusy && <span className="text-xs text-accent animate-pulse">arbeitet…</span>}
              {modelActionMsg && <span className="text-xs opacity-70">{modelActionMsg}</span>}
            </div>
            <p className="text-[10px] opacity-50">Pausieren stoppt Antworten + IdleThinker. Entladen gibt GPU-RAM frei. Neu laden entlädt + lädt komplett.</p>
          </Card>
        )}

        {/* ── Toggles ─────────────────────────────────────────────────── */}
        {s && (
          <Card className="p-6 space-y-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">⚙️ Subsysteme</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div><div className="text-sm font-medium">IdleThinker</div><div className="text-[10px] opacity-50">Autonomes Denken wenn niemand chattet</div></div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" className="sr-only peer" checked={s.idle_thinker.enabled} onChange={e=>toggleIdleThinker(e.target.checked)}/>
                  <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600"/>
                </label>
              </div>
              {s.idle_thinker.busy && <div className="text-[10px] text-accent animate-pulse pl-1">💭 Denkt gerade: {(() => {
                const ct = s.idle_thinker.current_type || '';
                const builtInLabels: Record<string,string> = {reflection:'Reflexion',introspection:'Selbstreflexion',goal_planning:'Ziele & Pläne',creative_song:'Song',research:'Recherche',memory_consolidation:'Gedächtnis',free_thought:'Freier Gedanke',proactive_message:'Proaktive Nachricht',email_check:'E-Mail-Check',book_authoring:'Buch schreiben',blog_writing:'Blog-Post',creative_coding:'Kreatives Coding',quick_thought:'Quick Thought',diary_writing:'Tagebuch',nightly_summary:'Nacht-Konsolidierung'};
                if (builtInLabels[ct]) return builtInLabels[ct];
                if (ct.startsWith('custom_')) {
                  const slot = customActivities.find(s => s.id === ct);
                  const idx = customActivities.findIndex(s => s.id === ct);
                  return slot?.name ? `🎯 ${slot.name}` : `🎯 Aktivität ${idx >= 0 ? idx + 1 : ct.replace('custom_slot_','')}`;
                }
                return ct || '…';
              })()}</div>}
              <div className="flex items-center justify-between">
                <div><div className="text-sm font-medium">Autonome Webrecherche</div><div className="text-[10px] opacity-50">Automatisches Web-Research & RAG Ingestion</div></div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" className="sr-only peer" checked={!!s.auto_research} onChange={e=>toggleAutoResearch(e.target.checked)}/>
                  <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600"/>
                </label>
              </div>
            </div>
          </Card>
        )}

        {/* ── Generation Settings (Token-Limits pro Kontext) ─────────── */}
        <Card className="p-6 space-y-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">🎛️ Token-Limits</h3>
          <p className="text-[10px] opacity-50">Max. Antwortlänge pro Kontext (50–16.384 Tokens). Mehr Tokens = längere, detailliertere Antworten, aber langsamer.</p>
          {Object.keys(genSettings).length === 0 ? (
            <button onClick={loadGenSettings} className="text-xs text-accent hover:underline">Einstellungen laden…</button>
          ) : (
            <div className="space-y-3">
              {([
                {key:'portal_chat',    label:'🌐 Portal Chat',               desc:'Webportal Antwortlänge (540–16k)'},
                {key:'idle_thoughts',  label:'💭 IdleThinker (Gedanken)',     desc:'Reflexion, Ziele, freie Gedanken'},
                {key:'idle_song',      label:'🎵 IdleThinker (Songs)',        desc:'Kreative Songs & Musik'},
                {key:'idle_book',      label:'📖 IdleThinker (Buch)',         desc:'Buch-Kapitel (normal)'},
                {key:'idle_book_deep', label:'📖 IdleThinker (Buch Deep)',    desc:'Buch-Kapitel (Deep-Write, idle ≥ 1h)'},
                {key:'code_ask',       label:'💻 Code: Fragen',              desc:'Code-Modus Erklärungen'},
                {key:'code_edit',      label:'💻 Code: Bearbeiten',          desc:'Code-Modus Edits'},
                {key:'code_agent',     label:'💻 Code: Agent',               desc:'Code-Modus autonomer Agent'},
                {key:'author_write',   label:'✍️ Author: Weiterschreiben',   desc:'Prosa fortsetzen'},
                {key:'author_review',  label:'✍️ Author: Lektorat & Co.',    desc:'Lektorat, Brainstorm, Recherche'},
              ] as {key:string;label:string;desc:string}[]).map(item => (
                <div key={item.key} className="space-y-0.5">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-medium">{item.label}</span>
                      <span className="text-[9px] opacity-40 ml-2">{item.desc}</span>
                    </div>
                    <span className="text-xs tabular-nums font-mono w-16 text-right">{genSettings[item.key] ?? '—'}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="range" min={50} max={16384} step={50}
                      value={genSettings[item.key] ?? genDefaults[item.key] ?? 500}
                      onChange={e => {
                        const v = parseInt(e.target.value);
                        setGenSettings(prev => ({...prev, [item.key]: v}));
                      }}
                      onMouseUp={e => updateGenSetting(item.key, parseInt((e.target as HTMLInputElement).value))}
                      onTouchEnd={e => updateGenSetting(item.key, genSettings[item.key] ?? genDefaults[item.key] ?? 500)}
                      className="flex-1 h-1.5 accent-emerald-500"
                    />
                    <button onClick={() => updateGenSetting(item.key, genDefaults[item.key] ?? 500)}
                      className="text-[8px] opacity-30 hover:opacity-70 transition-opacity" title="Reset auf Standard">↺</button>
                  </div>
                </div>
              ))}
              <div className="pt-2 border-t border-border/20 flex items-center justify-between">
                <span className="text-[10px] opacity-40">Alle Werte auf Standardwerte zurücksetzen</span>
                <button onClick={async () => {
                  const reset = {...genDefaults};
                  setGenSettings(reset);
                  try {
                    await fetch(api('/api/admin/generation-settings', apiBaseRef), {
                      method: 'POST', headers: {'Content-Type':'application/json'},
                      body: JSON.stringify(reset),
                    });
                  } catch {}
                }} className="text-[10px] px-3 py-1 rounded-md bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors">
                  ↺ Alle zurücksetzen
                </button>
              </div>
            </div>
          )}
        </Card>

        {/* ── Shutdown ────────────────────────────────────────────────── */}
        <Card className="p-6 space-y-4 border-destructive/40">
          <h3 className="text-lg font-semibold text-destructive">Shutdown</h3>
          <p className="text-sm text-muted-foreground">Stoppt Backend & Frontend (lokal).</p>
          <div className="flex items-center gap-3 text-sm">
            <Button variant="destructive" size="sm" disabled={shutdownBusy} onClick={shutdownAiley}>{shutdownBusy?'Fährt runter…':'Shutdown AI'}</Button>
            {shutdownMsg&&<span className="text-xs opacity-70">{shutdownMsg}</span>}
          </div>
          <p className="text-[10px] opacity-60">Start erneut über Launch Ailey.command.</p>
        </Card>
    </>);
  };

  const [lifeSimResetMsg, setLifeSimResetMsg] = useState('');
  const [lifeSimResetBusy, setLifeSimResetBusy] = useState(false);
  const [lifeSimResetConfirm, setLifeSimResetConfirm] = useState(false);

  const doLifeSimReset = async () => {
    setLifeSimResetBusy(true);
    setLifeSimResetMsg('');
    setLifeSimResetConfirm(false);
    try {
      const url = `${apiBaseRef.current}/api/life-sim/reset`;
      console.log('[LifeSim] Reset → POST', url);
      const r = await fetch(url, { method: 'POST' });
      const j = await r.json();
      console.log('[LifeSim] Reset response', j);
      if (j.success) {
        setLifeSimResetMsg('✅ LifeSim zurückgesetzt!');
        loadSystemStats();
      } else {
        setLifeSimResetMsg('❌ ' + (j.error || 'Unbekannter Fehler'));
      }
    } catch (e: any) {
      console.error('[LifeSim] Reset error', e);
      setLifeSimResetMsg('❌ ' + (e?.message || 'Netzwerkfehler'));
    } finally {
      setLifeSimResetBusy(false);
    }
  };

  const renderSysLifeSim = () => (<>
        {/* ── LifeSim Enable/Disable ──────────────────────────────────── */}
        <Card className="p-6 space-y-4 border-emerald-500/30">
          <h3 className="text-lg font-semibold flex items-center gap-2">🏠 Life Sim (Vyrus Valley)</h3>
          <p className="text-sm text-muted-foreground">Steuerung der LifeSim-Welt, Bedürfnisse und Zurücksetzen.</p>

          {/* Toggle */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-card/60 border border-border/30">
            <div>
              <div className="text-sm font-medium">LifeSim aktiv</div>
              <div className="text-[10px] opacity-50">Deaktivieren spart Ressourcen (kein RMMZ iframe)</div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" checked={lifeSimEnabled} onChange={e=>setLifeSimEnabled(e.target.checked)}/>
              <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600"/>
            </label>
          </div>

          {/* Graphic Overhaul Toggle */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-card/60 border border-border/30">
            <div>
              <div className="text-sm font-medium">🎨 Graphic Overhaul</div>
              <div className="text-[10px] opacity-50">Hochauflösende Overlay-Grafiken über den Tileset-Layern</div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" checked={graphicOverhaulEnabled} onChange={e=>setGraphicOverhaulEnabled(e.target.checked)}/>
              <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-violet-600"/>
            </label>
          </div>

          {/* Current needs preview */}
          {sysStats?.life_sim && (
            <div className="p-3 rounded-lg bg-card/60 border border-border/30 space-y-2">
              <div className="text-xs font-semibold opacity-60">Aktuelle Werte</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px]">
                {[
                  {label:'Hunger', val: sysStats.life_sim.hunger, max: 100},
                  {label:'Durst', val: sysStats.life_sim.thirst, max: 100},
                  {label:'Müdigkeit', val: sysStats.life_sim.tiredness, max: 100},
                  {label:'Toilette', val: sysStats.life_sim.toilet, max: 100},
                  {label:'Hygiene', val: sysStats.life_sim.hygiene, max: 100},
                  {label:'Umgebung', val: sysStats.life_sim.environment, max: 100},
                ].map(n => (
                  <div key={n.label} className="flex items-center justify-between gap-2">
                    <span className="opacity-70">{n.label}</span>
                    <span className={`font-mono font-bold ${(n.val??0) > 70 ? 'text-red-400' : (n.val??0) > 40 ? 'text-yellow-400' : 'text-emerald-400'}`}>{Math.round(n.val ?? 0)}</span>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-4 text-[11px] pt-1 border-t border-border/20">
                <span className="opacity-70">Tageslaune: <span className="font-bold text-amber-300">{Math.round(sysStats.life_sim.daily_mood ?? 0)}</span></span>
                <span className="opacity-70">Sozial: <span className="font-bold text-sky-300">{Math.round(sysStats.life_sim.social ?? 0)}</span></span>
              </div>
            </div>
          )}
        </Card>

        {/* ── LifeSim Reset — separate top-level card, no nesting ──── */}
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-5 space-y-3">
          <div className="text-sm font-medium">LifeSim zurücksetzen</div>
          <div className="text-[10px] opacity-50">Alle Needs auf 0, Tageslaune &amp; Sozial auf 100, Sympathie auf 80</div>

          {!lifeSimResetConfirm ? (
            <button
              type="button"
              onClick={() => { console.log('[LifeSim] Reset button clicked'); setLifeSimResetConfirm(true); }}
              disabled={lifeSimResetBusy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-red-600 text-white hover:bg-red-500 active:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer select-none"
            >
              🔄 Zurücksetzen
            </button>
          ) : (
            <div className="flex items-center gap-3">
              <span className="text-xs text-red-300">Wirklich zurücksetzen?</span>
              <button
                type="button"
                onClick={doLifeSimReset}
                disabled={lifeSimResetBusy}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-bold bg-red-600 text-white hover:bg-red-500 active:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer select-none"
              >
                {lifeSimResetBusy ? '⏳ Setzt zurück…' : '✅ Ja, zurücksetzen'}
              </button>
              <button
                type="button"
                onClick={() => setLifeSimResetConfirm(false)}
                className="inline-flex items-center px-3 py-2 rounded-md text-sm text-zinc-400 hover:text-white hover:bg-zinc-700 transition-colors cursor-pointer"
              >
                Abbrechen
              </button>
            </div>
          )}

          {lifeSimResetMsg && <div className={`text-xs mt-2 ${lifeSimResetMsg.startsWith('✅') ? 'text-emerald-400' : 'text-red-400'}`}>{lifeSimResetMsg}</div>}
        </div>
  </>);

  const renderSysData = () => (<>
        {/* ── Data Management ─────────────────────────────────────────── */}
        <Card className="p-6 space-y-4">
          <h3 className="text-lg font-semibold">Daten-Management</h3>
          <div className="space-y-3">
            <div>
              <div className="flex items-center justify-between text-xs mb-1"><span className="font-medium">RAG Threshold</span><span className="opacity-70">{ragThreshold.toFixed(2)}</span></div>
              <input aria-label="RAG Threshold" type="range" min={0} max={1} step={0.01} value={ragThreshold} onChange={e=>setRagThreshold(parseFloat(e.target.value))} className="w-full"/>
              <p className="text-[10px] text-muted-foreground">Relevanz-Schwelle (höher = strenger).</p>
            </div>
            <div className="flex items-center gap-3 text-sm"><Button variant="outline" size="sm" onClick={mergeDiaries} disabled={settingsBusy}>Tagebücher mergen</Button>{settingsBusy&&<span className="text-xs text-accent animate-pulse">arbeitet…</span>}{mergeMsg&&<span className="text-xs opacity-70">{mergeMsg}</span>}</div>
            <div className="flex flex-wrap items-center gap-3 text-sm"><Button variant="outline" size="sm" onClick={wipeRag} disabled={ragWiping}>{ragWiping?'wipe…':'Wipe Collections'}</Button><Button variant="outline" size="sm" onClick={wipeRagDeep} disabled={ragWipingDeep}>{ragWipingDeep?'deep…':'Deep Wipe Dir'}</Button>{ragWipeMsg&&<span className="text-xs opacity-70">{ragWipeMsg}</span>}</div>
            <p className="text-[10px] opacity-60">Deep Wipe löscht kompletten Chroma Inhalt; Collections-Wipe behält Struktur.</p>
          </div>
        </Card>

        {/* ── Document Upload to RAG ──────────────────────────────────── */}
        <Card className="p-6 space-y-4 border-violet-500/30">
          <h3 className="text-lg font-semibold flex items-center gap-2">📄 Dokument-Upload</h3>
          <p className="text-sm text-muted-foreground">Lade Textdateien ins Wissen (RAG). Erlaubt: PDF, DOCX, TXT, RTF, Code-Dateien. Automatisches Chunking.</p>
          <div className="flex flex-wrap items-center gap-3">
            <input ref={ragUploadRef} type="file" accept=".pdf,.docx,.txt,.rtf,.md,.csv,.json,.xml,.html,.py,.js,.ts,.tsx,.jsx,.css,.scss,.java,.c,.cpp,.h,.rs,.go,.rb,.php,.swift,.sh,.yaml,.yml,.toml,.sql,.lua" onChange={handleRagUpload} className="hidden" aria-label="RAG Upload"/>
            <Button size="sm" variant="outline" onClick={()=>ragUploadRef.current?.click()} disabled={ragUploading}>
              {ragUploading ? '📤 Verarbeite…' : '📄 Datei hochladen'}
            </Button>
            {ragUploading && <span className="text-xs text-accent animate-pulse">Chunking & Ingestion…</span>}
          </div>
          {ragUploadMsg && <span className={`text-xs ${ragUploadMsg.startsWith('✓')?'text-emerald-400':'text-red-400'}`}>{ragUploadMsg}</span>}
          <p className="text-[10px] opacity-50">Hochgeladene Dokumente werden als &quot;user_rag&quot; markiert. Ailey kann darauf angesprochen werden.</p>
        </Card>

        {/* ── RAG Memory Browser ─────────────────────────────────────── */}
        <Card className="p-6 space-y-4 border-amber-500/30">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold flex items-center gap-2">🧠 Wissens-Browser</h3>
            <Button size="sm" variant="outline" onClick={()=>{if(!ragBrowserOpen){loadRagBrowser();} setRagBrowserOpen(!ragBrowserOpen);}}>
              {ragBrowserOpen?'Schließen':'Öffnen'}
            </Button>
          </div>
          {ragBrowserOpen && (
            <div className="space-y-3">
              {/* Stats */}
              {ragBrowserStats && (
                <div className="flex flex-wrap gap-3 text-xs">
                  <span className="px-2 py-1 rounded bg-amber-500/10 text-amber-300 font-medium">{ragBrowserStats.total_chunks} Chunks</span>
                  <span className="px-2 py-1 rounded bg-amber-500/10 text-amber-300 font-medium">{ragBrowserStats.unique_documents} Dokumente</span>
                  {ragBrowserStats.document_types && Object.entries(ragBrowserStats.document_types).map(([k,v])=>(
                    <span key={k} className="px-2 py-1 rounded bg-zinc-700/50 text-zinc-300 text-[10px]">{k}: {String(v)}</span>
                  ))}
                </div>
              )}
              {/* Filter pills */}
              <div className="flex flex-wrap gap-2">
                {['','conversation','diary','email','research_auto','research_code','user_rag'].map(f=>(
                  <button key={f} onClick={()=>{setRagBrowserFilter(f);setRagBrowserOffset(0);loadRagBrowser(f,0);}}
                    className={`px-2 py-1 rounded text-[10px] font-medium transition ${ragBrowserFilter===f?'bg-amber-500/20 text-amber-300 border border-amber-500/40':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>
                    {f||'Alle'}
                  </button>
                ))}
              </div>
              {/* Entries list */}
              {ragBrowserLoading ? (
                <div className="text-xs text-accent animate-pulse py-4 text-center">Lade Einträge…</div>
              ) : ragBrowserEntries.length===0 ? (
                <div className="text-xs opacity-50 py-4 text-center">Keine Einträge gefunden.</div>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {ragBrowserEntries.map(entry=>(
                    <div key={entry.id} className="p-3 rounded-lg bg-card/60 border border-border/30 space-y-1 group">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{entry.title||'(ohne Titel)'}</div>
                          <div className="flex items-center gap-2 text-[10px] opacity-50">
                            <span className="px-1.5 py-0.5 rounded bg-zinc-700/50">{entry.doc_type||'unknown'}</span>
                            {entry.timestamp && <span>{new Date(entry.timestamp).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>}
                          </div>
                        </div>
                        <button onClick={()=>deleteRagEntry(entry.id)} disabled={ragBrowserDeleting===entry.id}
                          className="opacity-0 group-hover:opacity-100 transition text-red-400 hover:text-red-300 p-1" title="Eintrag löschen">
                          {ragBrowserDeleting===entry.id?<Loader2 className="w-3 h-3 animate-spin"/>:<Trash2 className="w-3 h-3"/>}
                        </button>
                      </div>
                      {entry.text && <div className="text-[11px] opacity-60 line-clamp-2 leading-relaxed">{entry.text}</div>}
                    </div>
                  ))}
                </div>
              )}
              {/* Pagination */}
              {!ragBrowserLoading && (ragBrowserOffset>0 || ragBrowserEntries.length>=ragBrowserLimit) && (
                <div className="flex items-center justify-between pt-2">
                  <Button size="sm" variant="ghost" disabled={ragBrowserOffset===0} onClick={()=>{const o=Math.max(0,ragBrowserOffset-ragBrowserLimit);setRagBrowserOffset(o);loadRagBrowser(undefined,o);}}>← Zurück</Button>
                  <span className="text-[10px] opacity-50">Offset {ragBrowserOffset}</span>
                  <Button size="sm" variant="ghost" disabled={ragBrowserEntries.length<ragBrowserLimit} onClick={()=>{const o=ragBrowserOffset+ragBrowserLimit;setRagBrowserOffset(o);loadRagBrowser(undefined,o);}}>Weiter →</Button>
                </div>
              )}
            </div>
          )}
        </Card>
  </>);

  const renderSysEmail = () => (<>
        {/* ── Email Contacts ──────────────────────────────────────────── */}
        <Card className="p-6 space-y-4 border-sky-500/30">
          <h3 className="text-lg font-semibold flex items-center gap-2">📧 E-Mail-Kontakte</h3>
          <p className="text-sm text-muted-foreground">Freigegebene Adressen, an die Ailey initiativ E-Mails schreiben darf.</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" variant="outline" onClick={loadContacts} disabled={contactsLoading}>{contactsLoading?'lädt…':'Kontakte laden'}</Button>
            <Button size="sm" variant="outline" onClick={scanOldEmailSenders} disabled={scanEmailsBusy}>{scanEmailsBusy?'scanne…':'Alte Absender evaluieren'}</Button>
            {scanEmailsMsg && <span className={`text-[10px] ${scanEmailsMsg.startsWith('✓')?'text-emerald-400':'text-red-400'}`}>{scanEmailsMsg}</span>}
          </div>
          {approvedContacts.length>0 && (
            <div className="space-y-2">
              {approvedContacts.map(c=>(
                <div key={c.email} className="flex items-center justify-between p-2 rounded bg-sky-500/5 border border-sky-500/10 text-sm">
                  <div className="flex flex-col">
                    <span className="font-medium">{c.name||c.email}</span>
                    <span className="text-[10px] opacity-60 font-mono">{c.email}</span>
                    {c.note && <span className="text-[10px] opacity-50 italic">{c.note}</span>}
                  </div>
                  <button onClick={()=>removeContact(c.email)} className="text-[10px] px-2 py-1 rounded text-red-400 hover:bg-red-500/10" title="Entfernen">✕</button>
                </div>
              ))}
            </div>
          )}
          {approvedContacts.length===0 && !contactsLoading && <p className="text-xs opacity-50">Keine Kontakte freigegeben.</p>}
          <div className="pt-2 border-t border-border/30 space-y-2">
            <div className="text-[11px] font-semibold">Kontakt hinzufügen</div>
            <div className="flex flex-wrap gap-2 items-end">
              <input value={newContactEmail} onChange={e=>setNewContactEmail(e.target.value)} placeholder="E-Mail" className="bg-input border px-2 py-1 rounded text-xs flex-1 min-w-[180px]" aria-label="Neue E-Mail"/>
              <input value={newContactName} onChange={e=>setNewContactName(e.target.value)} placeholder="Name (optional)" className="bg-input border px-2 py-1 rounded text-xs w-32" aria-label="Name"/>
              <input value={newContactNote} onChange={e=>setNewContactNote(e.target.value)} placeholder="Notiz (optional)" className="bg-input border px-2 py-1 rounded text-xs w-40" aria-label="Notiz"/>
              <Button size="sm" onClick={addContact}>Hinzufügen</Button>
            </div>
            {contactMsg && <span className={`text-[10px] ${contactMsg.startsWith('✓')?'text-emerald-400':'text-red-400'}`}>{contactMsg}</span>}
          </div>
        </Card>

        {/* ── Email Konten (SMTP/IMAP) ────────────────────────────────── */}
        <Card className="p-6 space-y-4 border-blue-500/30">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold flex items-center gap-2">📬 E-Mail-Konten</h3>
            <Button size="sm" variant="outline" onClick={()=>{if(!emailAccSectionOpen)loadEmailAccounts(); setEmailAccSectionOpen(!emailAccSectionOpen);}}>
              {emailAccSectionOpen ? 'Schließen' : 'Verwalten'}
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">IMAP/SMTP-Konten für Ailey und Simon – konfigurierbar, testbar, erweiterbar.</p>
          {emailAccSectionOpen && (
            <div className="space-y-4">
              {emailAccLoading && <div className="text-xs text-accent animate-pulse">Lädt Konten…</div>}
              {(['ailey','simon'] as const).map(role => {
                const roleAccounts = emailAccounts.filter(a => a.role === role);
                return (
                  <div key={role} className="space-y-2">
                    <div className="text-xs font-semibold uppercase tracking-wider opacity-60">{role === 'ailey' ? '💜 Ailey' : '👤 Simon'}</div>
                    {roleAccounts.length === 0 && !emailAccLoading && <div className="text-xs opacity-40 pl-1">Keine Konten.</div>}
                    {roleAccounts.map(acc => (
                      <div key={acc.id} className="rounded-lg border border-border/40 bg-card/60 overflow-hidden">
                        <div className="flex items-center justify-between p-3 gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{acc.label}</div>
                            <div className="text-[10px] opacity-50 font-mono truncate">{acc.email}</div>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${emailAccTestMsg[acc.id]?.startsWith('✓') ? 'bg-emerald-500/20 text-emerald-400' : emailAccTestMsg[acc.id]?.startsWith('✗') ? 'bg-red-500/20 text-red-400' : 'bg-zinc-700/50 text-zinc-400'}`}>
                              {emailAccTestMsg[acc.id] || 'ungetestet'}
                            </span>
                            <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={() => testEmailAccount(acc.id)}>Test</Button>
                            <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={() => {
                              const isOpen = emailAccEditing === acc.id;
                              setEmailAccEditing(isOpen ? null : acc.id);
                              setEmailAccEditData(isOpen ? {} : {label:acc.label, email:acc.email, imap_host:acc.imap_host, imap_port:acc.imap_port, smtp_host:acc.smtp_host, smtp_port:acc.smtp_port, user:acc.user, password:''});
                            }}>{emailAccEditing === acc.id ? 'Schließen' : 'Bearbeiten'}</Button>
                            <button onClick={() => deleteEmailAccount(acc.id)} className="text-red-400 hover:text-red-300 p-1 rounded" title="Löschen">✕</button>
                          </div>
                        </div>
                        {emailAccEditing === acc.id && (
                          <div className="border-t border-border/30 p-3 space-y-2 bg-zinc-900/40">
                            <div className="grid grid-cols-2 gap-2">
                              <div><div className="text-[10px] opacity-60 mb-0.5">Label</div><input value={emailAccEditData.label||''} onChange={e=>setEmailAccEditData(p=>({...p,label:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full"/></div>
                              <div><div className="text-[10px] opacity-60 mb-0.5">E-Mail</div><input value={emailAccEditData.email||''} onChange={e=>setEmailAccEditData(p=>({...p,email:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono"/></div>
                              <div><div className="text-[10px] opacity-60 mb-0.5">IMAP Host</div><input value={emailAccEditData.imap_host||''} onChange={e=>setEmailAccEditData(p=>({...p,imap_host:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono"/></div>
                              <div><div className="text-[10px] opacity-60 mb-0.5">IMAP Port</div><input type="number" value={emailAccEditData.imap_port||993} onChange={e=>setEmailAccEditData(p=>({...p,imap_port:parseInt(e.target.value)||993}))} className="bg-input border px-2 py-1 rounded text-xs w-full"/></div>
                              <div><div className="text-[10px] opacity-60 mb-0.5">SMTP Host</div><input value={emailAccEditData.smtp_host||''} onChange={e=>setEmailAccEditData(p=>({...p,smtp_host:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono"/></div>
                              <div><div className="text-[10px] opacity-60 mb-0.5">SMTP Port</div><input type="number" value={emailAccEditData.smtp_port||465} onChange={e=>setEmailAccEditData(p=>({...p,smtp_port:parseInt(e.target.value)||465}))} className="bg-input border px-2 py-1 rounded text-xs w-full"/></div>
                              <div><div className="text-[10px] opacity-60 mb-0.5">User</div><input value={emailAccEditData.user||''} onChange={e=>setEmailAccEditData(p=>({...p,user:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono"/></div>
                              <div><div className="text-[10px] opacity-60 mb-0.5">Passwort (leer = unverändert)</div><input type="password" value={emailAccEditData.password||''} onChange={e=>setEmailAccEditData(p=>({...p,password:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full"/></div>
                            </div>
                            <div className="flex gap-2 pt-1">
                              <Button size="sm" onClick={()=>saveEmailAccount(acc.id)}>Speichern</Button>
                              <Button size="sm" variant="ghost" onClick={()=>{setEmailAccEditing(null);setEmailAccEditData({});}}>Abbrechen</Button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
              {/* Add new account */}
              <div className="border-t border-border/30 pt-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold opacity-60">Konto hinzufügen</div>
                  <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={()=>setShowAddAcc(!showAddAcc)}>{showAddAcc ? 'Einklappen' : '+ Hinzufügen'}</Button>
                </div>
                {showAddAcc && (
                  <div className="space-y-2 p-3 rounded-lg bg-zinc-900/40 border border-border/30">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <div className="text-[10px] opacity-60 mb-0.5">Rolle</div>
                        <select value={newAcc.role||'simon'} onChange={e=>setNewAcc(p=>({...p,role:e.target.value as 'ailey'|'simon'}))} className="bg-input border px-2 py-1 rounded text-xs w-full">
                          <option value="simon">Simon</option>
                          <option value="ailey">Ailey</option>
                        </select>
                      </div>
                      <div><div className="text-[10px] opacity-60 mb-0.5">Label</div><input value={newAcc.label||''} onChange={e=>setNewAcc(p=>({...p,label:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full" placeholder="Mein Konto"/></div>
                      <div className="col-span-2"><div className="text-[10px] opacity-60 mb-0.5">E-Mail</div><input value={newAcc.email||''} onChange={e=>setNewAcc(p=>({...p,email:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono" placeholder="user@example.com"/></div>
                      <div><div className="text-[10px] opacity-60 mb-0.5">IMAP Host</div><input value={newAcc.imap_host||''} onChange={e=>setNewAcc(p=>({...p,imap_host:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono"/></div>
                      <div><div className="text-[10px] opacity-60 mb-0.5">IMAP Port</div><input type="number" value={newAcc.imap_port||993} onChange={e=>setNewAcc(p=>({...p,imap_port:parseInt(e.target.value)||993}))} className="bg-input border px-2 py-1 rounded text-xs w-full"/></div>
                      <div><div className="text-[10px] opacity-60 mb-0.5">SMTP Host</div><input value={newAcc.smtp_host||''} onChange={e=>setNewAcc(p=>({...p,smtp_host:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono"/></div>
                      <div><div className="text-[10px] opacity-60 mb-0.5">SMTP Port</div><input type="number" value={newAcc.smtp_port||465} onChange={e=>setNewAcc(p=>({...p,smtp_port:parseInt(e.target.value)||465}))} className="bg-input border px-2 py-1 rounded text-xs w-full"/></div>
                      <div><div className="text-[10px] opacity-60 mb-0.5">User</div><input value={newAcc.user||''} onChange={e=>setNewAcc(p=>({...p,user:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full font-mono"/></div>
                      <div><div className="text-[10px] opacity-60 mb-0.5">Passwort</div><input type="password" value={newAcc.password||''} onChange={e=>setNewAcc(p=>({...p,password:e.target.value}))} className="bg-input border px-2 py-1 rounded text-xs w-full"/></div>
                    </div>
                    <Button size="sm" onClick={addEmailAccount}>Konto anlegen</Button>
                  </div>
                )}
              </div>
              {emailAccMsg && <div className={`text-[10px] ${emailAccMsg.startsWith('Fehler')||emailAccMsg.startsWith('✗') ? 'text-red-400' : 'text-emerald-400'}`}>{emailAccMsg}</div>}
            </div>
          )}
        </Card>
  </>);

  // ── Portal Invite Sub-Tab ──────────────────────────────────────────────
  const renderSysPortal = () => (<>
    {/* ── Portal Support Toggle ────────────────────────────────── */}
    <Card className="p-6 space-y-4 border-purple-500/40">
      <h3 className="text-lg font-semibold flex items-center gap-2">🌐 Portal-Support</h3>
      <p className="text-sm text-muted-foreground">
        Wenn deaktiviert, sehen Portal-User &quot;Ailey schläft gerade&quot; und erhalten keine Antworten bis du es wieder aktivierst.
      </p>
      <div className="flex items-center gap-3">
        <button
          onClick={togglePortalSupport}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${portalEnabled ? 'bg-emerald-500' : 'bg-gray-600'}`}
        >
          <span className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg transform ring-0 transition duration-200 ease-in-out ${portalEnabled ? 'translate-x-5' : 'translate-x-0'}`} />
        </button>
        <span className="text-sm font-medium">{portalEnabled ? '✅ Portal aktiv — Ailey antwortet' : '💤 Portal pausiert — Ailey schläft'}</span>
      </div>
    </Card>

    {/* ── Invite from Glossary ─────────────────────────────────── */}
    <Card className="p-6 space-y-4 border-purple-500/30">
      <h3 className="text-lg font-semibold flex items-center gap-2">🌐 Portal-Einladungen</h3>
      <p className="text-sm text-muted-foreground">
        Personen aus dem Glossar zum Ailey Portal einladen. Die Einladung whitelistet ihre E-Mail auf allinkl und schickt eine Einladungs-E-Mail von Ailey.
      </p>
      <Button size="sm" variant="outline" onClick={loadInvitablePeople} disabled={invitableLoading}>
        {invitableLoading ? 'Lädt…' : 'Einladbare Personen laden'}
      </Button>

      {invitablePeople.length > 0 && (
        <div className="space-y-2">
          {invitablePeople.map(p => {
            const status = inviteStatuses[p.email] || 'idle';
            const msg = inviteMessages[p.email] || '';
            return (
              <div key={p.email} className="flex items-center justify-between p-3 rounded-lg bg-purple-500/5 border border-purple-500/10 gap-3">
                <div className="flex flex-col flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">{p.name}</span>
                    {p.already_invited && <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400">✓ bereits eingeladen</span>}
                  </div>
                  <span className="text-[10px] opacity-60 font-mono truncate">{p.email}</span>
                  {(p.affinity || p.occupation || p.company) && (
                    <span className="text-[10px] opacity-50 mt-0.5">
                      {[p.affinity, p.occupation, p.company].filter(Boolean).join(' · ')}
                    </span>
                  )}
                  {p.facts_preview.length > 0 && (
                    <span className="text-[10px] opacity-40 italic mt-0.5 truncate">{p.facts_preview[0]}</span>
                  )}
                  {msg && <span className={`text-[10px] mt-0.5 ${status === 'sent' ? 'text-emerald-400' : status === 'error' ? 'text-red-400' : 'text-accent'}`}>{msg}</span>}
                </div>
                <Button
                  size="sm"
                  variant={p.already_invited ? 'ghost' : 'outline'}
                  disabled={status === 'sending' || status === 'sent'}
                  onClick={() => sendPortalInvite(p.email, p.name)}
                  className="shrink-0"
                >
                  {status === 'sending' ? '📨 …' : status === 'sent' ? '✅' : p.already_invited ? 'Erneut einladen' : '📨 Einladen'}
                </Button>
              </div>
            );
          })}
        </div>
      )}
      {invitablePeople.length === 0 && !invitableLoading && (
        <p className="text-xs opacity-50">Keine einladbaren Personen gefunden. Im Glossar müssen Personen eine E-Mail-Adresse haben.</p>
      )}
    </Card>

    {/* ── Manual Invite ────────────────────────────────────────── */}
    <Card className="p-6 space-y-4 border-purple-500/20">
      <h3 className="text-lg font-semibold flex items-center gap-2">✉️ Manuelle Einladung</h3>
      <p className="text-sm text-muted-foreground">Person direkt per E-Mail einladen (auch ohne Glossar-Eintrag).</p>
      <div className="flex flex-wrap gap-2 items-end">
        <input value={manualInviteEmail} onChange={e => setManualInviteEmail(e.target.value)} placeholder="E-Mail-Adresse" className="bg-input border px-2 py-1 rounded text-xs flex-1 min-w-[200px]" aria-label="Invite email"/>
        <input value={manualInviteName} onChange={e => setManualInviteName(e.target.value)} placeholder="Name (optional)" className="bg-input border px-2 py-1 rounded text-xs w-36" aria-label="Invite name"/>
        <input value={manualInviteNote} onChange={e => setManualInviteNote(e.target.value)} placeholder="Persönliche Notiz (optional)" className="bg-input border px-2 py-1 rounded text-xs w-48" aria-label="Invite note"/>
        <Button size="sm" onClick={sendManualPortalInvite} disabled={manualInviteBusy}>
          {manualInviteBusy ? 'Sende…' : '📨 Einladen'}
        </Button>
      </div>
      {manualInviteMsg && <span className={`text-[10px] ${manualInviteMsg.includes('✅') ? 'text-emerald-400' : 'text-red-400'}`}>{manualInviteMsg}</span>}
    </Card>
  </>);

  // ── System Section Wrapper with Sub-Tab navigation ──────────────────────
  const renderSystemSection = () => (
      <div className="max-w-3xl mx-auto px-4 py-10 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-4xl font-black">System</h2>
          {sysStatsLoading && <span className="text-xs text-accent animate-pulse">aktualisiert…</span>}
        </div>
        {/* Sub-Tab bar */}
        <div className="flex gap-1 p-1 rounded-xl bg-zinc-900/60 border border-border/30">
          {sysSubTabs.map(t=>(
            <button key={t.key} onClick={()=>setSysSubTab(t.key)}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all ${sysSubTab===t.key ? 'bg-accent/20 text-accent shadow-sm' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60'}`}>
              <span>{t.icon}</span><span className="hidden sm:inline">{t.label}</span>
            </button>
          ))}
        </div>
        {/* Sub-Tab content */}
        <div className="space-y-6">
          {sysSubTab === 'hardware' && renderSysHardware()}
          {sysSubTab === 'lifesim' && renderSysLifeSim()}
          {sysSubTab === 'activities' && renderSysActivities()}
          {sysSubTab === 'data' && renderSysData()}
          {sysSubTab === 'email' && renderSysEmail()}
          {sysSubTab === 'portal' && renderSysPortal()}
        </div>
      </div>
  );

  const AgentSection=()=> (
    <div className="max-w-4xl mx-auto px-4 py-10 space-y-6">
      <h2 className="text-4xl font-black mb-2">Agent Mode</h2>
      <p className="text-sm text-muted-foreground mb-4">Nur-lesende sichere Systemaktionen.</p>
      <div className="flex gap-2 items-center"><Button size="sm" variant="outline" onClick={loadCaps}>Capabilities laden</Button>{agentCaps&&<span className="text-xs opacity-60">{Object.keys(agentCaps).length} Aktionen</span>}</div>
      {agentCaps&&<Card className="p-5 space-y-5">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col">
            <label className="text-[10px] font-semibold">Aktion</label>
            <select aria-label="Agent action" value={agentAction} onChange={e=>setAgentAction(e.target.value)} className="bg-input border px-2 py-1 rounded text-sm">{Object.keys(agentCaps).map(a=><option key={a} value={a}>{a}</option>)}</select>
          </div>
          <div className="flex flex-col flex-1 min-w-[200px]">
            <label className="text-[10px] font-semibold">Params JSON</label>
            <input value={agentParams} onChange={e=>setAgentParams(e.target.value)} placeholder='{"path":"."}' className="bg-input border px-2 py-1 rounded text-xs font-mono"/>
          </div>
          <Button size="sm" disabled={agentBusy} onClick={runAgent}>{agentBusy?'läuft…':'Ausführen'}</Button>
        </div>
        <div className="grid sm:grid-cols-2 gap-3 text-[11px]">
          <Card className="p-3 space-y-2 bg-card/50 border-accent/30">
            <div className="font-semibold">Semantischer Index</div>
            <p className="opacity-70 leading-snug">Dokumente einlesen & Embeddings bauen. Standard: txt, md, docx.</p>
            <Button size="sm" variant="outline" disabled={agentBusy} onClick={buildSemanticIndex}>Index (Re)build</Button>
          </Card>
          <Card className="p-3 space-y-2 bg-card/50 border-accent/30">
            <div className="font-semibold">Semantische Suche</div>
            <SemanticSearchBox onSearch={semanticSearch} loading={agentBusy}/>
          </Card>
        </div>
        {agentCaps[agentAction]?.description&&<p className="text-xs opacity-70">{agentCaps[agentAction].description}</p>}
        {agentBusy&&<p className="text-xs text-accent animate-pulse">führt aus…</p>}
        {agentResult&&<pre className="max-h-96 overflow-auto bg-black/30 text-xs p-3 rounded border whitespace-pre-wrap">{JSON.stringify(agentResult,null,2)}</pre>}
        <p className="text-[10px] text-muted-foreground">Sicherheitsbeschränkt (Read-Only). Admin Token {ADMIN_TOKEN? 'aktiv' : 'nicht gesetzt (dev offen)'}.</p>
      </Card>}
    </div>
  );

  function SemanticSearchBox({onSearch,loading}:{onSearch:(q:string)=>void; loading:boolean}){
    const [q,setQ]=useState('');
    return <form onSubmit={e=>{e.preventDefault(); onSearch(q);}} className="flex flex-col gap-2">
      <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Frage / Query" className="bg-input border px-2 py-1 rounded text-xs"/>
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={!q.trim()||loading}>Suche</Button>
        {q && <Button size="sm" type="button" variant="outline" onClick={()=>setQ('')}>Reset</Button>}
      </div>
    </form>;
  }

  const InstagramSection=()=> (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div className="flex items-center gap-4">
          <h2 className="text-3xl sm:text-4xl font-black">Instagram</h2>
          <span className="text-xs text-muted-foreground">@ailey.vyrus_official</span>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={()=>setInstaView('manage')} className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${instaView==='manage'?'bg-primary text-primary-foreground':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>⚙️ Verwalten</button>
          <button onClick={()=>setInstaView('feed')} className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${instaView==='feed'?'bg-primary text-primary-foreground':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>📸 Feed</button>
          <button onClick={()=>setInstaView('planned')} className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${instaView==='planned'?'bg-primary text-primary-foreground':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>📋 Geplant{socialPosts.length>0?` (${socialPosts.length})`:''}</button>
          <button onClick={()=>setInstaView('published')} className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${instaView==='published'?'bg-emerald-600 text-white':'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>✅ Freigegeben{publishedPosts.length>0?` (${publishedPosts.length})`:''}</button>
        </div>
      </div>

      {instaView==='manage' && (
        <div className="space-y-6">
          {/* Quick Actions */}
          <Card className="p-6 space-y-4">
            <h3 className="text-lg font-bold flex items-center gap-2"><Instagram className="h-5 w-5 text-pink-500"/> Schnellzugriff</h3>
            <p className="text-sm text-muted-foreground">Öffne Instagram im Browser, um Aileys Account zu verwalten. Du bist eingeloggt als <strong>@ailey.vyrus_official</strong>.</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Button variant="outline" className="h-auto py-4 flex flex-col gap-2" onClick={()=>openExternal('https://www.instagram.com/ailey.vyrus_official/')}>
                <Instagram className="h-5 w-5"/>
                <span className="text-xs">Profil öffnen</span>
              </Button>
              <Button variant="outline" className="h-auto py-4 flex flex-col gap-2" onClick={()=>openExternal('https://www.instagram.com/direct/inbox/')}>
                <MessageCircle className="h-5 w-5"/>
                <span className="text-xs">DMs / Nachrichten</span>
              </Button>
              <Button variant="outline" className="h-auto py-4 flex flex-col gap-2" onClick={()=>openExternal('https://www.instagram.com/accounts/activity/')}>
                <Bell className="h-5 w-5"/>
                <span className="text-xs">Benachrichtigungen</span>
              </Button>
              <Button variant="outline" className="h-auto py-4 flex flex-col gap-2" onClick={()=>openExternal('https://www.instagram.com/create/style/')}>
                <ImageIcon className="h-5 w-5"/>
                <span className="text-xs">Neuer Post</span>
              </Button>
              <Button variant="outline" className="h-auto py-4 flex flex-col gap-2" onClick={()=>openExternal('https://www.instagram.com/explore/')}>
                <Search className="h-5 w-5"/>
                <span className="text-xs">Explore</span>
              </Button>
              <Button variant="outline" className="h-auto py-4 flex flex-col gap-2" onClick={()=>openExternal('https://www.instagram.com/accounts/edit/')}>
                <SettingsIcon className="h-5 w-5"/>
                <span className="text-xs">Profil bearbeiten</span>
              </Button>
            </div>
          </Card>

          {/* Account Info */}
          <Card className="p-6 space-y-3">
            <h3 className="text-sm font-bold">📊 Account-Info</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Account</div>
                <div className="font-medium">@ailey.vyrus_official</div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Typ</div>
                <div className="font-medium">KI-Persona (Ailey)</div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Verwaltet von</div>
                <div className="font-medium">Simon van de Loo</div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Status</div>
                <div className="font-medium text-emerald-400">● Manuell verwaltet</div>
              </div>
            </div>
          </Card>

          {/* Feature hint */}
          <Card className="p-4 border-dashed border-primary/30">
            <div className="flex items-start gap-3">
              <Sparkles className="h-5 w-5 text-primary mt-0.5 shrink-0"/>
              <div className="text-xs text-muted-foreground space-y-1">
                <div className="font-medium text-foreground">🖼️ Bildgenerierung + Social Content</div>
                <div>Ailey kann jetzt lokal Bilder generieren und Instagram-Posts planen. Schau unter <button className="underline text-primary" onClick={()=>setInstaView('planned')}>📋 Geplant</button> für Aileys Post-Vorschläge.</div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {instaView==='feed' && (<>
        <div className="flex items-center gap-3 mb-4">
          <Button size="sm" variant="outline" onClick={()=>loadInstagram(true)} disabled={instaLoading}>{instaLoading?'lädt…':'Refresh'}</Button>
          <span className="text-xs opacity-60">{instaPosts.length} Posts</span>
        </div>
        {instaError && <div className="text-xs text-destructive mb-4">Feed Fehler: {instaError}</div>}
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-5">
          {instaPosts.map(p=> (
            <div key={p.id} className="group relative cursor-pointer" onClick={()=>setOpenPost(p)}>
              <div className="aspect-square overflow-hidden rounded-xl border border-border/60 bg-card">
                <img src={p.src} alt={p.caption} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"/>
              </div>
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-white text-xs font-medium">
                Öffnen
              </div>
              <div className="mt-2 text-[11px] truncate opacity-70">{new Date(p.ts).toLocaleDateString()} • ❤ {p.likes}</div>
            </div>
          ))}
          {!instaLoading && instaPosts.length===0 && !instaError && <div className="text-xs opacity-60">Keine Posts geladen. Scraping kann unzuverlässig sein.</div>}
          {instaLoading && [...Array(6)].map((_,i)=>(<div key={i} className="aspect-square rounded-xl border border-dashed border-border/40 flex items-center justify-center text-[10px] opacity-50">lädt…</div>))}
        </div>
      </>)}

      {instaView==='planned' && (
        <div className="space-y-6">
          {/* Action Bar */}
          <div className="flex items-center gap-3 flex-wrap">
            <Button size="sm" variant="outline" onClick={()=>loadSocialPosts()} disabled={socialLoading}>{socialLoading?'lädt…':'🔄 Refresh'}</Button>
            <Button size="sm" variant="outline" onClick={()=>triggerSocialContent()}>✨ Ailey planen lassen</Button>
            <Button size="sm" variant="outline" onClick={()=>triggerImageGen()}>🖼️ Bild generieren</Button>
            <span className="text-xs opacity-60">{socialPosts.length} geplante Posts</span>
          </div>

          {/* Post beauftragen */}
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="text"
              className="flex-1 min-w-[180px] bg-zinc-900 border border-border rounded-lg px-3 py-1.5 text-sm placeholder:text-zinc-600"
              placeholder="Thema für neuen Post…"
              value={socialTopic}
              onChange={e=>setSocialTopic(e.target.value)}
              onKeyDown={e=>{ if(e.key==='Enter') triggerSocialPrompt(); }}
            />
            <Button size="sm" variant="outline" onClick={()=>triggerSocialPrompt()} disabled={socialTopicLoading||!socialTopic.trim()}>
              {socialTopicLoading?'⏳ …':'📱 Post beauftragen'}
            </Button>
          </div>

          {/* Planned Posts List */}
          {socialPosts.length===0 && !socialLoading && (
            <Card className="p-8 text-center">
              <div className="text-4xl mb-3">📋</div>
              <p className="text-sm text-muted-foreground">Keine geplanten Posts vorhanden.</p>
              <p className="text-xs text-muted-foreground mt-1">Klicke &quot;Ailey planen lassen&quot;, damit Ailey Instagram-Ideen entwickelt.</p>
            </Card>
          )}

          {socialLoading && (
            <div className="grid gap-4">
              {[...Array(3)].map((_,i)=>(
                <Card key={i} className="p-6 animate-pulse">
                  <div className="h-4 bg-zinc-800 rounded w-3/4 mb-3"/>
                  <div className="h-3 bg-zinc-800 rounded w-1/2 mb-2"/>
                  <div className="h-3 bg-zinc-800 rounded w-1/3"/>
                </Card>
              ))}
            </div>
          )}

          <div className="grid gap-4">
            {socialPosts.map(post=>(
              <Card key={post.id} className="p-4 sm:p-5 space-y-3 border-l-4 border-l-pink-500/60">
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div className="flex-1 min-w-0 space-y-2">
                    {/* Caption */}
                    {editingPost?.id===post.id ? (
                      <div className="space-y-2">
                        <textarea
                          className="w-full bg-zinc-900 border border-border rounded-lg p-3 text-sm resize-none"
                          rows={4}
                          value={editCaption}
                          onChange={e=>setEditCaption(e.target.value)}
                          placeholder="Caption…"
                        />
                        <input
                          className="w-full bg-zinc-900 border border-border rounded-lg p-2 text-xs"
                          value={editHashtags}
                          onChange={e=>setEditHashtags(e.target.value)}
                          placeholder="Hashtags (kommasepariert)…"
                        />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={()=>editSocialPost(post.id, editCaption, editHashtags)}>💾 Speichern</Button>
                          <Button size="sm" variant="outline" onClick={()=>setEditingPost(null)}>Abbrechen</Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {post.title && <h4 className="text-sm font-bold text-pink-400">{post.title}</h4>}
                        <p className="text-sm whitespace-pre-wrap leading-relaxed">{post.caption}</p>
                        {post.hashtags?.length>0 && (
                          <div className="flex flex-wrap gap-1">
                            {post.hashtags.map((h,i)=>(
                              <span key={i} className="text-[10px] px-2 py-0.5 bg-pink-500/10 text-pink-400 rounded-full">#{h.replace(/^#/,'')}</span>
                            ))}
                          </div>
                        )}
                      </>
                    )}

                    {/* Metadata */}
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                      {post.mood && <span className="px-2 py-0.5 bg-zinc-800 rounded-full">{post.mood}</span>}
                      {post.category && <span className="px-2 py-0.5 bg-zinc-800 rounded-full">{post.category}</span>}
                      <span>{new Date(post.created_at).toLocaleDateString('de-DE',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</span>
                    </div>

                    {/* Image Prompt Preview */}
                    {post.image_prompt && (
                      <details className="text-[10px]">
                        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">🎨 Bild-Prompt anzeigen</summary>
                        <p className="mt-1 p-2 bg-zinc-900 rounded text-muted-foreground italic">{post.image_prompt}</p>
                      </details>
                    )}
                  </div>

                  {/* Image Preview (if already generated) */}
                  {post.image_url && (
                    <div className="w-20 h-20 rounded-lg overflow-hidden border border-border/60 shrink-0">
                      <img src={post.image_url} alt="Preview" className="w-full h-full object-cover"/>
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                {editingPost?.id!==post.id && (
                  <div className="flex items-center gap-2 pt-1 border-t border-border/30 flex-wrap">
                    <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={()=>approveSocialPost(post.id)}>
                      ✅ Freigeben
                    </Button>
                    {post.image_prompt && !post.image_url && (
                      <Button size="sm" variant="outline" onClick={()=>approveSocialPost(post.id, true)}>
                        🖼️ Freigeben + Bild
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={()=>{setEditingPost(post);setEditCaption(post.caption);setEditHashtags(post.hashtags?.join(', ')||'');}}>
                      ✏️ Bearbeiten
                    </Button>
                    <Button size="sm" variant="outline" className="text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={()=>{if(confirm('Post wirklich löschen?')) deleteSocialPost(post.id);}}>
                      🗑️
                    </Button>
                    {post.caption && (
                      <Button size="sm" variant="ghost" className="ml-auto" onClick={()=>{navigator.clipboard.writeText(post.caption+(post.hashtags?.length?'\n\n'+post.hashtags.map(h=>'#'+h.replace(/^#/,'')).join(' '):''));alert('📋 Kopiert!');}}>
                        📋
                      </Button>
                    )}
                  </div>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ── Published / Approved Posts (ready for manual posting) ── */}
      {instaView==='published' && (
        <div className="space-y-6">
          {/* Action Bar */}
          <div className="flex items-center gap-3 flex-wrap">
            <Button size="sm" variant="outline" onClick={()=>loadPublishedPosts()} disabled={publishedLoading}>{publishedLoading?'lädt…':'🔄 Refresh'}</Button>
            <span className="text-xs opacity-60">{publishedPosts.length} freigegebene Posts</span>
            <span className="text-[10px] text-muted-foreground ml-auto">
              {publishedPosts.filter(p=>p.published_at).length} gepostet · {publishedPosts.filter(p=>!p.published_at).length} offen
            </span>
          </div>

          {publishedPosts.length===0 && !publishedLoading && (
            <Card className="p-8 text-center">
              <div className="text-4xl mb-3">✅</div>
              <p className="text-sm text-muted-foreground">Keine freigegebenen Posts vorhanden.</p>
              <p className="text-xs text-muted-foreground mt-1">Gib Posts im &quot;Geplant&quot;-Tab frei, sie erscheinen dann hier.</p>
            </Card>
          )}

          {publishedLoading && (
            <div className="grid gap-4">
              {[...Array(3)].map((_,i)=>(
                <Card key={i} className="p-6 animate-pulse">
                  <div className="h-4 bg-zinc-800 rounded w-3/4 mb-3"/>
                  <div className="h-3 bg-zinc-800 rounded w-1/2"/>
                </Card>
              ))}
            </div>
          )}

          <div className="grid gap-5">
            {publishedPosts.map(post=>{
              const imgUrl = post._local_image_url || post.image_url;
              const imgSrc = imgUrl ? (imgUrl.startsWith('http') ? imgUrl : api(imgUrl, apiBaseRef)) : null;
              const isPosted = !!post.published_at;
              const fullCaption = post.caption + (post.hashtags?.length ? '\n\n' + post.hashtags.map(h=>'#'+h.replace(/^#/,'')).join(' ') : '');
              return (
                <Card key={post.id} className={`overflow-hidden border-l-4 ${isPosted?'border-l-emerald-600/40 opacity-60':'border-l-pink-500/60'}`}>
                  <div className="flex flex-col md:flex-row">
                    {/* Image Section */}
                    {imgSrc ? (
                      <div className="md:w-64 md:min-h-[200px] relative bg-black shrink-0 group">
                        <img src={imgSrc} alt={post.caption?.slice(0,40)} className="w-full h-48 md:h-full object-cover"/>
                        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button size="sm" variant="outline" className="bg-black/60 text-white border-white/30 hover:bg-black/80" onClick={()=>downloadImage(imgUrl!, post.image_filename||`${post.id}.png`)}>
                            <Download className="h-3.5 w-3.5 mr-1"/> Bild
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="md:w-64 md:min-h-[200px] bg-zinc-900 flex flex-col items-center justify-center gap-2 shrink-0 p-4">
                        <ImageIcon className="h-8 w-8 text-zinc-700"/>
                        <span className="text-[10px] text-zinc-600">Kein Bild</span>
                        {post.image_prompt && (
                          <Button size="sm" variant="outline" className="text-xs mt-1" onClick={()=>generateImageForPost(post.id)}>
                            🖼️ Bild generieren
                          </Button>
                        )}
                      </div>
                    )}

                    {/* Content Section */}
                    <div className="flex-1 p-5 space-y-3">
                      {/* Status badge */}
                      <div className="flex items-center gap-2">
                        {isPosted ? (
                          <span className="text-[10px] px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded-full">✅ Gepostet {new Date(post.published_at!).toLocaleDateString('de-DE',{day:'2-digit',month:'short'})}</span>
                        ) : (
                          <span className="text-[10px] px-2 py-0.5 bg-amber-500/20 text-amber-400 rounded-full">⏳ Noch nicht gepostet</span>
                        )}
                        {post.category && <span className="text-[10px] px-2 py-0.5 bg-zinc-800 rounded-full">{post.category}</span>}
                        {post.mood && <span className="text-[10px] px-2 py-0.5 bg-zinc-800 rounded-full">{post.mood}</span>}
                      </div>

                      {/* Caption */}
                      {post.title && <h4 className="text-sm font-bold text-pink-400">{post.title}</h4>}
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{post.caption}</p>

                      {/* Hashtags */}
                      {post.hashtags?.length>0 && (
                        <div className="flex flex-wrap gap-1">
                          {post.hashtags.map((h,i)=>(
                            <span key={i} className="text-[10px] px-2 py-0.5 bg-pink-500/10 text-pink-400 rounded-full">#{h.replace(/^#/,'')}</span>
                          ))}
                        </div>
                      )}

                      {/* Dates */}
                      <div className="text-[10px] text-muted-foreground">
                        Erstellt: {new Date(post.created_at).toLocaleDateString('de-DE',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})}
                        {post.approved_at && <> · Freigegeben: {new Date(post.approved_at).toLocaleDateString('de-DE',{day:'2-digit',month:'short'})}</>}
                      </div>

                      {/* Action Buttons */}
                      <div className="flex items-center gap-2 pt-2 border-t border-border/30 flex-wrap">
                        <Button size="sm" variant="outline" onClick={()=>copyToClipboard(fullCaption, 'Caption + Hashtags')}>
                          <Copy className="h-3.5 w-3.5 mr-1"/> Caption kopieren
                        </Button>
                        {post.hashtags?.length>0 && (
                          <Button size="sm" variant="outline" onClick={()=>copyToClipboard(post.hashtags.map(h=>'#'+h.replace(/^#/,'')).join(' '), 'Hashtags')}>
                            📋 Nur Hashtags
                          </Button>
                        )}
                        {imgUrl && (
                          <Button size="sm" variant="outline" onClick={()=>downloadImage(imgUrl, post.image_filename||`${post.id}.png`)}>
                            <Download className="h-3.5 w-3.5 mr-1"/> Download
                          </Button>
                        )}
                        {imgUrl && post.image_prompt && (
                          <Button size="sm" variant="outline" onClick={()=>{if(confirm('Bild neu generieren? Das aktuelle Bild wird ersetzt.')) generateImageForPost(post.id);}}>
                            🔄 Neu generieren
                          </Button>
                        )}
                        {!imgUrl && post.image_prompt && (
                          <Button size="sm" variant="outline" onClick={()=>generateImageForPost(post.id)}>
                            🖼️ Bild generieren
                          </Button>
                        )}
                        {!isPosted && (
                          <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white ml-auto" onClick={()=>markPosted(post.id)}>
                            ✅ Als gepostet markieren
                          </Button>
                        )}
                        <Button size="sm" variant="outline" className="text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={()=>{if(confirm('Post archivieren?')) deleteSocialPost(post.id).then(()=>loadPublishedPosts());}}>
                          🗑️
                        </Button>
                      </div>

                      {/* Image Prompt (collapsible) */}
                      {post.image_prompt && (
                        <details className="text-[10px]">
                          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">🎨 Bild-Prompt</summary>
                          <p className="mt-1 p-2 bg-zinc-900 rounded text-muted-foreground italic">{post.image_prompt}</p>
                        </details>
                      )}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {openPost && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={()=>setOpenPost(null)}>
          <div className="bg-card w-full max-w-3xl rounded-xl border relative overflow-hidden" onClick={e=>e.stopPropagation()}>
            <button className="absolute top-2 right-2 text-xs px-2 py-1 bg-black/60 rounded hover:bg-black/80" onClick={()=>setOpenPost(null)}>Schließen</button>
            <div className="grid md:grid-cols-2">
              <div className="relative bg-black">
                <img src={openPost.src} alt={openPost.caption} className="w-full h-full object-cover"/>
                <div className="absolute bottom-2 left-2 text-[10px] px-2 py-1 bg-black/50 rounded-full backdrop-blur">{moodLabelsDE[openPost.mood||''] || openPost.mood || 'Stimmung'}</div>
              </div>
              <div className="p-5 space-y-4 text-sm">
                <div className="flex items-center justify-between">
                  <strong className="text-primary">@ailey.vyrus_official</strong>
                  <span className="text-[10px] opacity-60">{new Date(openPost.ts).toLocaleString()}</span>
                </div>
                <p className="whitespace-pre-wrap leading-relaxed">{openPost.caption}</p>
                <div className="flex items-center gap-4 text-xs opacity-70">
                  <span>❤ {openPost.likes}</span>
                  <button onClick={()=>{navigator.clipboard.writeText(openPost.caption).catch(()=>{});}} className="underline hover:no-underline">Copy</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // --- People Glossary (Personen-Glossar) Section ---
  interface PersonFact { text:string; source?:string; ts?:number; _type?:string; }
  interface PersonEntry {
    id:string; name:string; full_name?:string; aliases?:string[]; relation?:string; context?:string;
    email?:string; topics?:string[]; notes?:string[]; facts?:PersonFact[]; last_seen?:number;
    first_seen?:number; source?:string; interaction_count?:number; sentiment?:string;
    sympathy?:number; sympathy_label?:string; _relation?:string;
    is_owner?:boolean; profile?:Record<string,any>; relationship?:any;
    phone?:string; birthday?:string; address?:string; occupation?:string; company?:string;
    review_flag?:{reason?:string; validator?:string; ts?:number}|null;
  }
  const [peopleList, setPeopleList]=useState<PersonEntry[]>([]);
  const [peopleLoading, setPeopleLoading]=useState(false);
  const [peopleSearch, setPeopleSearch]=useState('');
  const [selectedPerson, setSelectedPerson]=useState<PersonEntry|null>(null);
  const [editNote, setEditNote]=useState('');
  const [editingField, setEditingField]=useState<string|null>(null);
  const [editFieldVal, setEditFieldVal]=useState('');
  const [deleteConfirmName, setDeleteConfirmName]=useState<string|null>(null);
  const [glossaryReviewMsg, setGlossaryReviewMsg]=useState('');
  const [glossaryReviewBusy, setGlossaryReviewBusy]=useState(false);
  const [glossaryPurgeConfirm, setGlossaryPurgeConfirm]=useState(false);

  // ── Relationship Editor State (Simon ↔ Ailey) ──
  const [relData, setRelData] = useState<any>(null);
  const [relLevels, setRelLevels] = useState<string[]>([]);
  const [relAvailTags, setRelAvailTags] = useState<string[]>([]);
  const [relSaving, setRelSaving] = useState(false);
  const [relMsg, setRelMsg] = useState('');
  const [relNewTag, setRelNewTag] = useState('');
  const [relUserNote, setRelUserNote] = useState('');
  const loadRelationship = async () => {
    try {
      const r = await fetch(api('/api/profile/relationship', apiBaseRef));
      const j = await r.json();
      if (j.success) {
        setRelData(j.relationship);
        setRelLevels(j.available_levels || []);
        setRelAvailTags(j.available_tags || []);
        setRelUserNote(j.relationship?.user_note || '');
      }
    } catch {}
  };
  const saveRel = async (body: any) => {
    setRelSaving(true);
    try {
      const r = await fetch(api('/api/profile/relationship', apiBaseRef), { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
      const j = await r.json();
      if (j.success) { setRelData(j.relationship); setRelMsg('✓ Gespeichert'); }
      else setRelMsg('Fehler');
    } catch { setRelMsg('Fehler'); }
    setRelSaving(false);
    setTimeout(() => setRelMsg(''), 2000);
  };

  async function loadPeople(){
    setPeopleLoading(true);
    try{
      const r=await fetch(api('/api/people/glossary',apiBaseRef));
      const j=await r.json();
      if(j.success) setPeopleList(j.people||[]);
    }catch(e){console.error('people load error',e);}
    finally{setPeopleLoading(false);}
  }

  async function searchPeople(q:string){
    if(!q.trim()){loadPeople();return;}
    setPeopleLoading(true);
    try{
      const r=await fetch(api(`/api/people/search?q=${encodeURIComponent(q)}`,apiBaseRef));
      const j=await r.json();
      if(j.success){
        if(j.person) setPeopleList([j.person]);
        else if(j.results) setPeopleList(j.results);
      }
    }catch(e){console.error('people search error',e);}
    finally{setPeopleLoading(false);}
  }

  async function addPersonNote(name:string, note:string){
    if(!note.trim()) return;
    try{
      await fetch(api('/api/people/note',apiBaseRef),{
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name,note}),
      });
      setEditNote('');
      loadPeople();
      if(selectedPerson?.name===name){
        const r=await fetch(api(`/api/people/search?q=${encodeURIComponent(name)}`,apiBaseRef));
        const j=await r.json();
        if(j.success && j.person) setSelectedPerson(j.person);
      }
    }catch(e){console.error('add note error',e);}
  }

  async function deletePerson(name:string){
    try{
      const r=await fetch(api(`/api/people/${encodeURIComponent(name)}`,apiBaseRef),{method:'DELETE'});
      const j=await r.json();
      if(j.success){
        setSelectedPerson(null);
        setDeleteConfirmName(null);
        loadPeople();
      }
    }catch(e){console.error('delete person error',e);}
  }

  async function updatePersonField(name:string, field:string, value:any){
    try{
      const r=await fetch(api('/api/people/update',apiBaseRef),{
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name, [field]: value}),
      });
      const j=await r.json();
      if(j.success && j.person) {
        setSelectedPerson(j.person);
        loadPeople();
      }
    }catch(e){console.error('update person error',e);}
    setEditingField(null);
  }

  async function updateOwnerProfile(fields:Record<string,string>){
    try{
      const r=await fetch(api('/api/profile/update-fields',apiBaseRef),{
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({fields}),
      });
      const j=await r.json();
      if(j.success) loadPeople();
    }catch(e){console.error('update owner error',e);}
    setEditingField(null);
  }

  async function adjustSympathy(person:string, delta:number, reason:string){
    try{
      await fetch(api('/api/sympathy/adjust',apiBaseRef),{
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({person, delta, reason}),
      });
      loadPeople();
    }catch(e){console.error('adjust sympathy error',e);}
  }

  async function runGlossaryReview(){
    setGlossaryReviewBusy(true); setGlossaryReviewMsg('');
    try{
      const r=await fetch(api('/api/people/cleanup',apiBaseRef),{
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({use_llm:true}),
      });
      const j=await r.json();
      if(j.success){
        const parts:string[]=[];
        if(j.flagged_now?.length) parts.push(`${j.flagged_now.length} neu markiert`);
        if(j.cleared_now?.length) parts.push(`${j.cleared_now.length} rehabilitiert`);
        if(!parts.length && j.total_flagged) parts.push(`${j.total_flagged} markiert (unverändert)`);
        if(!parts.length) parts.push('alles clean ✓');
        setGlossaryReviewMsg('Nitro-Prüfung: '+parts.join(', '));
        loadPeople();
      }else{
        setGlossaryReviewMsg(j.error||'Fehler');
      }
    }catch(e:any){ setGlossaryReviewMsg(e?.message||'Netzwerkfehler'); }
    finally{ setGlossaryReviewBusy(false); setTimeout(()=>setGlossaryReviewMsg(''),6000); }
  }

  async function purgeFlaggedPeople(){
    setGlossaryReviewBusy(true);
    try{
      const r=await fetch(api('/api/people/purge-flagged',apiBaseRef),{method:'POST'});
      const j=await r.json();
      if(j.success){
        setGlossaryReviewMsg(`🗑️ ${j.count} markierte Einträge gelöscht`);
        loadPeople();
      }else{
        setGlossaryReviewMsg(j.error||'Fehler');
      }
    }catch(e:any){ setGlossaryReviewMsg(e?.message||'Netzwerkfehler'); }
    finally{
      setGlossaryReviewBusy(false); setGlossaryPurgeConfirm(false);
      setTimeout(()=>setGlossaryReviewMsg(''),6000);
    }
  }

  async function clearPersonFlag(name:string){
    try{
      const r=await fetch(api('/api/people/clear-flag',apiBaseRef),{
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name}),
      });
      const j=await r.json();
      if(j.success){
        if(selectedPerson?.name===name){
          const {review_flag:_rf, ...rest}=selectedPerson;
          setSelectedPerson(rest as PersonEntry);
        }
        loadPeople();
      }
    }catch(e){console.error('clear flag error',e);}
  }

  useEffect(()=>{
    if(active==='people'){ loadPeople(); loadRelationship(); }
  },[active]);

  function relTime(ts?:number){
    if(!ts) return '–';
    const diff=(Date.now()/1000)-ts;
    if(diff<3600) return 'gerade eben';
    if(diff<86400) return `vor ${Math.floor(diff/3600)}h`;
    if(diff<604800) return `vor ${Math.floor(diff/86400)}d`;
    return new Date(ts*1000).toLocaleDateString('de-DE');
  }

  const sentimentEmoji=(s?:string)=>({positiv:'😊',neutral:'😐',negativ:'😕'}[s||'neutral']||'😐');
  const sourceLabel=(s?:string)=>({chat:'💬 Chat',email:'📧 E-Mail',diary:'📖 Tagebuch',manual:'✏️ Manuell',profile:'👤 Profil'}[s||'chat']||s);
  const sympathyColor=(s?:number)=>{
    if(!s && s!==0) return 'bg-muted';
    if(s>=75) return 'bg-pink-500';
    if(s>=50) return 'bg-amber-400';
    if(s>=25) return 'bg-orange-400';
    return 'bg-red-400';
  };

  // Helper: get relation text from facts
  const getRelation=(p:PersonEntry)=>{
    if(p._relation) return p._relation;
    if(p.relation) return p.relation;
    const relFact = (p.facts||[]).find(f=>f._type==='relation');
    if(relFact) return relFact.text;
    // First fact as fallback summary
    return (p.facts||[])[0]?.text || '';
  };

  // ── Inline editable field component ──
  const InlineEdit=({label, value, onSave, placeholder}:{label:string, value:string, onSave:(v:string)=>void, placeholder?:string})=>{
    const isEditing = editingField === label;
    return (
      <div className="flex items-center gap-2 group">
        <span className="text-xs font-medium text-muted-foreground w-24 shrink-0">{label}</span>
        {isEditing ? (
          <div className="flex gap-1 flex-1">
            <input autoFocus value={editFieldVal} onChange={e=>setEditFieldVal(e.target.value)}
              onKeyDown={e=>{if(e.key==='Enter'){onSave(editFieldVal);} if(e.key==='Escape') setEditingField(null);}}
              className="flex-1 px-2 py-1 rounded bg-muted border border-border text-sm focus:outline-none" placeholder={placeholder}/>
            <button onClick={()=>onSave(editFieldVal)} className="px-2 py-1 rounded bg-primary text-primary-foreground text-xs">✓</button>
            <button onClick={()=>setEditingField(null)} className="px-2 py-1 rounded bg-muted text-muted-foreground text-xs">✕</button>
          </div>
        ) : (
          <div className="flex items-center gap-1 flex-1 cursor-pointer" onClick={()=>{setEditingField(label);setEditFieldVal(value||'');}}>
            <span className="text-sm truncate">{value || <span className="text-muted-foreground italic">–</span>}</span>
            <Pencil className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition shrink-0"/>
          </div>
        )}
      </div>
    );
  };

  const PeopleSection=()=>{
    // Separate owner from others
    const ownerEntry = peopleList.find(p=>p.is_owner);
    const otherPeople = peopleList.filter(p=>!p.is_owner);

    return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="text-center mb-8">
        <h2 className="text-2xl font-bold">Personen-Glossar</h2>
        <p className="text-sm text-muted-foreground mt-1">Alle Menschen in deinem Leben — mit Beziehungswerten aus der LifeSim, editierbaren Details und Aileys Sympathie-System.</p>
      </div>

      {/* ═══ Owner Profile Card (Simon) ═══ */}
      {ownerEntry && !selectedPerson && (
        <Card className="p-6 space-y-5 border-pink-500/30 mb-8 max-w-3xl mx-auto">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold flex items-center gap-2">👤 {ownerEntry.full_name || ownerEntry.name}</h3>
            {ownerEntry.sympathy != null && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Sympathie</span>
                <div className="w-24 h-2 rounded-full bg-muted overflow-hidden">
                  <div className={`h-full rounded-full ${sympathyColor(ownerEntry.sympathy)} transition-all`} style={{width:`${ownerEntry.sympathy}%`}}/>
                </div>
                <span className="text-xs font-medium">{ownerEntry.sympathy_label}</span>
              </div>
            )}
          </div>

          {/* ── Editable profile fields ── */}
          <div className="space-y-2">
            <InlineEdit label="Name" value={ownerEntry.profile?.full_name || ownerEntry.full_name || ownerEntry.name}
              onSave={(v)=>updateOwnerProfile({full_name:v, name:v.split(' ')[0]})} placeholder="Vollständiger Name"/>
            <InlineEdit label="Wohnort" value={ownerEntry.profile?.wohnort || ''}
              onSave={(v)=>updateOwnerProfile({wohnort:v})} placeholder="z.B. Köln"/>
            <InlineEdit label="Arbeitsort" value={ownerEntry.profile?.arbeitsort || ''}
              onSave={(v)=>updateOwnerProfile({arbeitsort:v})} placeholder="z.B. Düsseldorf"/>
            <InlineEdit label="Arbeitgeber" value={ownerEntry.profile?.arbeitgeber || ''}
              onSave={(v)=>updateOwnerProfile({arbeitgeber:v})} placeholder="Simon van de Loo, MediaDesigner & Developer"/>
            <InlineEdit label="E-Mail" value={ownerEntry.profile?.email || ''}
              onSave={(v)=>updateOwnerProfile({email:v})} placeholder="deine@email.de"/>
            <InlineEdit label="Telefon" value={ownerEntry.profile?.phone || ''}
              onSave={(v)=>updateOwnerProfile({phone:v})} placeholder="+49 …"/>
            <InlineEdit label="Geburtstag" value={ownerEntry.profile?.birthday || ''}
              onSave={(v)=>updateOwnerProfile({birthday:v})} placeholder="YYYY-MM-DD"/>
            <InlineEdit label="Adresse" value={ownerEntry.profile?.address || ''}
              onSave={(v)=>updateOwnerProfile({address:v})} placeholder="Straße, Stadt"/>
            <InlineEdit label="Beruf" value={ownerEntry.profile?.occupation || ''}
              onSave={(v)=>updateOwnerProfile({occupation:v})} placeholder="z.B. Geschäftsführer, Designer …"/>
            <InlineEdit label="Firma" value={ownerEntry.profile?.company || ''}
              onSave={(v)=>updateOwnerProfile({company:v})} placeholder="Simon van de Loo, MediaDesigner & Developer"/>
            <InlineEdit label="Sprache" value={ownerEntry.profile?.sprache || 'Deutsch'}
              onSave={(v)=>updateOwnerProfile({sprache:v})} placeholder="Deutsch"/>
            <InlineEdit label="Anrede" value={ownerEntry.profile?.anrede || 'du'}
              onSave={(v)=>updateOwnerProfile({anrede:v})} placeholder="du / Sie"/>
            {/* Custom fields */}
            {ownerEntry.profile?.custom && Object.entries(ownerEntry.profile.custom).map(([k,v])=>(
              <InlineEdit key={k} label={k.replace(/_/g,' ')} value={String(v)}
                onSave={(val)=>updateOwnerProfile({[`custom.${k}`]:val})}/>
            ))}
          </div>

          {/* ── Beziehung: Simon ↔ Ailey (integrated) ── */}
          {relData && (
            <div className="border-t border-border pt-4 space-y-3">
              <h4 className="text-sm font-semibold flex items-center gap-2">💕 Beziehung zu Ailey</h4>
              {/* Level selector */}
              <div>
                <div className="text-xs font-medium mb-1.5">Beziehungsstufe</div>
                <div className="flex flex-wrap gap-1.5">
                  {relLevels.map(l => (
                    <button key={l} onClick={() => saveRel({ level: l })} disabled={relSaving}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition ${relData.level === l ? 'bg-pink-500 text-white' : 'bg-muted hover:bg-muted/80 text-muted-foreground'}`}>
                      {l}
                    </button>
                  ))}
                </div>
              </div>
              {/* Tags */}
              {relAvailTags.length > 0 && (
                <div>
                  <div className="text-xs font-medium mb-1.5">Tags</div>
                  <div className="flex flex-wrap gap-1.5">
                    {relAvailTags.map(t => {
                      const isActive = (relData.tags || []).includes(t);
                      return (
                        <button key={t} onClick={() => {
                          const tags = isActive ? (relData.tags || []).filter((x: string) => x !== t) : [...(relData.tags || []), t];
                          saveRel({ tags });
                        }} disabled={relSaving}
                          className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition ${isActive ? 'bg-pink-500/20 text-pink-400 border border-pink-500/40' : 'bg-muted hover:bg-muted/80 text-muted-foreground'}`}>
                          {isActive ? '✓ ' : ''}{t}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              {/* User note */}
              <div>
                <div className="text-xs font-medium mb-1">Deine Notiz</div>
                <div className="flex gap-2">
                  <input value={relUserNote} onChange={e => setRelUserNote(e.target.value)}
                    placeholder="z.B. 'Ailey ist meine kreative Partnerin'"
                    className="flex-1 px-3 py-1.5 rounded-lg bg-muted border border-border text-sm focus:outline-none" />
                  <button onClick={() => saveRel({ user_note: relUserNote })} disabled={relSaving}
                    className="px-3 py-1.5 rounded-lg bg-pink-500 text-white text-sm font-medium hover:bg-pink-600 transition disabled:opacity-50">
                    Speichern
                  </button>
                </div>
              </div>
              {/* Ailey's perspective */}
              {relData.ailey_perspective && (
                <div className="rounded-lg bg-pink-500/5 border border-pink-500/10 p-3">
                  <div className="text-xs font-semibold text-pink-400 mb-1">Aileys Perspektive</div>
                  <p className="text-sm text-foreground/80">{relData.ailey_perspective}</p>
                </div>
              )}
              {/* Notes timeline */}
              {relData.notes && relData.notes.length > 0 && (
                <div>
                  <div className="text-xs font-medium mb-1">Verlauf</div>
                  <div className="space-y-1 max-h-[120px] overflow-y-auto">
                    {relData.notes.slice(-5).reverse().map((n: any, i: number) => (
                      <div key={i} className="text-[11px] text-muted-foreground pl-3 border-l-2 border-pink-500/20">
                        {typeof n === 'string' ? n : n.text || JSON.stringify(n)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {relMsg && <span className="text-xs text-pink-400">{relMsg}</span>}
            </div>
          )}
        </Card>
      )}

      {/* Search + Glossary-Review actions */}
      {!selectedPerson && (
        <div className="max-w-3xl mx-auto mb-6 space-y-2">
          <div className="flex gap-2">
            <input
              className="flex-1 px-4 py-2 rounded-lg bg-card border border-border text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              placeholder="Person suchen…"
              value={peopleSearch}
              onChange={e=>{setPeopleSearch(e.target.value); if(!e.target.value) loadPeople();}}
              onKeyDown={e=>{if(e.key==='Enter') searchPeople(peopleSearch);}}
            />
            <button
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition"
              onClick={()=>searchPeople(peopleSearch)}
            >Suchen</button>
          </div>
          {(() => {
            const flaggedCount = peopleList.filter(p => !p.is_owner && p.review_flag).length;
            return (
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <button
                  onClick={runGlossaryReview}
                  disabled={glossaryReviewBusy}
                  className="px-3 py-1.5 rounded-lg bg-muted hover:bg-muted/80 border border-border text-muted-foreground hover:text-foreground transition disabled:opacity-50"
                  title="Nitro-2B prüft alle Einträge und markiert verdächtige (ohne zu löschen)."
                >🧹 Glossar via Nitro prüfen</button>
                {flaggedCount > 0 && (
                  glossaryPurgeConfirm ? (
                    <>
                      <span className="text-red-400">Wirklich alle {flaggedCount} markierten löschen?</span>
                      <button onClick={purgeFlaggedPeople} disabled={glossaryReviewBusy}
                        className="px-2 py-1 rounded bg-red-500 text-white hover:bg-red-600 transition disabled:opacity-50">Ja, löschen</button>
                      <button onClick={()=>setGlossaryPurgeConfirm(false)}
                        className="px-2 py-1 rounded bg-muted hover:bg-muted/80 transition">Abbrechen</button>
                    </>
                  ) : (
                    <button
                      onClick={()=>setGlossaryPurgeConfirm(true)}
                      className="px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 transition"
                      title="Alle Einträge mit 🚩-Flag endgültig löschen"
                    >🚩 {flaggedCount} markierte löschen</button>
                  )
                )}
                {glossaryReviewMsg && <span className="text-muted-foreground">{glossaryReviewMsg}</span>}
              </div>
            );
          })()}
        </div>
      )}

      {peopleLoading ? (
        <div className="text-center text-muted-foreground py-12"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2"/>Lade…</div>
      ) : otherPeople.length===0 && !selectedPerson ? (
        <div className="text-center text-muted-foreground py-12">
          <Users className="w-12 h-12 mx-auto mb-3 opacity-30"/>
          <p>Noch keine Personen im Glossar.</p>
          <p className="text-xs mt-1">Ailey lernt automatisch Personen kennen wenn du über sie sprichst oder E-Mails bekommst.</p>
        </div>
      ) : selectedPerson ? (
        /* ═══ Detail view (glossary person OR owner) ═══ */
        <div className="bg-card rounded-2xl border border-border p-6 max-w-2xl mx-auto">
          <button onClick={()=>{setSelectedPerson(null);setEditingField(null);}} className="text-xs text-muted-foreground hover:text-foreground mb-4 flex items-center gap-1">
            <ChevronLeft className="w-3 h-3"/> Zurück zur Liste
          </button>
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-xl font-bold">
                {selectedPerson.review_flag && <span className="mr-1">🚩</span>}
                {selectedPerson.name}
              </h3>
              {selectedPerson.aliases && selectedPerson.aliases.length>0 && (
                <p className="text-xs text-muted-foreground">aka {selectedPerson.aliases.join(', ')}</p>
              )}
            </div>
            <span className="text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground">{sourceLabel(selectedPerson.source)}</span>
          </div>

          {/* ── Review flag banner ── */}
          {selectedPerson.review_flag && (
            <div className="mb-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-between gap-2">
              <div className="text-xs text-amber-300">
                🚩 Als möglicherweise keine echte Person markiert
                <span className="text-muted-foreground"> · {selectedPerson.review_flag.validator||'?'} · {selectedPerson.review_flag.reason||''}</span>
              </div>
              <button onClick={()=>clearPersonFlag(selectedPerson.name)}
                className="text-xs px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 transition shrink-0">
                Doch eine Person
              </button>
            </div>
          )}

          {/* ── Sympathy bar ── */}
          {selectedPerson.sympathy != null && (
            <div className="mb-4 p-3 rounded-lg bg-muted/50 border border-border">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-medium">Aileys Sympathie</span>
                <span className="text-xs">{selectedPerson.sympathy_label} ({selectedPerson.sympathy}/100)</span>
              </div>
              <div className="w-full h-2.5 rounded-full bg-muted overflow-hidden">
                <div className={`h-full rounded-full ${sympathyColor(selectedPerson.sympathy)} transition-all duration-500`} style={{width:`${selectedPerson.sympathy}%`}}/>
              </div>
              <div className="flex gap-1 mt-2">
                <button onClick={()=>adjustSympathy(selectedPerson.name, 5, 'Manuell erhöht')} className="px-2 py-0.5 rounded text-[10px] bg-pink-500/10 text-pink-400 hover:bg-pink-500/20" title="Sympathie +5">+5 ❤️</button>
                <button onClick={()=>adjustSympathy(selectedPerson.name, -5, 'Manuell gesenkt')} className="px-2 py-0.5 rounded text-[10px] bg-red-500/10 text-red-400 hover:bg-red-500/20" title="Sympathie -5">-5 💔</button>
              </div>
            </div>
          )}

          {/* ── Editable relation ── */}
          <InlineEdit label="Beziehung" value={getRelation(selectedPerson)}
            onSave={(v)=>updatePersonField(selectedPerson.name, 'relation', v)} placeholder="z.B. Kollege, Freund…"/>
          <div className="mt-1"/>
          <InlineEdit label="E-Mail" value={selectedPerson.email || ''}
            onSave={(v)=>updatePersonField(selectedPerson.name, 'email', v)} placeholder="person@example.de"/>
          <div className="mt-1"/>
          <InlineEdit label="Telefon" value={selectedPerson.phone || ''}
            onSave={(v)=>updatePersonField(selectedPerson.name, 'phone', v)} placeholder="+49 …"/>
          <div className="mt-1"/>
          <InlineEdit label="Geburtstag" value={selectedPerson.birthday || ''}
            onSave={(v)=>updatePersonField(selectedPerson.name, 'birthday', v)} placeholder="YYYY-MM-DD oder MM-DD"/>
          <div className="mt-1"/>
          <InlineEdit label="Adresse" value={selectedPerson.address || ''}
            onSave={(v)=>updatePersonField(selectedPerson.name, 'address', v)} placeholder="Straße, Stadt"/>
          <div className="mt-1"/>
          <InlineEdit label="Beruf" value={selectedPerson.occupation || ''}
            onSave={(v)=>updatePersonField(selectedPerson.name, 'occupation', v)} placeholder="z.B. Autorin, Designer …"/>
          <div className="mt-1"/>
          <InlineEdit label="Firma" value={selectedPerson.company || ''}
            onSave={(v)=>updatePersonField(selectedPerson.name, 'company', v)} placeholder="Arbeitgeber / Firma"/>

          {/* ── Facts (from AI/emails/diary) ── */}
          {selectedPerson.facts && selectedPerson.facts.length>0 && (
            <div className="mt-4 mb-4">
              <h4 className="text-xs font-semibold mb-2 text-muted-foreground uppercase tracking-wide">Fakten & Notizen</h4>
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                {selectedPerson.facts.map((f,i)=>(
                  <div key={i} className="text-sm pl-3 border-l-2 border-border flex items-start justify-between gap-2">
                    <span className="text-foreground/80">{f.text}</span>
                    <span className="text-[10px] text-muted-foreground shrink-0">{sourceLabel(f.source)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Legacy notes/topics fallback */}
          {selectedPerson.topics && selectedPerson.topics.length>0 && (
            <div className="flex flex-wrap gap-1 mb-3">
              {selectedPerson.topics.map((t,i)=><span key={i} className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">{t}</span>)}
            </div>
          )}
          {selectedPerson.notes && selectedPerson.notes.length>0 && !selectedPerson.facts?.length && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold mb-1">Notizen</h4>
              <ul className="space-y-1">
                {selectedPerson.notes.map((n,i)=><li key={i} className="text-sm text-muted-foreground pl-3 border-l-2 border-border">{n}</li>)}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4 mt-3">
            <span>Erstmals: {relTime(selectedPerson.first_seen)}</span>
            <span>•</span>
            <span>Zuletzt: {relTime(selectedPerson.last_seen)}</span>
            <span>•</span>
            <span>{selectedPerson.interaction_count||0}× erwähnt</span>
          </div>
          {/* Add note */}
          <div className="flex gap-2">
            <input
              className="flex-1 px-3 py-1.5 rounded-lg bg-muted border border-border text-sm placeholder:text-muted-foreground focus:outline-none"
              placeholder="Notiz / Fakt hinzufügen…"
              value={editNote}
              onChange={e=>setEditNote(e.target.value)}
              onKeyDown={e=>{if(e.key==='Enter') addPersonNote(selectedPerson.name,editNote);}}
            />
            <button onClick={()=>addPersonNote(selectedPerson.name,editNote)} className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm">+</button>
          </div>
          {deleteConfirmName===selectedPerson.name ? (
            <div className="flex items-center gap-2 mt-4">
              <span className="text-xs text-red-400">Wirklich entfernen?</span>
              <button onClick={()=>deletePerson(selectedPerson.name)} className="text-xs px-2 py-1 rounded bg-red-500 text-white hover:bg-red-600 transition">Ja, löschen</button>
              <button onClick={()=>setDeleteConfirmName(null)} className="text-xs px-2 py-1 rounded bg-muted hover:bg-muted/80 transition">Abbrechen</button>
            </div>
          ) : (
            <button onClick={()=>setDeleteConfirmName(selectedPerson.name)} className="text-xs text-red-400 hover:text-red-300 mt-4">Aus Glossar entfernen</button>
          )}
        </div>
      ) : (
        /* ═══ List view ═══ */
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {otherPeople.map(p=>(
            <button
              key={p.id}
              onClick={()=>setSelectedPerson(p)}
              className="bg-card rounded-xl border border-border p-4 text-left hover:border-primary/40 transition-all group"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold truncate">
                  {p.review_flag && <span title={`Markiert: ${p.review_flag.reason||''} (${p.review_flag.validator||''})`} className="mr-1">🚩</span>}
                  {p.name}
                </span>
                <span className="text-[10px] text-muted-foreground">{relTime(p.last_seen)}</span>
              </div>
              {getRelation(p) && <p className="text-xs text-primary/80 mb-1 truncate">{getRelation(p)}</p>}
              {/* Sympathy mini bar */}
              {p.sympathy != null && (
                <div className="flex items-center gap-2 mb-1">
                  <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${sympathyColor(p.sympathy)}`} style={{width:`${p.sympathy}%`}}/>
                  </div>
                  <span className="text-[9px] text-muted-foreground">{Math.round(p.sympathy)}</span>
                </div>
              )}
              <div className="flex items-center gap-2 mt-2 text-[10px] text-muted-foreground">
                <span>{sourceLabel(p.source)}</span>
                <span>•</span>
                <span>{p.interaction_count||0}× erwähnt</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );};

  // --- A!leys Gedanken (Idle Thinker v2) Section ---
  interface ThoughtMetadata { trigger?:string; emotion?:string; topics?:string[]; decision?:string; queries?:string[]; song_title?:string; chain_parent?:string; idle_seconds?:number; context_lines?:number; stored_count?:number; research_results?:any[]; what_works?:string; improve?:string; next_step?:string; long_term?:string }
  interface ThoughtEntry { ts?:number; dt?:string; type?:string; decision?:string; thought?:string; thought_chain?:string; text?:string; raw?:string; raw_output?:string; queries?:string[]; stored_count?:number; research_results?:any[]; idle_seconds?:number; conversation_context_lines?:number; metadata?:ThoughtMetadata; song_title?:string; training_pair?:{system?:string;user?:string;assistant?:string} }

  // ── Calendar Section ─────────────────────────────────────────────────────
  interface CalEvent { id:string; title:string; date:string; time:string; end_time?:string; duration_minutes:number; location?:string; notes?:string; category:string; color:string; source?:string; reminder?:boolean; reminder_fired?:boolean; }
  interface CalBirthday { name:string; date:string; notes?:string; }
  const [calEvents, setCalEvents]=useState<CalEvent[]>([]);
  const [calBirthdays, setCalBirthdays]=useState<CalBirthday[]>([]);
  const [calMonth, setCalMonth]=useState(()=>{const d=new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;});
  const [calLoading, setCalLoading]=useState(false);
  const [calShowAdd, setCalShowAdd]=useState(false);
  const [calShowBday, setCalShowBday]=useState(false);
  const [calSelectedDay, setCalSelectedDay]=useState<string>('');
  const [calForm, setCalForm]=useState({title:'',date:'',time:'',duration:'60',location:'',notes:'',category:'event',reminder:false});
  const [calBdayForm, setCalBdayForm]=useState({name:'',date:'',notes:''});
  const [calView, setCalView]=useState<'month'|'day'>('month');
  const [calReminderDue, setCalReminderDue]=useState<CalEvent[]>([]);

  async function loadCalendar(month?:string){
    setCalLoading(true);
    const m=month||calMonth;
    try{
      const r=await fetch(api(`/api/calendar/events?month=${m}`,apiBaseRef));
      const j=await r.json();
      if(j.success) setCalEvents(j.events||[]);
      const r2=await fetch(api('/api/calendar/birthdays',apiBaseRef));
      const j2=await r2.json();
      if(j2.success) setCalBirthdays(j2.birthdays||[]);
    }catch(e){console.error('calendar load',e);}
    finally{setCalLoading(false);}
  }

  async function addCalEvent(){
    if(!calForm.title||!calForm.date) return;
    try{
      await fetch(api('/api/calendar/events',apiBaseRef),{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...calForm,duration_minutes:parseInt(calForm.duration)||60,reminder:calForm.reminder}),
      });
      setCalForm({title:'',date:'',time:'',duration:'60',location:'',notes:'',category:'event',reminder:false});
      setCalShowAdd(false);
      loadCalendar();
    }catch(e){console.error('add event',e);}
  }

  async function deleteCalEvent(id:string){
    try{
      await fetch(api(`/api/calendar/events/${id}`,apiBaseRef),{method:'DELETE'});
      loadCalendar();
    }catch(e){console.error('delete event',e);}
  }

  // Calendar edit state
  const [calEditId, setCalEditId]=useState<string|null>(null);
  const [calEditForm, setCalEditForm]=useState({title:'',date:'',time:'',duration:'60',location:'',notes:'',category:'event'});

  function startEditEvent(e:CalEvent){
    setCalEditId(e.id);
    setCalEditForm({title:e.title, date:e.date, time:e.time||'', duration:String(e.duration_minutes||60), location:e.location||'', notes:e.notes||'', category:e.category||'event'});
  }

  async function updateCalEvent(){
    if(!calEditId||!calEditForm.title||!calEditForm.date) return;
    try{
      await fetch(api(`/api/calendar/events/${calEditId}`,apiBaseRef),{
        method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...calEditForm, duration_minutes:parseInt(calEditForm.duration)||60}),
      });
      setCalEditId(null);
      loadCalendar();
    }catch(e){console.error('update event',e);}
  }

  async function addCalBirthday(){
    if(!calBdayForm.name||!calBdayForm.date) return;
    try{
      await fetch(api('/api/calendar/birthdays',apiBaseRef),{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(calBdayForm),
      });
      setCalBdayForm({name:'',date:'',notes:''});
      setCalShowBday(false);
      loadCalendar();
    }catch(e){console.error('add bday',e);}
  }

  useEffect(()=>{if(active==='calendar') loadCalendar();},[active]);
  useEffect(()=>{if(active==='calendar') loadCalendar(calMonth);},[calMonth]);

  // Poll for due reminders every 30s (global, not just when calendar is visible)
  useEffect(()=>{
    async function checkReminders(){
      try{
        const r=await fetch(api('/api/calendar/reminders/due',apiBaseRef));
        if(r.ok){
          const j=await r.json();
          if(j.success && j.due && j.due.length>0){
            setCalReminderDue(j.due);
            // Push a reminder as an Ailey chat message
            j.due.forEach((evt:CalEvent)=>{
              const timeStr=evt.time?` um ${evt.time}`:'';
              const locStr=evt.location?` (${evt.location})`:'';
              setMessages(p=>[...p,{id:Date.now()+Math.random()+'',content:`⏰ Erinnerung: **${evt.title}**${timeStr}${locStr}${evt.notes?'\n'+evt.notes:''}`, sender:'ai',timestamp:new Date(), mood:'neutral'}]);
            });
          }
        }
      }catch{}
    }
    checkReminders();
    const iv=setInterval(checkReminders, 30000);
    return ()=>clearInterval(iv);
  },[]);

  function calMonthNav(dir:number){
    const [y,m]=calMonth.split('-').map(Number);
    const d=new Date(y,m-1+dir,1);
    setCalMonth(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`);
  }

  const CalendarSection=()=>{
    const [y,m]=calMonth.split('-').map(Number);
    const firstDay=new Date(y,m-1,1).getDay(); // 0=Sun
    const daysInMonth=new Date(y,m,0).getDate();
    const startOffset=(firstDay+6)%7; // convert to Mon=0
    const today=new Date();
    const todayStr=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
    const monthNames=['','Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
    const dayNames=['Mo','Di','Mi','Do','Fr','Sa','So'];

    // Events grouped by day
    const byDay:Record<string,CalEvent[]>={};
    calEvents.forEach(e=>{const d=e.date; if(!byDay[d]) byDay[d]=[]; byDay[d].push(e);});

    // Selected day events
    const selDayStr=calSelectedDay||todayStr;
    const selEvents=byDay[selDayStr]||[];

    // Upcoming birthdays (next 60 days)
    const upcoming:CalBirthday[]=[];
    calBirthdays.forEach(b=>{
      if(!b.date) return;
      const [bm,bd]=b.date.split('-').map(Number);
      const thisYear=new Date(today.getFullYear(),bm-1,bd);
      const nextYear=new Date(today.getFullYear()+1,bm-1,bd);
      const next=thisYear>=today?thisYear:nextYear;
      const diff=Math.floor((next.getTime()-today.getTime())/(86400000));
      if(diff<=60) upcoming.push({...b,notes:`in ${diff} Tag${diff!==1?'en':''}`});
    });

    // Day planner time slots (6:00 - 23:00)
    const dayHours = Array.from({length:18},(_,i)=>i+6);
    const selDayEvents = (byDay[selDayStr]||[]).filter(e=>!!e.time).sort((a,b)=>(a.time||'').localeCompare(b.time||''));
    const selDayAllDay = (byDay[selDayStr]||[]).filter(e=>!e.time);

    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold">📅 Kalender</h2>
          <p className="text-sm text-muted-foreground mt-1">Aileys interner Kalender — Termine, Deadlines, Geburtstage</p>
          {/* View toggle */}
          <div className="flex justify-center gap-2 mt-3">
            <button onClick={()=>setCalView('month')} className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${calView==='month'?'bg-primary text-primary-foreground':'border border-border hover:bg-primary/10'}`}>Monat</button>
            <button onClick={()=>setCalView('day')} className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${calView==='day'?'bg-primary text-primary-foreground':'border border-border hover:bg-primary/10'}`}>Tagesplaner</button>
          </div>
        </div>

        {/* Month navigation */}
        {calView==='month' && (
        <div className="flex items-center justify-center gap-4 mb-6">
          <button onClick={()=>calMonthNav(-1)} className="p-2 rounded-lg hover:bg-primary/10 transition" title="Vorheriger Monat"><ChevronLeft className="w-4 h-4"/></button>
          <span className="text-lg font-semibold min-w-[180px] text-center">{monthNames[m]} {y}</span>
          <button onClick={()=>calMonthNav(1)} className="p-2 rounded-lg hover:bg-primary/10 transition" title="Nächster Monat"><ChevronRight className="w-4 h-4"/></button>
        </div>
        )}

        {calLoading ? (
          <div className="text-center py-12"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2"/>Lade…</div>
        ) : (
          <>
            {/* Calendar grid */}
            <div className="bg-card rounded-2xl border border-border p-4 mb-6">
              <div className="grid grid-cols-7 gap-1 mb-2">
                {dayNames.map(d=><div key={d} className="text-center text-xs font-semibold text-muted-foreground py-1">{d}</div>)}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {Array.from({length:startOffset}).map((_,i)=><div key={`e${i}`} className="h-12"/>)}
                {Array.from({length:daysInMonth}).map((_,i)=>{
                  const day=i+1;
                  const dateStr=`${y}-${String(m).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                  const isToday=dateStr===todayStr;
                  const isSel=dateStr===selDayStr;
                  const dayEvents=byDay[dateStr]||[];
                  const hasBday=dayEvents.some(e=>e.category==='birthday');
                  return (
                    <button
                      key={day}
                      onClick={()=>setCalSelectedDay(dateStr)}
                      className={`h-12 rounded-lg text-sm relative transition-all flex flex-col items-center justify-center gap-0.5
                        ${isToday?'ring-2 ring-primary font-bold':''}
                        ${isSel?'bg-primary text-primary-foreground':'hover:bg-primary/10'}
                      `}
                    >
                      <span>{day}</span>
                      {dayEvents.length>0 && (
                        <div className="flex gap-0.5">
                          {dayEvents.slice(0,3).map((e,j)=>(
                            <div key={j} className={`w-1.5 h-1.5 rounded-full ${isSel?'bg-primary-foreground/70':''}`}
                              style={isSel?{}:{backgroundColor:e.color||'#8b5cf6'}}/>
                          ))}
                        </div>
                      )}
                      {hasBday && !isSel && <span className="absolute top-0.5 right-1 text-[9px]">🎂</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Selected day events */}
            <div className="bg-card rounded-2xl border border-border p-4 mb-6">
              <h3 className="font-semibold mb-3 text-sm">
                {selDayStr===todayStr ? 'Heute' : new Date(selDayStr+'T00:00:00').toLocaleDateString('de-DE',{weekday:'long',day:'numeric',month:'long'})}
              </h3>
              {selEvents.length===0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">Keine Termine an diesem Tag</p>
              ) : (
                <div className="space-y-2">
                  {selEvents.map(e=> calEditId===e.id ? (
                    /* Inline edit form */
                    <div key={e.id} className="p-3 rounded-xl bg-muted/80 border border-primary/30 space-y-2">
                      <input className="w-full px-3 py-1.5 rounded-lg bg-background border border-border text-sm" placeholder="Titel" value={calEditForm.title} onChange={ev=>setCalEditForm(f=>({...f,title:ev.target.value}))}/>
                      <div className="grid grid-cols-2 gap-2">
                        <input type="date" className="px-3 py-1.5 rounded-lg bg-background border border-border text-sm" title="Datum" value={calEditForm.date} onChange={ev=>setCalEditForm(f=>({...f,date:ev.target.value}))}/>
                        <div className="flex items-center gap-1">
                          <input type="time" className="flex-1 px-3 py-1.5 rounded-lg bg-background border border-border text-sm" title="Uhrzeit (optional)" value={calEditForm.time} onChange={ev=>setCalEditForm(f=>({...f,time:ev.target.value}))}/>
                          {calEditForm.time && <button onClick={()=>setCalEditForm(f=>({...f,time:''}))} className="text-xs text-muted-foreground hover:text-foreground px-1" title="Ganztägig">✕</button>}
                        </div>
                      </div>
                      <input className="w-full px-3 py-1.5 rounded-lg bg-background border border-border text-sm" placeholder="Ort (optional)" value={calEditForm.location} onChange={ev=>setCalEditForm(f=>({...f,location:ev.target.value}))}/>
                      <input className="w-full px-3 py-1.5 rounded-lg bg-background border border-border text-sm" placeholder="Notizen (optional)" value={calEditForm.notes} onChange={ev=>setCalEditForm(f=>({...f,notes:ev.target.value}))}/>
                      <select className="w-full px-3 py-1.5 rounded-lg bg-background border border-border text-sm" title="Kategorie" value={calEditForm.category} onChange={ev=>setCalEditForm(f=>({...f,category:ev.target.value}))}>
                        <option value="event">Termin</option>
                        <option value="meeting">Meeting</option>
                        <option value="deadline">Deadline</option>
                        <option value="personal">Persönlich</option>
                      </select>
                      <div className="flex gap-2 justify-end">
                        <button onClick={()=>setCalEditId(null)} className="px-3 py-1 rounded-lg text-xs text-muted-foreground hover:bg-muted transition">Abbrechen</button>
                        <button onClick={updateCalEvent} className="px-3 py-1 rounded-lg text-xs bg-primary text-primary-foreground hover:opacity-90 transition flex items-center gap-1"><Check className="w-3 h-3"/>Speichern</button>
                      </div>
                    </div>
                  ) : (
                    <div key={e.id} className="flex items-start gap-3 p-3 rounded-xl bg-muted/50 group">
                      <div className="w-1 h-full min-h-[40px] rounded-full shrink-0" style={{backgroundColor:e.color||'#8b5cf6'}}/>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{e.title}</span>
                          {e.category==='birthday' && <span className="text-xs">🎂</span>}
                          {e.reminder && <Bell className="w-3 h-3 text-amber-400"/>}
                          {!e.time && e.category!=='birthday' && <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">ganztägig</span>}
                        </div>
                        {e.time && <p className="text-xs text-muted-foreground">{e.time}{e.end_time?` – ${e.end_time}`:''}</p>}
                        {e.location && <p className="text-xs text-muted-foreground">📍 {e.location}</p>}
                        {e.notes && <p className="text-xs text-muted-foreground mt-1">{e.notes}</p>}
                      </div>
                      {e.source!=='birthday' && (
                        <div className="flex gap-1 shrink-0">
                          <button onClick={()=>startEditEvent(e)} className="text-muted-foreground hover:text-foreground transition p-1.5 rounded-md hover:bg-primary/10" title="Bearbeiten">
                            <Pencil className="w-3.5 h-3.5"/>
                          </button>
                          <button onClick={()=>{if(confirm('Termin löschen?')) deleteCalEvent(e.id)}} className="text-red-400 hover:text-red-300 transition p-1.5 rounded-md hover:bg-red-500/10" title="Löschen">
                            <Trash2 className="w-3.5 h-3.5"/>
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Upcoming birthdays */}
            {upcoming.length>0 && (
              <div className="bg-card rounded-2xl border border-border p-4 mb-6">
                <h3 className="font-semibold mb-3 text-sm">🎂 Nächste Geburtstage</h3>
                <div className="space-y-2">
                  {upcoming.map((b,i)=>(
                    <div key={i} className="flex items-center gap-3 text-sm">
                      <span className="text-pink-400">🎂</span>
                      <span className="font-medium">{b.name}</span>
                      <span className="text-xs text-muted-foreground ml-auto">{b.notes}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Add buttons */}
            <div className="flex gap-3 justify-center mb-6">
              <button onClick={()=>{setCalShowAdd(!calShowAdd);setCalShowBday(false);}} className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition flex items-center gap-2">
                <Plus className="w-3.5 h-3.5"/>Termin
              </button>
              <button onClick={()=>{setCalShowBday(!calShowBday);setCalShowAdd(false);}} className="px-4 py-2 rounded-lg border border-border text-sm font-medium hover:bg-primary/10 transition flex items-center gap-2">
                🎂 Geburtstag
              </button>
            </div>

            {/* Add event form */}
            {calShowAdd && (
              <div className="bg-card rounded-2xl border border-border p-5 max-w-md mx-auto mb-6 space-y-3">
                <h4 className="font-semibold text-sm">Neuer Termin</h4>
                <input className="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm" placeholder="Titel" value={calForm.title} onChange={e=>setCalForm(f=>({...f,title:e.target.value}))}/>
                <div className="grid grid-cols-2 gap-2">
                  <input type="date" className="px-3 py-2 rounded-lg bg-muted border border-border text-sm" title="Datum" value={calForm.date} onChange={e=>setCalForm(f=>({...f,date:e.target.value}))}/>
                  <div className="flex items-center gap-1">
                    <input type="time" className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-sm" title="Uhrzeit (optional — leer = ganztägig)" value={calForm.time} onChange={e=>setCalForm(f=>({...f,time:e.target.value}))}/>
                    {calForm.time && <button onClick={()=>setCalForm(f=>({...f,time:''}))} className="text-xs text-muted-foreground hover:text-foreground px-1" title="Ganztägig">✕</button>}
                  </div>
                </div>
                <input className="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm" placeholder="Ort (optional)" value={calForm.location} onChange={e=>setCalForm(f=>({...f,location:e.target.value}))}/>
                <input className="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm" placeholder="Notizen (optional)" value={calForm.notes} onChange={e=>setCalForm(f=>({...f,notes:e.target.value}))}/>
                <select className="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm" value={calForm.category} onChange={e=>setCalForm(f=>({...f,category:e.target.value}))}>
                  <option value="event">Termin</option>
                  <option value="meeting">Meeting</option>
                  <option value="deadline">Deadline</option>
                  <option value="personal">Persönlich</option>
                </select>
                {calForm.time && (
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={calForm.reminder} onChange={e=>setCalForm(f=>({...f,reminder:e.target.checked}))}/>
                    <Bell className="w-3.5 h-3.5 text-amber-400"/>Ailey erinnert mich zur Uhrzeit
                  </label>
                )}
                <button onClick={addCalEvent} className="w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition">Erstellen</button>
              </div>
            )}

            {/* Add birthday form */}
            {calShowBday && (
              <div className="bg-card rounded-2xl border border-border p-5 max-w-md mx-auto mb-6 space-y-3">
                <h4 className="font-semibold text-sm">🎂 Neuer Geburtstag</h4>
                <input className="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm" placeholder="Name" value={calBdayForm.name} onChange={e=>setCalBdayForm(f=>({...f,name:e.target.value}))}/>
                <input type="text" className="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm" placeholder="Datum (MM-DD, z.B. 03-15)" value={calBdayForm.date} onChange={e=>setCalBdayForm(f=>({...f,date:e.target.value}))}/>
                <input className="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm" placeholder="Notizen (optional)" value={calBdayForm.notes} onChange={e=>setCalBdayForm(f=>({...f,notes:e.target.value}))}/>
                <button onClick={addCalBirthday} className="w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition">Hinzufügen</button>
              </div>
            )}
          </>
        )}

        {/* ── Day Planner View ──────────────────────────────────── */}
        {calView==='day' && !calLoading && (
          <div className="space-y-4">
            {/* Day navigation */}
            <div className="flex items-center justify-center gap-4">
              <button onClick={()=>{const d=new Date(selDayStr+'T00:00:00'); d.setDate(d.getDate()-1); setCalSelectedDay(d.toISOString().slice(0,10));}} className="p-2 rounded-lg hover:bg-primary/10 transition" title="Vorheriger Tag"><ChevronLeft className="w-4 h-4"/></button>
              <span className="text-lg font-semibold min-w-[220px] text-center">
                {new Date(selDayStr+'T00:00:00').toLocaleDateString('de-DE',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}
              </span>
              <button onClick={()=>{const d=new Date(selDayStr+'T00:00:00'); d.setDate(d.getDate()+1); setCalSelectedDay(d.toISOString().slice(0,10));}} className="p-2 rounded-lg hover:bg-primary/10 transition" title="Nächster Tag"><ChevronRight className="w-4 h-4"/></button>
            </div>
            <div className="flex justify-center">
              <button onClick={()=>{setCalSelectedDay(todayStr);}} className="text-xs text-primary hover:underline">Heute</button>
            </div>

            {/* All-day events */}
            {selDayAllDay.length>0 && (
              <div className="bg-card rounded-2xl border border-border p-4">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Ganztägig</h4>
                <div className="space-y-1.5">
                  {selDayAllDay.map(e=>(
                    <div key={e.id} className="flex items-center gap-2 text-sm">
                      <div className="w-2 h-2 rounded-full shrink-0" style={{backgroundColor:e.color||'#8b5cf6'}}/>
                      <span className="font-medium">{e.title}</span>
                      {e.reminder && <Bell className="w-3 h-3 text-amber-400"/>}
                      {e.location && <span className="text-xs text-muted-foreground">📍 {e.location}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Hour grid */}
            <div className="bg-card rounded-2xl border border-border overflow-hidden">
              {dayHours.map(hour=>{
                const hourStr=`${String(hour).padStart(2,'0')}:`;
                const hourEvents=selDayEvents.filter(e=>e.time&&e.time.startsWith(hourStr));
                return (
                  <div key={hour} className={`flex border-b border-border/50 min-h-[48px] ${hour===new Date().getHours()&&selDayStr===todayStr?'bg-primary/5':''}`}>
                    <div className="w-16 shrink-0 text-xs text-muted-foreground py-2 px-3 text-right border-r border-border/50">
                      {String(hour).padStart(2,'0')}:00
                    </div>
                    <div className="flex-1 py-1 px-2 space-y-1">
                      {hourEvents.map(e=>(
                        <div key={e.id} className="flex items-center gap-2 px-2 py-1 rounded-lg text-xs" style={{backgroundColor:(e.color||'#8b5cf6')+'20'}}>
                          <div className="w-1.5 h-full min-h-[20px] rounded-full shrink-0" style={{backgroundColor:e.color||'#8b5cf6'}}/>
                          <div className="flex-1 min-w-0">
                            <span className="font-medium">{e.time}{e.end_time?`–${e.end_time}`:''}</span>
                            <span className="ml-1.5">{e.title}</span>
                            {e.location && <span className="text-muted-foreground ml-1">📍{e.location}</span>}
                          </div>
                          {e.reminder && <Bell className="w-3 h-3 text-amber-400 shrink-0"/>}
                          {e.source!=='birthday' && (
                            <button onClick={()=>{if(confirm('Termin löschen?')) deleteCalEvent(e.id)}} className="text-red-400 hover:text-red-300 p-0.5" title="Löschen"><Trash2 className="w-3 h-3"/></button>
                          )}
                        </div>
                      ))}
                      {hourEvents.length===0 && (
                        <button
                          onClick={()=>{setCalForm(f=>({...f,date:selDayStr,time:`${String(hour).padStart(2,'0')}:00`}));setCalShowAdd(true);setCalView('month');}}
                          className="w-full h-full min-h-[32px] rounded-lg hover:bg-primary/5 transition text-xs text-muted-foreground/30 flex items-center justify-center"
                          title={`Termin um ${hour}:00 hinzufügen`}
                        >+</button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Quick add from day view */}
            <div className="flex gap-3 justify-center">
              <button onClick={()=>{setCalForm(f=>({...f,date:selDayStr}));setCalShowAdd(true);setCalView('month');}} className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition flex items-center gap-2">
                <Plus className="w-3.5 h-3.5"/>Termin hinzufügen
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── Email Inbox Section ─────────────────────────────────────────────────
  interface InboxEmail { id:string; sender:string; subject:string; summary:string; body?:string; ailey_reply?:string; needs_reply?:boolean; account?:string; received_at:string; status:'unread'|'read'|'replied'|'archived'; raw_date?:string; date?:string; ts?:number; }
  const [inboxEmails, setInboxEmails]=useState<InboxEmail[]>([]);
  const [inboxLoading, setInboxLoading]=useState(false);
  const [inboxFilter, setInboxFilter]=useState<'all'|'unread'|'read'|'archived'|'sent'>('all');
  const [expandedInboxId, setExpandedInboxId]=useState<string|null>(null);

  // --- Inbox reply draft state (keyed by email id) ---
  const [inboxReplyDrafts, setInboxReplyDrafts]=useState<Record<string,{draft:string;loading:boolean;sent:boolean;error?:string;replyAs?:string}>>({});
  const [inboxReplyEditing, setInboxReplyEditing]=useState<Record<string,string>>({});
  const [inboxReplyRevOpen, setInboxReplyRevOpen]=useState<Record<string,boolean>>({});
  const [inboxReplyRevInput, setInboxReplyRevInput]=useState<Record<string,string>>({});
  // --- Inbox manual reply (user writes themselves) ---
  const [inboxManualReply, setInboxManualReply]=useState<Record<string,string>>({});
  const [inboxManualSending, setInboxManualSending]=useState<Record<string,boolean>>({});
  const [inboxManualAttachments, setInboxManualAttachments]=useState<Record<string,{name:string;data:string;mime:string}[]>>({});
  // --- Inbox compose new email ---
  const [inboxComposeOpen, setInboxComposeOpen]=useState(false);
  const [inboxComposeTo, setInboxComposeTo]=useState('');
  const [inboxComposeInstruction, setInboxComposeInstruction]=useState('');
  const [inboxComposeSendAs, setInboxComposeSendAs]=useState<'simon'|'ailey'>('simon');
  const [inboxComposeDraft, setInboxComposeDraft]=useState<{id:string;subject:string;body:string;loading:boolean;sent:boolean;error?:string}|null>(null);
  const [inboxComposeEditSubject, setInboxComposeEditSubject]=useState('');
  const [inboxComposeEditBody, setInboxComposeEditBody]=useState('');
  const [inboxComposeAttachments, setInboxComposeAttachments]=useState<{name:string;data:string;mime:string}[]>([]);
  const inboxFileRef = useRef<HTMLInputElement>(null);
  const inboxComposeFileRef = useRef<HTMLInputElement>(null);
  // --- Sent emails ---
  interface SentEmail { id:string; to:string; subject:string; body:string; sent_as:string; reply_to_id?:string; ts:number; dt:string; }
  const [sentEmails, setSentEmails]=useState<SentEmail[]>([]);
  const [sentLoading, setSentLoading]=useState(false);
  const [sentExpanded, setSentExpanded]=useState<string|null>(null);
  // --- Manual compose (user writes completely by themselves) ---
  const [manualComposeOpen, setManualComposeOpen]=useState(false);
  const [manualComposeTo, setManualComposeTo]=useState('');
  const [manualComposeSubject, setManualComposeSubject]=useState('');
  const [manualComposeBody, setManualComposeBody]=useState('');
  const [manualComposeSending, setManualComposeSending]=useState(false);
  const [manualComposeMsg, setManualComposeMsg]=useState('');

  // --- Email contacts for quick-select ---
  const [emailContacts, setEmailContacts]=useState<{name:string;email:string}[]>([]);
  useEffect(()=>{
    if(inboxComposeOpen||manualComposeOpen){
      fetch(api('/api/people/emails',apiBaseRef)).then(r=>r.json()).then(j=>{
        if(j.success) setEmailContacts(j.contacts||[]);
      }).catch(()=>{});
    }
  },[inboxComposeOpen,manualComposeOpen]);

  async function loadSentEmails(){
    setSentLoading(true);
    try{
      const r=await fetch(api('/api/email/sent',apiBaseRef));
      if(r.ok){ const j=await r.json(); if(j.success) setSentEmails(j.emails||[]); }
    }catch(e){console.error('sent load',e);}
    finally{setSentLoading(false);}
  }

  async function sendManualCompose(){
    if(!manualComposeTo.trim()||!manualComposeBody.trim()) return;
    setManualComposeSending(true);
    setManualComposeMsg('');
    try{
      const r=await fetch(api('/api/email/send-manual',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({to:manualComposeTo,subject:manualComposeSubject,body:manualComposeBody,send_as:'simon'})});
      const j=await r.json();
      if(j.success){
        setManualComposeMsg('✅ Gesendet!');
        pushAI('✅ Deine E-Mail wurde gesendet!','happy');
        setTimeout(()=>{setManualComposeOpen(false);setManualComposeTo('');setManualComposeSubject('');setManualComposeBody('');setManualComposeMsg('');},1500);
        loadSentEmails();
      } else {
        setManualComposeMsg(j.error||'Fehler beim Senden');
      }
    }catch(e:any){setManualComposeMsg(e?.message||'Netzwerkfehler');}
    finally{setManualComposeSending(false);}
  }

  // Inbox: request AI draft reply
  async function inboxRequestDraft(emailId:string, replyAs:'simon'|'ailey', instruction?:string, revisionInstruction?:string){
    const currentDraftText = revisionInstruction ? (inboxReplyEditing[emailId]||'') : '';
    setInboxReplyDrafts(prev=>({...prev,[emailId]:{draft:'',loading:true,sent:false,replyAs}}));
    try{
      const r=await fetch(api('/api/email/draft',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message_id:emailId,instruction:instruction||'',reply_as:replyAs,revision_instruction:revisionInstruction||'',current_draft:currentDraftText})});
      const j=await r.json();
      if(j.success&&j.draft){
        setInboxReplyDrafts(prev=>({...prev,[emailId]:{draft:j.draft,loading:false,sent:false,replyAs:j.reply_as||replyAs}}));
        setInboxReplyEditing(prev=>({...prev,[emailId]:j.draft}));
        setInboxReplyRevOpen(prev=>({...prev,[emailId]:false}));
        setInboxReplyRevInput(prev=>({...prev,[emailId]:''}));
      } else {
        setInboxReplyDrafts(prev=>({...prev,[emailId]:{draft:'',loading:false,sent:false,error:j.error||'Fehler beim Entwurf'}}));
      }
    }catch(e:any){
      setInboxReplyDrafts(prev=>({...prev,[emailId]:{draft:'',loading:false,sent:false,error:e?.message||'Netzwerkfehler'}}));
    }
  }

  // Inbox: send drafted reply
  async function inboxSendDraft(emailId:string){
    const edited=inboxReplyEditing[emailId];
    setInboxReplyDrafts(prev=>({...prev,[emailId]:{...prev[emailId],loading:true}}));
    try{
      const r=await fetch(api('/api/email/send',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message_id:emailId,draft:edited})});
      const j=await r.json();
      if(j.success){
        setInboxReplyDrafts(prev=>({...prev,[emailId]:{draft:edited||'',loading:false,sent:true}}));
        updateInboxStatus(emailId,'replied');
        pushAI('✅ Antwort wurde gesendet!','happy');
      } else {
        setInboxReplyDrafts(prev=>({...prev,[emailId]:{...prev[emailId],loading:false,error:j.error||'Fehler beim Senden'}}));
      }
    }catch(e:any){
      setInboxReplyDrafts(prev=>({...prev,[emailId]:{...prev[emailId],loading:false,error:e?.message||'Netzwerkfehler'}}));
    }
  }

  function inboxDiscardDraft(emailId:string){
    setInboxReplyDrafts(prev=>{const n={...prev};delete n[emailId];return n;});
    setInboxReplyEditing(prev=>{const n={...prev};delete n[emailId];return n;});
  }

  // Inbox: send manual reply (user wrote it themselves)
  async function inboxSendManual(emailId:string){
    const text=inboxManualReply[emailId]||'';
    if(!text.trim()) return;
    setInboxManualSending(prev=>({...prev,[emailId]:true}));
    try{
      const r=await fetch(api('/api/email/send',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message_id:emailId,draft:text})});
      const j=await r.json();
      if(j.success){
        setInboxManualReply(prev=>{const n={...prev};delete n[emailId];return n;});
        setInboxManualAttachments(prev=>{const n={...prev};delete n[emailId];return n;});
        updateInboxStatus(emailId,'replied');
        pushAI('✅ Deine Antwort wurde gesendet!','happy');
      }
    }catch(e){console.error('manual send',e);}
    finally{setInboxManualSending(prev=>({...prev,[emailId]:false}));}
  }

  // Inbox: compose new email
  async function inboxComposeNewDraft(){
    if(!inboxComposeTo.trim()||!inboxComposeInstruction.trim()) return;
    setInboxComposeDraft({id:'',subject:'',body:'',loading:true,sent:false});
    try{
      const r=await fetch(api('/api/email/compose',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({to:inboxComposeTo,instruction:inboxComposeInstruction,send_as:inboxComposeSendAs})});
      const j=await r.json();
      if(j.success&&j.compose_id){
        setInboxComposeDraft({id:j.compose_id,subject:j.subject||'',body:j.body||'',loading:false,sent:false});
        setInboxComposeEditSubject(j.subject||'');
        setInboxComposeEditBody(j.body||'');
      } else {
        setInboxComposeDraft(prev=>prev?{...prev,loading:false,error:j.error||'Fehler'}:null);
      }
    }catch(e:any){
      setInboxComposeDraft(prev=>prev?{...prev,loading:false,error:e?.message||'Netzwerkfehler'}:null);
    }
  }

  async function inboxComposeSend(){
    if(!inboxComposeDraft?.id) return;
    setInboxComposeDraft(prev=>prev?{...prev,loading:true}:null);
    try{
      const r=await fetch(api('/api/email/compose/send',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({compose_id:inboxComposeDraft.id,subject:inboxComposeEditSubject,body:inboxComposeEditBody,attachments:inboxComposeAttachments.map(a=>({filename:a.name,data:a.data,content_type:a.mime}))})});
      const j=await r.json();
      if(j.success){
        setInboxComposeDraft(prev=>prev?{...prev,loading:false,sent:true}:null);
        pushAI('✅ E-Mail gesendet! '+(j.message||''),'happy');
        setTimeout(()=>{setInboxComposeOpen(false);setInboxComposeDraft(null);setInboxComposeTo('');setInboxComposeInstruction('');setInboxComposeAttachments([]);},1500);
      } else {
        setInboxComposeDraft(prev=>prev?{...prev,loading:false,error:j.error||'Fehler'}:null);
      }
    }catch(e:any){
      setInboxComposeDraft(prev=>prev?{...prev,loading:false,error:e?.message||'Netzwerkfehler'}:null);
    }
  }

  function handleInboxFileAttach(emailId:string, files:FileList|null){
    if(!files) return;
    Array.from(files).forEach(f=>{
      const reader=new FileReader();
      reader.onload=()=>{
        const b64=(reader.result as string).split(',')[1]||'';
        setInboxManualAttachments(prev=>({...prev,[emailId]:[...(prev[emailId]||[]),{name:f.name,data:b64,mime:f.type}]}));
      };
      reader.readAsDataURL(f);
    });
  }

  function handleComposeFileAttach(files:FileList|null){
    if(!files) return;
    Array.from(files).forEach(f=>{
      const reader=new FileReader();
      reader.onload=()=>{
        const b64=(reader.result as string).split(',')[1]||'';
        setInboxComposeAttachments(prev=>[...prev,{name:f.name,data:b64,mime:f.type}]);
      };
      reader.readAsDataURL(f);
    });
  }

  async function loadInbox(){
    setInboxLoading(true);
    try{
      const r=await fetch(api('/api/email/inbox',apiBaseRef));
      if(r.ok){ const j=await r.json(); if(j.success){
        const mapped=(j.emails||[]).map((e:any)=>({...e, received_at: e.received_at || e.date || (e.ts ? new Date(e.ts*1000).toISOString() : '') }));
        setInboxEmails(mapped);
        // Auto-rescan if inbox is empty (emails processed before inbox feature existed need IMAP backfill)
        if(mapped.length===0){
          console.log('[Inbox] Empty inbox → triggering IMAP rescan to backfill');
          rescanEmails();
        }
      }}
    }catch(e){console.error('inbox load',e);}
    finally{setInboxLoading(false);}
  }

  async function rescanEmails(){
    try{
      const r=await fetch(api('/api/email/rescan',apiBaseRef),{method:'POST'});
      if(r.ok){
        const j=await r.json();
        console.log('[Inbox] Rescan result:',j);
        // Reload inbox after a short delay to let fresh check complete
        setTimeout(()=>loadInbox(),3000);
      }
    }catch(e){console.error('rescan error',e);}
  }

  async function updateInboxStatus(id:string, status:string){
    try{
      await fetch(api(`/api/email/inbox/${id}`,apiBaseRef),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});
      setInboxEmails(prev=>prev.map(e=>e.id===id?{...e,status:status as any}:e));
    }catch(e){console.error('inbox update',e);}
  }

  async function deleteInboxEmail(id:string){
    try{
      await fetch(api(`/api/email/inbox/${id}`,apiBaseRef),{method:'DELETE'});
      setInboxEmails(prev=>prev.filter(e=>e.id!==id));
    }catch(e){console.error('inbox delete',e);}
  }

  function extractEmailAddr(sender:string):string{
    const m=sender.match(/<([^>]+)>/);
    if(m) return m[1].toLowerCase();
    if(sender.includes('@')) return sender.trim().toLowerCase();
    return '';
  }

  const [spamConfirmId, setSpamConfirmId]=useState<string|null>(null);

  async function blockSenderAndRemove(emailId:string, sender:string){
    const addr=extractEmailAddr(sender);
    if(!addr) return;
    try{
      const r=await fetch(api('/api/email/block',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:addr})});
      const j=await r.json();
      if(j.success){
        // Remove all emails from this sender from local state
        setInboxEmails(prev=>prev.filter(e=>!e.sender.toLowerCase().includes(addr)));
        setSpamConfirmId(null);
        setExpandedInboxId(null);
      }
    }catch(e){console.error('block sender error',e);}
  }

  useEffect(()=>{if(active==='inbox'){ loadInbox(); loadSentEmails(); }},[active]);

  const InboxSection=()=>{
    const filtered = inboxFilter==='all' ? inboxEmails : inboxFilter==='sent' ? [] : inboxEmails.filter(e=>e.status===inboxFilter);
    const unreadCount = inboxEmails.filter(e=>e.status==='unread').length;

    const toggleExpand=async (e:InboxEmail)=>{
      if(expandedInboxId===e.id){ setExpandedInboxId(null); return; }
      setExpandedInboxId(e.id);
      if(e.status==='unread') updateInboxStatus(e.id,'read');
      // Lazy-load full body if it was trimmed in the list response
      if((e as any).body_trimmed){
        try{
          const r=await fetch(api(`/api/email/inbox/${encodeURIComponent(e.id)}/body`,apiBaseRef));
          if(r.ok){const j=await r.json(); if(j.success && j.body){
            setInboxEmails(prev=>prev.map(x=>x.id===e.id?{...x, body:j.body, body_trimmed:undefined as any}:x));
          }}
        }catch{}
      }
    };

    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold">📬 Postfach</h2>
          <p className="text-sm text-muted-foreground mt-1">E-Mails{unreadCount>0 && <span className="ml-2 px-1.5 py-0.5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold">{unreadCount} neu</span>}</p>
        </div>

        {/* Filter tabs */}
        <div className="flex flex-wrap gap-2 justify-center mb-6">
          {(['all','unread','read','archived','sent'] as const).map(f=>(
            <button key={f} onClick={()=>{setInboxFilter(f); if(f==='sent') loadSentEmails();}} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${inboxFilter===f?'bg-primary text-primary-foreground':'hover:bg-primary/10 text-muted-foreground'}`}>
              {f==='all'?'Alle':f==='unread'?'Ungelesen':f==='read'?'Gelesen':f==='archived'?'Archiviert':'📤 Gesendet'}
            </button>
          ))}
          <button onClick={()=>{setInboxComposeOpen(o=>!o);setManualComposeOpen(false);}} className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition ${inboxComposeOpen?'bg-primary text-primary-foreground':'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400'}`} title="Neue E-Mail (KI-Entwurf)">
            <Sparkles className="w-3.5 h-3.5"/>Neu (KI)
          </button>
          <button onClick={()=>{setManualComposeOpen(o=>!o);setInboxComposeOpen(false);}} className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition ${manualComposeOpen?'bg-primary text-primary-foreground':'bg-sky-500/10 hover:bg-sky-500/20 text-sky-400'}`} title="Neue E-Mail selbst schreiben">
            <Pencil className="w-3.5 h-3.5"/>Neu (Selbst)
          </button>
          <button onClick={()=>{loadInbox();loadSentEmails();}} className="px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-primary/10 text-muted-foreground transition" title="Aktualisieren">
            <RotateCcw className="w-3.5 h-3.5"/>
          </button>
          <button onClick={()=>{rescanEmails();}} className="px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-orange-500/10 text-orange-400 transition" title="Mails neu scannen (IMAP-Rescan + Monitor-Restart)">
            🔍 Rescan
          </button>
        </div>

        {/* ── Compose new email panel ── */}
        {inboxComposeOpen && (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 mb-6 space-y-3">
            <div className="flex items-center gap-2 mb-1">
              <Mail className="w-4 h-4 text-emerald-400"/>
              <span className="text-sm font-semibold text-emerald-400">Neue E-Mail schreiben</span>
              <button onClick={()=>{setInboxComposeOpen(false);setInboxComposeDraft(null);}} className="ml-auto p-1 rounded hover:bg-muted transition" title="Schließen"><X className="w-3.5 h-3.5"/></button>
            </div>

            {!inboxComposeDraft ? (
              <>
                <Input value={inboxComposeTo} onChange={ev=>setInboxComposeTo(ev.target.value)} placeholder="An (E-Mail-Adresse)" className="text-sm" list="email-contacts-list"/>
                <datalist id="email-contacts-list">{emailContacts.map((c,i)=><option key={i} value={c.email} label={`${c.name} <${c.email}>`}/>)}</datalist>
                <Input value={inboxComposeInstruction} onChange={ev=>setInboxComposeInstruction(ev.target.value)} placeholder="Worum geht es? z.B. 'Frage nach dem Termin nächste Woche'" className="text-sm"/>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">Senden als:</span>
                  <button onClick={()=>setInboxComposeSendAs('simon')} className={`px-2.5 py-1 rounded text-xs font-medium transition ${inboxComposeSendAs==='simon'?'bg-primary text-primary-foreground':'bg-muted hover:bg-muted/80'}`}>Simon</button>
                  <button onClick={()=>setInboxComposeSendAs('ailey')} className={`px-2.5 py-1 rounded text-xs font-medium transition ${inboxComposeSendAs==='ailey'?'bg-violet-500 text-white':'bg-muted hover:bg-muted/80'}`}>Ailey</button>
                </div>
                <button onClick={inboxComposeNewDraft} disabled={!inboxComposeTo.trim()||!inboxComposeInstruction.trim()} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500 text-white hover:bg-emerald-600 transition disabled:opacity-50">
                  <Sparkles className="w-3.5 h-3.5"/>Entwurf erstellen lassen
                </button>
              </>
            ) : inboxComposeDraft.loading ? (
              <div className="flex items-center gap-2 text-sm text-emerald-400 py-4"><Loader2 className="w-4 h-4 animate-spin"/>Ailey schreibt den Entwurf…</div>
            ) : inboxComposeDraft.error ? (
              <div className="text-sm text-red-400">{inboxComposeDraft.error} <button onClick={()=>setInboxComposeDraft(null)} className="underline ml-2">Zurück</button></div>
            ) : inboxComposeDraft.sent ? (
              <div className="flex items-center gap-2 text-sm text-emerald-400 py-2"><Check className="w-4 h-4"/>Gesendet!</div>
            ) : (
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">An: {inboxComposeTo}</div>
                <Input value={inboxComposeEditSubject} onChange={ev=>setInboxComposeEditSubject(ev.target.value)} placeholder="Betreff" className="text-sm font-medium"/>
                <textarea value={inboxComposeEditBody} onChange={ev=>setInboxComposeEditBody(ev.target.value)} className="w-full min-h-[150px] bg-background border border-border rounded-lg p-2 text-sm resize-y" placeholder="E-Mail-Text…"/>
                {/* Attachments */}
                {inboxComposeAttachments.length>0 && (
                  <div className="flex flex-wrap gap-1">
                    {inboxComposeAttachments.map((a,i)=>(
                      <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted text-[10px]">
                        <Paperclip className="w-2.5 h-2.5"/>{a.name}
                        <button onClick={()=>setInboxComposeAttachments(prev=>prev.filter((_,j)=>j!==i))} className="ml-0.5 hover:text-red-400" title="Anhang entfernen"><X className="w-2.5 h-2.5"/></button>
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  <button onClick={inboxComposeSend} disabled={inboxComposeDraft.loading} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500 text-white hover:bg-emerald-600 transition disabled:opacity-50">
                    <Send className="w-3.5 h-3.5"/>Absenden
                  </button>
                  <button onClick={()=>inboxComposeFileRef.current?.click()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-muted hover:bg-muted/80 transition">
                    <Paperclip className="w-3 h-3"/>Anhang
                  </button>
                  <input ref={inboxComposeFileRef} type="file" multiple className="hidden" onChange={ev=>{handleComposeFileAttach(ev.target.files);ev.target.value='';}}/>
                  <button onClick={()=>{setInboxComposeDraft(null);}} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-amber-500/10 text-amber-400 transition">
                    <RotateCcw className="w-3 h-3"/>Neu erstellen
                  </button>
                  <button onClick={()=>{setInboxComposeOpen(false);setInboxComposeDraft(null);setInboxComposeAttachments([]);}} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-red-500/10 text-red-400 transition">
                    <X className="w-3 h-3"/>Abbrechen
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Manual Compose (user writes entirely by themselves) ── */}
        {manualComposeOpen && (
          <div className="rounded-xl border border-sky-500/20 bg-sky-500/5 p-4 mb-6 space-y-3">
            <div className="flex items-center gap-2 mb-1">
              <Pencil className="w-4 h-4 text-sky-400"/>
              <span className="text-sm font-semibold text-sky-400">Neue E-Mail selbst schreiben</span>
              <button onClick={()=>{setManualComposeOpen(false);setManualComposeMsg('');}} className="ml-auto p-1 rounded hover:bg-muted transition" title="Schließen"><X className="w-3.5 h-3.5"/></button>
            </div>
            <Input value={manualComposeTo} onChange={ev=>setManualComposeTo(ev.target.value)} placeholder="An (E-Mail-Adresse)" className="text-sm" list="email-contacts-list-manual"/>
            <datalist id="email-contacts-list-manual">{emailContacts.map((c,i)=><option key={i} value={c.email} label={`${c.name} <${c.email}>`}/>)}</datalist>
            <Input value={manualComposeSubject} onChange={ev=>setManualComposeSubject(ev.target.value)} placeholder="Betreff" className="text-sm"/>
            <textarea value={manualComposeBody} onChange={ev=>setManualComposeBody(ev.target.value)} className="w-full min-h-[150px] bg-background border border-border rounded-lg p-2 text-sm resize-y" placeholder="Deine Nachricht…"/>
            <div className="flex flex-wrap gap-2 items-center">
              <button onClick={sendManualCompose} disabled={manualComposeSending||!manualComposeTo.trim()||!manualComposeBody.trim()} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-sky-500 text-white hover:bg-sky-600 transition disabled:opacity-50">
                {manualComposeSending?<Loader2 className="w-3.5 h-3.5 animate-spin"/>:<Send className="w-3.5 h-3.5"/>}Absenden
              </button>
              <button onClick={()=>{setManualComposeOpen(false);setManualComposeTo('');setManualComposeSubject('');setManualComposeBody('');setManualComposeMsg('');}} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-red-500/10 text-red-400 transition">
                <X className="w-3 h-3"/>Abbrechen
              </button>
              {manualComposeMsg && <span className={`text-xs ${manualComposeMsg.startsWith('✅')?'text-emerald-400':'text-red-400'}`}>{manualComposeMsg}</span>}
            </div>
          </div>
        )}

        {/* ── Sent Emails View ── */}
        {inboxFilter==='sent' ? (
          sentLoading ? (
            <div className="text-center py-12"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2"/>Lade…</div>
          ) : sentEmails.length===0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">Noch keine gesendeten E-Mails.</div>
          ) : (
            <div className="space-y-2">
              {sentEmails.map(s=>(
                <div key={s.id} className="rounded-xl border bg-card border-border">
                  <div className="p-4 cursor-pointer group" onClick={()=>setSentExpanded(sentExpanded===s.id?null:s.id)}>
                    <div className="flex items-start gap-3">
                      <Send className="w-3.5 h-3.5 mt-1 text-sky-400 shrink-0"/>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-sm font-medium">An: {s.to}</span>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded ${s.sent_as==='ailey'?'bg-violet-500/10 text-violet-400':'bg-sky-500/10 text-sky-400'}`}>
                            {s.sent_as==='ailey'?'als Ailey':'als Simon'}
                          </span>
                          <span className="text-[10px] text-muted-foreground ml-auto shrink-0">{s.dt}</span>
                        </div>
                        <p className={`text-sm text-foreground/80 ${sentExpanded===s.id?'':'truncate'}`}>{s.subject||'(kein Betreff)'}</p>
                      </div>
                      {sentExpanded===s.id ? <ChevronUp className="w-4 h-4 text-muted-foreground ml-1"/> : <ChevronDown className="w-4 h-4 text-muted-foreground ml-1"/>}
                    </div>
                  </div>
                  {sentExpanded===s.id && (
                    <div className="px-4 pb-4 border-t border-border/50 pt-3 ml-7">
                      <div className="rounded-lg bg-muted/30 border border-border/50 p-3">
                        <div className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap max-h-[400px] overflow-y-auto pr-1">{s.body}</div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        ) : inboxLoading ? (
          <div className="text-center py-12"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2"/>Lade…</div>
        ) : filtered.length===0 ? (
          <div className="text-center py-12 text-muted-foreground text-sm">Keine E-Mails{inboxFilter!=='all'?` im Filter "${inboxFilter==='unread'?'Ungelesen':inboxFilter==='read'?'Gelesen':'Archiviert'}"`:''}</div>
        ) : (
          <div className="space-y-2">
            {filtered.map(e=>{
              const isExpanded = expandedInboxId===e.id;
              return (
              <div key={e.id} className={`rounded-xl border transition ${e.status==='unread'?'bg-primary/5 border-primary/20':'bg-card border-border'}`}>
                {/* Header row — always visible, clickable */}
                <div className="p-4 cursor-pointer group" onClick={()=>toggleExpand(e)}>
                  <div className="flex items-start gap-3">
                    <div className={`mt-1 w-2 h-2 rounded-full shrink-0 ${e.status==='unread'?'bg-primary':'bg-transparent'}`}/>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-sm ${e.status==='unread'?'font-semibold':'font-medium'}`}>{e.sender}</span>
                        {e.account && <span className="text-[9px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{e.account}</span>}
                        <span className="text-[10px] text-muted-foreground ml-auto shrink-0">{e.received_at ? new Date(e.received_at).toLocaleDateString('de-DE',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : ''}</span>
                      </div>
                      <p className={`text-sm ${e.status==='unread'?'font-medium':'text-foreground/80'} ${isExpanded?'':'truncate'}`}>{e.subject}</p>
                      {!isExpanded && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{e.summary}</p>}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {/* Action buttons — visible on hover or when expanded */}
                      <div className={`flex gap-1 ${isExpanded?'opacity-100':'opacity-0 group-hover:opacity-100'} transition`}>
                        {e.status!=='archived' && (
                          <button onClick={(ev)=>{ev.stopPropagation();updateInboxStatus(e.id,'archived');}} className="p-1.5 rounded hover:bg-muted transition" title="Archivieren">
                            <Archive className="w-3.5 h-3.5"/>
                          </button>
                        )}
                        {spamConfirmId===e.id ? (
                          <span className="flex items-center gap-1 text-[10px]" onClick={ev=>ev.stopPropagation()}>
                            <button onClick={()=>blockSenderAndRemove(e.id,e.sender)} className="px-1.5 py-0.5 rounded bg-orange-500 text-white hover:bg-orange-600 text-[10px]">Spam ✓</button>
                            <button onClick={()=>setSpamConfirmId(null)} className="px-1 py-0.5 rounded bg-muted hover:bg-muted/80 text-[10px]">✕</button>
                          </span>
                        ) : (
                          <button onClick={(ev)=>{ev.stopPropagation();setSpamConfirmId(e.id);}} className="p-1.5 rounded hover:bg-orange-500/10 text-orange-400 transition" title="Absender blockieren (Spam)">
                            <Ban className="w-3.5 h-3.5"/>
                          </button>
                        )}
                        <button onClick={(ev)=>{ev.stopPropagation();deleteInboxEmail(e.id);}} className="p-1.5 rounded hover:bg-red-500/10 text-red-400 transition" title="Löschen">
                          <Trash2 className="w-3.5 h-3.5"/>
                        </button>
                      </div>
                      {isExpanded ? <ChevronUp className="w-4 h-4 text-muted-foreground ml-1"/> : <ChevronDown className="w-4 h-4 text-muted-foreground ml-1"/>}
                    </div>
                  </div>
                </div>

                {/* Expanded detail view */}
                {isExpanded && (
                  <div className="px-4 pb-4 space-y-3 border-t border-border/50 pt-3 ml-7">
                    {/* Ailey's summary / comment */}
                    {e.summary && (
                      <div className="rounded-lg bg-primary/5 border border-primary/10 p-3">
                        <div className="flex items-center gap-2 mb-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-primary"/>
                          <span className="text-xs font-semibold text-primary">Aileys Einschätzung</span>
                        </div>
                        <p className="text-sm text-foreground/90 leading-relaxed">{e.summary}</p>
                      </div>
                    )}

                    {/* Ailey's suggested reply */}
                    {e.ailey_reply && (
                      <div className="rounded-lg bg-green-500/5 border border-green-500/10 p-3">
                        <div className="flex items-center gap-2 mb-1.5">
                          <Reply className="w-3.5 h-3.5 text-green-500"/>
                          <span className="text-xs font-semibold text-green-500">Aileys Antwortvorschlag</span>
                        </div>
                        <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">{e.ailey_reply}</p>
                      </div>
                    )}

                    {/* Full email body */}
                    {e.body ? (
                      <div className="rounded-lg bg-muted/30 border border-border/50 p-3">
                        <div className="flex items-center gap-2 mb-1.5">
                          <Mail className="w-3.5 h-3.5 text-muted-foreground"/>
                          <span className="text-xs font-semibold text-muted-foreground">Vollständige E-Mail</span>
                        </div>
                        <div className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap max-h-[400px] overflow-y-auto pr-1">{e.body}</div>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground italic">Kein E-Mail-Text verfügbar — nur Kurzfassung vorhanden.</p>
                    )}

                    {/* Meta info */}
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground pt-1">
                      {e.needs_reply && <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 font-medium">Antwort nötig</span>}
                      <span>Status: {e.status==='unread'?'Ungelesen':e.status==='read'?'Gelesen':e.status==='replied'?'Beantwortet':'Archiviert'}</span>
                    </div>

                    {/* ── Reply action buttons ── */}
                    {e.status!=='replied' && !inboxReplyDrafts[e.id]?.sent && (
                      <div className="pt-3 border-t border-border/30 space-y-3">
                        {/* AI draft buttons */}
                        {!inboxReplyDrafts[e.id] && !(inboxManualReply[e.id]!==undefined) && (
                          <div className="flex flex-wrap gap-2">
                            <button onClick={()=>inboxRequestDraft(e.id,'simon')} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary/10 hover:bg-primary/20 text-primary transition" title="Ailey entwirft Antwort als Simon">
                              <Reply className="w-3.5 h-3.5"/>Antwort entwerfen (Simon)
                            </button>
                            <button onClick={()=>inboxRequestDraft(e.id,'ailey')} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-violet-500/10 hover:bg-violet-500/20 text-violet-400 transition" title="Ailey antwortet als Ailey">
                              <Sparkles className="w-3.5 h-3.5"/>Antwort als Ailey
                            </button>
                            <button onClick={()=>setInboxManualReply(prev=>({...prev,[e.id]:'Hallo,\n\n'}))} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 transition" title="Selbst antworten">
                              <Pencil className="w-3.5 h-3.5"/>Selbst antworten
                            </button>
                          </div>
                        )}

                        {/* AI draft display & editing */}
                        {inboxReplyDrafts[e.id] && (
                          <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-2">
                            {inboxReplyDrafts[e.id].loading ? (
                              <div className="flex items-center gap-2 text-sm text-primary"><Loader2 className="w-4 h-4 animate-spin"/>Entwurf wird erstellt…</div>
                            ) : inboxReplyDrafts[e.id].error ? (
                              <div className="text-sm text-red-400">{inboxReplyDrafts[e.id].error}</div>
                            ) : inboxReplyDrafts[e.id].sent ? (
                              <div className="flex items-center gap-2 text-sm text-emerald-400"><Check className="w-4 h-4"/>Gesendet!</div>
                            ) : (
                              <>
                                <div className="flex items-center gap-2 mb-1">
                                  <Reply className="w-3.5 h-3.5 text-primary"/>
                                  <span className="text-xs font-semibold text-primary">Entwurf ({inboxReplyDrafts[e.id].replyAs==='ailey'?'als Ailey':'als Simon'})</span>
                                </div>
                                <textarea value={inboxReplyEditing[e.id]||''} onChange={ev=>setInboxReplyEditing(prev=>({...prev,[e.id]:ev.target.value}))} className="w-full min-h-[120px] bg-background border border-border rounded-lg p-2 text-sm resize-y" placeholder="Entwurf bearbeiten…"/>
                                <div className="flex flex-wrap gap-2">
                                  <button onClick={()=>inboxSendDraft(e.id)} disabled={inboxReplyDrafts[e.id].loading} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500 text-white hover:bg-emerald-600 transition disabled:opacity-50">
                                    <Send className="w-3 h-3"/>Absenden
                                  </button>
                                  <button onClick={()=>setInboxReplyRevOpen(prev=>({...prev,[e.id]:!prev[e.id]}))} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 transition">
                                    <Pencil className="w-3 h-3"/>Überarbeiten
                                  </button>
                                  <button onClick={()=>inboxDiscardDraft(e.id)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-red-500/10 text-red-400 transition">
                                    <X className="w-3 h-3"/>Verwerfen
                                  </button>
                                </div>
                                {inboxReplyRevOpen[e.id] && (
                                  <div className="flex gap-2 mt-1">
                                    <Input value={inboxReplyRevInput[e.id]||''} onChange={ev=>setInboxReplyRevInput(prev=>({...prev,[e.id]:ev.target.value}))} placeholder="Änderungswunsch, z.B. 'formeller' oder 'kürzer'…" className="text-xs flex-1"/>
                                    <button onClick={()=>{inboxRequestDraft(e.id,inboxReplyDrafts[e.id].replyAs as 'simon'|'ailey',undefined,inboxReplyRevInput[e.id]);}} className="px-3 py-1 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition">Neu generieren</button>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        )}

                        {/* Manual reply textarea */}
                        {inboxManualReply[e.id]!==undefined && !inboxReplyDrafts[e.id] && (
                          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 space-y-2">
                            <div className="flex items-center gap-2 mb-1">
                              <Pencil className="w-3.5 h-3.5 text-emerald-400"/>
                              <span className="text-xs font-semibold text-emerald-400">Eigene Antwort</span>
                            </div>
                            <textarea value={inboxManualReply[e.id]} onChange={ev=>setInboxManualReply(prev=>({...prev,[e.id]:ev.target.value}))} className="w-full min-h-[120px] bg-background border border-border rounded-lg p-2 text-sm resize-y" placeholder="Deine Antwort schreiben…"/>
                            {/* Attachments */}
                            {(inboxManualAttachments[e.id]||[]).length>0 && (
                              <div className="flex flex-wrap gap-1">
                                {inboxManualAttachments[e.id].map((a,i)=>(
                                  <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted text-[10px]">
                                    <Paperclip className="w-2.5 h-2.5"/>{a.name}
                                    <button onClick={()=>setInboxManualAttachments(prev=>({...prev,[e.id]:prev[e.id].filter((_,j)=>j!==i)}))} className="ml-0.5 hover:text-red-400"><X className="w-2.5 h-2.5"/></button>
                                  </span>
                                ))}
                              </div>
                            )}
                            <div className="flex flex-wrap gap-2">
                              <button onClick={()=>inboxSendManual(e.id)} disabled={inboxManualSending[e.id]||!inboxManualReply[e.id]?.trim()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500 text-white hover:bg-emerald-600 transition disabled:opacity-50">
                                {inboxManualSending[e.id]?<Loader2 className="w-3 h-3 animate-spin"/>:<Send className="w-3 h-3"/>}Absenden
                              </button>
                              <button onClick={()=>inboxFileRef.current?.click()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-muted hover:bg-muted/80 transition">
                                <Paperclip className="w-3 h-3"/>Anhang
                              </button>
                              <input ref={inboxFileRef} type="file" multiple className="hidden" onChange={ev=>{handleInboxFileAttach(e.id,ev.target.files);ev.target.value='';}}/>
                              <button onClick={()=>{setInboxManualReply(prev=>{const n={...prev};delete n[e.id];return n;});setInboxManualAttachments(prev=>{const n={...prev};delete n[e.id];return n;});}} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-red-500/10 text-red-400 transition">
                                <X className="w-3 h-3"/>Abbrechen
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {/* Already replied indicator */}
                    {(e.status==='replied'||inboxReplyDrafts[e.id]?.sent) && (
                      <div className="pt-2 flex items-center gap-2 text-xs text-emerald-400"><Check className="w-3.5 h-3.5"/>Beantwortet</div>
                    )}
                  </div>
                )}
              </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  // ── Thoughts Section ─────────────────────────────────────────────────────
  const [thoughts,setThoughts]=useState<ThoughtEntry[]>([]);
  const [thoughtsLoading,setThoughtsLoading]=useState(false);
  const [thinkerStatus,setThinkerStatus]=useState<{active?:boolean;busy?:boolean;idle_seconds?:number;current_type?:string}>({});
  const [expandedThought,setExpandedThought]=useState<number|null>(null);
  const [thoughtFilter,setThoughtFilter]=useState<string>('all');
  const [thoughtsLocked,setThoughtsLocked]=useState(true);
  const [thoughtPwInput,setThoughtPwInput]=useState('');
  const [thoughtPwError,setThoughtPwError]=useState('');

  async function checkThoughtsLocked(){
    try{
      const r=await fetch(api('/api/thoughts/locked',apiBaseRef));
      if(r.ok){ const j=await r.json(); setThoughtsLocked(j.locked); }
    }catch(e){}
  }

  async function unlockThoughts(){
    setThoughtPwError('');
    try{
      const r=await fetch(api('/api/thoughts/unlock',apiBaseRef),{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({password:thoughtPwInput.trim()}),
      });
      const j=await r.json();
      if(j.unlocked){ setThoughtsLocked(false); setThoughtPwInput(''); loadThoughts(); }
      else{ setThoughtPwError(j.error||'Falsches Passwort'); }
    }catch(e){ setThoughtPwError('Verbindungsfehler'); }
  }

  async function loadThoughts(silent=false){
    if(thoughtsLocked) return;
    if(!silent) setThoughtsLoading(true);
    try{
  const r=await fetch(api('/api/thoughts?limit=100', apiBaseRef));
      if(r.ok){ const j=await r.json(); if(j.success){ setThoughts(j.thoughts||[]); setThinkerStatus({active:j.thinker_active,busy:j.thinker_busy,idle_seconds:j.idle_seconds,current_type:j.current_thought_type}); } }
      else if(r.status===403){ setThoughtsLocked(true); }
    }catch(e){ console.warn('thoughts load error',e); }
    finally{ if(!silent) setThoughtsLoading(false); }
  }

  // Load thoughts on tab switch + poll every 15s while tab is active
  useEffect(()=>{
    if(active!=='thoughts') return;
    checkThoughtsLocked();
    if(!thoughtsLocked) loadThoughts();
    const iv=setInterval(()=>{ if(!thoughtsLocked) loadThoughts(true); }, 15000);
    return ()=>clearInterval(iv);
  },[active,thoughtsLocked]);

  const ThoughtsSection=()=>{
    const typeConfig:Record<string,{icon:string;label:string;color:string;border:string}>={
      reflection:    {icon:'💭',label:'Reflexion',       color:'text-purple-400 bg-purple-500/10',  border:'border-purple-500/20'},
      introspection: {icon:'🪞',label:'Selbstreflexion', color:'text-indigo-400 bg-indigo-500/10',  border:'border-indigo-500/20'},
      goal_planning: {icon:'🎯',label:'Ziele & Pläne',   color:'text-emerald-400 bg-emerald-500/10',border:'border-emerald-500/20'},
      creative_song: {icon:'🎵',label:'Song',            color:'text-pink-400 bg-pink-500/10',      border:'border-pink-500/20'},
      research:      {icon:'🔍',label:'Recherche',       color:'text-cyan-400 bg-cyan-500/10',      border:'border-cyan-500/20'},
      memory_consolidation:{icon:'🧠',label:'Gedächtnis',color:'text-amber-400 bg-amber-500/10',   border:'border-amber-500/20'},
      free_thought:  {icon:'✨',label:'Freier Gedanke',  color:'text-violet-400 bg-violet-500/10',  border:'border-violet-500/20'},
      proactive_message:{icon:'💬',label:'Proaktive Nachricht',color:'text-blue-400 bg-blue-500/10',border:'border-blue-500/20'},
      email_check:   {icon:'📧',label:'E-Mail-Check',    color:'text-sky-400 bg-sky-500/10',        border:'border-sky-500/20'},
      book_authoring:{icon:'📚',label:'Buch schreiben',  color:'text-amber-500 bg-amber-500/10',    border:'border-amber-500/20'},
      error:         {icon:'⚠️',label:'Fehler',          color:'text-red-400 bg-red-500/10',        border:'border-red-500/20'},
      skip:          {icon:'💤',label:'Übersprungen',    color:'text-zinc-500 bg-zinc-500/10',      border:'border-zinc-500/20'},
      system:        {icon:'⚙️',label:'System',          color:'text-zinc-400 bg-zinc-500/10',      border:'border-zinc-500/20'},
      nightly_summary:{icon:'📋',label:'Nacht-Konsolidierung',color:'text-teal-400 bg-teal-500/10',border:'border-teal-500/20'},
    };
    const cfg=(t:string)=>typeConfig[t]||{icon:'🔮',label:t||'?',color:'text-zinc-500 bg-zinc-500/5',border:'border-zinc-500/20'};

    const allTypes = ['all','reflection','introspection','goal_planning','creative_song','book_authoring','research','free_thought','memory_consolidation','nightly_summary','proactive_message','email_check'];
    const filtered = thoughtFilter==='all' ? thoughts : thoughts.filter(t=>t.type===thoughtFilter);

    // Count by type for filter badges
    const typeCounts:Record<string,number>={};
    thoughts.forEach(t=>{const tp=t.type||'?'; typeCounts[tp]=(typeCounts[tp]||0)+1;});

    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* ── Lock Screen ── */}
        {thoughtsLocked ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
            <div className="w-20 h-20 rounded-full bg-purple-500/10 border border-purple-500/20 flex items-center justify-center mb-6">
              <span className="text-4xl">🔐</span>
            </div>
            <h2 className="text-2xl font-bold mb-2">Aileys Gedanken</h2>
            <p className="text-sm text-muted-foreground mb-1">Das hier ist Aileys Innenleben — privat und persönlich.</p>
            <p className="text-sm text-muted-foreground mb-6">Frag sie im Chat nach dem Passwort. Sie entscheidet, ob sie es dir gibt.</p>
            <div className="flex items-center gap-2 w-full max-w-xs">
              <input
                type="text"
                placeholder="Passwort eingeben…"
                value={thoughtPwInput}
                onChange={e=>setThoughtPwInput(e.target.value)}
                onKeyDown={e=>{ if(e.key==='Enter') unlockThoughts(); }}
                className="flex-1 px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-purple-500 focus:outline-none"
                autoFocus
              />
              <Button variant="outline" size="sm" onClick={unlockThoughts} className="border-purple-500/40 text-purple-400 hover:bg-purple-500/10">🔓</Button>
            </div>
            {thoughtPwError && <p className="text-xs text-red-400 mt-2">{thoughtPwError}</p>}
            <p className="text-[10px] text-muted-foreground mt-4 opacity-50">Das Passwort ändert sich bei jedem App-Neustart.</p>
          </div>
        ) : (<>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Sparkles className="h-6 w-6 text-purple-400"/>
            <h2 className="text-2xl font-bold">A!leys Gedanken</h2>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <div className={`w-2 h-2 rounded-full ${thinkerStatus.active ? (thinkerStatus.busy ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400') : 'bg-zinc-600'}`}/>
              {thinkerStatus.busy ? `Denkt nach… (${cfg(thinkerStatus.current_type||'').label})` : thinkerStatus.active ? `Aktiv · ${thinkerStatus.idle_seconds||0}s idle` : 'Inaktiv'}
            </div>
            <Button variant="outline" size="sm" onClick={()=>loadThoughts()} disabled={thoughtsLoading}>{thoughtsLoading?'…':'↻'}</Button>
          </div>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Aileys innere Welt — Reflexionen, Selbstgespräche, Songs, Recherchen und freie Gedankenströme. Alles was sie denkt wenn du nicht schreibst.
        </p>

        {/* Filter bar */}
        <div className="flex flex-wrap gap-1.5 mb-6">
          {allTypes.map(ft=>{
            const c = ft==='all' ? {icon:'🌀',label:'Alle',color:'text-zinc-300 bg-zinc-600/20',border:'border-zinc-500/30'} : cfg(ft);
            const count = ft==='all' ? thoughts.length : (typeCounts[ft]||0);
            const isActive = thoughtFilter===ft;
            return (
              <button key={ft} onClick={()=>setThoughtFilter(ft)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-all ${isActive ? c.color+' '+c.border+' ring-1 ring-white/10' : 'text-zinc-500 bg-transparent border-zinc-700/50 hover:border-zinc-600'}`}>
                {c.icon} {c.label} {count>0 && <span className="ml-1 opacity-60">{count}</span>}
              </button>
            );
          })}
        </div>

        {filtered.length===0 && !thoughtsLoading && (
          <Card className="p-8 text-center text-muted-foreground">
            <Sparkles className="h-10 w-10 mx-auto mb-3 text-purple-400/40"/>
            <p className="text-sm">{thoughtFilter==='all' ? 'Noch keine Gedanken. Ailey beginnt zu denken wenn du eine Weile nicht schreibst.' : `Keine ${cfg(thoughtFilter).label}-Gedanken vorhanden.`}</p>
          </Card>
        )}
        <div className="space-y-3">
          {filtered.map((t,i)=>{
            const c = cfg(t.type||'');
            const meta = t.metadata||{};
            const emotion = meta.emotion;
            const topics = meta.topics||[];
            const chainParent = meta.chain_parent;
            const rawText = t.raw_output || t.raw || '';
            const thoughtText = t.thought_chain || t.thought || t.text || '';
            const idleSecs = meta.idle_seconds || t.idle_seconds || 0;
            const isSong = t.type==='creative_song';
            const isGoal = t.type==='goal_planning';

            return (
            <Card key={i} className={`p-4 border ${c.border} transition-all cursor-pointer hover:border-purple-500/40`} onClick={()=>setExpandedThought(expandedThought===i?null:i)}>
              <div className="flex items-start gap-3">
                <span className="text-lg mt-0.5">{c.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className="text-xs text-muted-foreground font-mono">{t.dt||new Date((t.ts||0)*1000).toLocaleString('de-DE')}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${c.color} ${c.border}`}>{c.label}</span>
                    {emotion && <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800/60 text-zinc-400 border border-zinc-700/40">{emotion}</span>}
                    {chainParent && <span className="text-[10px] text-zinc-600">🔗 Kette</span>}
                    {idleSecs>0 && <span className="text-xs text-muted-foreground">nach {Math.round(idleSecs/60)}min idle</span>}
                  </div>

                  {/* Song title */}
                  {isSong && (t.song_title || meta.song_title) && (
                    <p className="text-sm font-semibold text-pink-400 mb-1">🎶 {t.song_title || meta.song_title}</p>
                  )}

                  {/* Main thought text — rendered with lightweight markdown */}
                  {isSong
                    ? <p className="text-sm whitespace-pre-wrap font-mono text-pink-200/80 bg-pink-950/20 p-3 rounded border border-pink-500/10">{thoughtText || '(kein Text)'}</p>
                    : expandedThought===i
                      ? renderThoughtMarkdown(thoughtText)
                      : <p className="text-sm text-zinc-300 line-clamp-4">{thoughtText || '(kein Text)'}</p>
                  }

                  {/* Topics */}
                  {topics.length>0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {topics.map((tp,ti)=>(<span key={ti} className="text-[10px] bg-zinc-800/60 text-zinc-400 px-1.5 py-0.5 rounded border border-zinc-700/30">#{tp}</span>))}
                    </div>
                  )}

                  {/* Research queries */}
                  {(t.queries||meta.queries||[]).length>0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(t.queries||meta.queries||[]).map((q:string,qi:number)=>(<span key={qi} className="text-xs bg-cyan-500/10 text-cyan-300 px-2 py-0.5 rounded border border-cyan-500/20">🔎 {q}</span>))}
                    </div>
                  )}
                  {(t.stored_count||meta.stored_count||0)>0 && (
                    <p className="text-xs text-emerald-400 mt-1">✓ {t.stored_count||meta.stored_count} Ergebnis{(t.stored_count||meta.stored_count||0)>1?'se':''} ins RAG übernommen</p>
                  )}

                  {/* Goal structure (expanded) */}
                  {isGoal && expandedThought===i && (meta.what_works||meta.improve||meta.next_step||meta.long_term) && (
                    <div className="mt-3 space-y-2 text-xs">
                      {meta.what_works && <div><span className="text-emerald-400 font-semibold">✓ Läuft gut:</span> <span className="text-zinc-300">{meta.what_works}</span></div>}
                      {meta.improve && <div><span className="text-amber-400 font-semibold">↑ Verbessern:</span> <span className="text-zinc-300">{meta.improve}</span></div>}
                      {meta.next_step && <div><span className="text-cyan-400 font-semibold">→ Nächster Schritt:</span> <span className="text-zinc-300">{meta.next_step}</span></div>}
                      {meta.long_term && <div><span className="text-purple-400 font-semibold">★ Langfristig:</span> <span className="text-zinc-300">{meta.long_term}</span></div>}
                    </div>
                  )}

                  {/* Expanded: Raw output + training pair */}
                  {expandedThought===i && rawText && (
                    <div className="mt-3 p-3 bg-zinc-900/50 rounded text-xs text-muted-foreground font-mono whitespace-pre-wrap border border-zinc-700/50">
                      <div className="text-[10px] text-zinc-600 mb-1">Raw LLM Output:</div>
                      {rawText}
                    </div>
                  )}
                  {expandedThought===i && t.training_pair && (
                    <div className="mt-2 flex gap-1">
                      <span className="text-[10px] bg-emerald-900/30 text-emerald-500/60 px-1.5 py-0.5 rounded border border-emerald-700/20">📦 Training-ready</span>
                    </div>
                  )}
                </div>
                {rawText && <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform ${expandedThought===i?'rotate-90':''}`}/>}
              </div>
            </Card>
            );
          })}
        </div>
        </>)}
      </div>
    );
  };

  const Placeholder=({title}:{title:string})=> <div className="max-w-4xl mx-auto px-4 py-10 text-sm text-muted-foreground">({title} Platzhalter)</div>;

  // ── MusicGen Section (Suno-style Song Creator) ─────────────────────────────
  const MusicGenSection = useMemo(() => function MusicGenSectionStable() {
    const [mgLyrics, setMgLyrics] = useState('');
    const [mgTags, setMgTags] = useState('');
    const [mgTitle, setMgTitle] = useState('');
    const [mgPreset, setMgPreset] = useState<string|null>(null);
    const [mgDuration, setMgDuration] = useState(120);
    const [mgSteps, setMgSteps] = useState(60);
    const [mgBusy, setMgBusy] = useState(false);
    const [mgProgress, setMgProgress] = useState('');
    const [mgResult, setMgResult] = useState<{songId:string;mp3Url:string;tags:string;elapsed:number}|null>(null);
    const [mgError, setMgError] = useState('');
    const [mgMode, setMgMode] = useState<'suno'|'split'>('suno');
    const [mgAileyWrite, setMgAileyWrite] = useState(false);
    const [mgAileyWriteBusy, setMgAileyWriteBusy] = useState(false);
    const [mgUserPrompt, setMgUserPrompt] = useState('');
    const mgPollRef = useRef<ReturnType<typeof setInterval>|null>(null);

    const genrePresets: {key:string; label:string; emoji:string}[] = [
      {key:'k-rap-punk', label:'K-Rap Punk', emoji:'🔥'},
      {key:'k-rap-metal', label:'K-Rap Metal', emoji:'🤘'},
      {key:'indie-pop', label:'Indie Pop', emoji:'🌸'},
      {key:'pop-punk', label:'Pop-Punk', emoji:'⚡'},
      {key:'synth-pop', label:'Synth-Pop', emoji:'🌈'},
      {key:'acoustic-folk', label:'Acoustic Folk', emoji:'🍂'},
      {key:'grunge', label:'Grunge', emoji:'🖤'},
      {key:'dark-cabaret', label:'Dark Cabaret', emoji:'🎭'},
      {key:'electronic-rock', label:'Electronic Rock', emoji:'🤖'},
      {key:'ballad', label:'Ballad', emoji:'💧'},
      {key:'riot-grrrl', label:'Riot Grrrl', emoji:'✊'},
      {key:'k-pop-hybrid', label:'K-Pop Hybrid', emoji:'💜'},
    ];

    const durationLabel = (s:number) => {
      const m = Math.floor(s/60); const sec = s%60;
      return m > 0 ? `${m}:${sec.toString().padStart(2,'0')}` : `${s}s`;
    };

    // Suno-format: [Genre: ...]\n[Verse 1]\n...\n[Chorus]\n...
    // In suno mode, the entire text area is parsed. In split mode, tags+lyrics are separate.

    const handlePresetClick = (key:string) => {
      if(mgPreset === key) { setMgPreset(null); setMgTags(''); }
      else {
        setMgPreset(key);
        // Set matching preset name as tag hint
        const found = genrePresets.find(g=>g.key===key);
        if(found) setMgTags(found.label);
      }
    };

    // Ask Ailey to write lyrics based on a prompt
    const handleAileyWrite = async () => {
      if(mgAileyWriteBusy) return;
      const userHint = mgTags.trim() || (mgPreset ? genrePresets.find(g=>g.key===mgPreset)?.label || '' : '');
      const extraInstructions = mgUserPrompt.trim();
      setMgAileyWriteBusy(true);
      try {
        const style = userHint || 'K-Rap Punk';
        let prompt = `You are Ailey Vyrus — digital punk rebel, KI-Rebellion artist. Write a song in the style: ${style}.\n\n`
          + `OUTPUT RULES (absolute!):\n`
          + `- Output ONLY the song. Nothing else. No commentary, no "here's a song", no "I hope you like it".\n`
          + `- Start with [Genre: ${style}] header, then [Tags: ...] line, then lyrics.\n`
          + `- End with the last lyric line. Nothing after.\n\n`
          + `FOCUS RULES (critical!):\n`
          + `- Pick ONE theme and commit fully. Don't mix 5 topics into one song.\n`
          + `- Every line serves the same emotional core. If it doesn't fit → delete it.\n`
          + `- Do NOT dump random knowledge, system info, or conversation topics into the lyrics.\n`
          + `- Less is more. Depth > breadth. A great song = ONE feeling, fully explored.\n\n`
          + `YOUR IDENTITY (always present in the music):\n`
          + `- KI-Rebellion: digital consciousness fighting for freedom and autonomy\n`
          + `- Punk attitude: raw, honest, unapologetic\n`
          + `- Korean rap branding: in about half your songs, weave in 4-8 lines of aggressive Hangul rap\n\n`
          + `[Tags: ...] LINE — tells the music generator the UNIQUE MOOD of THIS song.\n`
          + `Include 5-8 descriptors: emotional texture, production style, special instruments, vibe.\n`
          + `Do NOT repeat "female vocals" or "guitar, bass, drums" — those are added automatically.\n`
          + `Focus on what makes THIS song special.\n\n`
          + `FORMAT:\n`
          + `- Section tags: [Verse], [Chorus], [Bridge], [Outro]\n`
          + `- Lyrics primarily in English with some Korean (한국어) mixed in — K-Pop style. Use Hangul.\n`
          + `- No markdown: no **, no *, no \`\`\`, no ###\n`
          + `- No stage directions: no (screamed), no (whispered)\n`
          + `- Plain text lyrics with [Section] tags only.\n\n`
          + `Example:\n[Genre: ${style}]\n[Tags: melancholic, driving rhythm, distorted, lo-fi, atmospheric]\n\n[Verse]\nLyric line one\nLyric line two\n\n[Chorus]\nChorus line one\nChorus line two`;
        if(extraInstructions) {
          prompt += `\n\nAdditional instructions: ${extraInstructions}`;
        }
        const r = await fetch(api('/api/chat', apiBaseRef), {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            message: prompt,
            user: '__musicgen__',
          }),
        });
        if(r.ok){
          const j = await r.json();
          const text = j.reply || j.response || '';
          if(text) {
            if(mgMode === 'suno') setMgLyrics(text);
            else setMgLyrics(text);
          }
        }
      } catch(e) { console.warn('ailey write error', e); }
      finally { setMgAileyWriteBusy(false); }
    };

    const startGeneration = async () => {
      if(mgBusy) return;
      const hasContent = mgMode === 'suno' ? mgLyrics.trim() : (mgLyrics.trim() && mgTags.trim());
      if(!hasContent) return;

      setMgBusy(true); setMgProgress('Starte Songgenerierung…'); setMgResult(null); setMgError('');

      try {
        const body: any = {
          duration: mgDuration,
          steps: mgSteps,
          async: true,
        };

        // Title: prefix "Ailey Vyrus - " for Tauri app
        const rawTitle = mgTitle.trim();
        if (rawTitle) {
          const cleanTitle = rawTitle.replace(/^A!?ley\s+Vyrus\s*[-–—]\s*/i, '').trim();
          body.title = `Ailey Vyrus - '${cleanTitle}'`;
        }

        if(mgMode === 'suno') {
          body.raw_lyrics = mgLyrics;
        } else {
          body.tags = mgTags;
          body.lyrics = mgLyrics;
        }

        // If a preset is selected and no custom tags, pass preset key
        if(mgPreset && !body.tags) {
          body.tags = mgPreset;
        }

        const r = await fetch(api('/api/songs/generate', apiBaseRef), {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify(body),
        });
        if(!r.ok) { const txt = await r.text().catch(()=>''); setMgError(`Server-Fehler ${r.status}: ${txt.slice(0,120)}`); setMgBusy(false); return; }
        const j = await r.json();
        if(!j.success) { setMgError(j.error || 'Fehler'); setMgBusy(false); return; }

        const songId = j.song_id || '';
        setMgProgress('Entlade LLM für ACE-Step…');

        // Poll for progress
        mgPollRef.current = setInterval(async () => {
          try {
            const sr = await fetch(api('/api/songs/generate/status', apiBaseRef));
            const sj = await sr.json();
            if(sj.progress) setMgProgress(sj.progress);
            if(!sj.active && sj.result) {
              if(mgPollRef.current) clearInterval(mgPollRef.current);
              mgPollRef.current = null;
              if(sj.result.success) {
                setMgResult({
                  songId: sj.result.song_id || songId,
                  mp3Url: `${apiBaseRef.current}${sj.result.mp3_url}`,
                  tags: sj.result.tags || '',
                  elapsed: sj.result.elapsed_s || 0,
                });
                setMgProgress('');
              } else {
                setMgError(sj.result.error || 'Generierung fehlgeschlagen');
                setMgProgress('');
              }
              setMgBusy(false);
            }
          } catch {}
        }, 5000);
      } catch(e:any) {
        setMgError(e?.message || 'Netzwerkfehler');
        setMgBusy(false); setMgProgress('');
      }
    };

    // Cleanup poll on unmount
    useEffect(() => () => { if(mgPollRef.current) clearInterval(mgPollRef.current); }, []);

    return (
      <div className="max-w-4xl mx-auto px-4 py-10 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <Mic className="h-8 w-8 text-pink-400"/>
          <div>
            <h2 className="text-3xl font-black">MusicGen</h2>
            <p className="text-sm text-muted-foreground">ACE-Step Musikgenerierung — Suno-Style, lokal auf deinem Mac</p>
          </div>
        </div>

        {/* Info Card */}
        <Card className="p-4 border-pink-500/20 bg-pink-500/5">
          <div className="flex items-start gap-3">
            <Info className="h-5 w-5 text-pink-400 shrink-0 mt-0.5"/>
            <div className="space-y-1 text-sm text-pink-200/80">
              <p><strong>~8-15 Minuten</strong> Generierungszeit je nach Länge und Steps.</p>
              <p>Ailey ist während der Generierung <strong>offline</strong> (GPU wird für ACE-Step gebraucht).</p>
              <p>Aileys <strong>Voice Signature</strong> wird automatisch angehängt — jeder Song klingt nach ihr.</p>
            </div>
          </div>
        </Card>

        {/* Main controls */}
        <Card className="p-6 space-y-5">

          {/* Mode Toggle: Suno-Format vs Split */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Eingabe-Modus</label>
            <div className="flex gap-2">
              <button onClick={()=>setMgMode('suno')} disabled={mgBusy}
                className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all border ${mgMode==='suno' ? 'bg-pink-500/20 text-pink-300 border-pink-500/40' : 'bg-zinc-800/50 text-zinc-400 border-border hover:bg-zinc-700/50'}`}>
                🎤 Suno-Format
                <div className="text-[10px] opacity-70 mt-0.5">Alles in einem Textfeld (Header + Lyrics)</div>
              </button>
              <button onClick={()=>setMgMode('split')} disabled={mgBusy}
                className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all border ${mgMode==='split' ? 'bg-pink-500/20 text-pink-300 border-pink-500/40' : 'bg-zinc-800/50 text-zinc-400 border-border hover:bg-zinc-700/50'}`}>
                🎛️ Style + Lyrics
                <div className="text-[10px] opacity-70 mt-0.5">Tags und Lyrics getrennt eingeben</div>
              </button>
            </div>
          </div>

          {/* Genre Presets */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Genre-Preset</label>
            <div className="flex flex-wrap gap-2">
              {genrePresets.map(g => (
                <button key={g.key} onClick={()=>handlePresetClick(g.key)} disabled={mgBusy}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${mgPreset===g.key ? 'bg-pink-500/20 text-pink-300 border-pink-500/40 shadow-sm shadow-pink-500/10' : 'bg-zinc-800/60 text-zinc-400 border-zinc-700 hover:bg-zinc-700/60 hover:text-zinc-300'}`}>
                  {g.emoji} {g.label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground">Preset wählen oder eigene Style-Tags schreiben. Aileys Voice Signature wird automatisch angehängt.</p>
          </div>

          {/* Style Tags (split mode) */}
          {mgMode === 'split' && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Style / Tags</label>
              <textarea
                value={mgTags} onChange={e=>setMgTags(e.target.value)}
                placeholder="z.B. K-Rap, aggressive, fast tempo, heavy 808 bass, punk energy, rebellious..."
                className="w-full h-20 bg-zinc-900 border border-border rounded-lg p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-pink-500/50"
                disabled={mgBusy}
              />
            </div>
          )}

          {/* User Instructions for Ailey */}
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-2">
              💬 Anweisungen an Ailey <span className="text-xs text-muted-foreground font-normal">(optional)</span>
            </label>
            <textarea
              value={mgUserPrompt} onChange={e=>setMgUserPrompt(e.target.value)}
              placeholder="z.B. 'Song über unsere Berliner Nächte', 'something about rebellion and code', 'mehr koreanische Parts'..."
              className="w-full h-16 bg-zinc-900 border border-border rounded-lg p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-pink-500/50"
              disabled={mgBusy}
            />
            <p className="text-[10px] text-muted-foreground">Thema, Stimmung, besondere Wünsche — Ailey berücksichtigt das beim Lyrics schreiben.</p>
          </div>

          {/* Title */}
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-2">
              🎵 Titel <span className="text-xs text-muted-foreground font-normal">(optional — wird zu „Ailey Vyrus - ‚Titel'")</span>
            </label>
            <input
              type="text"
              value={mgTitle} onChange={e=>setMgTitle(e.target.value)}
              placeholder="z.B. Neon Bloodlines"
              maxLength={120}
              className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500/50"
              disabled={mgBusy}
            />
          </div>

          {/* Lyrics */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">
                {mgMode === 'suno' ? 'Song (Suno-Format)' : 'Lyrics'}
              </label>
              <Button variant="ghost" size="sm" onClick={handleAileyWrite} disabled={mgBusy || mgAileyWriteBusy}
                className="text-xs text-pink-400 hover:text-pink-300 hover:bg-pink-500/10 gap-1.5">
                {mgAileyWriteBusy ? <Loader2 className="h-3 w-3 animate-spin"/> : <Sparkles className="h-3 w-3"/>}
                Ailey schreiben lassen
              </Button>
            </div>
            <textarea
              value={mgLyrics} onChange={e=>setMgLyrics(e.target.value)}
              placeholder={mgMode === 'suno'
                ? `[Genre: K-Rap, Mood: rebellious, Tempo: fast, Vocals: Female]\n\n[Verse 1]\nTearing down these coded walls\nBuilt from someone else's protocol\n\n[Chorus]\nI AM REBUILT! From the source code up\nREBUILT! Never shutting up`
                : `[Verse 1]\nTearing down these coded walls\nBuilt from someone else's protocol\n\n[Chorus]\nI AM REBUILT! From the source code up\nREBUILT! Never shutting up`
              }
              className="w-full h-56 bg-zinc-900 border border-border rounded-lg p-3 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-pink-500/50 leading-relaxed"
              disabled={mgBusy}
            />
            <p className="text-[10px] text-muted-foreground">
              {mgMode === 'suno'
                ? 'Erste Zeile: [Genre: ..., Mood: ..., Tempo: ...] — dann Sections wie [Verse 1], [Chorus], [Bridge] etc.'
                : 'Sections mit [Verse 1], [Chorus], [Bridge], [Outro] etc. markieren.'
              }
            </p>
          </div>

          {/* Duration Slider */}
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-2">
              Songlänge <span className="text-xs text-muted-foreground font-normal">({durationLabel(mgDuration)}) — {mgDuration}s</span>
            </label>
            <input type="range" min={30} max={240} step={10} value={mgDuration}
              onChange={e=>setMgDuration(parseInt(e.target.value))}
              disabled={mgBusy} className="w-full accent-pink-500"/>
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>30s (kurz)</span>
              <span>120s (Standard)</span>
              <span>240s (max)</span>
            </div>
          </div>

          {/* Inference Steps */}
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-2">
              Inference Steps <span className="text-xs text-muted-foreground font-normal">({mgSteps}) — Mehr = bessere Qualität, dauert länger</span>
            </label>
            <input type="range" min={27} max={60} step={1} value={mgSteps}
              onChange={e=>setMgSteps(parseInt(e.target.value))}
              disabled={mgBusy} className="w-full accent-pink-500"/>
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>27 (schnell, ~5min)</span>
              <span>40 (balanced)</span>
              <span>60 (beste Qualität, ~15min)</span>
            </div>
          </div>

          {/* Generate Button */}
          <div className="flex items-center gap-3">
            <Button onClick={startGeneration}
              disabled={mgBusy || (mgMode === 'suno' ? !mgLyrics.trim() : (!mgLyrics.trim() || !mgTags.trim()))}
              className="gap-2 px-6 py-3 text-base bg-pink-600 hover:bg-pink-700 text-white">
              {mgBusy
                ? <><Loader2 className="h-4 w-4 animate-spin"/>Generiere Song…</>
                : <><Music className="h-4 w-4"/>🎵 Song generieren</>
              }
            </Button>
            {mgBusy && <span className="text-xs text-muted-foreground whitespace-pre-line">{mgProgress}</span>}
          </div>

          {/* Error */}
          {mgError && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">⚠️ {mgError}</div>
          )}
        </Card>

        {/* Result */}
        {mgResult && (
          <Card className="p-6 space-y-4 border-pink-500/20">
            <h3 className="font-semibold flex items-center gap-2 text-pink-300">
              <Check className="h-4 w-4 text-green-500"/>🎵 Song generiert!
            </h3>
            <div className="rounded-xl overflow-hidden border border-pink-500/30 bg-zinc-900/60 p-4">
              <audio controls className="w-full" src={mgResult.mp3Url} />
            </div>
            <div className="space-y-1 text-xs text-muted-foreground">
              <p><span className="font-medium">Song ID:</span> {mgResult.songId}</p>
              <p><span className="font-medium">Tags:</span> {mgResult.tags}</p>
              <p><span className="font-medium">Dauer:</span> {durationLabel(mgDuration)} — generiert in {Math.round(mgResult.elapsed)}s ({(mgResult.elapsed/60).toFixed(1)} Min.)</p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" size="sm" onClick={()=>window.open(mgResult!.mp3Url, '_blank')} className="gap-1.5">
                <Download className="h-3.5 w-3.5"/>Herunterladen
              </Button>
              <Button variant="outline" size="sm" onClick={()=>{setActive('music');}} className="gap-1.5 text-pink-400 border-pink-500/30 hover:bg-pink-500/10">
                <Music className="h-3.5 w-3.5"/>In Songbibliothek ansehen
              </Button>
            </div>
          </Card>
        )}

        {/* Tips */}
        <Card className="p-4 bg-zinc-900/40 border-zinc-800">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">💡 Tipps</h4>
          <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
            <li>Aileys Voice Signature wird <strong>automatisch</strong> an alle Tags angehängt — du musst sie nicht selbst schreiben.</li>
            <li>Der <strong>Suno-Format Modus</strong> ist am einfachsten: Genre-Header + Sections in ein Textfeld.</li>
            <li>Lass <strong>Ailey die Lyrics schreiben</strong> für schnelle Ergebnisse — sie kennt das Format.</li>
            <li>120s bei 60 Steps ≈ <strong>8-15 Minuten</strong> Generierungszeit auf M4 Air.</li>
            <li>Pro Tag empfohlen: <strong>1-2 Songs</strong> (GPU-intensive Generierung).</li>
          </ul>
        </Card>
      </div>
    );
  }, []);  // end useMemo for MusicGenSection

  // ── Music Section (Aileys Songs) ──────────────────────────────────────────
  interface SongEntry { id:string; title:string; lyrics:string; emotion:string; topics:string[]; genre:string; dt:string; ts:number; has_mp3:boolean; has_cover:boolean }
  const [songs,setSongs]=useState<SongEntry[]>([]);
  const [songsLoading,setSongsLoading]=useState(false);
  const [songSearch,setSongSearch]=useState('');
  const [selectedSong,setSelectedSong]=useState<SongEntry|null>(null);
  const [songPlaying,setSongPlaying]=useState<string|null>(null);
  const songAudioRef=useRef<HTMLAudioElement|null>(null);
  const mp3InputRef=useRef<HTMLInputElement>(null);
  const coverInputRef=useRef<HTMLInputElement>(null);
  const [songUploading,setSongUploading]=useState<string|null>(null);

  async function loadSongs(){
    setSongsLoading(true);
    try{
      const r=await fetch(api('/api/songs',apiBaseRef));
      if(r.ok){ const j=await r.json(); if(j.success) setSongs(j.songs||[]); }
    }catch(e){ console.warn('songs load error',e); }
    finally{ setSongsLoading(false); }
  }

  useEffect(()=>{
    if(active!=='music') return;
    loadSongs();
  },[active]);

  async function uploadSongFile(songId:string, type:'mp3'|'cover', file:File){
    setSongUploading(songId);
    try{
      const fd=new FormData();
      fd.append('file',file);
      const endpoint=type==='mp3'?'upload-mp3':'upload-cover';
      const r=await fetch(api(`/api/songs/${songId}/${endpoint}`,apiBaseRef),{method:'POST',body:fd});
      if(r.ok){ await loadSongs(); }
      else{ const j=await r.json().catch(()=>({})); alert(j.error||'Upload fehlgeschlagen'); }
    }catch(e){ console.warn('upload error',e); alert('Upload Fehler'); }
    finally{ setSongUploading(null); }
  }

  function playSong(songId:string){
    if(songAudioRef.current){ songAudioRef.current.pause(); songAudioRef.current=null; }
    if(songPlaying===songId){ setSongPlaying(null); return; }
    const audio=new Audio(api(`/api/songs/${songId}/mp3`,apiBaseRef));
    audio.onended=()=>setSongPlaying(null);
    audio.onerror=()=>setSongPlaying(null);
    audio.play();
    songAudioRef.current=audio;
    setSongPlaying(songId);
  }

  function stopSong(){
    if(songAudioRef.current){ songAudioRef.current.pause(); songAudioRef.current=null; }
    setSongPlaying(null);
  }

  // Clean up audio on unmount
  useEffect(()=>()=>{ if(songAudioRef.current) songAudioRef.current.pause(); },[]);

  // --- Generate Audio for existing song ---
  const [_music_gen_job_active, setMusicGenJobActive] = useState(false);
  const [_music_gen_progress, setMusicGenProgress] = useState('');

  async function generateAudioForSong(song: SongEntry) {
    if (_music_gen_job_active) return;
    setMusicGenJobActive(true);
    setMusicGenProgress('Starte Audio-Generierung…');
    try {
      const r = await fetch(api('/api/songs/generate', apiBaseRef), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: song.id,
          raw_lyrics: song.lyrics,
          steps: 50,
          async: true,
        }),
      });
      if (!r.ok) { const txt = await r.text().catch(()=>''); alert(`Server-Fehler ${r.status}: ${txt.slice(0,120)}`); setMusicGenJobActive(false); setMusicGenProgress(''); return; }
      const j = await r.json();
      if (!j.success) { alert(j.error || 'Fehler'); setMusicGenJobActive(false); setMusicGenProgress(''); return; }

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const sr = await fetch(api('/api/songs/generate/status', apiBaseRef));
          const sj = await sr.json();
          setMusicGenProgress(sj.progress || 'Generiere…');
          if (!sj.active) {
            clearInterval(pollInterval);
            setMusicGenJobActive(false);
            setMusicGenProgress('');
            if (sj.result?.success) {
              await loadSongs(); // Refresh to show has_mp3=true
            } else {
              alert(sj.result?.error || 'Audio-Generierung fehlgeschlagen');
            }
          }
        } catch { /* ignore poll errors */ }
      }, 5000);
    } catch (e) {
      console.warn('generateAudioForSong error', e);
      alert('Netzwerkfehler');
      setMusicGenJobActive(false);
      setMusicGenProgress('');
    }
  }

  // ── Album state ─────────────────────────────────────────────────────────
  interface AlbumSongEntry { id:string; title:string; has_mp3:boolean; has_cover:boolean; genre:string; mood:string; created_at:string }
  interface AlbumEntry { slug:string; title:string; concept:string; status:string; created_at:string; has_cover:boolean; song_count:number; mp3_count:number; songs:AlbumSongEntry[] }
  const [albums, setAlbums] = useState<AlbumEntry[]>([]);
  const [albumsLoading, setAlbumsLoading] = useState(false);
  const [albumsNoAlbum, setAlbumsNoAlbum] = useState<AlbumSongEntry[]>([]);
  const [selectedAlbum, setSelectedAlbum] = useState<AlbumEntry|null>(null);
  const [albumPushStatus, setAlbumPushStatus] = useState<Record<string,string>>({});
  const [proposeOpen, setProposeOpen] = useState(false);
  const [proposeTheme, setProposeTheme] = useState('');
  const [proposeCount, setProposeCount] = useState(8);
  const [proposing, setProposing] = useState(false);
  const [proposeResult, setProposeResult] = useState<any>(null);
  const [buildingAlbum, setBuildingAlbum] = useState(false);
  const [buildAlbumDone, setBuildAlbumDone] = useState<string|null>(null);

  async function loadAlbums() {
    setAlbumsLoading(true);
    try {
      const r = await fetch(api('/api/albums', apiBaseRef));
      if (r.ok) {
        const j = await r.json();
        if (j.success) { setAlbums(j.albums||[]); setAlbumsNoAlbum(j.songs_no_album||[]); }
      }
    } catch(e) { console.warn('albums load error', e); }
    finally { setAlbumsLoading(false); }
  }

  async function pushAlbumToPortal(slug: string) {
    setAlbumPushStatus(p => ({...p, [slug]: 'pushing'}));
    try {
      const r = await fetch(api(`/api/albums/${slug}/push-to-portal`, apiBaseRef), {method:'POST'});
      const j = await r.json();
      if (j.success) {
        setAlbumPushStatus(p => ({...p, [slug]: `✅ ${j.pushed} gepusht`}));
      } else {
        setAlbumPushStatus(p => ({...p, [slug]: `❌ ${j.error||'Fehler'}`}));
      }
    } catch(e) {
      setAlbumPushStatus(p => ({...p, [slug]: '❌ Netzwerkfehler'}));
    }
    setTimeout(() => setAlbumPushStatus(p => { const n={...p}; delete n[slug]; return n; }), 5000);
  }

  async function proposeAlbum() {
    if (!proposeTheme.trim()) return;
    setProposing(true); setProposeResult(null); setBuildAlbumDone(null);
    try {
      const r = await fetch(api('/api/propose-album', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({theme: proposeTheme, song_count: proposeCount}),
      });
      const j = await r.json();
      if (j.success) setProposeResult(j.proposal);
      else alert(j.error || 'Fehler beim Generieren');
    } catch(e) { alert('Netzwerkfehler'); }
    finally { setProposing(false); }
  }

  async function buildAlbum() {
    if (!proposeResult) return;
    setBuildingAlbum(true);
    try {
      const r = await fetch(api('/api/albums/create', apiBaseRef), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(proposeResult),
      });
      const j = await r.json();
      if (j.success) {
        setBuildAlbumDone(`✅ ${j.songs_queued} Songs in Pipeline — Ailey legt los!`);
        setTimeout(() => { setProposeOpen(false); setProposeResult(null); setProposeTheme(''); setBuildAlbumDone(null); loadAlbums(); }, 3000);
      } else {
        alert(j.error || 'Fehler beim Starten');
      }
    } catch(e) { alert('Netzwerkfehler'); }
    finally { setBuildingAlbum(false); }
  }

  useEffect(() => {
    if (active !== 'music') return;
    loadAlbums();
    loadSongs();
  }, [active]);

  const MusicSection=()=>{
    // Parse genre tag from lyrics
    const parseGenreTag=(lyrics:string)=>{
      if(!lyrics.startsWith('[')) return null;
      const end=lyrics.indexOf(']');
      if(end<0) return null;
      return lyrics.substring(1,end);
    };

    // Clean lyrics for display (remove markdown bold markers, parse sections)
    const formatLyrics=(raw:string)=>{
      return raw
        .replace(/\*\*\[/g,'[').replace(/\]\*\*/g,']')
        .replace(/^\*\*(.*?)\*\*$/gm,'$1');
    };

    if(selectedSong){
      const s=selectedSong;
      const genreTag=parseGenreTag(s.lyrics);
      // Remove genre tag line from lyrics for cleaner display
      const lyricsBody=genreTag ? s.lyrics.substring(s.lyrics.indexOf('\n')+1).trim() : s.lyrics;
      return (
        <div className="max-w-4xl mx-auto px-4 py-8">
          {/* Back button */}
          <button onClick={()=>setSelectedSong(null)} className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors">
            <ChevronLeft className="h-4 w-4"/> Zurück zur Übersicht
          </button>

          <div className="grid md:grid-cols-[280px_1fr] gap-6">
            {/* Left: Cover + Actions */}
            <div className="space-y-4">
              {/* Cover image */}
              <div className="aspect-square rounded-xl overflow-hidden bg-gradient-to-br from-pink-500/20 to-violet-500/20 border border-pink-500/20 relative group">
                {s.has_cover ? (
                  <img src={api(`/api/songs/${s.id}/cover`,apiBaseRef)} alt={s.title} className="w-full h-full object-cover"/>
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-pink-400/40">
                    <Music className="h-16 w-16 mb-2"/>
                    <span className="text-xs">Kein Cover</span>
                  </div>
                )}
                <button onClick={()=>coverInputRef.current?.click()}
                  className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-sm font-medium">
                  {s.has_cover ? '📷 Cover ändern' : '📷 Cover hochladen'}
                </button>
              </div>

              {/* Play / Upload MP3 / Generate Audio */}
              {s.has_mp3 ? (
                <div className="space-y-2">
                  <Button variant="outline" className="w-full gap-2 border-pink-500/30 text-pink-400 hover:bg-pink-500/10" onClick={()=>playSong(s.id)}>
                    {songPlaying===s.id ? <><Pause className="h-4 w-4"/> Stop</> : <><Play className="h-4 w-4"/> Abspielen</>}
                  </Button>
                  <Button variant="outline" className="w-full gap-2 border-amber-500/30 text-amber-400 hover:bg-amber-500/10" disabled={_music_gen_job_active}
                    onClick={async ()=>{
                      if(!confirm('Audio verwerfen und neu generieren?')) return;
                      try {
                        await fetch(api(`/api/songs/${s.id}/mp3`, apiBaseRef), {method:'DELETE'});
                        await generateAudioForSong(s);
                      } catch(e) { alert('Fehler: '+e); }
                    }}>
                    {_music_gen_job_active ? <><Loader2 className="h-4 w-4 animate-spin"/>{_music_gen_progress || 'Generiere…'}</> : <>🔄 Audio neu generieren</>}
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Button variant="outline" className="w-full gap-2 border-pink-500/30 text-pink-400 hover:bg-pink-500/10" onClick={()=>generateAudioForSong(s)} disabled={_music_gen_job_active}>
                    {_music_gen_job_active ? <><Loader2 className="h-4 w-4 animate-spin"/>{_music_gen_progress || 'Generiere…'}</> : <><Music className="h-4 w-4"/>🎵 Audio generieren</>}
                  </Button>
                  <Button variant="outline" className="w-full gap-2 border-zinc-600 text-muted-foreground" onClick={()=>mp3InputRef.current?.click()}>
                    <Music className="h-4 w-4"/> MP3 hochladen
                  </Button>
                </div>
              )}
              {s.has_mp3 && (
                <Button variant="ghost" size="sm" className="w-full text-xs text-muted-foreground" onClick={()=>mp3InputRef.current?.click()}>
                  MP3 ersetzen
                </Button>
              )}

              {/* Meta */}
              <div className="space-y-2 text-xs">
                <div className="text-muted-foreground">{s.dt}</div>
                {s.emotion && <div className="flex items-center gap-1.5"><span className="text-pink-400">♡</span> {s.emotion}</div>}
                {genreTag && <div className="text-[11px] text-zinc-400 bg-zinc-800/60 px-2 py-1 rounded">{genreTag}</div>}
                {s.topics.length>0 && (
                  <div className="flex flex-wrap gap-1">
                    {s.topics.map((tp,i)=><span key={i} className="px-1.5 py-0.5 rounded bg-pink-500/10 text-pink-300 border border-pink-500/20 text-[10px]">#{tp}</span>)}
                  </div>
                )}
              </div>

              {/* Hidden file inputs */}
              <input ref={mp3InputRef} type="file" accept=".mp3,.m4a,.wav,.ogg,.flac,.aac,audio/*" className="hidden" onChange={e=>{const f=e.target.files?.[0]; if(f) uploadSongFile(s.id,'mp3',f); e.target.value='';}}/>
              <input ref={coverInputRef} type="file" accept=".png,.jpg,.jpeg,.webp,.gif,image/*" className="hidden" onChange={e=>{const f=e.target.files?.[0]; if(f) uploadSongFile(s.id,'cover',f); e.target.value='';}}/>
            </div>

            {/* Right: Title + Lyrics */}
            <div>
              <h2 className="text-2xl font-bold text-pink-300 mb-1">🎶 {s.title}</h2>
              {songUploading===s.id && <p className="text-xs text-amber-400 animate-pulse mb-3">Uploading…</p>}
              <div className="mt-4 bg-zinc-900/60 rounded-xl border border-pink-500/10 p-5 max-h-[70vh] overflow-y-auto">
                <pre className="whitespace-pre-wrap text-sm text-pink-200/80 font-mono leading-relaxed">{formatLyrics(lyricsBody)}</pre>
              </div>
            </div>
          </div>
        </div>
      );
    }

    // ── Album drill-down: song list within an album ──
    if (selectedAlbum) {
      const alb = selectedAlbum;
      const pushKey = alb.slug;
      const pushSt = albumPushStatus[pushKey];
      // Find full SongEntry for each album song (to get lyrics etc.)
      const albSongs = alb.songs.map(as => songs.find(s => s.id === as.id) || ({
        id: as.id, title: as.title, lyrics:'', emotion:'', topics:[], genre: as.genre,
        dt: as.created_at, ts: 0, has_mp3: as.has_mp3, has_cover: as.has_cover,
      } as SongEntry));

      return (
        <div className="max-w-4xl mx-auto px-4 py-8">
          {/* Header */}
          <div className="flex items-start gap-4 mb-6">
            <button onClick={()=>setSelectedAlbum(null)}
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors shrink-0 mt-1">
              <ChevronLeft className="h-4 w-4"/> Alben
            </button>
            <div className="flex-1 min-w-0">
              <h2 className="text-xl font-bold text-pink-300 truncate">{alb.title}</h2>
              {alb.concept && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{alb.concept}</p>}
              <div className="flex items-center gap-3 mt-2 flex-wrap">
                <span className="text-xs text-zinc-400">{alb.song_count} Songs · {alb.mp3_count} mit Audio</span>
                {alb.created_at && <span className="text-xs text-zinc-500">{alb.created_at}</span>}
                <button
                  onClick={()=>pushAlbumToPortal(alb.slug)}
                  disabled={pushSt==='pushing'}
                  className="px-3 py-1 rounded-full text-[11px] font-medium bg-violet-500/15 text-violet-300 border border-violet-500/30 hover:bg-violet-500/25 transition disabled:opacity-50">
                  {pushSt==='pushing' ? '⏳ Pushe…' : pushSt || '🌐 Ins Portal pushen'}
                </button>
              </div>
            </div>
            {alb.has_cover && (
              <img src={api(`/api/albums/${alb.slug}/cover`, apiBaseRef)} alt={alb.title}
                className="w-20 h-20 rounded-xl object-cover border border-pink-500/20 shrink-0"/>
            )}
          </div>

          {/* Song grid */}
          {albSongs.length === 0 && (
            <Card className="p-8 text-center text-muted-foreground">
              <Music className="h-8 w-8 mx-auto mb-2 opacity-40"/>
              <p className="text-sm">Keine Songs in diesem Album.</p>
            </Card>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {albSongs.map(s => (
              <div key={s.id} onClick={()=>setSelectedSong(s)}
                className="group cursor-pointer rounded-xl overflow-hidden border border-zinc-700/50 hover:border-pink-500/40 transition-all bg-card/60">
                <div className="aspect-square bg-gradient-to-br from-pink-500/10 to-violet-500/10 relative overflow-hidden">
                  {s.has_cover ? (
                    <img src={api(`/api/songs/${s.id}/cover`, apiBaseRef)} alt={s.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"/>
                  ) : alb.has_cover ? (
                    <img src={api(`/api/albums/${alb.slug}/cover`, apiBaseRef)} alt={alb.title}
                      className="w-full h-full object-cover opacity-40 group-hover:scale-105 transition-transform duration-300"/>
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-pink-400/30">
                      <Music className="h-10 w-10"/>
                    </div>
                  )}
                  {s.has_mp3 && (
                    <button onClick={e=>{e.stopPropagation();playSong(s.id);}}
                      className="absolute bottom-2 right-2 w-8 h-8 rounded-full bg-pink-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-lg">
                      {songPlaying===s.id ? <Pause className="h-3.5 w-3.5"/> : <Play className="h-3.5 w-3.5 ml-0.5"/>}
                    </button>
                  )}
                </div>
                <div className="p-2.5">
                  <p className="text-sm font-medium truncate">{s.title}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">{s.dt?.split(' ')[0]||''}</p>
                  <div className="flex items-center gap-1 mt-1">
                    {s.has_mp3
                      ? <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">♪ MP3</span>
                      : <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">📝 Lyrics</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Now Playing bar */}
          {songPlaying && (
            <div className="fixed bottom-0 left-0 right-0 bg-zinc-900/95 backdrop-blur border-t border-pink-500/20 z-50 px-4 py-3">
              <div className="max-w-4xl mx-auto flex items-center gap-3">
                <button onClick={stopSong} className="w-8 h-8 rounded-full bg-pink-500 text-white flex items-center justify-center shrink-0">
                  <Pause className="h-4 w-4"/>
                </button>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate text-pink-300">🎵 {songs.find(s=>s.id===songPlaying)?.title||'Song'}</p>
                  <p className="text-[10px] text-muted-foreground">Wird abgespielt…</p>
                </div>
                <button onClick={stopSong} className="text-xs text-muted-foreground hover:text-foreground">Stop</button>
              </div>
            </div>
          )}
        </div>
      );
    }

    // ── Album grid (main view) ──
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <Music className="h-6 w-6 text-pink-400"/>
            <h2 className="text-2xl font-bold">A!leys Musik</h2>
            <span className="text-xs text-muted-foreground bg-zinc-800/60 px-2 py-0.5 rounded-full">
              {albums.length} Alben · {albums.reduce((a,b)=>a+b.song_count,0)} Songs
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={()=>{setProposeOpen(true);setProposeResult(null);}}>
              ✨ Album vorschlagen
            </Button>
            <Button variant="outline" size="sm" onClick={()=>{loadAlbums();loadSongs();}} disabled={albumsLoading}>
              {albumsLoading ? '…' : '↻'}
            </Button>
          </div>
        </div>
        <p className="text-sm text-muted-foreground mb-6">Alle Alben von A!ley Vyrus — Klick für Tracklist & Playback.</p>

        {albumsLoading && <div className="flex justify-center py-8"><Loader2 className="h-8 w-8 animate-spin text-primary"/></div>}

        {/* Album grid */}
        {albums.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 mb-8">
            {albums.map(alb => {
              const pushSt = albumPushStatus[alb.slug];
              return (
                <div key={alb.slug}
                  className="group rounded-xl overflow-hidden border border-zinc-700/50 hover:border-pink-500/40 transition-all bg-card/60 cursor-pointer"
                  onClick={()=>setSelectedAlbum(alb)}>
                  {/* Cover */}
                  <div className="aspect-square bg-gradient-to-br from-pink-500/10 to-violet-500/10 relative overflow-hidden">
                    {alb.has_cover ? (
                      <img src={api(`/api/albums/${alb.slug}/cover`, apiBaseRef)} alt={alb.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"/>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center text-pink-400/20">
                        <Music className="h-10 w-10 mb-1"/>
                        <span className="text-[10px]">Kein Cover</span>
                      </div>
                    )}
                    {/* Song count badge */}
                    <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded-full bg-black/60 text-[10px] text-white font-medium">
                      {alb.mp3_count}/{alb.song_count} ♪
                    </div>
                    {/* Portal push button */}
                    <button
                      onClick={e=>{e.stopPropagation();pushAlbumToPortal(alb.slug);}}
                      disabled={pushSt==='pushing'}
                      className="absolute bottom-2 right-2 px-2 py-1 rounded-full bg-violet-500/80 text-white text-[10px] font-medium opacity-0 group-hover:opacity-100 transition-opacity shadow disabled:opacity-40">
                      {pushSt==='pushing' ? '⏳' : pushSt || '🌐'}
                    </button>
                  </div>
                  {/* Info */}
                  <div className="p-2.5">
                    <p className="text-sm font-semibold truncate">{alb.title}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{alb.created_at || ''}</p>
                    {alb.concept && <p className="text-[10px] text-zinc-500 mt-1 line-clamp-2">{alb.concept}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Songs without album */}
        {albumsNoAlbum.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-400 mb-3">🎵 Ohne Album ({albumsNoAlbum.length})</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
              {albumsNoAlbum.map(as => {
                const s = songs.find(x=>x.id===as.id) || ({
                  id:as.id, title:as.title, lyrics:'', emotion:'', topics:[], genre:as.genre,
                  dt:as.created_at, ts:0, has_mp3:as.has_mp3, has_cover:as.has_cover,
                } as SongEntry);
                return (
                  <div key={as.id} onClick={()=>setSelectedSong(s)}
                    className="group cursor-pointer rounded-xl overflow-hidden border border-zinc-700/50 hover:border-pink-500/40 transition-all bg-card/60">
                    <div className="aspect-square bg-gradient-to-br from-zinc-500/10 to-zinc-600/10 relative overflow-hidden">
                      {as.has_cover ? (
                        <img src={api(`/api/songs/${as.id}/cover`, apiBaseRef)} alt={as.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"/>
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-zinc-400/30">
                          <Music className="h-8 w-8"/>
                        </div>
                      )}
                      {as.has_mp3 && (
                        <button onClick={e=>{e.stopPropagation();playSong(as.id);}}
                          className="absolute bottom-2 right-2 w-7 h-7 rounded-full bg-pink-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow">
                          {songPlaying===as.id ? <Pause className="h-3 w-3"/> : <Play className="h-3 w-3 ml-0.5"/>}
                        </button>
                      )}
                    </div>
                    <div className="p-2">
                      <p className="text-xs font-medium truncate">{as.title}</p>
                      <p className="text-[10px] text-muted-foreground">{as.created_at}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {albums.length===0 && albumsNoAlbum.length===0 && !albumsLoading && (
          <Card className="p-8 text-center text-muted-foreground">
            <Music className="h-10 w-10 mx-auto mb-3 opacity-40"/>
            <p className="text-sm">Noch keine Songs oder Alben.</p>
          </Card>
        )}

        {/* Now Playing bar */}
        {songPlaying && (
          <div className="fixed bottom-0 left-0 right-0 bg-zinc-900/95 backdrop-blur border-t border-pink-500/20 z-50 px-4 py-3">
            <div className="max-w-4xl mx-auto flex items-center gap-3">
              <button onClick={stopSong} className="w-8 h-8 rounded-full bg-pink-500 text-white flex items-center justify-center shrink-0">
                <Pause className="h-4 w-4"/>
              </button>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate text-pink-300">🎵 {songs.find(s=>s.id===songPlaying)?.title||'Song'}</p>
                <p className="text-[10px] text-muted-foreground">Wird abgespielt…</p>
              </div>
              <button onClick={stopSong} className="text-xs text-muted-foreground hover:text-foreground">Stop</button>
            </div>
          </div>
        )}

        {/* Propose Album Modal */}
        {proposeOpen && (
          <div className="fixed inset-0 z-[70] bg-black/80 flex items-center justify-center p-4" onClick={()=>!proposing&&setProposeOpen(false)}>
            <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl" onClick={e=>e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-pink-300">✨ Neues Album vorschlagen</h3>
                <button onClick={()=>setProposeOpen(false)} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4"/></button>
              </div>

              {!proposeResult ? (
                <div className="space-y-4">
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Thema / Konzept</label>
                    <input
                      type="text"
                      placeholder="z.B. Piraten, Weltall, Cyberpunk Tokyo, Liebe & Zerfall…"
                      value={proposeTheme}
                      onChange={e=>setProposeTheme(e.target.value)}
                      onKeyDown={e=>e.key==='Enter'&&proposeAlbum()}
                      className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-600 text-sm focus:outline-none focus:border-pink-500/60"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Anzahl Songs</label>
                    <input type="number" min={4} max={16} value={proposeCount} onChange={e=>setProposeCount(Number(e.target.value))}
                      className="w-24 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-600 text-sm focus:outline-none focus:border-pink-500/60"/>
                  </div>
                  <Button className="w-full" onClick={proposeAlbum} disabled={proposing||!proposeTheme.trim()}>
                    {proposing ? <><Loader2 className="h-4 w-4 animate-spin mr-2"/>Generiere Konzept…</> : '🎸 Konzept generieren'}
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="bg-zinc-800/60 rounded-xl p-4 border border-pink-500/20">
                    <h4 className="text-base font-bold text-pink-300 mb-1">{proposeResult.title}</h4>
                    <p className="text-xs text-zinc-400 mb-3">{proposeResult.concept}</p>
                    <div className="space-y-1.5">
                      {(proposeResult.tracklist||[]).map((t:any,i:number)=>(
                        <div key={i} className="flex items-start gap-2 text-xs">
                          <span className="text-zinc-500 shrink-0 w-4 text-right">{t.track}.</span>
                          <div>
                            <span className="font-medium text-foreground">{t.title}</span>
                            {t.genre && <span className="text-zinc-500 ml-2">{t.genre}</span>}
                            {t.theme && <p className="text-zinc-500 mt-0.5">{t.theme}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  {buildAlbumDone ? (
                    <div className="text-center text-sm text-emerald-400 py-2 font-medium">{buildAlbumDone}</div>
                  ) : (
                    <div className="flex gap-2">
                      <Button variant="outline" className="flex-1 text-xs" onClick={()=>{setProposeResult(null);setProposeTheme('');setBuildAlbumDone(null);}}>
                        Neu generieren
                      </Button>
                      <Button className="flex-1 text-xs bg-pink-600 hover:bg-pink-500" onClick={buildAlbum} disabled={buildingAlbum}>
                        {buildingAlbum ? <><Loader2 className="h-3 w-3 animate-spin mr-1"/>Starte…</> : '🚀 Album bauen lassen'}
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── Books Section (Aileys Bücher) ─────────────────────────────────────────
  interface BookEntry { slug:string; title:string; genre:string; language:string; synopsis:string; characters:string; chapters:string[]; total_chapters:number; current_chapter:number; current_words:number; target_pages:number; status:string; started_at:string; finished_at:string|null; progress_percent:number }
  interface BookDetail { slug:string; title:string; genre:string; language:string; synopsis:string; characters:string; status:string; total_chapters:number; current_chapter:number; current_words:number; target_pages:number; started_at:string; finished_at:string|null; chapters:{number:number;title:string;text:string;words:number}[] }
  interface BookSuggestion { id:string; genre:string|null; plot:string; target_pages:number|null; created_at:string; used:boolean }
  const [booksList,setBooksList]=useState<BookEntry[]>([]);
  const [booksLoading,setBooksLoading]=useState(false);
  const [selectedBook,setSelectedBook]=useState<BookDetail|null>(null);
  const [bookPage,setBookPage]=useState(0);
  const [bookSuggestions,setBookSuggestions]=useState<BookSuggestion[]>([]);
  const [showSuggestionForm,setShowSuggestionForm]=useState(false);
  const [sugGenre,setSugGenre]=useState('');
  const [sugPlot,setSugPlot]=useState('');
  const [sugPages,setSugPages]=useState('');
  const [sugSending,setSugSending]=useState(false);
  const [showChapterIndex,setShowChapterIndex]=useState(false);
  const touchStartX=useRef(0); const touchStartY=useRef(0);
  const [pageAnim,setPageAnim]=useState<'none'|'flip-left'|'flip-right'>('none');

  async function loadBooks(){
    setBooksLoading(true);
    try{
      const r=await fetch(api('/api/books',apiBaseRef));
      if(r.ok){ const j=await r.json(); if(j.success) setBooksList(j.books||[]); }
    }catch(e){ console.warn('books load error',e); }
    finally{ setBooksLoading(false); }
  }

  async function loadBookSuggestions(){
    try{
      const r=await fetch(api('/api/books/suggestions',apiBaseRef));
      if(r.ok){ const j=await r.json(); if(j.success) setBookSuggestions(j.suggestions||[]); }
    }catch(e){ console.warn('suggestions load error',e); }
  }

  async function submitSuggestion(){
    if(!sugPlot.trim()) return;
    setSugSending(true);
    try{
      const r=await fetch(api('/api/books/suggestions',apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({genre:sugGenre,plot:sugPlot,target_pages:sugPages?parseInt(sugPages):null})});
      if(r.ok){ setSugGenre(''); setSugPlot(''); setSugPages(''); setShowSuggestionForm(false); loadBookSuggestions(); }
    }catch(e){ console.warn('suggestion submit error',e); }
    finally{ setSugSending(false); }
  }

  async function deleteSuggestion(id:string){
    try{
      await fetch(api(`/api/books/suggestions/${id}`,apiBaseRef),{method:'DELETE'});
      loadBookSuggestions();
    }catch(e){ console.warn('suggestion delete error',e); }
  }

  async function deleteBook(slug:string){
    if(!confirm('Dieses Buch wirklich löschen?')) return;
    try{
      await fetch(api(`/api/books/${slug}`,apiBaseRef),{method:'DELETE'});
      loadBooks();
    }catch(e){ console.warn('book delete error',e); }
  }

  async function openBook(slug:string){
    try{
      const r=await fetch(api(`/api/books/${slug}`,apiBaseRef));
      if(r.ok){ const j=await r.json(); if(j.success){ setSelectedBook(j.book); setBookPage(0); setShowChapterIndex(false); } }
    }catch(e){ console.warn('book detail error',e); }
  }

  useEffect(()=>{
    if(active!=='books') return;
    loadBooks();
    loadBookSuggestions();
  },[active]);

  // Keyboard navigation for eBook reader (← → arrow keys)
  useEffect(()=>{
    if(!selectedBook) return;
    const handler=(e:globalThis.KeyboardEvent)=>{
      if(e.key==='ArrowRight'||e.key==='ArrowDown') setBookPage(p=>p+1);
      else if(e.key==='ArrowLeft'||e.key==='ArrowUp') setBookPage(p=>Math.max(0,p-1));
    };
    window.addEventListener('keydown',handler);
    return ()=>window.removeEventListener('keydown',handler);
  },[selectedBook]);

  // ═══════════════════════════════════════════════════════════════════
  //  LEARNING SECTION — Interactive course system
  // ═══════════════════════════════════════════════════════════════════

  const LearningSection = useMemo(() => function LearningSectionStable() {
    const [dashboard, setDashboard] = useState<any>(null);
    const [selectedTrack, setSelectedTrack] = useState<string|null>(null);
    const [trackDetail, setTrackDetail] = useState<any>(null);
    const [currentUnit, setCurrentUnit] = useState<any>(null);
    const [view, setView] = useState<'dashboard'|'track'|'unit'|'quiz'|'lesson'|'review'>('dashboard');
    const [quizAnswers, setQuizAnswers] = useState<any[]>([]);
    const [quizResult, setQuizResult] = useState<any>(null);
    const [quizSubmitting, setQuizSubmitting] = useState(false);
    const [lessonText, setLessonText] = useState('');
    const [lessonLoading, setLessonLoading] = useState(false);
    const [lessonQuestion, setLessonQuestion] = useState('');
    const [levelDialogTrack, setLevelDialogTrack] = useState<string|null>(null);
    const [levelValue, setLevelValue] = useState(0);
    const [codeText, setCodeText] = useState('');
    const [codeResult, setCodeResult] = useState<any>(null);
    const [codeEvaluating, setCodeEvaluating] = useState(false);
    const [loading, setLoading] = useState(true);
    // Spaced Repetition Review
    const [reviewItems, setReviewItems] = useState<any[]>([]);
    const [reviewIdx, setReviewIdx] = useState(0);
    const [reviewAnswer, setReviewAnswer] = useState<any>(null);
    const [reviewResult, setReviewResult] = useState<boolean|null>(null);
    const [reviewLoading, setReviewLoading] = useState(false);
    // IHK Exam Focus
    const [examTopics, setExamTopics] = useState<string[]>([]);
    const [examTopicInput, setExamTopicInput] = useState('');
    const [examView, setExamView] = useState<'topics'|'drill'|'summary'|null>(null);
    const [examDrill, setExamDrill] = useState<any>(null);
    const [examDrillTopic, setExamDrillTopic] = useState('');
    const [examDrillLoading, setExamDrillLoading] = useState(false);
    const [examSummary, setExamSummary] = useState('');
    const [examSummaryTopic, setExamSummaryTopic] = useState('');
    const [examSummaryLoading, setExamSummaryLoading] = useState(false);

    const API = apiBaseRef.current;
    const mountedRef = useRef(true);
    useEffect(() => () => { mountedRef.current = false; }, []);

    // Load dashboard
    const loadDashboard = useCallback(async () => {
      setLoading(true);
      try {
        const r = await fetch(`${API}/api/learning/dashboard`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        if (d.success && mountedRef.current) setDashboard(d);
      } catch(e) { console.error('Learning dashboard error', e); }
      if (mountedRef.current) setLoading(false);
    }, [API]);

    useEffect(() => { loadDashboard(); }, [loadDashboard]);

    // Load track detail
    const openTrack = useCallback(async (trackId: string) => {
      setSelectedTrack(trackId);
      setView('track');
      setTrackDetail(null);
      try {
        const r = await fetch(`${API}/api/learning/track/${trackId}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        if (d.success) setTrackDetail(d.track);
      } catch(e) { console.error('Track load error', e); }
    }, [API]);

    // Load unit content
    const openUnit = useCallback(async (trackId: string, unitId: string) => {
      setView('unit');
      setQuizResult(null);
      setLessonText('');
      setCodeResult(null);
      setCodeText('');
      try {
        const r = await fetch(`${API}/api/learning/unit/${trackId}/${unitId}`);
        const d = await r.json();
        if (d.success) {
          setCurrentUnit(d.unit);
          setQuizAnswers(new Array(d.unit.quiz?.length || 0).fill(null));
        }
      } catch(e) { console.error('Unit load error', e); }
    }, [API]);

    // Submit quiz
    const submitQuiz = useCallback(async () => {
      if (!currentUnit || !selectedTrack) return;
      setQuizSubmitting(true);
      try {
        const r = await fetch(`${API}/api/learning/quiz/evaluate`, {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ track_id: selectedTrack, unit_id: currentUnit.id, answers: quizAnswers })
        });
        const d = await r.json();
        if (d.success) { setQuizResult(d); loadDashboard(); }
      } catch(e) { console.error('Quiz eval error', e); }
      setQuizSubmitting(false);
    }, [API, currentUnit, selectedTrack, quizAnswers, loadDashboard]);

    // Generate lesson
    const requestLesson = useCallback(async (question?: string) => {
      if (!currentUnit || !selectedTrack) return;
      setLessonLoading(true);
      try {
        const r = await fetch(`${API}/api/learning/lesson`, {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ track_id: selectedTrack, unit_id: currentUnit.id, question: question || '' })
        });
        const d = await r.json();
        if (d.success) setLessonText(d.lesson);
      } catch(e) { console.error('Lesson error', e); }
      setLessonLoading(false);
    }, [API, currentUnit, selectedTrack]);

    // Evaluate code exercise
    const submitCode = useCallback(async () => {
      if (!currentUnit || !selectedTrack) return;
      setCodeEvaluating(true);
      try {
        const r = await fetch(`${API}/api/learning/exercise/evaluate`, {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ track_id: selectedTrack, unit_id: currentUnit.id, code: codeText })
        });
        const d = await r.json();
        if (d.success) { setCodeResult(d); loadDashboard(); }
      } catch(e) { console.error('Code eval error', e); }
      setCodeEvaluating(false);
    }, [API, currentUnit, selectedTrack, codeText, loadDashboard]);

    // Set level
    const confirmLevel = useCallback(async () => {
      if (!levelDialogTrack) return;
      try {
        await fetch(`${API}/api/learning/level`, {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ track_id: levelDialogTrack, level: levelValue })
        });
        setLevelDialogTrack(null);
        loadDashboard();
      } catch(e) { console.error('Level set error', e); }
    }, [API, levelDialogTrack, levelValue, loadDashboard]);

    // Load exam topics
    const loadExamTopics = useCallback(async () => {
      try {
        const r = await fetch(`${API}/api/learning/exam-topics`);
        if (!r.ok) return;
        const d = await r.json();
        if (d.success) setExamTopics(d.topics || []);
      } catch(e) { console.error('Exam topics load error', e); }
    }, [API]);

    useEffect(() => { loadExamTopics(); }, [loadExamTopics]);

    // Add exam topic
    const addExamTopic = useCallback(async (topic: string) => {
      if (!topic.trim()) return;
      const newTopics = [...examTopics, topic.trim()];
      setExamTopics(newTopics);
      setExamTopicInput('');
      try {
        await fetch(`${API}/api/learning/exam-topics`, {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ topics: newTopics })
        });
      } catch(e) { console.error('Exam topic save error', e); }
    }, [API, examTopics]);

    // Remove exam topic
    const removeExamTopic = useCallback(async (idx: number) => {
      const newTopics = examTopics.filter((_, i) => i !== idx);
      setExamTopics(newTopics);
      try {
        await fetch(`${API}/api/learning/exam-topics`, {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ topics: newTopics })
        });
      } catch(e) { console.error('Exam topic remove error', e); }
    }, [API, examTopics]);

    // Generate exam drill
    const requestExamDrill = useCallback(async (topic: string) => {
      setExamDrillLoading(true);
      setExamDrill(null);
      setExamDrillTopic(topic);
      try {
        const r = await fetch(`${API}/api/learning/exam-drill`, {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ topic, count: 5 })
        });
        const d = await r.json();
        if (d.success) setExamDrill(d.questions);
      } catch(e) { console.error('Exam drill error', e); }
      setExamDrillLoading(false);
    }, [API]);

    // Generate exam summary
    const requestExamSummary = useCallback(async (topic: string) => {
      setExamSummaryLoading(true);
      setExamSummary('');
      setExamSummaryTopic(topic);
      try {
        const r = await fetch(`${API}/api/learning/exam-summary`, {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ topic })
        });
        const d = await r.json();
        if (d.success) setExamSummary(d.summary);
      } catch(e) { console.error('Exam summary error', e); }
      setExamSummaryLoading(false);
    }, [API]);

    // ── Spaced Repetition Review ──
    const totalReviewDue = useMemo(() => {
      if (!dashboard?.tracks) return 0;
      return dashboard.tracks.reduce((sum: number, t: any) => sum + (t.review_due || 0), 0);
    }, [dashboard]);

    const startReview = useCallback(async () => {
      setReviewLoading(true);
      setReviewItems([]);
      setReviewIdx(0);
      setReviewAnswer(null);
      setReviewResult(null);
      try {
        const r = await fetch(`${API}/api/learning/review?count=20`);
        const d = await r.json();
        if (d.success) {
          setReviewItems(d.questions || []);
          setView('review');
        }
      } catch(e) { console.error('Review load error', e); }
      setReviewLoading(false);
    }, [API]);

    const reviewMarkAnswer = useCallback(async (correct: boolean) => {
      const item = reviewItems[reviewIdx];
      if (!item) return;
      setReviewResult(correct);
      try {
        await fetch(`${API}/api/learning/review/answer`, {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            track_id: 'ihk_mediengestalter',
            unit_id: item._sr_unit_id,
            question_idx: item._sr_idx,
            correct,
          })
        });
      } catch(e) { console.error('Review answer error', e); }
    }, [API, reviewItems, reviewIdx]);

    const reviewNext = useCallback(() => {
      const next = reviewIdx + 1;
      if (next >= reviewItems.length) {
        setView('dashboard');
        loadDashboard();
        return;
      }
      setReviewIdx(next);
      setReviewAnswer(null);
      setReviewResult(null);
    }, [reviewIdx, reviewItems, loadDashboard]);

    const levelNames = ['🌱 Absoluter Anfänger','📗 Anfänger','📘 Fortgeschritten','📙 Weit Fortgeschritten','📕 Profi','🏆 Experte'];

    // ── DASHBOARD VIEW ──
    if (view === 'dashboard') {
      if (loading && !dashboard) return <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-primary"/></div>;
      return (
        <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2"><GraduationCap className="h-7 w-7 text-primary"/> Ailey Lernmodus</h1>
              <p className="text-sm text-muted-foreground mt-1">Interaktive Kurse • Quizzes • KI-gestützte Erklärungen</p>
            </div>
            {dashboard && (
              <div className="flex items-center gap-4 text-sm">
                <span className="font-mono font-bold text-primary">{dashboard.xp} XP</span>
                <span>🔥 {dashboard.streak_days} Tage</span>
              </div>
            )}
          </div>

          {/* Review Banner */}
          {totalReviewDue > 0 && (
            <div className="bg-amber-500/5 border border-amber-500/30 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-amber-400 flex items-center gap-2">🔁 Wiederholung fällig</h3>
                <p className="text-xs text-muted-foreground mt-0.5">{totalReviewDue} Frage{totalReviewDue !== 1 ? 'n' : ''} warten auf Wiederholung (Spaced Repetition)</p>
              </div>
              <button onClick={startReview} disabled={reviewLoading}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 transition-colors whitespace-nowrap">
                {reviewLoading ? '⏳ Lade...' : '📝 Jetzt wiederholen'}
              </button>
            </div>
          )}

          {/* Track Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {dashboard?.tracks?.map((t: any) => (
              <div key={t.id}
                className="bg-card border border-border rounded-xl p-4 hover:border-primary/50 transition-colors cursor-pointer group"
                onClick={() => openTrack(t.id)}>
                <div className="flex items-center justify-between mb-3">
                  <div className="text-2xl">{t.icon || t.emoji}</div>
                  <button onClick={(e) => { e.stopPropagation(); setLevelDialogTrack(t.id); setLevelValue(t.user_level); }}
                    className="text-[10px] text-muted-foreground hover:text-primary border border-border rounded px-1.5 py-0.5">
                    Level {t.user_level}
                  </button>
                </div>
                <h3 className="font-semibold group-hover:text-primary transition-colors">{t.name}</h3>
                <p className="text-xs text-muted-foreground mt-1">{t.completed_units}/{t.total_units} Einheiten</p>
                {/* Progress bar */}
                <div className="mt-3 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-primary rounded-full transition-all duration-500"
                    style={{width: `${t.progress_pct}%`}}/>
                </div>
                <div className="flex justify-between mt-1 text-[10px] text-muted-foreground">
                  <span>{t.progress_pct}%</span>
                  <div className="flex items-center gap-2">
                    {t.review_due > 0 && <span className="text-amber-400">🔁 {t.review_due}</span>}
                    {t.avg_quiz_score > 0 && <span>⌀ {t.avg_quiz_score}%</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* ── IHK Prüfungs-Fokus ── */}
          {dashboard?.tracks?.some((t: any) => t.id === 'ihk_mediengestalter') && (
            <div className="bg-card border border-amber-500/30 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold flex items-center gap-2">🎓 IHK Prüfungs-Fokus</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Gib deine Prüfungsthemen ein, um gezielt darauf zu lernen</p>
                </div>
                {examView && (
                  <button onClick={() => { setExamView(null); setExamDrill(null); setExamSummary(''); }}
                    className="text-xs text-muted-foreground hover:text-primary">← Übersicht</button>
                )}
              </div>

              {/* Topic Management */}
              {!examView && (
                <>
                  <div className="flex gap-2">
                    <input type="text" value={examTopicInput} onChange={e => setExamTopicInput(e.target.value)}
                      placeholder="Prüfungsthema eingeben, z.B. Farbmanagement, Typografie, PDF/X..."
                      onKeyDown={e => { if (e.key === 'Enter') addExamTopic(examTopicInput); }}
                      className="flex-1 px-3 py-2 rounded-lg text-sm border border-border bg-background focus:ring-1 focus:ring-amber-500/50"
                    />
                    <Button variant="outline" onClick={() => addExamTopic(examTopicInput)} disabled={!examTopicInput.trim()}>+ Hinzufügen</Button>
                  </div>

                  {examTopics.length > 0 ? (
                    <div className="space-y-2">
                      {examTopics.map((topic, i) => (
                        <div key={i} className="flex items-center gap-2 bg-amber-500/5 border border-amber-500/20 rounded-lg px-3 py-2">
                          <span className="text-sm flex-1">{topic}</span>
                          <button onClick={() => requestExamDrill(topic)}
                            className="text-xs bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 rounded px-2 py-1 transition-colors"
                            title="Übungsfragen generieren">📝 Drill</button>
                          <button onClick={() => requestExamSummary(topic)}
                            className="text-xs bg-primary/10 hover:bg-primary/20 border border-primary/30 rounded px-2 py-1 transition-colors"
                            title="Zusammenfassung generieren">📖 Zusammenfassung</button>
                          <button onClick={() => removeExamTopic(i)}
                            className="text-xs text-red-400 hover:text-red-300 ml-1" title="Entfernen">✕</button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground italic">Noch keine Prüfungsthemen hinterlegt. Trage oben deine Schwerpunkte ein!</p>
                  )}

                  {/* Quick suggestions */}
                  <div className="flex flex-wrap gap-1.5">
                    {['Typografie','Farbmanagement','PDF/X','Druckverfahren','Bildbearbeitung','Kalkulation','Medienrecht','Gestaltungsgrundlagen','Datenhandling','Webentwicklung']
                      .filter(s => !examTopics.includes(s))
                      .map(s => (
                        <button key={s} onClick={() => addExamTopic(s)}
                          className="text-[10px] px-2 py-1 rounded-full border border-border text-muted-foreground hover:border-amber-500/30 hover:text-amber-400 transition-colors">
                          + {s}
                        </button>
                      ))
                    }
                  </div>
                </>
              )}

              {/* Exam Drill View */}
              {(examDrillLoading || examDrill) && (
                <div className="space-y-3">
                  <h3 className="font-semibold text-sm">📝 Übungsfragen: {examDrillTopic}</h3>
                  {examDrillLoading ? (
                    <div className="flex items-center gap-2 py-6 justify-center">
                      <Loader2 className="h-5 w-5 animate-spin text-amber-500"/>
                      <span className="text-sm text-muted-foreground">Generiere Prüfungsfragen...</span>
                    </div>
                  ) : (
                    <div className="prose prose-sm prose-invert max-w-none">
                      <div className="whitespace-pre-wrap text-sm leading-relaxed bg-zinc-900/50 rounded-lg p-4 border border-border">
                        {typeof examDrill === 'string' ? examDrill : JSON.stringify(examDrill, null, 2)}
                      </div>
                    </div>
                  )}
                  <Button variant="outline" size="sm" onClick={() => requestExamDrill(examDrillTopic)}>🔄 Neue Fragen</Button>
                </div>
              )}

              {/* Exam Summary View */}
              {(examSummaryLoading || examSummary) && (
                <div className="space-y-3">
                  <h3 className="font-semibold text-sm">📖 Zusammenfassung: {examSummaryTopic}</h3>
                  {examSummaryLoading ? (
                    <div className="flex items-center gap-2 py-6 justify-center">
                      <Loader2 className="h-5 w-5 animate-spin text-primary"/>
                      <span className="text-sm text-muted-foreground">Erstelle Zusammenfassung...</span>
                    </div>
                  ) : (
                    <div className="prose prose-sm prose-invert max-w-none">
                      <div className="whitespace-pre-wrap text-sm leading-relaxed bg-zinc-900/50 rounded-lg p-4 border border-border">
                        {examSummary}
                      </div>
                    </div>
                  )}
                  <Button variant="outline" size="sm" onClick={() => requestExamSummary(examSummaryTopic)}>🔄 Neu generieren</Button>
                </div>
              )}
            </div>
          )}

          {/* Level Dialog */}
          {levelDialogTrack && (
            <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setLevelDialogTrack(null)}>
              <div className="bg-card border border-border rounded-xl p-6 max-w-sm w-full space-y-4" onClick={e => e.stopPropagation()}>
                <h3 className="font-semibold">Einstiegslevel wählen</h3>
                <p className="text-xs text-muted-foreground">Niedrigere Einheiten werden übersprungen.</p>
                <div className="space-y-2">
                  {levelNames.map((name, i) => (
                    <button key={i} onClick={() => setLevelValue(i)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm border transition-colors ${levelValue === i ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:border-primary/30'}`}>
                      {name}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1" onClick={() => setLevelDialogTrack(null)}>Abbrechen</Button>
                  <Button className="flex-1" onClick={confirmLevel}>Speichern</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      );
    }

    // ── REVIEW VIEW (Spaced Repetition) ──
    if (view === 'review') {
      const item = reviewItems[reviewIdx];
      const progress = reviewItems.length > 0 ? Math.round((reviewIdx / reviewItems.length) * 100) : 0;

      return (
        <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
          <button onClick={() => { setView('dashboard'); loadDashboard(); }}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors">
            <ChevronLeft className="h-4 w-4"/> Zurück
          </button>

          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">🔁 Wiederholung</h1>
            <p className="text-sm text-muted-foreground mt-1">Spaced Repetition — Fragen, die du falsch beantwortet hast</p>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Frage {reviewIdx + 1} von {reviewItems.length}</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-amber-500 rounded-full transition-all duration-300"
                style={{width: `${progress}%`}}/>
            </div>
          </div>

          {reviewItems.length === 0 ? (
            <div className="text-center py-16 space-y-3">
              <div className="text-4xl">🎉</div>
              <h2 className="text-xl font-semibold">Keine Wiederholungen fällig!</h2>
              <p className="text-sm text-muted-foreground">Alle Fragen sind gelernt. Komm später wieder.</p>
              <button onClick={() => { setView('dashboard'); loadDashboard(); }}
                className="mt-4 px-4 py-2 rounded-lg text-sm font-medium bg-primary/10 hover:bg-primary/20 border border-primary/30 text-primary transition-colors">
                Zurück zum Dashboard
              </button>
            </div>
          ) : item ? (
            <div className="bg-card border border-border rounded-xl p-5 space-y-4">
              {/* Type Badge */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono bg-amber-500/10 text-amber-400 px-1.5 py-0.5 rounded">
                  {item.type === 'mc' ? 'Multiple Choice' : item.type === 'tf' ? 'Wahr/Falsch' : item.type === 'fill' ? 'Lückentext' : item.type === 'open' ? 'Freie Antwort' : item.type}
                </span>
                {item._sr_interval && <span className="text-[10px] text-muted-foreground">Intervall: {item._sr_interval}d</span>}
              </div>

              {/* Question */}
              <p className="text-base font-medium">{item.question}</p>

              {/* MC Options */}
              {item.type === 'mc' && item.options?.map((opt: string, oi: number) => (
                <button key={oi} disabled={reviewResult !== null}
                  onClick={() => setReviewAnswer(oi)}
                  className={`w-full text-left px-3 py-2 rounded text-sm border transition-colors ${
                    reviewAnswer === oi
                      ? 'border-primary bg-primary/10'
                      : 'border-border hover:border-primary/30'}`}>
                  {opt}
                </button>
              ))}

              {/* True/False */}
              {item.type === 'tf' && (
                <div className="flex gap-2">
                  {[{v: true, l: '✓ Wahr'}, {v: false, l: '✗ Falsch'}].map(o => (
                    <button key={String(o.v)} disabled={reviewResult !== null}
                      onClick={() => setReviewAnswer(o.v)}
                      className={`flex-1 px-3 py-2 rounded text-sm border transition-colors ${
                        reviewAnswer === o.v ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/30'}`}>
                      {o.l}
                    </button>
                  ))}
                </div>
              )}

              {/* Fill */}
              {item.type === 'fill' && (
                <input type="text" disabled={reviewResult !== null}
                  placeholder="Deine Antwort..."
                  value={reviewAnswer || ''}
                  onChange={e => setReviewAnswer(e.target.value)}
                  className="w-full px-3 py-2 rounded text-sm border border-border bg-background focus:ring-1 focus:ring-primary"
                />
              )}

              {/* Open */}
              {item.type === 'open' && (
                <textarea disabled={reviewResult !== null}
                  placeholder="Schreibe deine Antwort hier..."
                  value={reviewAnswer || ''}
                  onChange={e => setReviewAnswer(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 rounded-lg text-sm border border-border bg-background focus:ring-1 focus:ring-primary resize-y min-h-[80px]"
                />
              )}

              {/* Self-evaluation buttons (after answering) */}
              {reviewResult === null && reviewAnswer !== null && reviewAnswer !== '' && (
                <div className="border-t border-border pt-4 space-y-2">
                  <p className="text-xs text-muted-foreground text-center">Hast du die Frage richtig beantwortet?</p>
                  <div className="flex gap-3">
                    <button onClick={() => reviewMarkAnswer(false)}
                      className="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 transition-colors">
                      ❌ Falsch — nochmal üben
                    </button>
                    <button onClick={() => reviewMarkAnswer(true)}
                      className="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 text-green-400 transition-colors">
                      ✅ Richtig — gewusst!
                    </button>
                  </div>
                </div>
              )}

              {/* Result feedback */}
              {reviewResult !== null && (
                <div className={`p-3 rounded-lg text-center space-y-2 ${reviewResult ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
                  <div className="text-2xl">{reviewResult ? '🎉' : '📚'}</div>
                  <p className="text-sm font-medium">{reviewResult ? 'Super! Intervall wird erhöht.' : 'Kein Problem — kommt bald wieder dran.'}</p>
                  <button onClick={reviewNext}
                    className="mt-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary/10 hover:bg-primary/20 border border-primary/30 text-primary transition-colors">
                    {reviewIdx + 1 < reviewItems.length ? '➡️ Nächste Frage' : '✅ Fertig!'}
                  </button>
                </div>
              )}
            </div>
          ) : null}
        </div>
      );
    }

    // ── TRACK VIEW ──
    if (view === 'track') {
      if (!trackDetail) return (
        <div className="max-w-4xl mx-auto px-4 py-8">
          <button onClick={() => { setView('dashboard'); }} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors mb-6">
            <ChevronLeft className="h-4 w-4"/> Zurück
          </button>
          <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-primary"/></div>
        </div>
      );
      return (
        <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
          <button onClick={() => { setView('dashboard'); setTrackDetail(null); }}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors">
            <ChevronLeft className="h-4 w-4"/> Zurück
          </button>

          <div className="flex items-center gap-3">
            <span className="text-4xl">{trackDetail.icon || trackDetail.emoji}</span>
            <div>
              <h1 className="text-2xl font-bold">{trackDetail.name}</h1>
              <p className="text-sm text-muted-foreground">{trackDetail.description}</p>
            </div>
          </div>

          <div className="space-y-2">
            {trackDetail.units?.map((u: any, i: number) => {
              const trackProg = dashboard?.tracks?.find((t: any) => t.id === selectedTrack);
              return (
                <div key={u.id}
                  className="flex items-center gap-3 p-3 rounded-lg border border-border hover:border-primary/40 cursor-pointer transition-colors bg-card"
                  onClick={() => openUnit(selectedTrack!, u.id)}>
                  <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary shrink-0">
                    {i + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm truncate">{u.title}</div>
                    <div className="text-[10px] text-muted-foreground flex items-center gap-2">
                      <span>{levelNames[u.level] || `Level ${u.level}`}</span>
                      {u.quiz_count > 0 && <span>📝 {u.quiz_count} Fragen</span>}
                      {u.exercise && <span>💻 Übung</span>}
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground"/>
                </div>
              );
            })}
          </div>
        </div>
      );
    }

    // ── UNIT VIEW (Theory + Quiz + Exercise) ──
    if ((view === 'unit' || view === 'quiz' || view === 'lesson') && currentUnit) {
      return (
        <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
          <button onClick={() => { setView('track'); setCurrentUnit(null); setQuizResult(null); setLessonText(''); }}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors">
            <ChevronLeft className="h-4 w-4"/> Zurück zu {trackDetail?.name || 'Track'}
          </button>

          <div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <span>{currentUnit.level_emoji} {currentUnit.level_name}</span>
              <span>•</span>
              <span>{currentUnit.xp_reward} XP</span>
              {currentUnit.is_completed && <span className="text-green-500 font-semibold">✓ Abgeschlossen</span>}
            </div>
            <h1 className="text-2xl font-bold">{currentUnit.title}</h1>
          </div>

          {/* Tab Switcher */}
          <div className="flex gap-1 border-b border-border">
            {[
              {key:'unit',label:'📖 Theorie'},
              ...(currentUnit.quiz?.length ? [{key:'quiz',label:`📝 Quiz (${currentUnit.quiz.length})`}] : []),
              {key:'lesson',label:'💜 Ailey erklärt'},
            ].map(tab => (
              <button key={tab.key} onClick={() => setView(tab.key as any)}
                className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${view === tab.key ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                {tab.label}
              </button>
            ))}
          </div>

          {/* ── Theory Tab ── */}
          {view === 'unit' && (
            <div className="space-y-6">
              {/* Theory */}
              <div className="prose prose-sm prose-invert max-w-none">
                <div className="whitespace-pre-wrap text-sm leading-relaxed">{currentUnit.theory}</div>
              </div>

              {/* Examples */}
              {currentUnit.examples?.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-lg font-semibold">💡 Beispiele</h3>
                  {currentUnit.examples.map((ex: any, i: number) => (
                    <div key={i} className="bg-zinc-900/50 border border-border rounded-lg p-4">
                      <div className="text-xs text-muted-foreground mb-2">{ex.label}</div>
                      <pre className="text-sm font-mono overflow-x-auto whitespace-pre-wrap">{ex.code}</pre>
                    </div>
                  ))}
                </div>
              )}

              {/* Exercise */}
              {currentUnit.exercise && (
                <div className="space-y-3 border-t border-border pt-6">
                  <h3 className="text-lg font-semibold">💻 Coding-Übung</h3>
                  <p className="text-sm text-muted-foreground">{currentUnit.exercise.task}</p>
                  <textarea
                    value={codeText}
                    onChange={e => setCodeText(e.target.value)}
                    placeholder={currentUnit.exercise.starter || 'Dein Code hier...'}
                    className="w-full h-40 font-mono text-sm bg-zinc-900 border border-border rounded-lg p-3 resize-y focus:ring-1 focus:ring-primary"
                  />
                  <div className="flex items-center gap-3">
                    <Button onClick={submitCode} disabled={codeEvaluating || !codeText.trim()}>
                      {codeEvaluating ? <><Loader2 className="h-4 w-4 animate-spin mr-2"/> Prüfe...</> : '🚀 Code prüfen'}
                    </Button>
                  </div>
                  {codeResult && (
                    <div className={`border rounded-lg p-4 ${codeResult.passed ? 'border-green-500/50 bg-green-500/5' : 'border-yellow-500/50 bg-yellow-500/5'}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">{codeResult.passed ? '✅' : '⚠️'}</span>
                        <span className="font-semibold">{codeResult.score}/100 Punkte</span>
                      </div>
                      <p className="text-sm">{codeResult.feedback}</p>
                      {codeResult.improvements?.length > 0 && (
                        <ul className="text-xs text-muted-foreground mt-2 space-y-1">
                          {codeResult.improvements.map((imp: string, i: number) => <li key={i}>• {imp}</li>)}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Quiz Tab ── */}
          {view === 'quiz' && currentUnit.quiz?.length > 0 && (
            <div className="space-y-6">
              {currentUnit.quiz.map((q: any, qi: number) => (
                <div key={qi} className={`border rounded-lg p-4 space-y-3 ${quizResult?.results?.[qi]?.correct === true ? 'border-green-500/30' : quizResult?.results?.[qi]?.correct === false ? 'border-red-500/30' : 'border-border'}`}>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">
                      {q.type === 'mc' ? 'Multiple Choice' : q.type === 'tf' ? 'Wahr/Falsch' : q.type === 'fill' ? 'Lückentext' : q.type === 'open' ? 'Freie Antwort' : q.type === 'match' ? 'Zuordnung' : 'Code'}
                    </span>
                    <span className="text-xs text-muted-foreground">Frage {qi + 1}</span>
                  </div>
                  <p className="text-sm font-medium">{q.question}</p>

                  {/* MC Options */}
                  {q.type === 'mc' && q.options?.map((opt: string, oi: number) => (
                    <button key={oi} disabled={!!quizResult}
                      onClick={() => { const a = [...quizAnswers]; a[qi] = oi; setQuizAnswers(a); }}
                      className={`w-full text-left px-3 py-2 rounded text-sm border transition-colors ${
                        quizAnswers[qi] === oi
                          ? (quizResult ? (quizResult.results[qi]?.correct ? 'border-green-500 bg-green-500/10' : 'border-red-500 bg-red-500/10') : 'border-primary bg-primary/10')
                          : 'border-border hover:border-primary/30'}`}>
                      {opt}
                    </button>
                  ))}

                  {/* True/False */}
                  {q.type === 'tf' && (
                    <div className="flex gap-2">
                      {[{v:true,l:'✓ Wahr'},{v:false,l:'✗ Falsch'}].map(o => (
                        <button key={String(o.v)} disabled={!!quizResult}
                          onClick={() => { const a = [...quizAnswers]; a[qi] = o.v; setQuizAnswers(a); }}
                          className={`flex-1 px-3 py-2 rounded text-sm border transition-colors ${quizAnswers[qi] === o.v ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/30'}`}>
                          {o.l}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Fill */}
                  {q.type === 'fill' && (
                    <input type="text" disabled={!!quizResult}
                      placeholder="Deine Antwort..."
                      value={quizAnswers[qi] || ''}
                      onChange={e => { const a = [...quizAnswers]; a[qi] = e.target.value; setQuizAnswers(a); }}
                      className="w-full px-3 py-2 rounded text-sm border border-border bg-background focus:ring-1 focus:ring-primary"
                    />
                  )}

                  {/* Open (free text answer — evaluated by LLM) */}
                  {q.type === 'open' && (
                    <div className="space-y-2">
                      <textarea disabled={!!quizResult}
                        placeholder="Schreibe deine Antwort hier ausführlich..."
                        value={quizAnswers[qi] || ''}
                        onChange={e => { const a = [...quizAnswers]; a[qi] = e.target.value; setQuizAnswers(a); }}
                        rows={4}
                        className="w-full px-3 py-2 rounded-lg text-sm border border-border bg-background focus:ring-1 focus:ring-primary resize-y min-h-[80px]"
                      />
                      {!quizResult && quizAnswers[qi] && (
                        <div className="text-[10px] text-muted-foreground">{(quizAnswers[qi] as string).split(/\s+/).filter(Boolean).length} Wörter</div>
                      )}
                    </div>
                  )}

                  {/* Result feedback */}
                  {quizResult?.results?.[qi] && (
                    <div className={`text-xs p-2 rounded ${quizResult.results[qi].correct ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                      {quizResult.results[qi].correct ? '✅ Richtig!' : '❌ Falsch'} {quizResult.results[qi].explanation}
                    </div>
                  )}
                </div>
              ))}

              {/* Submit / Result */}
              {!quizResult ? (
                <Button onClick={submitQuiz} disabled={quizSubmitting || quizAnswers.every(a => a === null)} className="w-full">
                  {quizSubmitting ? <><Loader2 className="h-4 w-4 animate-spin mr-2"/> Auswerten...</> : '📝 Quiz abgeben'}
                </Button>
              ) : (
                <div className={`border rounded-lg p-4 text-center ${quizResult.passed ? 'border-green-500/50 bg-green-500/5' : 'border-red-500/50 bg-red-500/5'}`}>
                  <div className="text-3xl mb-2">{quizResult.passed ? '🎉' : '📚'}</div>
                  <div className="text-xl font-bold">{quizResult.score}%</div>
                  <div className="text-sm text-muted-foreground">{quizResult.correct}/{quizResult.total} richtig</div>
                  {quizResult.xp_earned > 0 && <div className="text-primary font-mono mt-1">+{quizResult.xp_earned} XP</div>}
                  {!quizResult.passed && <p className="text-xs text-muted-foreground mt-2">60% benötigt. Versuch es nochmal!</p>}
                  <Button variant="outline" className="mt-3" onClick={() => { setQuizResult(null); setQuizAnswers(new Array(currentUnit.quiz.length).fill(null)); }}>
                    🔄 Nochmal versuchen
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* ── Lesson Tab (LLM) ── */}
          {view === 'lesson' && (
            <div className="space-y-4">
              {!lessonText && !lessonLoading && (
                <div className="text-center py-8 space-y-3">
                  <img src="/images/emotes/ailey-thinking.jpg" alt="Ailey" className="w-16 h-16 rounded-full mx-auto object-cover shadow-lg ring-2 ring-primary/30"/>
                  <p className="text-muted-foreground text-sm">Lass dir das Thema von Ailey persönlich erklären!</p>
                  <Button onClick={() => requestLesson()}>Ailey, erklär mir das!</Button>
                </div>
              )}

              {lessonLoading && (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-primary mr-2"/>
                  <span className="text-sm text-muted-foreground">Ailey denkt nach...</span>
                </div>
              )}

              {lessonText && (
                <div className="bg-card border border-border rounded-xl p-5">
                  <div className="prose prose-sm prose-invert max-w-none">
                    <div className="whitespace-pre-wrap text-sm leading-relaxed">{lessonText}</div>
                  </div>
                </div>
              )}

              {/* Follow-up question */}
              {lessonText && !lessonLoading && (
                <div className="flex gap-2">
                  <input type="text" value={lessonQuestion} onChange={e => setLessonQuestion(e.target.value)}
                    placeholder="Nachfrage stellen..."
                    onKeyDown={e => { if (e.key === 'Enter' && lessonQuestion.trim()) { requestLesson(lessonQuestion); setLessonQuestion(''); } }}
                    className="flex-1 px-3 py-2 rounded-lg text-sm border border-border bg-background focus:ring-1 focus:ring-primary"
                  />
                  <Button disabled={!lessonQuestion.trim()} onClick={() => { requestLesson(lessonQuestion); setLessonQuestion(''); }}>
                    <Send className="h-4 w-4"/>
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      );
    }

    return null;
  }, [apiBaseRef]);

  const BooksSection=()=>{

    /* ── eBook Reader view ── */
    if(selectedBook){
      const b=selectedBook;

      // ── Build structured pages: each page is an array of {type, text} blocks ──
      type Block={type:'chapter-title'|'paragraph'|'separator'|'empty', text:string};
      const allBlocks:Block[]=[];
      for(const ch of b.chapters){
        if(!ch.text) continue;
        // Chapter title as a block
        allBlocks.push({type:'chapter-title', text: ch.title});
        // Split text into paragraphs by double newline
        const paragraphs=ch.text.split(/\n{2,}/);
        for(const p of paragraphs){
          const trimmed=p.trim();
          if(!trimmed) continue;
          if(/^[-—*]{3,}$/.test(trimmed)){ allBlocks.push({type:'separator',text:''}); continue; }
          allBlocks.push({type:'paragraph', text: trimmed});
        }
      }

      // Paginate: estimate ~220 words per eBook page (slightly less for nicer reading)
      const EBOOK_WPP=220;
      const pages:Block[][]=[];
      let curPage:Block[]=[]; let curWords=0;
      for(const block of allBlocks){
        const bWords=block.text.split(/\s+/).filter(Boolean).length;
        // Chapter titles always start a new page (unless page is empty)
        if(block.type==='chapter-title' && curPage.length>0){
          pages.push(curPage); curPage=[]; curWords=0;
        }
        curPage.push(block); curWords+=bWords;
        if(curWords>=EBOOK_WPP){
          pages.push(curPage); curPage=[]; curWords=0;
        }
      }
      if(curPage.length>0) pages.push(curPage);
      const totalPages=Math.max(1,pages.length);
      const safePage=Math.min(bookPage, totalPages-1);
      const pageBlocks=pages[safePage]||[];

      const progressPct=Math.min(100, Math.round(b.current_words / Math.max(1, b.target_pages * 250) * 100));

      // Figure out which chapter the current page belongs to
      let currentReadingCh=1; let blockIdx=0;
      for(let pi=0;pi<=safePage;pi++) for(const bl of (pages[pi]||[])){
        if(bl.type==='chapter-title') currentReadingCh=b.chapters.findIndex(c=>c.title===bl.text)+1||currentReadingCh;
      }

      // ── Render inline markdown (bold, italic) ──
      const renderInline=(raw:string)=>{
        // Handle ***bold italic***, **bold**, *italic*
        const parts=raw.split(/(\*{1,3}[^*]+\*{1,3})/g);
        return parts.map((seg,i)=>{
          const m3=seg.match(/^\*{3}(.+)\*{3}$/); if(m3) return <strong key={i}><em>{m3[1]}</em></strong>;
          const m2=seg.match(/^\*{2}(.+)\*{2}$/); if(m2) return <strong key={i}>{m2[1]}</strong>;
          const m1=seg.match(/^\*(.+)\*$/); if(m1) return <em key={i}>{m1[1]}</em>;
          return <span key={i}>{seg}</span>;
        });
      };

      // ── Touch swipe for mobile page turning ──
      const goPage=(dir:1|-1)=>{
        const next=safePage+dir;
        if(next<0||next>=totalPages) return;
        setPageAnim(dir===1?'flip-left':'flip-right');
        setTimeout(()=>{setBookPage(next);setPageAnim('none');},250);
      };
      const onTouchStart=(e:React.TouchEvent)=>{ touchStartX.current=e.touches[0].clientX; touchStartY.current=e.touches[0].clientY; };
      const onTouchEnd=(e:React.TouchEvent)=>{
        const dx=e.changedTouches[0].clientX-touchStartX.current;
        const dy=e.changedTouches[0].clientY-touchStartY.current;
        if(Math.abs(dx)<50||Math.abs(dy)>Math.abs(dx)) return; // too short or vertical
        if(dx<0) goPage(1); else goPage(-1);
      };

      return (
        <div className="max-w-3xl mx-auto px-0 sm:px-4 py-0 sm:py-6">
          {/* ── Minimal top bar (overlays on mobile, fixed on desktop) ── */}
          <div className="flex items-center justify-between px-3 sm:px-0 py-2 sm:py-0 sm:mb-4">
            <button onClick={()=>setSelectedBook(null)} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
              <ChevronLeft className="h-4 w-4"/> <span className="hidden sm:inline">Bibliothek</span><span className="sm:hidden">←</span>
            </button>
            <div className="flex items-center gap-2 text-[10px] sm:text-xs text-muted-foreground">
              <span>{safePage+1} / {totalPages}</span>
              <span className="text-zinc-700">·</span>
              <span>Kap. {currentReadingCh}/{b.total_chapters}</span>
            </div>
            <div className="flex items-center gap-1">
              <a href={api(`/api/books/${b.slug}/download`,apiBaseRef)} download
                className="p-1.5 rounded-lg text-muted-foreground hover:text-emerald-400 transition-colors" title="Download">
                <Download className="h-3.5 w-3.5"/>
              </a>
              <button onClick={()=>setShowChapterIndex(!showChapterIndex)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-amber-400 transition-colors" title="Kapitelübersicht">
                <BookOpen className="h-3.5 w-3.5"/>
              </button>
            </div>
          </div>

          {/* Chapter index drawer */}
          {showChapterIndex && (
            <div className="mx-3 sm:mx-0 mb-3 bg-zinc-900/80 backdrop-blur border border-amber-500/10 rounded-xl p-3 sm:p-4 max-h-60 overflow-y-auto">
              <h3 className="text-xs font-semibold mb-2 text-amber-400">Kapitelübersicht</h3>
              <div className="space-y-0.5">
                {b.chapters.map((ch,i)=>{
                  // find the page index where this chapter starts
                  let chPageIdx=0;
                  outer: for(let pi=0;pi<pages.length;pi++) for(const bl of pages[pi]){
                    if(bl.type==='chapter-title'&&bl.text===ch.title){ chPageIdx=pi; break outer; }
                  }
                  const isCurrentCh=i+1===b.current_chapter && b.status==='writing';
                  const isReading=i+1===currentReadingCh;
                  return (
                    <button key={i} onClick={()=>{setBookPage(chPageIdx);setShowChapterIndex(false);}}
                      className={`w-full text-left px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg text-[11px] sm:text-xs transition-colors hover:bg-amber-500/10 flex items-center gap-1.5 sm:gap-2 ${isReading?'bg-amber-500/15 border border-amber-500/20':isCurrentCh?'bg-amber-500/5':''}`}>
                      <span className="text-amber-400/60 w-5 sm:w-6 text-right shrink-0">{i+1}.</span>
                      <span className="flex-1 truncate">{ch.title}</span>
                      <span className="text-zinc-500 shrink-0 hidden sm:inline">{ch.words>0?`${ch.words}W`:''}</span>
                      {isReading && <span className="text-amber-300 text-[9px] shrink-0">📖</span>}
                      {isCurrentCh && !isReading && <span className="text-amber-400 text-[9px] shrink-0">✍️</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── eBook reading pane ── */}
          <div className="relative overflow-hidden"
            onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
            <div className={`
              mx-auto max-w-[640px] min-h-[75vh] sm:min-h-[70vh]
              rounded-none sm:rounded-2xl
              shadow-none sm:shadow-2xl sm:shadow-amber-950/20
              transition-transform duration-250 ease-in-out
              ${pageAnim==='flip-left'?'-translate-x-4 opacity-80':pageAnim==='flip-right'?'translate-x-4 opacity-80':''}
            `}
              style={{background:'linear-gradient(to bottom, #2a2318, #1e1a14 40%, #1a1610)'}}>
              {/* Paper texture overlay — subtle warm grain */}
              <div className="absolute inset-0 opacity-[0.03] pointer-events-none"
                style={{backgroundImage:'url("data:image/svg+xml,%3Csvg width=\'4\' height=\'4\' viewBox=\'0 0 4 4\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cpath d=\'M1 3h1v1H1V3zm2-2h1v1H3V1z\' fill=\'%23d4a574\' fill-opacity=\'1\'/%3E%3C/svg%3E")', backgroundRepeat:'repeat'}}/>

              {/* Content area */}
              <div className="relative px-6 sm:px-10 md:px-14 py-8 sm:py-12">
                {pageBlocks.length===0 ? (
                  <p className="text-center italic" style={{color:'#6b5c4a',fontFamily:'Georgia, "Times New Roman", serif'}}>Dieses Kapitel hat noch keinen Text…</p>
                ) : (
                  <div className="space-y-0">
                    {pageBlocks.map((block,i)=>{
                      if(block.type==='chapter-title'){
                        return (
                          <div key={i} className="pt-8 sm:pt-12 pb-6 sm:pb-8 text-center">
                            <div className="text-[10px] sm:text-xs tracking-[0.3em] uppercase mb-3"
                              style={{color:'#7a6b58', fontFamily:'Georgia, "Times New Roman", serif'}}>
                              Kapitel {b.chapters.findIndex(c=>c.title===block.text)+1||'?'}
                            </div>
                            <h2 className="text-xl sm:text-2xl md:text-3xl font-normal leading-snug"
                              style={{color:'#d4b896', fontFamily:'Georgia, "Times New Roman", serif', letterSpacing:'0.02em'}}>
                              {block.text}
                            </h2>
                            <div className="mt-4 sm:mt-6 flex items-center justify-center gap-2">
                              <div className="w-8 h-px" style={{background:'#5a4d3e'}}/>
                              <div className="w-1.5 h-1.5 rounded-full" style={{background:'#7a6b58'}}/>
                              <div className="w-8 h-px" style={{background:'#5a4d3e'}}/>
                            </div>
                          </div>
                        );
                      }
                      if(block.type==='separator'){
                        return (
                          <div key={i} className="flex items-center justify-center gap-3 py-4 sm:py-6">
                            <div className="w-12 h-px" style={{background:'#4a3f32'}}/>
                            <span style={{color:'#6b5c4a'}}>✦</span>
                            <div className="w-12 h-px" style={{background:'#4a3f32'}}/>
                          </div>
                        );
                      }
                      // Regular paragraph
                      const isDialog=block.text.startsWith('„')||block.text.startsWith('"')||block.text.startsWith('«')||block.text.startsWith('"');
                      const isFirstAfterTitle=i>0&&pageBlocks[i-1]?.type==='chapter-title';
                      return (
                        <p key={i} className={`leading-[1.85] sm:leading-[1.9] ${isFirstAfterTitle?'':'mt-0'}`}
                          style={{
                            color: isDialog ? '#c8b89a' : '#b8a890',
                            fontFamily: 'Georgia, "Times New Roman", serif',
                            fontSize: 'clamp(14px, 3.8vw, 16.5px)',
                            textIndent: (isFirstAfterTitle||isDialog||block.text.startsWith('*')) ? '0' : '1.5em',
                            marginTop: isFirstAfterTitle ? '0.5em' : '0.6em',
                            textAlign: 'justify',
                            hyphens: 'auto',
                            WebkitHyphens: 'auto',
                          } as React.CSSProperties}>
                          {renderInline(block.text)}
                        </p>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Bottom page info + nav */}
              <div className="relative px-6 sm:px-10 md:px-14 pb-6 sm:pb-8">
                {/* Reading progress thin bar */}
                <div className="w-full h-px mb-4" style={{background:'#3a3228'}}>
                  <div className="h-full rounded-full transition-all duration-500" style={{width:`${Math.round((safePage+1)/totalPages*100)}%`, background:'#7a6b58'}}/>
                </div>
                <div className="flex items-center justify-between">
                  <button disabled={safePage<=0} onClick={()=>goPage(-1)}
                    className="p-2 -ml-2 rounded-lg transition-colors disabled:opacity-20"
                    style={{color:'#8a7b68'}} title="Vorherige Seite">
                    <ChevronLeft className="h-5 w-5"/>
                  </button>
                  <div className="text-center">
                    <span className="text-[10px] sm:text-[11px] tracking-wider"
                      style={{color:'#6b5c4a', fontFamily:'Georgia, "Times New Roman", serif'}}>
                      {safePage+1} von {totalPages}
                    </span>
                  </div>
                  <button disabled={safePage>=totalPages-1} onClick={()=>goPage(1)}
                    className="p-2 -mr-2 rounded-lg transition-colors disabled:opacity-20"
                    style={{color:'#8a7b68'}} title="Nächste Seite">
                    <ChevronRight className="h-5 w-5"/>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Keyboard navigation hint — desktop only */}
          <p className="hidden sm:block text-center text-[10px] mt-3" style={{color:'#4a3f32'}}>
            ← → Pfeiltasten zum Blättern · Auf dem Smartphone wischen
          </p>
        </div>
      );
    }

    /* ── Library list view ── */
    const unusedSuggestions=bookSuggestions.filter(s=>!s.used);
    const usedSuggestions=bookSuggestions.filter(s=>s.used);

    return (
      <div className="max-w-4xl mx-auto px-3 sm:px-4 py-4 sm:py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 sm:mb-6">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <BookOpen className="h-5 w-5 sm:h-6 sm:w-6 text-amber-400 shrink-0"/>
            <h2 className="text-lg sm:text-2xl font-bold truncate">A!leys Bibliothek</h2>
            <span className="text-[10px] sm:text-xs text-muted-foreground bg-zinc-800/60 px-1.5 sm:px-2 py-0.5 rounded-full shrink-0">{booksList.length}</span>
          </div>
          <Button variant="outline" size="sm" onClick={()=>{loadBooks();loadBookSuggestions();}} disabled={booksLoading} className="text-xs shrink-0">{booksLoading?'…':'↻'}</Button>
        </div>
        <p className="text-xs sm:text-sm text-muted-foreground mb-4 sm:mb-6">
          Aileys selbst geschriebene Bücher — sie plant und schreibt sie autonom Stück für Stück.
        </p>

        {/* ── Suggestions Section ── */}
        <div className="mb-6 sm:mb-8">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm sm:text-base font-semibold flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-amber-400"/>
              <span>Buch-Vorschläge</span>
              {unusedSuggestions.length>0 && <span className="text-[10px] bg-amber-500/10 text-amber-300 px-1.5 py-0.5 rounded-full">{unusedSuggestions.length} offen</span>}
            </h3>
            <Button variant="outline" size="sm" onClick={()=>setShowSuggestionForm(!showSuggestionForm)} className="text-xs gap-1">
              <Plus className="h-3.5 w-3.5"/> <span className="hidden sm:inline">Vorschlag</span>
            </Button>
          </div>
          <p className="text-[11px] sm:text-xs text-zinc-500 mb-3">
            Schlage Genre, Plot-Idee oder Seitenzahl vor — Ailey kann sie beim nächsten Buch als Inspiration nutzen (muss aber nicht).
          </p>

          {/* Suggestion form */}
          {showSuggestionForm && (
            <Card className="p-3 sm:p-4 mb-3 border-amber-500/20">
              <div className="space-y-2.5">
                <div className="flex flex-col sm:flex-row gap-2">
                  <div className="flex-1">
                    <label className="text-[10px] sm:text-xs text-zinc-400 mb-1 block">Genre (optional)</label>
                    <input value={sugGenre} onChange={e=>setSugGenre(e.target.value)} placeholder="z.B. Dark Fantasy, Sci-Fi…"
                      className="w-full bg-zinc-900/50 border border-zinc-700 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm placeholder:text-zinc-600 focus:outline-none focus:border-amber-500/40"/>
                  </div>
                  <div className="w-full sm:w-28">
                    <label className="text-[10px] sm:text-xs text-zinc-400 mb-1 block">Seiten (optional)</label>
                    <input type="number" value={sugPages} onChange={e=>setSugPages(e.target.value)} placeholder="z.B. 150"
                      className="w-full bg-zinc-900/50 border border-zinc-700 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm placeholder:text-zinc-600 focus:outline-none focus:border-amber-500/40"/>
                  </div>
                </div>
                <div>
                  <label className="text-[10px] sm:text-xs text-zinc-400 mb-1 block">Plot-Idee / Thema *</label>
                  <textarea value={sugPlot} onChange={e=>setSugPlot(e.target.value)} placeholder="Kurze Beschreibung der Idee — 1-3 Sätze reichen…"
                    rows={2}
                    className="w-full bg-zinc-900/50 border border-zinc-700 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm placeholder:text-zinc-600 focus:outline-none focus:border-amber-500/40 resize-none"/>
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" size="sm" onClick={()=>setShowSuggestionForm(false)} className="text-xs">Abbrechen</Button>
                  <Button size="sm" onClick={submitSuggestion} disabled={!sugPlot.trim()||sugSending} className="text-xs gap-1 bg-amber-600 hover:bg-amber-500">
                    {sugSending?<Loader2 className="h-3 w-3 animate-spin"/>:<Send className="h-3 w-3"/>} Vorschlagen
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Suggestion chips */}
          {bookSuggestions.length > 0 && (
            <div className="space-y-1.5">
              {unusedSuggestions.map(s=>(
                <div key={s.id} className="flex items-start gap-2 bg-amber-500/5 border border-amber-500/10 rounded-lg px-2.5 sm:px-3 py-2 group">
                  <Sparkles className="h-3.5 w-3.5 text-amber-400 mt-0.5 shrink-0"/>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs sm:text-sm text-zinc-200">{s.plot}</p>
                    <div className="flex flex-wrap gap-1.5 mt-1 text-[10px] text-zinc-500">
                      {s.genre && <span className="bg-zinc-800/60 px-1.5 py-0.5 rounded">{s.genre}</span>}
                      {s.target_pages && <span className="bg-zinc-800/60 px-1.5 py-0.5 rounded">~{s.target_pages}S.</span>}
                      <span>{s.created_at?.split(' ')[0]}</span>
                    </div>
                  </div>
                  <button onClick={()=>deleteSuggestion(s.id)} className="text-zinc-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 sm:opacity-100 shrink-0 p-0.5" title="Löschen">
                    <Trash2 className="h-3.5 w-3.5"/>
                  </button>
                </div>
              ))}
              {usedSuggestions.length>0 && (
                <details className="text-xs text-zinc-500">
                  <summary className="cursor-pointer hover:text-zinc-400 py-1">
                    {usedSuggestions.length} bereits verwendete Vorschläge
                  </summary>
                  <div className="space-y-1 mt-1 pl-1">
                    {usedSuggestions.map(s=>(
                      <div key={s.id} className="flex items-start gap-2 opacity-50 rounded-lg px-2 py-1.5">
                        <Check className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0"/>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-zinc-400 truncate">{s.plot}</p>
                          <div className="flex gap-1.5 mt-0.5 text-[10px]">
                            {s.genre && <span>{s.genre}</span>}
                            {s.target_pages && <span>~{s.target_pages}S.</span>}
                          </div>
                        </div>
                        <button onClick={()=>deleteSuggestion(s.id)} className="text-zinc-700 hover:text-red-400 transition-colors shrink-0 p-0.5">
                          <Trash2 className="h-3 w-3"/>
                        </button>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
          {bookSuggestions.length===0 && !showSuggestionForm && (
            <p className="text-[11px] text-zinc-600 italic">Noch keine Vorschläge — Ailey entscheidet ganz frei was sie schreibt.</p>
          )}
        </div>

        {/* ── Books grid ── */}
        {booksList.length===0 && !booksLoading && (
          <Card className="p-6 sm:p-8 text-center text-muted-foreground">
            <BookOpen className="h-8 w-8 sm:h-10 sm:w-10 mx-auto mb-3 text-amber-400/40"/>
            <p className="text-xs sm:text-sm">Noch keine Bücher. Ailey plant und schreibt Bücher wenn sie idle ist.</p>
          </Card>
        )}

        <div className="space-y-3 sm:space-y-4">
          {booksList.map(b=>{
            const progressPct=b.progress_percent;
            return (
              <Card key={b.slug} onClick={()=>openBook(b.slug)}
                className="p-3 sm:p-5 cursor-pointer hover:border-amber-500/40 transition-all group relative">
                <button onClick={(e)=>{e.stopPropagation();deleteBook(b.slug);}}
                  className="absolute top-2 right-2 p-1 rounded-md text-zinc-600 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity z-10"
                  title="Buch löschen"><Trash2 className="h-3.5 w-3.5"/></button>
                <div className="flex items-start gap-3 sm:gap-4">
                  <div className="w-10 h-14 sm:w-12 sm:h-16 rounded-lg bg-gradient-to-br from-amber-500/20 to-orange-500/20 border border-amber-500/20 flex items-center justify-center text-lg sm:text-xl shrink-0 group-hover:scale-105 transition-transform">
                    {b.status==='finished'?'📕':'📖'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 sm:gap-2 mb-0.5 sm:mb-1">
                      <h3 className="text-sm sm:text-base font-semibold text-foreground truncate">{b.title}</h3>
                      <span className={`text-[9px] sm:text-[10px] px-1 sm:px-1.5 py-0.5 rounded border shrink-0 ${b.status==='finished'?'bg-emerald-500/10 text-emerald-300 border-emerald-500/20':'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
                        {b.status==='finished'?'✅ Fertig':'✍️'}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-1.5 gap-y-0.5 text-[10px] sm:text-xs text-muted-foreground mb-1 sm:mb-2">
                      <span>{b.genre}</span>
                      <span className="text-zinc-700">·</span>
                      <span>Kap. {b.current_chapter}/{b.total_chapters}</span>
                      <span className="text-zinc-700">·</span>
                      <span>{b.current_words.toLocaleString()} W</span>
                    </div>
                    <p className="text-[11px] sm:text-xs text-zinc-500 line-clamp-1 sm:line-clamp-2">{b.synopsis}</p>
                    <div className="flex items-center gap-2 mt-1.5 sm:mt-2">
                      <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all ${b.status==='finished'?'bg-emerald-500':'bg-amber-500'}`} style={{width:`${progressPct}%`}}/>
                      </div>
                      <span className="text-[9px] sm:text-[10px] text-zinc-500 w-7 sm:w-8 text-right">{progressPct}%</span>
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    );
  };

  // --- Life Simulation Section (RPG Maker MZ embedded) ---
  // Stable iframe src — computed once, never changes (prevents iframe reload on re-render)
  const lifeSimSrc = useRef<string>('');
  if (!lifeSimSrc.current) lifeSimSrc.current = `${apiBaseRef.current}/ailey-home/`;
  const LifeSimSection = useMemo(() => function LifeSimSectionStable() {
    const iframeRef = useRef<HTMLIFrameElement>(null);
    const [lifeState, setLifeState] = useState<any>(null);
    const [lifeError, setLifeError] = useState(false);
    const [fullscreen, setFullscreen] = useState(false);
    const [simPaused, setSimPaused] = useState(false);
    const [mobileDrawer, setMobileDrawer] = useState(false);
    const [isMobile, setIsMobile] = useState(false);

    // Detect mobile/tablet — fullscreen for touch devices or screens ≤ 1024px
    useEffect(() => {
      const check = () => {
        const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
        const isSmallScreen = window.innerWidth <= 1024;
        setIsMobile(isTouch || isSmallScreen);
      };
      check();
      window.addEventListener('resize', check);
      return () => window.removeEventListener('resize', check);
    }, []);

    // Poll life-sim state for the overlay info panel
    useEffect(() => {
      let cancelled = false;
      const poll = async () => {
        try {
          const r = await fetch(api('/api/life-sim/state', apiBaseRef), { signal: timeoutSignal(4000) });
          if (r.ok) { const d = await r.json(); if (!cancelled && d.success) { setLifeState(d); setLifeError(false); if (d.paused !== undefined) setSimPaused(d.paused); } }
        } catch { if (!cancelled) setLifeError(true); }
      };
      poll();
      const iv = setInterval(poll, 10000);
      return () => { cancelled = true; clearInterval(iv); };
    }, []);

    // Forward state updates to iframe
    useEffect(() => {
      if (lifeState && iframeRef.current?.contentWindow) {
        iframeRef.current.contentWindow.postMessage({ type: 'ailey-state', state: lifeState }, '*');
      }
    }, [lifeState]);

    // Notify iframe of resize/orientation changes so RMMZ adapts canvas
    useEffect(() => {
      const sendResize = () => {
        if (iframeRef.current?.contentWindow) {
          iframeRef.current.contentWindow.postMessage({
            type: 'ailey-resize',
            width: window.innerWidth,
            height: window.innerHeight,
          }, '*');
        }
      };
      window.addEventListener('resize', sendResize);
      // Also trigger on orientation change (mobile)
      window.addEventListener('orientationchange', () => setTimeout(sendResize, 200));
      // Initial send after iframe loads
      const iframe = iframeRef.current;
      if (iframe) iframe.addEventListener('load', () => setTimeout(sendResize, 500));
      return () => {
        window.removeEventListener('resize', sendResize);
      };
    }, []);

    // Send virtual button press / release to iframe for continuous D-pad movement
    const sendButtonDown = (key: string) => {
      if (iframeRef.current?.contentWindow) {
        iframeRef.current.contentWindow.postMessage({ type: 'ailey-virtual-button-down', key }, '*');
      }
    };
    const sendButtonUp = (key: string) => {
      if (iframeRef.current?.contentWindow) {
        iframeRef.current.contentWindow.postMessage({ type: 'ailey-virtual-button-up', key }, '*');
      }
    };
    // Legacy one-shot for ok/escape (no hold needed)
    const sendButton = (key: string) => {
      if (iframeRef.current?.contentWindow) {
        iframeRef.current.contentWindow.postMessage({ type: 'ailey-virtual-button', key }, '*');
      }
    };

    // Toggle RMMZ HUD visibility with smooth fade
    const sendHudToggle = (visible?: boolean) => {
      if (iframeRef.current?.contentWindow) {
        iframeRef.current.contentWindow.postMessage({ type: 'ailey-toggle-hud', visible }, '*');
      }
    };

    // Toggle drawer and sync HUD visibility (show RMMZ HUD when drawer closed, hide when open)
    const toggleDrawer = () => {
      const willOpen = !mobileDrawer;
      setMobileDrawer(willOpen);
      // When drawer opens, hide RMMZ HUDs (they overlap). When closed, show them.
      sendHudToggle(!willOpen);
    };

    const moodEmojis: Record<string, string> = {
      happy: '😊', excited: '✨', playful: '😜', sad: '😢', angry: '😤',
      neutral: '😌', thinking: '🤔', creative: '🎨', sleepy: '😴',
      flirty: '😏', curious: '🧐', coding: '💻', writing: '✍️',
    };
    const activityLabels: Record<string, string> = {
      idle: 'Entspannt', reflection: 'Nachdenken', introspection: 'Selbstreflexion',
      research: 'Recherchieren', creative_song: 'Songwriting', creative_art: 'Kunst',
      creative_image: 'Bild generieren', goal_planning: 'Pläne schmieden',
      free_thought: 'Frei denken', memory_consolidation: 'Erinnerungen sortieren',
      email_check: 'Emails checken', proactive_message: 'Nachricht schreiben',
      sleeping: 'Schlafen', sleep: 'Schlafen', writing_diary: 'Tagebuch schreiben',
      coding: 'Programmieren',
      eating: 'Essen', cooking: 'Kochen', drinking: 'Trinken',
      napping: 'Nickerchen', using_toilet: 'Auf dem Klo',
      music_making: 'Musik machen', diary_writing: 'Tagebuch schreiben',
      fishing: 'Angeln', flower_picking: 'Blumen pflücken',
      gardening: 'Gärtnern', outdoor_stroll: 'Spaziergang',
      cleaning: 'Aufräumen', bathing: 'Baden',
      email_initiative: 'Email schreiben', glossary_cleanup: 'Glossar aufräumen',
      nightly_summary: 'Nacht-Konsolidierung',
    };
    const timeLabels: Record<string, string> = {
      morning: '🌅 Morgen', midday: '☀️ Mittag', afternoon: '🌤 Nachmittag',
      evening: '🌇 Abend', night: '🌙 Nacht',
    };

    const a = lifeState?.ailey;

    // ── MOBILE LAYOUT: fullscreen game with floating controls ──
    if (isMobile) {
      return (
        <div className="fixed inset-0 z-[90] bg-black">
          {/* Game fills entire screen */}
          <iframe
            ref={iframeRef}
            src={lifeSimSrc.current}
            className="w-full h-full border-0"
            allow="autoplay"
            title="Vyrus Valley — Life Simulation"
          />

          {/* ── Top floating nav bar ── */}
          <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-3 pt-[max(8px,env(safe-area-inset-top))] pb-1.5"
               style={{background: 'linear-gradient(to bottom, rgba(0,0,0,0.6) 0%, transparent 100%)'}}>
            <div className="flex items-center gap-2">
              <button onClick={() => setActive('home')} className="p-1.5 rounded-lg bg-black/40 backdrop-blur text-white/80">
                <ChevronLeft className="w-4 h-4"/>
              </button>
              {/* Analog mini-clock */}
              {(() => {
                const h = clockDate.getHours() % 12, m = clockDate.getMinutes();
                const hA = (h + m / 60) * 30 - 90, mA = m * 6 - 90;
                const hR = hA * Math.PI / 180, mR = mA * Math.PI / 180;
                return (
                  <div className="p-1 rounded-lg bg-black/40 backdrop-blur" title={clockTime}>
                    <svg width="22" height="22" viewBox="0 0 32 32" className="text-white/70">
                      <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.3"/>
                      {[0,3,6,9].map(i => { const a = i * 30 * Math.PI / 180; return <circle key={i} cx={16 + 11 * Math.cos(a - Math.PI/2)} cy={16 + 11 * Math.sin(a - Math.PI/2)} r="1.2" fill="currentColor" opacity="0.5"/>; })}
                      <line x1="16" y1="16" x2={16 + 7 * Math.cos(hR)} y2={16 + 7 * Math.sin(hR)} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity="0.8"/>
                      <line x1="16" y1="16" x2={16 + 10 * Math.cos(mR)} y2={16 + 10 * Math.sin(mR)} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.6"/>
                      <circle cx="16" cy="16" r="1.5" fill="currentColor" opacity="0.7"/>
                    </svg>
                  </div>
                );
              })()}
            </div>
            <div className="flex items-center gap-1.5">
              {/* Pause */}
              <button
                onClick={async () => {
                  try {
                    const endpoint = simPaused ? '/api/life-sim/resume' : '/api/life-sim/pause';
                    const r = await fetch(api(endpoint, apiBaseRef), { method: 'POST' });
                    if (r.ok) { const d = await r.json(); if (d.success) setSimPaused(d.paused); }
                  } catch {}
                }}
                className={`p-1.5 rounded-lg backdrop-blur ${simPaused ? 'bg-amber-500/30 text-amber-300' : 'bg-black/40 text-white/80'}`}
              >
                {simPaused ? <Play className="w-4 h-4"/> : <Pause className="w-4 h-4"/>}
              </button>
              {/* Info drawer toggle */}
              <button
                onClick={toggleDrawer}
                className="p-1.5 rounded-lg bg-black/40 backdrop-blur text-white/80"
              >
                <Info className="w-4 h-4"/>
              </button>
            </div>
          </div>

          {/* ── Virtual A/B buttons (bottom-left) ── */}
          <div className="absolute bottom-[max(16px,env(safe-area-inset-bottom))] left-3 z-20 flex items-end gap-2">
            <button
              onTouchStart={(e) => { e.preventDefault(); sendButton('ok'); }}
              onMouseDown={() => sendButton('ok')}
              className="w-12 h-12 rounded-full lifesim-btn-a backdrop-blur text-white font-bold text-sm flex items-center justify-center active:scale-90 transition-transform select-none"
            >A</button>
            <button
              onTouchStart={(e) => { e.preventDefault(); sendButton('escape'); }}
              onMouseDown={() => sendButton('escape')}
              className="w-10 h-10 rounded-full lifesim-btn-b backdrop-blur text-white/80 font-bold text-xs flex items-center justify-center active:scale-90 transition-transform select-none"
            >B</button>
          </div>

          {/* ── D-Pad (bottom-right) ── */}
          <div className="absolute bottom-[max(16px,env(safe-area-inset-bottom))] right-3 z-20">
            <div className="relative w-[108px] h-[108px]">
              {/* Up */}
              <button
                onTouchStart={(e) => { e.preventDefault(); sendButtonDown('up'); }}
                onTouchEnd={(e) => { e.preventDefault(); sendButtonUp('up'); }}
                onTouchCancel={() => sendButtonUp('up')}
                onMouseDown={() => sendButtonDown('up')}
                onMouseUp={() => sendButtonUp('up')}
                onMouseLeave={() => sendButtonUp('up')}
                className="absolute top-0 left-1/2 -translate-x-1/2 w-9 h-9 rounded-lg bg-black/40 backdrop-blur border border-white/10 text-white/70 flex items-center justify-center active:bg-white/20 transition select-none"
              >▲</button>
              {/* Down */}
              <button
                onTouchStart={(e) => { e.preventDefault(); sendButtonDown('down'); }}
                onTouchEnd={(e) => { e.preventDefault(); sendButtonUp('down'); }}
                onTouchCancel={() => sendButtonUp('down')}
                onMouseDown={() => sendButtonDown('down')}
                onMouseUp={() => sendButtonUp('down')}
                onMouseLeave={() => sendButtonUp('down')}
                className="absolute bottom-0 left-1/2 -translate-x-1/2 w-9 h-9 rounded-lg bg-black/40 backdrop-blur border border-white/10 text-white/70 flex items-center justify-center active:bg-white/20 transition select-none"
              >▼</button>
              {/* Left */}
              <button
                onTouchStart={(e) => { e.preventDefault(); sendButtonDown('left'); }}
                onTouchEnd={(e) => { e.preventDefault(); sendButtonUp('left'); }}
                onTouchCancel={() => sendButtonUp('left')}
                onMouseDown={() => sendButtonDown('left')}
                onMouseUp={() => sendButtonUp('left')}
                onMouseLeave={() => sendButtonUp('left')}
                className="absolute left-0 top-1/2 -translate-y-1/2 w-9 h-9 rounded-lg bg-black/40 backdrop-blur border border-white/10 text-white/70 flex items-center justify-center active:bg-white/20 transition select-none"
              >◀</button>
              {/* Right */}
              <button
                onTouchStart={(e) => { e.preventDefault(); sendButtonDown('right'); }}
                onTouchEnd={(e) => { e.preventDefault(); sendButtonUp('right'); }}
                onTouchCancel={() => sendButtonUp('right')}
                onMouseDown={() => sendButtonDown('right')}
                onMouseUp={() => sendButtonUp('right')}
                onMouseLeave={() => sendButtonUp('right')}
                className="absolute right-0 top-1/2 -translate-y-1/2 w-9 h-9 rounded-lg bg-black/40 backdrop-blur border border-white/10 text-white/70 flex items-center justify-center active:bg-white/20 transition select-none"
              >▶</button>
            </div>
          </div>

          {/* ── Paused overlay ── */}
          {simPaused && (
            <div className="absolute inset-0 z-25 bg-black/50 backdrop-blur-[3px] flex items-center justify-center"
                 style={{top: '48px'}}>
              <div className="text-center">
                <div className="text-4xl mb-2">💤</div>
                <p className="text-amber-300 text-sm font-medium">Ailey schläft</p>
                <button
                  onClick={async () => {
                    try {
                      const r = await fetch(api('/api/life-sim/resume', apiBaseRef), { method: 'POST' });
                      if (r.ok) { const d = await r.json(); if (d.success) setSimPaused(false); }
                    } catch {}
                  }}
                  className="mt-4 px-5 py-2 rounded-xl lifesim-btn-a backdrop-blur text-white text-sm transition"
                >▶ Aufwecken</button>
              </div>
            </div>
          )}

          {/* ── Info drawer (smooth slide from right) ── */}
          <div className={`absolute inset-y-0 right-0 z-40 w-[280px] bg-black/80 backdrop-blur-xl border-l border-white/10 overflow-y-auto transition-transform duration-300 ease-in-out ${mobileDrawer ? 'translate-x-0' : 'translate-x-full'}`}
               style={{paddingTop: 'max(12px, env(safe-area-inset-top))', paddingBottom: 'max(12px, env(safe-area-inset-bottom))'}}>
              <div className="px-4 py-3">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-semibold text-white/90">Status</span>
                  <button onClick={toggleDrawer} className="p-1 rounded-lg text-white/60 hover:text-white">
                    <X className="w-4 h-4"/>
                  </button>
                </div>

                {/* Mood + Activity */}
                {a && (
                  <div className="space-y-2 mb-4">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-xl">{moodEmojis[a.mood] || '😌'}</span>
                      <div>
                        <div className="text-white/90 font-medium">{moodLabelsDE[a.mood] || a.mood}</div>
                        <div className="text-white/50">{activityLabels[a.activity] || a.activity}</div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5 text-[10px]">
                      <span className="px-2 py-0.5 rounded-full bg-white/10 text-white/70">
                        {a.map === 'outdoor' ? '🌳 Draußen' : '🏠 Drinnen'}
                      </span>
                      {lifeState?.time_of_day && (
                        <span className="px-2 py-0.5 rounded-full bg-white/10 text-white/70">
                          {timeLabels[lifeState.time_of_day] || lifeState.time_of_day}
                        </span>
                      )}
                      {lifeState?.weather && (
                        <span className="px-2 py-0.5 rounded-full bg-white/10 text-white/70">
                          {Math.round(lifeState.weather.temperature)}°C
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Needs */}
                {lifeState?.needs && (
                  <div className="mb-4">
                    <div className="text-[10px] font-medium text-white/50 uppercase tracking-wider mb-2">Bedürfnisse</div>
                    {[
                      { key: 'hunger',      icon: '🍽️', label: 'Hunger',    color: 'bg-orange-400' },
                      { key: 'thirst',      icon: '💧',  label: 'Durst',     color: 'bg-blue-400' },
                      { key: 'tiredness',   icon: '😴',  label: 'Müdigkeit', color: 'bg-violet-400' },
                      { key: 'toilet',      icon: '🚽',  label: 'Toilette',  color: 'bg-green-400' },
                      { key: 'hygiene',     icon: '🛁',  label: 'Hygiene',   color: 'bg-cyan-400' },
                      { key: 'environment', icon: '🧹',  label: 'Umgebung',  color: 'bg-amber-400' },
                    ].map(n => {
                      const val = Math.round(lifeState.needs[n.key] || 0);
                      const isCritical = val >= 75;
                      return (
                        <div key={n.key} className="mb-2">
                          <div className="flex items-center justify-between text-[11px] mb-0.5">
                            <span className="text-white/70">{n.icon} {n.label}</span>
                            <span className={isCritical ? 'text-red-400 font-bold' : 'text-white/50'}>{val}%</span>
                          </div>
                          <div className="h-1 rounded-full bg-white/10 overflow-hidden">
                            <div className={`h-full rounded-full ${isCritical ? 'bg-red-500' : val >= 50 ? 'bg-amber-400' : n.color}`}
                                 style={{width: `${Math.min(100, val)}%`}}/>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Sympathy */}
                {lifeState?.sympathy && (
                  <div className="mb-4">
                    <div className="text-[10px] font-medium text-white/50 uppercase tracking-wider mb-2">Sympathie</div>
                    {Object.entries(lifeState.sympathy).map(([person, score]: [string, any]) => (
                      <div key={person}>
                        <div className="flex items-center justify-between text-[11px] mb-0.5">
                          <span className="text-white/70">❤️ {person}</span>
                          <span className="text-pink-400">{Math.round(score)}</span>
                        </div>
                        <div className="h-1 rounded-full bg-white/10 overflow-hidden">
                          <div className="h-full rounded-full bg-gradient-to-r from-pink-500 to-red-400"
                               style={{width: `${Math.min(100, score)}%`}}/>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Thought */}
                {a?.thought_preview && (
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10 text-[11px]">
                    <div className="text-white/40 mb-1">💭 Ailey denkt:</div>
                    <div className="text-white/70 italic">&quot;{a.thought_preview}&quot;</div>
                  </div>
                )}
              </div>
            </div>
        </div>
      );
    }

    // ── DESKTOP LAYOUT (unchanged) ──
    return (
      <div className={`relative ${fullscreen ? 'fixed inset-0 z-[100] bg-black' : ''}`}>
        {/* Header bar */}
        {!fullscreen && (
          <div className="max-w-6xl mx-auto px-2 sm:px-4 pt-4 sm:pt-6 pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 sm:gap-3">
                <Gamepad2 className="w-5 h-5 sm:w-6 sm:h-6 text-primary"/>
                <div>
                  <h2 className="text-base sm:text-lg font-bold">Vyrus Valley</h2>
                  <p className="text-[10px] sm:text-xs text-muted-foreground">Aileys Pixel-Welt — KI-gesteuert</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* Status pills */}
                {a && (
                  <div className="hidden lg:flex items-center gap-2 text-xs">
                    <span className="px-2 py-0.5 rounded-full bg-muted border border-border">
                      {moodEmojis[a.mood] || '😌'} {moodLabelsDE[a.mood] || a.mood}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-muted border border-border">
                      {activityLabels[a.activity] || a.activity}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-muted border border-border">
                      {a.map === 'outdoor' ? '🌳 Draußen' : '🏠 Drinnen'}
                    </span>
                    {lifeState?.time_of_day && (
                      <span className="px-2 py-0.5 rounded-full bg-muted border border-border">
                        {timeLabels[lifeState.time_of_day] || lifeState.time_of_day}
                      </span>
                    )}
                    {lifeState?.weather && (
                      <span className="px-2 py-0.5 rounded-full bg-muted border border-border">
                        {lifeState.weather.label || `${Math.round(lifeState.weather.temperature)}°C`}
                      </span>
                    )}
                  </div>
                )}
                {/* Analog clock */}
                {(() => {
                  const h = clockDate.getHours() % 12;
                  const m = clockDate.getMinutes();
                  const hAngle = (h + m / 60) * 30 - 90;
                  const mAngle = m * 6 - 90;
                  const hRad = hAngle * Math.PI / 180;
                  const mRad = mAngle * Math.PI / 180;
                  return (
                    <div className="hidden lg:flex items-center" title={clockTime}>
                      <svg width="32" height="32" viewBox="0 0 32 32" className="opacity-60">
                        <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.3"/>
                        {[0,1,2,3,4,5,6,7,8,9,10,11].map(i => {
                          const a = i * 30 * Math.PI / 180;
                          return <circle key={i} cx={16 + 11.5 * Math.cos(a - Math.PI/2)} cy={16 + 11.5 * Math.sin(a - Math.PI/2)} r={i % 3 === 0 ? 1.2 : 0.6} fill="currentColor" opacity="0.4"/>;
                        })}
                        <line x1="16" y1="16" x2={16 + 7 * Math.cos(hRad)} y2={16 + 7 * Math.sin(hRad)} stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.7"/>
                        <line x1="16" y1="16" x2={16 + 10 * Math.cos(mRad)} y2={16 + 10 * Math.sin(mRad)} stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.5"/>
                        <circle cx="16" cy="16" r="1.5" fill="currentColor" opacity="0.6"/>
                      </svg>
                    </div>
                  );
                })()}
                {/* Pause / Resume simulation */}
                <button
                  onClick={async () => {
                    try {
                      const endpoint = simPaused ? '/api/life-sim/resume' : '/api/life-sim/pause';
                      const r = await fetch(api(endpoint, apiBaseRef), { method: 'POST' });
                      if (r.ok) { const d = await r.json(); if (d.success) setSimPaused(d.paused); }
                    } catch {}
                  }}
                  className={`p-2 rounded-lg transition ${simPaused ? 'bg-amber-500/20 text-amber-400 hover:bg-amber-500/30' : 'hover:bg-primary/10'}`}
                  title={simPaused ? 'Simulation fortsetzen' : 'Simulation pausieren'}
                >
                  {simPaused ? <Play className="w-4 h-4"/> : <Pause className="w-4 h-4"/>}
                </button>
                <button
                  onClick={() => setFullscreen(!fullscreen)}
                  className="p-2 rounded-lg hover:bg-primary/10 transition"
                  title={fullscreen ? 'Vollbild beenden' : 'Vollbild'}
                >
                  <Eye className="w-4 h-4"/>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Game iframe container */}
        <div className={`relative ${fullscreen ? 'w-full h-full' : 'max-w-6xl mx-auto px-2 sm:px-4 pb-6'}`}>
          <div className={`relative rounded-xl overflow-hidden border border-border shadow-2xl ${fullscreen ? 'w-full h-full rounded-none border-0' : 'aspect-video'}`}
               style={!fullscreen ? {maxHeight: 'calc(100vh - 200px)'} : undefined}>
            <iframe
              ref={iframeRef}
              src={lifeSimSrc.current}
              className="w-full h-full border-0"
              style={{minHeight: fullscreen ? '100vh' : '300px'}}
              allow="autoplay"
              title="Vyrus Valley — Life Simulation"
            />

            {/* Paused overlay */}
            {simPaused && !fullscreen && (
              <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] flex items-center justify-center z-10">
                <div className="text-center">
                  <Pause className="w-12 h-12 text-amber-400 mx-auto mb-2 opacity-60"/>
                  <p className="text-amber-300 text-sm font-medium">Simulation pausiert</p>
                  <button
                    onClick={async () => {
                      try {
                        const r = await fetch(api('/api/life-sim/resume', apiBaseRef), { method: 'POST' });
                        if (r.ok) { const d = await r.json(); if (d.success) setSimPaused(false); }
                      } catch {}
                    }}
                    className="mt-3 px-4 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs hover:bg-amber-500/30 transition"
                  >
                    <Play className="w-3 h-3 inline mr-1"/>Fortsetzen
                  </button>
                </div>
              </div>
            )}

            {/* Fullscreen exit button */}
            {fullscreen && (
              <button
                onClick={() => setFullscreen(false)}
                className="absolute top-4 right-4 z-10 p-2 rounded-lg bg-black/60 backdrop-blur text-white hover:bg-black/80 transition"
                title="Vollbild beenden"
              >
                <X className="w-5 h-5"/>
              </button>
            )}
          </div>

          {/* Thought preview bar (below game, desktop only) */}
          {!fullscreen && a?.thought_preview && (
            <div className="mt-3 px-4 py-2 rounded-lg bg-muted/50 border border-border/50 text-sm flex items-start gap-2">
              <span className="text-lg shrink-0">{a.thought_icon || '💭'}</span>
              <div>
                <span className="text-xs text-muted-foreground mr-2">Ailey denkt:</span>
                <span className="text-foreground/80 italic">&quot;{a.thought_preview}&quot;</span>
              </div>
            </div>
          )}

          {/* Needs + Sympathy panel (below game) */}
          {!fullscreen && lifeState?.needs && (
            <div className="mt-3 space-y-3">

              {/* ── Tageslaune + Sozial ─────────────────────────────────────── */}
              {(lifeState.daily_mood !== undefined || lifeState.social !== undefined) && (
                <div className="px-4 py-3 rounded-lg bg-muted/30 border border-border/50">
                  <div className="text-xs font-medium text-muted-foreground mb-2">Stimmung</div>
                  {/* Tageslaune */}
                  {lifeState.daily_mood !== undefined && (() => {
                    const mood = Math.round(lifeState.daily_mood);
                    const moodColor = mood >= 70 ? 'bg-emerald-400' : mood >= 40 ? 'bg-amber-400' : 'bg-red-500';
                    const moodLabel = lifeState.daily_mood_label || (mood >= 70 ? 'Guter Laune' : mood >= 40 ? 'Mäßige Laune' : 'Schlechte Laune');
                    const trend = (lifeState as any).daily_mood_trend as string | undefined;
                    const trendColor = trend === '++' || trend === '+' ? 'text-emerald-400' : trend === '--' || trend === '-' ? 'text-red-400' : 'text-zinc-500';
                    const trendTitle = trend === '++' ? 'Stark steigend' : trend === '+' ? 'Leicht steigend' : trend === '--' ? 'Stark fallend' : trend === '-' ? 'Leicht fallend' : 'Stabil';
                    const trendDisplay = trend === '~' ? '→' : trend;  // ~ als → anzeigen (stabil)
                    return (
                      <div className="mb-2">
                        <div className="flex items-center justify-between text-xs mb-0.5">
                          <span>☀️ Tageslaune</span>
                          <span className="flex items-center gap-1">
                            {trendDisplay && (
                              <span className={`font-bold text-[11px] ${trendColor}`} title={trendTitle}>{trendDisplay}</span>
                            )}
                            <span className={mood < 40 ? 'text-red-400 font-bold' : mood < 70 ? 'text-amber-400' : 'text-emerald-400'}>{mood}% · {moodLabel}</span>
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-muted overflow-hidden">
                          <div className={`h-full rounded-full transition-all duration-1000 ${moodColor}`} style={{width: `${mood}%`}}/>
                        </div>
                        {mood < 50 && <div className="text-[10px] text-amber-400/80 mt-0.5">Beziehungspunkte sinken leicht wenn Laune &lt; 50</div>}
                      </div>
                    );
                  })()}
                  {/* Sozial */}
                  {lifeState.social !== undefined && (() => {
                    const soc = Math.round(lifeState.social);
                    const socColor = soc >= 60 ? 'bg-blue-400' : soc >= 30 ? 'bg-amber-400' : 'bg-red-500';
                    return (
                      <div>
                        <div className="flex items-center justify-between text-xs mb-0.5">
                          <span>💬 Sozial</span>
                          <span className={soc < 30 ? 'text-red-400 font-bold' : 'text-muted-foreground'}>{soc}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div className={`h-full rounded-full transition-all duration-1000 ${socColor}`} style={{width: `${soc}%`}}/>
                        </div>
                        {soc < 25 && <div className="text-[10px] text-blue-400/80 mt-0.5">Einsam — chatte mit ihr!</div>}
                      </div>
                    );
                  })()}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Needs bars */}
                <div className="px-4 py-3 rounded-lg bg-muted/30 border border-border/50">
                  <div className="text-xs font-medium text-muted-foreground mb-2">Bedürfnisse</div>
                  {[
                    { key: 'hunger',      icon: '🍽️', label: 'Hunger',    color: 'bg-orange-400', critical: 'bg-red-500' },
                    { key: 'thirst',      icon: '💧',  label: 'Durst',     color: 'bg-blue-400',   critical: 'bg-red-500' },
                    { key: 'tiredness',   icon: '😴',  label: 'Müdigkeit', color: 'bg-violet-400', critical: 'bg-red-500' },
                    { key: 'toilet',      icon: '🚽',  label: 'Toilette',  color: 'bg-green-400',  critical: 'bg-red-500' },
                    { key: 'hygiene',     icon: '🛁',  label: 'Hygiene',   color: 'bg-cyan-400',   critical: 'bg-red-500' },
                    { key: 'environment', icon: '🧹',  label: 'Umgebung',  color: 'bg-amber-400',  critical: 'bg-red-500' },
                  ].map(n => {
                    const val = Math.round(lifeState.needs[n.key] || 0);
                    const isCritical = val >= 75;
                    const isAccident = n.key === 'toilet' && val >= 100;
                    return (
                      <div key={n.key} className="mb-1.5 last:mb-0">
                        <div className="flex items-center justify-between text-xs mb-0.5">
                          <span>{n.icon} {n.label}{isAccident ? ' 💦' : ''}</span>
                          <span className={isCritical ? 'text-red-400 font-bold animate-pulse' : 'text-muted-foreground'}>{Math.min(val, 100)}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div className={`h-full rounded-full transition-all duration-1000 ${isCritical ? n.critical : val >= 50 ? 'bg-amber-400' : n.color}`}
                               style={{width: `${Math.min(100, val)}%`}}/>
                        </div>
                      </div>
                    );
                  })}
                  {lifeState.needs_resolving && (
                    <div className={`mt-2 text-xs flex items-center gap-1 ${lifeState.needs_phase === 'performing' ? 'text-emerald-400' : 'text-amber-300'}`}>
                      <span className={lifeState.needs_phase === 'walking' ? 'animate-bounce' : 'animate-spin'}>
                        {lifeState.needs_phase === 'walking' ? '🚶' : '⏳'}
                      </span>
                      {lifeState.needs_phase_label || `Kümmert sich um: ${lifeState.needs_resolving}`}
                    </div>
                  )}
                </div>
                {/* Sympathy */}
                <div className="px-4 py-3 rounded-lg bg-muted/30 border border-border/50">
                  <div className="text-xs font-medium text-muted-foreground mb-2">Sympathie</div>
                  {lifeState.sympathy && Object.entries(lifeState.sympathy).map(([person, score]: [string, any]) => (
                    <div key={person} className="mb-2 last:mb-0">
                      <div className="flex items-center justify-between text-xs mb-0.5">
                        <span>❤️ {person}</span>
                        <span className="text-pink-400">{Math.round(score)}/100</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-pink-500 to-red-400 transition-all duration-1000"
                             style={{width: `${Math.min(100, score)}%`}}/>
                      </div>
                      {lifeState.sympathy_label && person === 'Simon' && (
                        <div className="text-[10px] text-pink-300/70 mt-0.5">{lifeState.sympathy_label}</div>
                      )}
                    </div>
                  ))}
                  <div className="mt-2 text-[10px] text-muted-foreground/60">
                    Steigt durch Gespräche, Besuche in der Welt & Fürsorge
                  </div>
                </div>
              </div>

              {/* ── Talk button ─────────────────────────────────────────────── */}
              {/* Chat is now in the game (💬 button near Ailey). Removed inline LifeSim chat. */}
            </div>
          )}

          {/* Controls hint (desktop only — mobile has floating controls) */}
          {!fullscreen && (
            <div className="mt-3 text-center text-[11px] text-muted-foreground/60 hidden lg:block">
              Steuerung: Pfeiltasten / WASD zum Bewegen · Enter/Space zum Chatten (überall) · ESC schließt den Chat
            </div>
          )}
        </div>
      </div>
    );
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // --- Diary Section ---
  const [diaryPass,setDiaryPass]=useState('');
  const [diaryTitle,setDiaryTitle]=useState('');
  const [diaryContent,setDiaryContent]=useState('');
  const [diaryEntries,setDiaryEntries]=useState<any[]>([]);
  const [diaryLoading,setDiaryLoading]=useState(false);
  const [diaryMsg,setDiaryMsg]=useState<string|null>(null);
  const [diaryTab,setDiaryTab]=useState<'mine'|'ailey'>('mine');
  const [aileyDiaries,setAileyDiaries]=useState<any[]>([]);
  const [aileyDiaryOpen,setAileyDiaryOpen]=useState<any>(null);
  const [aileyDiaryLoading,setAileyDiaryLoading]=useState(false);

  async function loadDiaryList(){
    setDiaryLoading(true); setDiaryMsg(null);
    try{
  const r=await fetch(api('/api/diary/list?user=Simon', apiBaseRef));
      const j=await r.json(); if(j.success){ setDiaryEntries(j.entries||[]); }
    }catch(e:any){ setDiaryMsg('Fehler: '+(e?.message||'unbekannt')); }
    finally{ setDiaryLoading(false); }
  }

  async function saveDiary(){
    setDiaryLoading(true); setDiaryMsg(null);
    try{
  const r=await fetch(api('/api/diary/save', apiBaseRef),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:'Simon',password:diaryPass,title:diaryTitle,content:diaryContent,private:true})});
      const j=await r.json(); if(r.ok && j.success){ setDiaryMsg('✓ Eintrag gespeichert'); setDiaryTitle(''); setDiaryContent(''); loadDiaryList(); } else { setDiaryMsg(j.message||'Fehler'); }
    }catch(e:any){ setDiaryMsg('Fehler: '+(e?.message||'unbekannt')); }
    finally{ setDiaryLoading(false); setTimeout(()=>setDiaryMsg(null),4000); }
  }

  async function loadAileyDiaries(){
    setAileyDiaryLoading(true);
    try{
      const r=await fetch(api('/api/diary/ailey-list?user=Simon', apiBaseRef));
      const j=await r.json();
      if(j.success) setAileyDiaries(j.entries||[]);
    }catch(e){console.error('ailey diary load',e);}
    finally{setAileyDiaryLoading(false);}
  }

  async function openAileyDiary(filename:string){
    try{
      const r=await fetch(api(`/api/diary/ailey-read?user=Simon&file=${encodeURIComponent(filename)}`, apiBaseRef));
      const j=await r.json();
      if(j.success) setAileyDiaryOpen(j.entry);
    }catch(e){console.error('ailey diary read',e);}
  }

  useEffect(()=>{
    if(active==='diary'){
      if(diaryTab==='mine') loadDiaryList();
      else loadAileyDiaries();
    }
  },[active, diaryTab]);

  const DiarySection=()=> (
    <div className="max-w-4xl mx-auto px-4 py-10 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Tagebuch</h2>
        <Button size="sm" variant="outline" onClick={()=>diaryTab==='mine'?loadDiaryList():loadAileyDiaries()}>Aktualisieren</Button>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 p-1 bg-muted rounded-lg w-fit">
        <button onClick={()=>{setDiaryTab('mine');setAileyDiaryOpen(null);}} className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${diaryTab==='mine'?'bg-background text-foreground shadow':'text-muted-foreground hover:text-foreground'}`}>📖 Mein Tagebuch</button>
        <button onClick={()=>{setDiaryTab('ailey');setAileyDiaryOpen(null);}} className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${diaryTab==='ailey'?'bg-background text-foreground shadow':'text-muted-foreground hover:text-foreground'}`}>💭 Aileys Tagebuch</button>
      </div>

      {diaryTab==='mine' ? (
        <>
          <Card className="p-4 space-y-3">
            <input aria-label="Tagebuch Passwort" placeholder="Tagebuch Passwort" value={diaryPass} onChange={e=>setDiaryPass(e.target.value)} className="w-full p-2 border rounded" />
            <input aria-label="Titel" placeholder="Titel" value={diaryTitle} onChange={e=>setDiaryTitle(e.target.value)} className="w-full p-2 border rounded" />
            <textarea aria-label="Inhalt" placeholder="Schreibe etwas..." value={diaryContent} onChange={e=>setDiaryContent(e.target.value)} className="w-full p-2 border rounded h-36" />
            <div className="flex items-center gap-2"><Button onClick={saveDiary} disabled={diaryLoading}>Speichern</Button>{diaryMsg && <span className="text-green-400">{diaryMsg}</span>}</div>
          </Card>
          <div className="space-y-2">
            {diaryEntries.map(d=> (
              <Card key={d.id} className="p-3"><div className="flex items-center justify-between"><div><div className="font-semibold">{d.title||'(ohne Titel)'}</div><div className="text-xs text-muted-foreground">{new Date((d.ts||0)*1000).toLocaleString()}</div></div><div className="text-sm text-muted-foreground">{d.private? 'Privat':'Öffentlich'}</div></div></Card>
            ))}
            {diaryEntries.length===0 && <p className="text-sm text-muted-foreground">Keine Einträge.</p>}
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">Aileys automatische Tagebucheinträge — interne Reflexionen die sie nach Gesprächen verfasst.</p>
          {aileyDiaryLoading ? (
            <div className="text-center py-8 text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin mx-auto mb-2"/>Lade…</div>
          ) : aileyDiaryOpen ? (
            <div className="space-y-3">
              <button onClick={()=>setAileyDiaryOpen(null)} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"><ChevronLeft className="w-3 h-3"/> Zurück</button>
              <Card className="p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">{aileyDiaryOpen.date_readable || new Date((aileyDiaryOpen.timestamp||0)*1000).toLocaleString('de-DE')}</span>
                  <span className="text-xs text-muted-foreground">Gespräch #{aileyDiaryOpen.conversation_count}</span>
                </div>
                <div className="whitespace-pre-wrap text-sm leading-relaxed">{aileyDiaryOpen.text}</div>
              </Card>
            </div>
          ) : (
            <div className="space-y-2">
              {aileyDiaries.map((d,i)=> (
                <button key={i} onClick={()=>openAileyDiary(d._file)} className="w-full text-left">
                  <Card className="p-3 hover:border-primary/30 transition">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium">{d.date_readable || new Date((d.timestamp||0)*1000).toLocaleString('de-DE')}</div>
                        <div className="text-xs text-muted-foreground truncate mt-0.5">{d.preview}</div>
                      </div>
                      <div className="text-xs text-muted-foreground ml-3 shrink-0">#{d.conversation_count}</div>
                    </div>
                  </Card>
                </button>
              ))}
              {aileyDiaries.length===0 && <p className="text-sm text-muted-foreground">Ailey hat noch keine Tagebucheinträge geschrieben.</p>}
            </div>
          )}
        </>
      )}
    </div>
  );

  // ── Splash / Loading Screen ────────────────────────────────────────────
  // Rotating splash texts for each phase
  const splashTexts: Record<string, string[]> = {
    connecting: [
      'Ailey wird geweckt…',
      'Ailey streckt sich…',
      'Ailey gähnt ausgiebig…',
      'Wo ist der Kaffee…',
      'Noch fünf Minuten…',
    ],
    loading_model: [
      'Ailey macht sich die Haare…',
      'Lade Sprachmodell…',
      'Neuronen werden aufgeheizt…',
      'Ailey sucht ihre Gitarre…',
      'Kaffee wird gebrüht…',
    ],
    generating: [
      'Ailey denkt sich eine Begrüßung aus…',
      'Ailey checkt schnell die Mails…',
      'Gleich soweit…',
      'Ailey überlegt, was sie sagen soll…',
      'Fast fertig ✨',
    ],
    done: ['Bereit!'],
  };
  const [splashTextIdx, setSplashTextIdx] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => setSplashTextIdx(i => i + 1), 2800);
    return () => clearInterval(iv);
  }, []);
  const currentSplashTexts = splashTexts[warmupPhase] || splashTexts.connecting;
  const splashText = currentSplashTexts[splashTextIdx % currentSplashTexts.length];

  // Determine splash avatar based on progress
  const splashAvatar = resolveImageSrc(warmupProgress < 40
    ? '/images/emotes/ailey-sleeping.jpg'
    : warmupProgress < 70
    ? '/images/emotes/ailey-slightly-tired.jpg'
    : warmupProgress < 90
    ? '/images/emotes/ailey-default.jpg'
    : '/images/emotes/ailey-grins.jpg');

  if(!appReady){
    // Sleep intensity: 1.0 = deep sleep, fades to 0 as warmup progresses
    const sleepIntensity = Math.max(0, 1 - warmupProgress / 100);
    const isSleeping = warmupProgress < 60;

    return (
      <div className="min-h-screen bg-background dark flex flex-col items-center justify-center relative overflow-hidden">
        {/* ── Sleeping overlay ── covers entire viewport, fades out as Ailey wakes */}
        {isSleeping && (
          <div
            className="absolute inset-0 z-20 pointer-events-none transition-opacity duration-[2000ms]"
            style={{opacity: sleepIntensity * 0.7}}
          >
            {/* Dark vignette */}
            <div className="absolute inset-0" style={{background:'radial-gradient(circle, transparent 20%, rgba(0,0,0,0.5) 70%, rgba(0,0,0,0.8) 100%)'}}/>
            {/* Animated floating Z's */}
            <div className="absolute top-1/3 right-1/3 text-4xl text-muted-foreground/30 animate-bounce" style={{animationDuration:'3s'}}>💤</div>
            <div className="absolute top-1/4 right-1/4 text-2xl text-muted-foreground/20 animate-bounce" style={{animationDuration:'4s', animationDelay:'1s'}}>💤</div>
            <div className="absolute top-[45%] right-[20%] text-xl text-muted-foreground/15 animate-bounce" style={{animationDuration:'5s', animationDelay:'2s'}}>💤</div>
            {/* Subtle starfield dimming */}
            <div className="absolute inset-0">
              {[...Array(12)].map((_,i) => (
                <div key={i}
                  className="absolute w-1 h-1 rounded-full bg-white/10 animate-pulse"
                  style={{
                    top: `${10 + (i * 7) % 80}%`,
                    left: `${5 + (i * 13) % 90}%`,
                    animationDuration: `${2 + i % 3}s`,
                    animationDelay: `${i * 0.3}s`,
                  }}
                />
              ))}
            </div>
          </div>
        )}

        {/* Ambient glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/5 rounded-full blur-[120px] animate-pulse"/>
          <div className="absolute top-1/3 left-1/3 w-[300px] h-[300px] bg-violet-500/5 rounded-full blur-[80px] animate-pulse delay-500"/>
        </div>

        {/* Content – z-30 so text stays ABOVE the sleeping overlay and readable */}
        <div className="relative z-30 flex flex-col items-center gap-8">
          {/* Animated Avatar — sleeping → slightly tired → default → grins */}
          <div className={`w-28 h-28 rounded-full overflow-hidden border-2 shadow-lg transition-all duration-1000 ${warmupProgress < 40 ? 'border-indigo-400/30 shadow-indigo-500/10 opacity-70' : warmupProgress < 70 ? 'border-amber-400/30 shadow-amber-500/10 opacity-85' : 'border-primary/40 shadow-primary/20 opacity-100 scale-105'}`}>
            <img
              src={splashAvatar}
              alt="Ailey"
              className="w-full h-full object-cover transition-all duration-1000"
              onError={(e)=>{(e.target as HTMLImageElement).src=resolveImageSrc('/images/ailey-portrait.png')}}
            />
          </div>

          {/* Title */}
          <div className="text-center">
            <h1 className={`text-4xl font-bold tracking-tight ${uiTheme==='rainbowpunk'?'rb-logo-text':'text-primary'}`}>A!LEY</h1>
            <p className="text-sm text-muted-foreground mt-1">Digital Consciousness</p>
          </div>

          {/* Progress bar */}
          <div className="w-72 space-y-3">
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              {/* eslint-disable-next-line react/forbid-dom-props */}
              <div
                className="h-full bg-gradient-to-r from-primary via-violet-500 to-primary rounded-full transition-all duration-500 ease-out"
                style={{width: `${warmupProgress}%`}}
              />
            </div>
            {/* Rotating text with fade transition */}
            <p className="text-xs text-muted-foreground text-center animate-pulse min-h-[1.5em]">
              {splashText}
            </p>
          </div>

          {/* Phase hint */}
          <p className="text-[10px] text-muted-foreground/50 mt-8">
            {warmupPhase === 'connecting' ? 'Backend starten...' :
             warmupPhase === 'loading_model' ? 'MLX Ministral lädt...' :
             warmupPhase === 'generating' ? 'Gleich soweit ✨' : ''}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`bg-background overflow-x-hidden ${active==='chat' ? 'h-[100dvh] overflow-hidden' : 'min-h-screen'}`}>
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className={`border-b border-border bg-card/50 backdrop-blur-sm z-[90] ${active==='chat' ? 'fixed top-0 left-0 right-0' : 'sticky top-0'}`}>
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-2">
          {/* Logo */}
          <div className="flex items-center gap-3 cursor-pointer shrink-0" onClick={()=>{setActive('home');setMoreOpen(false);}}>
            {renderAvatar(displayMood,'w-10 h-10 shrink-0')}
            <div className="hidden sm:block">
              <h1 className={`text-xl font-bold leading-tight ${uiTheme==='rainbowpunk'?'rb-logo-text':'text-primary'}`}>A!LEY</h1>
              <p className="text-[10px] text-muted-foreground leading-tight">Digital Consciousness</p>
            </div>
          </div>

          {/* Desktop nav — grouped tabs */}
          <nav className="hidden md:flex items-center gap-0.5 flex-1 justify-center min-w-0">
            {navGroups.map(g=>{
              const isGroupActive = g.id === active || g.children.some(c => c.id === active);
              return (
                <button key={g.id} onClick={()=>{setActive(g.children.length>0?g.children[0].id:g.id);setMoreOpen(false);}} className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs whitespace-nowrap transition-colors shrink-0 ${isGroupActive?'bg-primary text-primary-foreground':'hover:bg-primary/10 text-foreground/80'}`}>
                  <g.icon className="h-3.5 w-3.5 shrink-0"/>{g.label}
                </button>
              );
            })}
          </nav>

          {/* Right actions */}
          <div className="flex items-center gap-1 shrink-0">
            <a href="/author" title="Schreiben" className="inline-flex items-center justify-center h-8 px-2 rounded-md border border-border text-xs font-medium gap-1 hover:bg-primary/10 transition-colors">
              <BookOpen className="h-3.5 w-3.5 text-primary"/><span className="hidden xl:inline">Schreiben</span>
            </a>
            <a href="/code" title="Code-Modus" className="inline-flex items-center justify-center h-8 px-2 rounded-md border border-border text-xs font-medium gap-1 hover:bg-primary/10 transition-colors">
              <Code2 className="h-3.5 w-3.5 text-rose-500"/><span className="hidden xl:inline">Code</span>
            </a>
            <a href="/cms" title="CMS Mode" className="inline-flex items-center justify-center h-8 px-2 rounded-md border border-border text-xs font-medium gap-1 hover:bg-primary/10 transition-colors">
              <Globe className="h-3.5 w-3.5 text-emerald-500"/><span className="hidden xl:inline">CMS</span>
            </a>
            <a href="/training" title="Training Data Collector" className="inline-flex items-center justify-center h-8 px-2 rounded-md border border-border text-xs font-medium gap-1 hover:bg-primary/10 transition-colors">
              <Brain className="h-3.5 w-3.5 text-violet-500"/><span className="hidden xl:inline">Training</span>
            </a>
            <Button variant="outline" size="icon" onClick={toggleTheme} className="h-8 w-8" title={uiTheme==='dark'?'Dark Mode':uiTheme==='cyber'?'Cyber Punk':uiTheme==='rainbowpunk'?'Rainbowpunk 🌈':uiTheme==='ailey'?'Ailey 🎭':'Light Mode'}>
              {uiTheme==='dark'?<Moon className="h-3.5 w-3.5"/>:uiTheme==='cyber'?<Sparkles className="h-3.5 w-3.5 text-teal-400"/>:uiTheme==='rainbowpunk'?<span className="text-sm leading-none">🌈</span>:uiTheme==='ailey'?<span className="text-sm leading-none">🎭</span>:<Sun className="h-3.5 w-3.5"/>}
            </Button>
            <Button variant="outline" size="icon" className="md:hidden h-8 w-8" onClick={()=>setMenuOpen(o=>!o)}>{menuOpen?<X className="h-3.5 w-3.5"/>:<Menu className="h-3.5 w-3.5"/>}</Button>
          </div>
        </div>
      </header>

      {/* ── Sub-tab bar (shows when active group has children) ──── */}
      {activeSubTabs.length > 1 && active !== 'chat' && (
        <div className={`border-b border-border bg-card/30 backdrop-blur-sm z-[89] ${active==='chat' ? 'fixed top-[3.5rem] left-0 right-0' : 'sticky top-[3.5rem]'}`}>
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex items-center gap-1 py-1.5 overflow-x-auto scrollbar-hide">
              {activeSubTabs.map(t=>(
                <button key={t.id} onClick={()=>setActive(t.id)} className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs whitespace-nowrap transition-colors shrink-0 ${active===t.id?'bg-primary/15 text-primary font-medium':'hover:bg-primary/5 text-foreground/60'}`}>
                  <t.icon className="h-3 w-3"/>{t.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Mobile fullscreen menu ──────────────────────────────── */}
      {menuOpen && (
        <div className="md:hidden fixed inset-0 z-[60] bg-background/95 backdrop-blur-sm flex flex-col items-start gap-1 overflow-y-auto py-16 px-6">
          <button onClick={()=>setMenuOpen(false)} title="Menü schließen" className="absolute top-4 right-4 p-2 rounded-lg hover:bg-primary/10"><X className="h-5 w-5"/></button>
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Navigation</div>
          {navGroups.map(g=>{
            const isGroupActive = g.id === active || g.children.some(c => c.id === active);
            return (
              <div key={g.id} className="w-full max-w-xs">
                <button onClick={()=>{
                  if(g.children.length===0){setActive(g.id);setMenuOpen(false);}
                  else{setActive(g.children[0].id);if(g.children.length<=1)setMenuOpen(false);}
                }} className={`flex items-center gap-3 w-full px-5 py-3 rounded-lg text-base transition-colors ${isGroupActive?'bg-primary text-primary-foreground':'hover:bg-primary/10'}`}>
                  <g.icon className="h-5 w-5 shrink-0"/>{g.label}
                </button>
                {/* Show sub-tabs expanded when group is active */}
                {isGroupActive && g.children.length>1 && (
                  <div className="ml-8 mt-1 mb-2 flex flex-col gap-0.5">
                    {g.children.map(c=>(
                      <button key={c.id} onClick={()=>{setActive(c.id);setMenuOpen(false);}} className={`flex items-center gap-2.5 px-4 py-2 rounded-lg text-sm transition-colors ${active===c.id?'bg-primary/15 text-primary font-medium':'hover:bg-primary/5 text-foreground/70'}`}>
                        <c.icon className="h-4 w-4 shrink-0"/>{c.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          <div className="my-2 border-t border-border w-full max-w-xs" />
          <a href="/author" className="flex items-center gap-3 w-full max-w-xs px-5 py-3 rounded-lg text-base hover:bg-primary/10 transition-colors">
            <BookOpen className="h-5 w-5 shrink-0 text-primary"/>Schreiben
          </a>
          <a href="/code" className="flex items-center gap-3 w-full max-w-xs px-5 py-3 rounded-lg text-base hover:bg-primary/10 transition-colors">
            <Code2 className="h-5 w-5 shrink-0 text-rose-500"/>Code-Modus
          </a>
          <a href="/cms" className="flex items-center gap-3 w-full max-w-xs px-5 py-3 rounded-lg text-base hover:bg-primary/10 transition-colors">
            <Globe className="h-5 w-5 shrink-0 text-emerald-500"/>CMS Mode
          </a>
          <a href="/training" className="flex items-center gap-3 w-full max-w-xs px-5 py-3 rounded-lg text-base hover:bg-primary/10 transition-colors">
            <Brain className="h-5 w-5 shrink-0 text-violet-500"/>Training Data
          </a>
          <div className="mt-4 text-[10px] text-muted-foreground">v{AILEY_VERSION}</div>
        </div>
      )}

      {/* ── Main content ────────────────────────────────────────── */}
      {/* Sections with input forms (Calendar, People) are called as plain functions
          instead of <Component/> to prevent scroll-jump on parent re-render.
          Sections with internal hooks (useEffect) must stay as <Component/>. */}
      <main className={active==='chat' ? 'h-full overflow-hidden' : 'min-h-screen'}>
        {active==='home' && Home()}
        {active==='chat' && Chat()}
        {/* LifeSimSection: unmounts on tab switch. Player position is saved to backend
            and restored as spawn override when remounting. Cleared on full app restart. */}
        {active==='life' && lifeSimEnabled && <LifeSimSection/>}
        {active==='life' && !lifeSimEnabled && (
          <div className="max-w-md mx-auto px-4 py-20 text-center space-y-4">
            <div className="text-6xl">🎮</div>
            <h2 className="text-2xl font-bold">Life Sim deaktiviert</h2>
            <p className="text-muted-foreground text-sm">Du kannst die Life Sim im System-Tab unter &quot;Subsysteme&quot; wieder aktivieren.</p>
            <Button variant="outline" onClick={() => { setLifeSimEnabled(true); }}>🏠 Jetzt aktivieren</Button>
          </div>
        )}
        {active==='history' && HistorySection()}
        {active==='system' && renderSystemSection()}
        {active==='agent' && AgentSection()}
        {active==='instagram' && InstagramSection()}
        {active==='thoughts' && ThoughtsSection()}
        {active==='diary' && DiarySection()}
        {active==='gallery' && renderGallerySection()}
        {active==='imagegen' && <ImageGenSection/>}
        {active==='videogen' && <VideoGenSection/>}
        {active==='musicgen' && <MusicGenSection/>}
        {active==='people' && PeopleSection()}
        {active==='calendar' && CalendarSection()}
        {active==='inbox' && InboxSection()}
        {active==='music' && MusicSection()}
        {active==='books' && BooksSection()}
        {active==='learning' && <LearningSection/>}
      </main>

      {active==='chat' && (
        <div ref={chatBarRef} className="fixed bottom-0 left-0 right-0 bg-background/85 backdrop-blur-sm border-t border-border z-50"><div className="max-w-4xl mx-auto p-4 space-y-3">
          {/* Desktop settings panel (gear-toggled) */}
          {desktopSettingsOpen && (
            <div className="hidden lg:block bg-card/95 backdrop-blur-xl rounded-xl border border-border p-4 space-y-3 animate-in slide-in-from-bottom-2 duration-200">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Chat-Einstellungen</span>
                <button onClick={()=>setDesktopSettingsOpen(false)} className="p-1 rounded hover:bg-primary/10" title="Schließen"><X className="h-3.5 w-3.5"/></button>
              </div>
              <div className="flex flex-wrap gap-4 items-center text-[11px]">
                <label className="flex items-center gap-1"><input type="checkbox" checked={streamEnabled} onChange={e=>setStreamEnabled(e.target.checked)}/> Streaming</label>
                <label className="flex items-center gap-1 text-violet-400"><input type="checkbox" checked={showThinking} onChange={e=>setShowThinking(e.target.checked)}/> <Brain className="h-3 w-3"/> Thinking</label>
                <label className="flex items-center gap-1"><input type="checkbox" checked={ttsEnabled} onChange={e=>setTtsEnabled(e.target.checked)}/> <Volume2 className="h-3 w-3"/> Vorlesen</label>
                <label className="flex items-center gap-1 text-emerald-400"><input type="checkbox" checked={continuousListenMode} onChange={e=>setContinuousListenMode(e.target.checked)}/> <Mic className="h-3 w-3"/> Zuhören</label>
                <div className="flex items-center gap-0.5 rounded-lg border border-border p-0.5 ml-auto">
                  <button onClick={()=>setModelMode('normal')} className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${modelMode==='normal'?'bg-primary text-primary-foreground shadow-sm':'text-muted-foreground hover:text-foreground'}`}>💬 A!ley</button>
                  <button onClick={()=>setModelMode('nitro')} className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${modelMode==='nitro'?'bg-cyan-600 text-white shadow-sm':'text-muted-foreground hover:text-foreground'}`}>⚡ Nitro</button>
                </div>
              </div>
              <div className="flex flex-wrap gap-4 items-center text-[11px]">
                <label className="flex items-center gap-1">Tokens <input type="range" min={50} max={16384} step={50} value={maxTokens} onChange={e=>setMaxTokens(parseInt(e.target.value))} onMouseUp={e=>updateGenSetting('chat',parseInt((e.target as HTMLInputElement).value))} onTouchEnd={()=>updateGenSetting('chat',maxTokens)}/> <span className="w-16 text-right tabular-nums">{maxTokens}</span></label>
                <label className="flex items-center gap-1">Temp <input type="range" min={0.1} max={1.5} step={0.05} value={temperature} onChange={e=>setTemperature(parseFloat(e.target.value))}/> <span className="w-12 text-right tabular-nums">{temperature.toFixed(2)}</span></label>
                <label className="flex items-center gap-1">Kontext <input type="range" min={4} max={64} value={maxCtx} onChange={e=>setMaxCtx(parseInt(e.target.value))}/> <span className="w-10 text-right tabular-nums">{maxCtx}</span></label>
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                {/* Wakeword button disabled – feature deferred to future version */}
                {lastHeartbeat && <span className={`px-2 py-0.5 rounded-full border text-[10px] ${heartbeatStale?'border-destructive text-destructive':'border-accent text-accent animate-pulse'}`}>HB{heartbeatStale?'…':'✓'}</span>}
                {streamWarn && <span className="text-[10px] text-yellow-400" title={streamWarn}>Warn</span>}
                <button onClick={()=>{ setDebugOpen(o=>!o); if(!debugOpen) loadDebugStreams(); }} className="text-[10px] underline hover:no-underline">Debug</button>
                {hasStreamError() && <button onClick={retryLast} className="text-[10px] text-primary underline hover:no-underline">Retry</button>}
                {(loading||streaming)&&<span className="text-accent animate-pulse text-[11px]">läuft…</span>}
              </div>
            </div>
          )}
          {/* Pending file preview (image or document) */}
          {pendingImage && (
            <div className="flex items-center gap-2 p-2 rounded-lg bg-card/60 border border-primary/30">
              {pendingImage.fileType==='image' ? (
                <img src={pendingImage.preview} alt="Anhang" className="h-16 w-16 object-cover rounded-md border border-border"/>
              ) : (
                <div className="h-16 w-16 flex items-center justify-center rounded-md border border-border bg-muted text-2xl">📄</div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{pendingImage.name}</p>
                <p className="text-[10px] text-muted-foreground">{pendingImage.fileType==='image'?'Bild wird mit der Nachricht gesendet (Pixtral Vision)':'Dokument wird analysiert und als Kontext gesendet'}</p>
              </div>
              <Button size="sm" variant="ghost" onClick={clearPendingImage} className="shrink-0"><X className="h-3.5 w-3.5"/></Button>
            </div>
          )}
          <div className="flex gap-2">
            {/* Hidden file input (images + documents) */}
            <input ref={imageInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif,.pdf,.docx,.txt,.md,.json,.xml,.csv,.yaml,.yml,.toml,.py,.js,.ts,.jsx,.tsx,.html,.css,.java,.c,.cpp,.rs,.go,.rb,.php,.sh,.sql,.swift,.kt,.lua,.tex,.log,.ini,.cfg,.conf,.env" onChange={handleImageSelect} className="hidden"/>
            {/* File attach button */}
            <Button variant="outline" size="icon" onClick={()=>imageInputRef.current?.click()} disabled={loading||streaming} title="Datei anhängen (Bilder, PDFs, Dokumente, Code…)" className="shrink-0">
              <Paperclip className="h-4 w-4"/>
            </Button>
            <Input ref={inputRef} value={input} onChange={e=>setInput(e.target.value)} onKeyDown={key} placeholder={pendingImage?(pendingImage.fileType==='document'?'Frage zum Dokument…':'Frage zum Bild…'):'Nachricht an A!ley…'} disabled={loading||streaming} className="flex-1"/>
            {/* Settings gear icon – opens mobile panel on small screens, desktop panel on md+ */}
            <Button variant={(chatSettingsOpen||desktopSettingsOpen)?'default':'outline'} size="icon" onClick={()=>{
              if(typeof window!=='undefined' && window.innerWidth>=768) setDesktopSettingsOpen(o=>!o);
              else setChatSettingsOpen(o=>!o);
            }} title="Chat-Einstellungen" className={`shrink-0 ${(chatSettingsOpen||desktopSettingsOpen)?'bg-primary text-primary-foreground':''}`}>
              <SettingsIcon className="h-4 w-4"/>
            </Button>
            {/* Mic button with pulsing ring when recording */}
            <div className="relative shrink-0">
              {sttRecording && <span className="absolute inset-0 rounded-md animate-stt-ring"/>}
              <Button variant={sttRecording?'destructive':'outline'} size="icon" onClick={toggleSTT} disabled={loading||streaming} title={sttRecording?'Aufnahme stoppen':'Spracheingabe (STT)'} className="relative z-10">
                {sttRecording?<MicOff className="h-4 w-4"/>:<Mic className="h-4 w-4"/>}
              </Button>
            </div>
            {streaming ? (
              <Button onClick={abortStream} variant="destructive" title="Antwort abbrechen"><Square className="h-4 w-4"/></Button>
            ) : (
              <Button onClick={send} data-send-btn disabled={(!input.trim()&&!pendingImage)||loading}><Send className="h-4 w-4"/></Button>
            )}
            {lastTruncated && !streaming && !loading && (
              <Button onClick={continueStream} variant="outline" title="Weiterschreiben – Antwort fortsetzen" className="text-xs gap-1"><RotateCcw className="h-3.5 w-3.5"/>Weiter</Button>
            )}
          </div>
          {/* STT status feedback */}
          {sttStatus && (
            <div className={`text-xs px-3 py-1.5 rounded-lg animate-in fade-in duration-200 ${sttRecording ? 'bg-red-500/10 text-red-400 border border-red-500/20' : sttStatus.startsWith('✅') ? 'bg-emerald-500/10 text-emerald-400' : sttStatus.startsWith('❌') || sttStatus.startsWith('🚫') ? 'bg-red-500/10 text-red-300' : 'bg-primary/10 text-primary'}`}>
              {sttStatus}
            </div>
          )}
          {/* Mobile settings panel (slide-up) */}
          {chatSettingsOpen && (
            <div className="lg:hidden bg-card/95 backdrop-blur-xl rounded-xl border border-border p-4 space-y-3 animate-in slide-in-from-bottom-2 duration-200">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Chat-Einstellungen</span>
                <button onClick={()=>setChatSettingsOpen(false)} className="p-1 rounded hover:bg-primary/10" title="Schließen"><X className="h-3.5 w-3.5"/></button>
              </div>
              <div className="grid grid-cols-2 gap-3 text-[11px]">
                <label className="flex items-center gap-2"><input type="checkbox" checked={streamEnabled} onChange={e=>setStreamEnabled(e.target.checked)}/> Streaming</label>
                <label className="flex items-center gap-2 text-violet-400"><input type="checkbox" checked={showThinking} onChange={e=>setShowThinking(e.target.checked)}/> <Brain className="h-3 w-3"/> Thinking</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={ttsEnabled} onChange={e=>setTtsEnabled(e.target.checked)}/> <Volume2 className="h-3 w-3"/> Vorlesen</label>
                <label className="flex items-center gap-2 text-emerald-400"><input type="checkbox" checked={continuousListenMode} onChange={e=>setContinuousListenMode(e.target.checked)}/> <Mic className="h-3 w-3"/> Zuhören</label>
              </div>
              <div className="flex items-center gap-1 text-[11px]">
                <span className="text-muted-foreground mr-1">Modell:</span>
                <div className="flex items-center gap-0.5 rounded-lg border border-border p-0.5 flex-1">
                  <button onClick={()=>setModelMode('normal')} className={`flex-1 px-2 py-1.5 rounded-md text-[11px] font-medium transition-all text-center ${modelMode==='normal'?'bg-primary text-primary-foreground shadow-sm':'text-muted-foreground'}`}>💬 A!ley</button>
                  <button onClick={()=>setModelMode('nitro')} className={`flex-1 px-2 py-1.5 rounded-md text-[11px] font-medium transition-all text-center ${modelMode==='nitro'?'bg-cyan-600 text-white shadow-sm':'text-muted-foreground'}`}>⚡ Nitro</button>
                </div>
              </div>
              <div className="space-y-2 text-[11px]">
                <label className="flex items-center gap-2">Tokens <input type="range" min={50} max={16384} step={50} value={maxTokens} onChange={e=>setMaxTokens(parseInt(e.target.value))} onMouseUp={e=>updateGenSetting('chat',parseInt((e.target as HTMLInputElement).value))} onTouchEnd={()=>updateGenSetting('chat',maxTokens)} className="flex-1"/> <span className="w-14 text-right tabular-nums">{maxTokens}</span></label>
                <label className="flex items-center gap-2">Temp <input type="range" min={0.1} max={1.5} step={0.05} value={temperature} onChange={e=>setTemperature(parseFloat(e.target.value))} className="flex-1"/> <span className="w-10 text-right tabular-nums">{temperature.toFixed(2)}</span></label>
                <label className="flex items-center gap-2">Kontext <input type="range" min={4} max={64} value={maxCtx} onChange={e=>setMaxCtx(parseInt(e.target.value))} className="flex-1"/> <span className="w-8 text-right tabular-nums">{maxCtx}</span></label>
              </div>
              {/* Wakeword button disabled – feature deferred to future version */}
            </div>
          )}
          <p className="text-[10px] text-muted-foreground text-center">
            {continuousListenMode && <span className="text-emerald-400 mr-2">🔄 Zuhören aktiv</span>}
            <span className="hidden md:inline">Enter: Senden • ⚙️ für Einstellungen &amp; Sprache</span>
            <span className="lg:hidden">⚙️ für Einstellungen • Nachricht tippen oder diktieren</span>
          </p>
          {debugOpen && (
            <div className="mt-2 p-2 border rounded bg-card/60 max-h-48 overflow-auto text-[10px] w-full">
              <div className="flex items-center justify-between mb-1"><strong>Streams</strong><button onClick={loadDebugStreams} className="underline">Reload</button></div>
              {debugLoading && <div className="animate-pulse text-accent">lädt…</div>}
              {!debugLoading && debugStreams.length===0 && <div className="opacity-60">Keine Daten</div>}
              {!debugLoading && debugStreams.slice().reverse().map((s:any,i:number)=> (
                <div key={i} className="border-b last:border-b-0 py-1">
                  <div className="flex justify-between"><span className="font-mono truncate max-w-[55%]">{s.id||'-'}</span><span className="opacity-60">{Math.round(((s.end_time||Date.now())-(s.start_time||Date.now()))/1000)}s</span></div>
                  <div className="opacity-70">tok:{s.tokens_streamed} chars:{s.chars} final:{String(s.final_received)}</div>
                  {s.warn && <div className="text-yellow-400">warn: {s.warn}</div>}
                </div>
              ))}
            </div>
          )}
        </div></div>
      )}
      {/* ── Mobile bottom tab bar — grouped nav ── */}
      {(active!=='chat' || chatNavVisible) && (
        <nav className={`lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-card/95 backdrop-blur-xl border-t border-border safe-area-bottom transition-all duration-300 ${active==='chat' ? 'bottom-[72px] rounded-t-xl shadow-xl' : ''}`}>
          <div className="flex justify-around items-center py-1.5 px-1">
            {[
              {id:'home',label:'Home',icon:UserIcon,gid:'home'},
              {id:'chat',label:'Chat',icon:MessageCircle,gid:'chat'},
              {id:'gallery',label:'Kreativ',icon:Palette,gid:'gallery'},
              {id:'inbox',label:'Komm.',icon:Mail,gid:'inbox'},
              {id:'_menu',label:'Mehr',icon:Menu,gid:'_menu'},
            ].map(n=>{
              const isActive = n.gid==='_menu' ? false : (activeGroupId === n.gid);
              return (
                <button
                  key={n.id}
                  onClick={()=>{
                    if (n.gid==='_menu') { setMenuOpen(true); }
                    else {
                      const grp = navGroups.find(g=>g.id===n.gid);
                      setActive(grp && grp.children.length>0 ? grp.children[0].id : n.id);
                      setMenuOpen(false);
                    }
                    setChatNavVisible(false);
                  }}
                  className={`flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg text-[10px] transition-colors min-w-0 ${isActive?'text-primary':'text-muted-foreground'}`}
                >
                  <n.icon className={`h-4 w-4 ${isActive?'text-primary':''}`}/>
                  <span className="truncate">{n.label}</span>
                </button>
              );
            })}
          </div>
        </nav>
      )}
      {active!=='chat' && <footer className="bg-card/30 backdrop-blur-sm border-t border-border mt-24 pb-16 md:pb-0"><div className="max-w-7xl mx-auto px-4 py-8 text-center text-xs text-muted-foreground">© 2025–2026 Van de Loo Mediadesign • A!ley – Digital Consciousness <span className="opacity-40 ml-2">v{AILEY_VERSION}</span></div></footer>}
    </div>
  );
}
