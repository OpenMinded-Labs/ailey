<?php
/**
 * Ailey Portal - Learning Hub v2.0
 * Features: Fachrichtung filter, Exam area grouping, Context-aware Ask Ailey,
 * AI Quiz generator, Mock Exam mode, Spaced Repetition, Code exercises, responsive
 */
require_once __DIR__ . '/layout.php';
if (!$user) { header('Location: /login'); exit; }
portal_head('Learning');
$userId = $user['id'];
$userName = htmlspecialchars($user['display_name'] ?? 'User');
?>
<style>
.learning-page{max-width:1100px;margin:0 auto;padding:2rem 1rem 4rem;min-height:100vh;overflow-y:auto;-webkit-overflow-scrolling:touch}
.learning-header{text-align:center;margin-bottom:2rem}
.learning-header h1{font-size:1.75rem;font-weight:700;display:flex;align-items:center;justify-content:center;gap:.5rem}
.learning-header p{color:var(--text-muted);font-size:.85rem;margin-top:.25rem}
.learning-stats{display:flex;justify-content:center;gap:2rem;margin-top:1rem;font-size:.9rem}
.learning-stats .stat{font-weight:600}
.learning-stats .stat-label{color:var(--text-muted);font-size:.75rem}
.error-bar{background:#ef444420;border:1px solid #ef444460;border-radius:8px;padding:.75rem;color:#f87171;font-size:.85rem;margin-bottom:1rem;text-align:center}
.track-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem}
.track-card{background:var(--card-bg);border:1px solid var(--border);border-radius:12px;padding:1.25rem;cursor:pointer;transition:border-color .2s,transform .1s}
.track-card:hover{border-color:var(--primary);transform:translateY(-2px)}
.track-card-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.75rem}
.track-emoji{font-size:2rem}
.track-level-btn{font-size:.65rem;color:var(--text-muted);border:1px solid var(--border);border-radius:4px;padding:2px 6px;cursor:pointer;background:transparent}
.track-level-btn:hover{color:var(--primary);border-color:var(--primary)}
.track-name{font-weight:600;font-size:1rem}
.track-meta{font-size:.75rem;color:var(--text-muted);margin-top:.25rem}
.progress-bar{height:6px;background:var(--input-bg);border-radius:3px;overflow:hidden;margin-top:.75rem}
.progress-fill{height:100%;background:var(--primary);border-radius:3px;transition:width .5s ease}
.progress-labels{display:flex;justify-content:space-between;margin-top:.25rem;font-size:.65rem;color:var(--text-muted)}
.review-banner{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(135deg,rgba(168,85,247,.1),rgba(59,130,246,.08));border:1px solid rgba(168,85,247,.25);border-radius:12px;padding:.75rem 1rem;margin-bottom:1.25rem;cursor:pointer;transition:border-color .2s}
.review-banner:hover{border-color:var(--primary)}
.review-banner-left{font-size:.85rem}
.review-banner-right{font-size:.8rem;color:var(--primary);font-weight:600;white-space:nowrap}
.track-detail{max-width:800px;margin:0 auto}
.back-btn{display:inline-flex;align-items:center;gap:4px;font-size:.85rem;color:var(--text-muted);cursor:pointer;background:none;border:none;padding:0;margin-bottom:1rem}
.back-btn:hover{color:var(--primary)}
.track-detail-header{display:flex;align-items:center;gap:1rem;margin-bottom:1rem}
.track-detail-header .td-emoji{font-size:3rem;flex-shrink:0}
.track-detail-header h2{font-size:1.5rem;font-weight:700;margin:0}
.track-detail-header p{font-size:.8rem;color:var(--text-muted);margin:.25rem 0 0}
.fr-filter{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap;align-items:center}
.fr-filter-label{font-size:.75rem;color:var(--text-muted);margin-right:.25rem;font-weight:500}
.fr-btn{font-size:.75rem;padding:.3rem .75rem;border-radius:20px;border:1px solid var(--border);background:transparent;color:var(--text-muted);cursor:pointer;transition:all .2s;white-space:nowrap}
.fr-btn:hover{border-color:var(--primary);color:var(--primary)}
.fr-btn.active{background:var(--primary);border-color:var(--primary);color:#fff}
.fr-btn .fr-count{font-size:.6rem;opacity:.7;margin-left:2px}
.exam-area-group{margin-bottom:1.5rem}
.exam-area-header{display:flex;align-items:center;gap:.5rem;margin-bottom:.75rem;padding-bottom:.5rem;border-bottom:1px solid var(--border)}
.exam-area-header h3{font-size:.95rem;font-weight:600;margin:0}
.exam-area-header .area-count{font-size:.7rem;color:var(--text-muted);background:var(--input-bg);padding:2px 8px;border-radius:10px}
.unit-list{display:flex;flex-direction:column;gap:.5rem}
.unit-item{display:flex;flex-direction:column;background:var(--card-bg);border:1px solid var(--border);border-radius:8px;transition:border-color .2s;overflow:hidden}
.unit-item:hover{border-color:var(--primary)}
.unit-main{display:flex;align-items:center;gap:.75rem;padding:.75rem 1rem;cursor:pointer}
.unit-actions{display:flex;gap:.5rem;padding:0 1rem .6rem 3.5rem;flex-wrap:wrap}
.unit-action-btn{font-size:.7rem;padding:.25rem .6rem;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--text-muted);cursor:pointer;transition:all .15s;white-space:nowrap}
.unit-action-btn:hover{border-color:var(--primary);color:var(--primary)}
.unit-action-btn.quiz-btn:hover{background:rgba(34,197,94,.1);border-color:#22c55e;color:#22c55e}
.unit-num{width:2rem;height:2rem;border-radius:50%;background:rgba(139,92,246,.1);display:flex;align-items:center;justify-content:center;font-size:.85rem;font-weight:700;color:var(--primary);flex-shrink:0}
.unit-check{background:rgba(34,197,94,.15);color:#22c55e}
.unit-info{flex:1;min-width:0}
.unit-title{font-weight:500;font-size:.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.unit-meta{font-size:.65rem;color:var(--text-muted);display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
.unit-best-score{font-size:.6rem;background:rgba(34,197,94,.1);color:#4ade80;padding:1px 5px;border-radius:3px}
.fr-badge{font-size:.55rem;padding:1px 5px;border-radius:3px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.fr-badge-alle{background:rgba(59,130,246,.12);color:#60a5fa}
.fr-badge-print{background:rgba(234,179,8,.12);color:#facc15}
.fr-badge-digital{background:rgba(34,197,94,.12);color:#4ade80}
.unit-view{max-width:800px;margin:0 auto}
.unit-tabs{display:flex;gap:2px;border-bottom:1px solid var(--border);margin-bottom:1.5rem;overflow-x:auto;-webkit-overflow-scrolling:touch}
.unit-tab{padding:.5rem 1rem;font-size:.85rem;font-weight:500;border-bottom:2px solid transparent;cursor:pointer;color:var(--text-muted);background:none;border-top:0;border-left:0;border-right:0;transition:color .2s,border-color .2s;white-space:nowrap}
.unit-tab.active{color:var(--primary);border-bottom-color:var(--primary)}
.unit-tab:hover{color:var(--text)}
.theory-content{font-size:.9rem;line-height:1.8;word-wrap:break-word}
.theory-content h1,.theory-content h2,.theory-content h3,.theory-content h4{margin:1.2em 0 .5em;font-weight:700;line-height:1.3}
.theory-content h1{font-size:1.3em}.theory-content h2{font-size:1.15em}.theory-content h3{font-size:1.05em}
.theory-content p{margin:.5em 0}
.theory-content ul,.theory-content ol{margin:.5em 0;padding-left:1.5em}
.theory-content li{margin:.25em 0}
.theory-content code{background:rgba(139,92,246,.12);padding:.15em .35em;border-radius:4px;font-family:'Fira Code','Cascadia Code',monospace;font-size:.85em}
.theory-content pre{background:var(--input-bg);border:1px solid var(--border);border-radius:8px;padding:.85rem;margin:.75em 0;overflow-x:auto}
.theory-content pre code{background:none;padding:0;font-size:.82em;display:block;white-space:pre-wrap;word-break:break-word}
.theory-content blockquote{border-left:3px solid var(--primary);margin:.75em 0;padding:.5em .75em;color:var(--text-muted);background:rgba(139,92,246,.04);border-radius:0 6px 6px 0}
.theory-content strong{font-weight:700;color:var(--text)}
.theory-content em{font-style:italic;color:var(--text-muted)}
.theory-content hr{border:none;border-top:1px solid var(--border);margin:1em 0}
.theory-content table{width:100%;border-collapse:collapse;margin:.75em 0;font-size:.85em}
.theory-content th,.theory-content td{border:1px solid var(--border);padding:.4em .6em;text-align:left}
.theory-content th{background:var(--input-bg);font-weight:600}
.example-block{background:var(--input-bg);border:1px solid var(--border);border-radius:8px;padding:1rem;margin-bottom:1rem;overflow-x:auto}
.example-label{font-size:.7rem;color:var(--text-muted);margin-bottom:.5rem}
.example-code{font-family:'Fira Code','Cascadia Code',monospace;font-size:.8rem;white-space:pre-wrap;overflow-x:auto}
.code-exercise textarea{width:100%;min-height:150px;font-family:'Fira Code',monospace;font-size:.8rem;padding:.75rem;background:var(--input-bg);border:1px solid var(--border);border-radius:8px;color:var(--text);resize:vertical;box-sizing:border-box}
.code-result{border:1px solid var(--border);border-radius:8px;padding:1rem;margin-top:1rem}
.code-result.passed{border-color:#22c55e50}
.code-result.failed{border-color:#eab30850}
.quiz-question{border:1px solid var(--border);border-radius:8px;padding:1rem;margin-bottom:1rem}
.quiz-question.correct{border-color:#22c55e40;background:#22c55e08}
.quiz-question.incorrect{border-color:#ef444440;background:#ef444408}
.quiz-type-badge{font-size:.65rem;font-family:monospace;background:var(--input-bg);padding:2px 6px;border-radius:4px}
.quiz-text{font-size:.9rem;font-weight:500;margin:.75rem 0}
.quiz-text p{margin:.2em 0}
.quiz-text code{background:rgba(139,92,246,.12);padding:.1em .25em;border-radius:3px;font-family:'Fira Code',monospace;font-size:.88em}
.quiz-text pre{background:var(--input-bg);border:1px solid var(--border);border-radius:6px;padding:.5rem;margin:.4em 0;overflow-x:auto}
.quiz-text pre code{background:none;padding:0;display:block;white-space:pre-wrap;font-weight:400}
.quiz-text strong{font-weight:700}
.quiz-options{display:flex;flex-direction:column;gap:.5rem}
.quiz-option{width:100%;text-align:left;padding:.5rem .75rem;border:1px solid var(--border);border-radius:6px;background:transparent;cursor:pointer;font-size:.85rem;color:var(--text);transition:border-color .15s,background .15s}
.quiz-option:hover{border-color:var(--primary)}
.quiz-option.selected{border-color:var(--primary);background:rgba(139,92,246,.1)}
.quiz-option.selected.correct-answer{border-color:#22c55e;background:#22c55e15}
.quiz-option.selected.wrong-answer{border-color:#ef4444;background:#ef444415}
.quiz-option:not(.selected).correct-answer{border-color:#22c55e80;background:#22c55e08}
.quiz-option:disabled{cursor:default;opacity:.8}
.quiz-feedback{font-size:.75rem;padding:.5rem;border-radius:4px;margin-top:.5rem;line-height:1.5}
.quiz-feedback p{display:inline;margin:0}
.quiz-feedback code{background:rgba(139,92,246,.12);padding:.1em .2em;border-radius:3px;font-family:'Fira Code',monospace;font-size:.9em}
.quiz-feedback strong{font-weight:700}
.quiz-feedback.correct{background:#22c55e15;color:#4ade80}
.quiz-feedback.incorrect{background:#ef444415;color:#f87171}
.tf-row{display:flex;gap:.5rem}
.tf-row button{flex:1}
.fill-input{width:100%;padding:.5rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.85rem;box-sizing:border-box}
.match-grid{display:flex;flex-direction:column;gap:.5rem}
.match-row{display:flex;align-items:center;gap:.5rem}
.match-left{flex:1;padding:.4rem .6rem;background:var(--input-bg);border-radius:6px;font-size:.82rem}
.match-select{flex:1;padding:.4rem .6rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.82rem}
.quiz-submit-btn{width:100%;margin-top:1rem}
.quiz-result{text-align:center;border:1px solid var(--border);border-radius:8px;padding:1.5rem;margin-top:1rem}
.quiz-result.passed{border-color:#22c55e50;background:#22c55e08}
.quiz-result.failed{border-color:#ef444450;background:#ef444408}
.quiz-result .big-emoji{font-size:2.5rem}
.quiz-result .score{font-size:1.5rem;font-weight:700}
.open-answer-wrapper{display:flex;flex-direction:column;gap:.25rem}
.open-textarea{width:100%;min-height:100px;padding:.5rem .75rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.85rem;resize:vertical;box-sizing:border-box;font-family:inherit;line-height:1.5}
.open-meta{display:flex;justify-content:space-between;align-items:center;font-size:.65rem;color:var(--text-muted);flex-wrap:wrap;gap:.25rem}
.open-word-count.low{color:#f87171}
.open-word-count.ok{color:#4ade80}
.open-hint{font-style:italic}
.lesson-cta{text-align:center;padding:3rem 1rem}
.lesson-content{background:var(--card-bg);border:1px solid var(--border);border-radius:12px;padding:1.25rem;font-size:.9rem;line-height:1.7;word-wrap:break-word}
.lesson-content h1,.lesson-content h2,.lesson-content h3,.lesson-content h4{margin:1em 0 .4em;font-weight:700;line-height:1.3}
.lesson-content h1{font-size:1.25em}.lesson-content h2{font-size:1.1em}.lesson-content h3{font-size:1em}
.lesson-content p{margin:.4em 0}.lesson-content ul,.lesson-content ol{margin:.4em 0;padding-left:1.5em}
.lesson-content li{margin:.2em 0}
.lesson-content code{background:rgba(139,92,246,.12);padding:.12em .3em;border-radius:4px;font-family:'Fira Code',monospace;font-size:.85em}
.lesson-content pre{background:var(--input-bg);border:1px solid var(--border);border-radius:8px;padding:.75rem;margin:.6em 0;overflow-x:auto}
.lesson-content pre code{background:none;padding:0;font-size:.82em;display:block;white-space:pre-wrap}
.lesson-content blockquote{border-left:3px solid var(--primary);margin:.6em 0;padding:.4em .7em;color:var(--text-muted);background:rgba(139,92,246,.04);border-radius:0 6px 6px 0}
.lesson-content strong{font-weight:700}.lesson-content em{font-style:italic;color:var(--text-muted)}
.lesson-content table{width:100%;border-collapse:collapse;margin:.6em 0;font-size:.85em}
.lesson-content th,.lesson-content td{border:1px solid var(--border);padding:.35em .5em;text-align:left}
.lesson-content th{background:var(--input-bg);font-weight:600}
.lesson-followup{display:flex;gap:.5rem;margin-top:1rem}
.lesson-followup input{flex:1;padding:.5rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.85rem;min-width:0}
.ask-ailey-inline{margin-top:.75rem;border-top:1px solid var(--border);padding-top:.75rem}
.ask-ailey-trigger{display:flex;align-items:center;gap:.5rem;font-size:.78rem;color:var(--primary);cursor:pointer;background:none;border:none;padding:.25rem 0;opacity:.85;transition:opacity .15s}
.ask-ailey-trigger:hover{opacity:1}
.ask-ailey-panel{margin-top:.5rem;background:rgba(168,85,247,.04);border:1px solid rgba(168,85,247,.2);border-radius:8px;padding:.75rem}
.ask-ailey-panel .ask-row{display:flex;gap:.5rem;margin-bottom:.5rem}
.ask-ailey-panel .ask-row input{flex:1;padding:.4rem .6rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.8rem;min-width:0}
.ask-ailey-panel .ask-row button{padding:.4rem .8rem;border-radius:6px;font-size:.8rem;white-space:nowrap}
.ask-ailey-response{font-size:.85rem;line-height:1.6;background:rgba(0,0,0,.15);border-radius:6px;padding:.75rem;margin-top:.5rem;max-height:300px;overflow-y:auto;word-wrap:break-word}
.ask-ailey-response h1,.ask-ailey-response h2,.ask-ailey-response h3,.ask-ailey-response h4{margin:.8em 0 .3em;font-weight:700;line-height:1.3}
.ask-ailey-response h1{font-size:1.15em}.ask-ailey-response h2{font-size:1.05em}.ask-ailey-response h3{font-size:.95em}
.ask-ailey-response p{margin:.3em 0}.ask-ailey-response ul,.ask-ailey-response ol{margin:.3em 0;padding-left:1.4em}
.ask-ailey-response li{margin:.15em 0}
.ask-ailey-response code{background:rgba(139,92,246,.15);padding:.1em .25em;border-radius:3px;font-family:'Fira Code',monospace;font-size:.85em}
.ask-ailey-response pre{background:var(--input-bg);border:1px solid var(--border);border-radius:6px;padding:.6rem;margin:.5em 0;overflow-x:auto}
.ask-ailey-response pre code{background:none;padding:0;font-size:.82em;display:block;white-space:pre-wrap}
.ask-ailey-response blockquote{border-left:3px solid var(--primary);margin:.5em 0;padding:.3em .6em;color:var(--text-muted);background:rgba(139,92,246,.04);border-radius:0 6px 6px 0}
.ask-ailey-response strong{font-weight:700}.ask-ailey-response em{font-style:italic;color:var(--text-muted)}
.ask-ailey-response table{width:100%;border-collapse:collapse;margin:.5em 0;font-size:.85em}
.ask-ailey-response th,.ask-ailey-response td{border:1px solid var(--border);padding:.3em .5em;text-align:left}
.ask-ailey-response th{background:var(--input-bg);font-weight:600}
.ask-ailey-loading{text-align:center;padding:1rem;font-size:.8rem;color:var(--text-muted)}
.exam-panel{background:var(--card-bg);border:1px solid var(--border);border-radius:12px;padding:1.25rem;margin-top:2rem}
.exam-input-row{display:flex;gap:.5rem;margin-bottom:1rem}
.exam-input-row input{flex:1;padding:.5rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.85rem;min-width:0}
.exam-topic-row{display:flex;align-items:center;gap:.5rem;padding:.5rem 0;border-bottom:1px solid rgba(255,255,255,.05);flex-wrap:wrap}
.exam-topic-row span{flex:1;font-size:.85rem;min-width:0}
.exam-btn{font-size:.7rem;padding:.25rem .5rem;border-radius:4px;cursor:pointer;border:1px solid var(--border);background:transparent;transition:all .15s;white-space:nowrap}
.exam-btn-drill{color:var(--primary)}.exam-btn-drill:hover{background:rgba(139,92,246,.1);border-color:var(--primary)}
.exam-btn-summary{color:#60a5fa}.exam-btn-summary:hover{background:rgba(59,130,246,.1);border-color:#60a5fa}
.exam-btn-remove{background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:.85rem;padding:.25rem}.exam-btn-remove:hover{color:#f87171}
.exam-suggestions{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.75rem}
.exam-suggestion-btn{font-size:.65rem;padding:.2rem .5rem;border-radius:12px;border:1px solid var(--border);background:transparent;color:var(--text-muted);cursor:pointer;transition:all .15s}
.exam-suggestion-btn:hover{border-color:var(--primary);color:var(--primary)}
.mock-exam-section{margin-top:1.5rem;border-top:1px solid var(--border);padding-top:1rem}
.mock-exam-config{display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;margin-bottom:.75rem}
.mock-exam-config label{font-size:.8rem;color:var(--text-muted)}
.mock-exam-config select{padding:.35rem .6rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.8rem}
.mock-exam-result{margin-top:1rem}
.mock-exam-result .meq{border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.75rem}
.mock-exam-result .meq-num{font-size:.65rem;color:var(--text-muted);margin-bottom:.25rem}
.mock-exam-result .meq-q{font-size:.9rem;font-weight:500;margin-bottom:.5rem}
.mock-exam-result .meq-hint{font-size:.75rem;color:var(--text-muted);font-style:italic}
.mock-exam-result .meq-answer{display:none;font-size:.85rem;background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.2);border-radius:6px;padding:.5rem .75rem;margin-top:.5rem;line-height:1.5;word-wrap:break-word}
.mock-exam-result .meq-answer h1,.mock-exam-result .meq-answer h2,.mock-exam-result .meq-answer h3{margin:.5em 0 .25em;font-weight:600;font-size:.95em}
.mock-exam-result .meq-answer p{margin:.25em 0}
.mock-exam-result .meq-answer ul,.mock-exam-result .meq-answer ol{margin:.25em 0;padding-left:1.3em}
.mock-exam-result .meq-answer code{background:rgba(139,92,246,.12);padding:.1em .25em;border-radius:3px;font-family:'Fira Code',monospace;font-size:.85em}
.mock-exam-result .meq-answer pre{background:var(--input-bg);border:1px solid var(--border);border-radius:6px;padding:.5rem;margin:.4em 0;overflow-x:auto}
.mock-exam-result .meq-answer pre code{background:none;padding:0;display:block;white-space:pre-wrap}
.mock-exam-result .meq-answer strong{font-weight:700}
.mock-exam-result .meq-answer.visible{display:block}
.meq-toggle{font-size:.7rem;padding:.2rem .5rem;border:1px solid var(--border);border-radius:4px;background:transparent;color:var(--text-muted);cursor:pointer;margin-top:.25rem}
.meq-toggle:hover{border-color:var(--primary);color:var(--primary)}
.ai-quiz-section{margin-top:1rem;border-top:1px solid var(--border);padding-top:1rem}
.ai-quiz-config{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin-bottom:.75rem}
.ai-quiz-questions .aiq{border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.75rem}
.level-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:flex;align-items:center;justify-content:center;padding:1rem}
.level-dialog{background:var(--card-bg);border:1px solid var(--border);border-radius:12px;padding:1.5rem;max-width:360px;width:100%}
.level-option{width:100%;padding:.5rem .75rem;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--text);cursor:pointer;text-align:left;margin-bottom:.35rem;font-size:.85rem;transition:all .15s}
.level-option:hover{border-color:var(--primary)}
.level-option.active{border-color:var(--primary);background:rgba(139,92,246,.1)}
.level-actions{display:flex;gap:.5rem;justify-content:flex-end;margin-top:1rem}
.review-view{max-width:700px;margin:0 auto}
.review-progress{display:flex;align-items:center;gap:.5rem;margin-bottom:1rem;font-size:.8rem}
.review-progress-bar{flex:1;height:4px;background:var(--input-bg);border-radius:2px;overflow:hidden}
.review-progress-fill{height:100%;background:var(--primary);border-radius:2px;transition:width .3s ease}
.review-card{border:1px solid var(--border);border-radius:12px;padding:1.5rem;background:var(--card-bg)}
.review-card-unit{font-size:.7rem;color:var(--text-muted);margin-bottom:.75rem}
.review-card-question{font-size:1rem;font-weight:500;margin-bottom:1rem;line-height:1.5}
.review-card-question p{margin:.2em 0}
.review-card-question code{background:rgba(139,92,246,.12);padding:.1em .25em;border-radius:3px;font-family:'Fira Code',monospace;font-size:.88em}
.review-card-question pre{background:var(--input-bg);border:1px solid var(--border);border-radius:6px;padding:.5rem;margin:.4em 0;overflow-x:auto}
.review-card-question pre code{background:none;padding:0;display:block;white-space:pre-wrap;font-weight:400}
.review-actions{display:flex;gap:.75rem;margin-top:1rem}
.review-actions .btn{flex:1}
.review-wrong-btn{border-color:#ef4444;color:#f87171;background:transparent}
.review-wrong-btn:hover{background:#ef444415}
.review-correct-btn{border-color:#22c55e;color:#4ade80;background:transparent}
.review-correct-btn:hover{background:#22c55e15}
.review-done{text-align:center;padding:3rem 1rem}
.spinner{width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto}
@keyframes spin{to{transform:rotate(360deg)}}
.disabled-screen{text-align:center;padding:4rem 1rem}
.disabled-screen img{width:80px;height:80px;border-radius:50%;object-fit:cover;margin:0 auto 1rem;display:block;box-shadow:0 4px 12px rgba(0,0,0,.3)}
@media(max-width:640px){
.learning-page{padding:1rem .5rem 3rem}
.learning-header h1{font-size:1.3rem}
.track-grid{grid-template-columns:1fr}
.track-detail-header{flex-direction:column;align-items:flex-start;gap:.5rem}
.track-detail-header .td-emoji{font-size:2rem}
.track-detail-header h2{font-size:1.2rem}
.unit-main{padding:.6rem .75rem}
.unit-actions{padding:0 .75rem .5rem 2.75rem}
.unit-title{font-size:.82rem}
.exam-input-row{flex-direction:column}
.fr-filter{gap:.35rem}
.mock-exam-config{flex-direction:column;align-items:flex-start}
.review-actions{flex-direction:column}
.unit-tabs{gap:0}
.unit-tab{padding:.5rem .6rem;font-size:.78rem}
.lesson-followup{flex-direction:column}
.lesson-followup input{width:100%}
.ai-quiz-config{flex-direction:column}
.ask-ailey-panel .ask-row{flex-direction:column}
}
</style>
<div class="learning-page" id="learningApp"></div>
<script>
(function(){
var API='/api.php';
var app=document.getElementById('learningApp');
var LEVEL_NAMES=['Einsteiger','Grundlagen','Fortgeschritten','Profi','Experte','Meister'];
var FR_LABELS={'alle':'Allgemein','print':'Print','digital':'Digital'};
var FR_ICONS={'alle':'\u{1F4CB}','print':'\u{1F5A8}\uFE0F','digital':'\u{1F4BB}'};
var state={
  view:'dashboard',dashboard:null,selectedTrack:null,trackDetail:null,
  currentUnit:null,quizAnswers:[],quizResult:null,
  lessonText:'',lessonLoading:false,lessonError:'',
  lessonHistory:[],lessonHistoryLoaded:false,
  codeText:'',codeResult:null,activeTab:'theory',
  levelDialog:null,levelValue:0,error:'',examTopics:[],
  examDrill:null,examDrillTopic:'',examDrillLoading:false,
  examSummary:'',examSummaryTopic:'',examSummaryLoading:false,
  accessDenied:false,
  reviewItems:[],reviewIdx:0,reviewAnswer:null,reviewResult:null,reviewStats:null,reviewLoading:false,
  frFilter:'',
  askAileyOpen:null,askAileyLoading:false,askAileyResponse:'',
  mockExamFr:'alle',mockExamCount:10,mockExamLoading:false,mockExamQuestions:null,
  aiQuizTopic:'',aiQuizCount:5,aiQuizLoading:false,aiQuizQuestions:null,aiQuizAnswers:[],aiQuizResult:null
};
async function api(action,data){
  try{var r=await fetch(API+'?action='+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data||{})});
  var json=await r.json();if(json.error==='learning_disabled'){state.accessDenied=true;render();return null;}return json;
  }catch(e){console.error('API err:',action,e);return null;}
}
async function pollerCmd(cmd,maxWait){
  maxWait=maxWait||45;
  try{var msg='[LEARNING_CMD:'+cmd+']';var sendR=await api('send_message',{message:msg});
  if(!sendR||sendR.error||!sendR.queue_id)return null;if(sendR.status==='away')return null;
  for(var i=0;i<maxWait;i++){await new Promise(function(r){setTimeout(r,1000);});
  var checkR=await api('check_reply',{queue_id:sendR.queue_id});
  if(checkR&&(checkR.status==='done'||checkR.reply)){try{return JSON.parse(checkR.reply||'{}');}catch(e){return checkR.reply;}}
  if(checkR&&checkR.status==='failed')return null;}
  }catch(e){console.error('pollerCmd err:',cmd,e);}return null;
}
async function loadDashboard(){
  state.error='';var results=await Promise.all([api('learning_dashboard'),api('learning_exam_topics')]);
  var dash=results[0],examData=results[1];if(!dash)return;
  if(dash.success&&dash.tracks)state.dashboard=dash;else state.error=dash.error||'Dashboard konnte nicht geladen werden.';
  if(examData&&examData.success)state.examTopics=examData.topics||[];render();
}
function render(){
  /* Save focused element before DOM rebuild */
  var _fId=document.activeElement?document.activeElement.id:'';
  var _fClass=document.activeElement?document.activeElement.className:'';
  var _fVal=document.activeElement&&(document.activeElement.tagName==='INPUT'||document.activeElement.tagName==='TEXTAREA')?document.activeElement.value:null;
  var _fSel=document.activeElement?document.activeElement.selectionStart:null;
  if(state.accessDenied){renderAccessDenied();return;}
  if(state.view==='dashboard')renderDashboard();
  else if(state.view==='track')renderTrackDetail();
  else if(state.view==='unit')renderUnit();
  else if(state.view==='review')renderReview();
  /* Restore focus after DOM rebuild */
  if(_fId){var el=document.getElementById(_fId);if(el){el.focus();if(_fVal!==null){el.value=_fVal;if(_fSel!==null)try{el.setSelectionRange(_fSel,_fSel);}catch(e){}}}}
  else if(_fClass&&_fVal!==null){var els=document.querySelectorAll('.'+_fClass.split(' ')[0]);if(els.length===1){els[0].focus();els[0].value=_fVal;if(_fSel!==null)try{els[0].setSelectionRange(_fSel,_fSel);}catch(e){}}}
}
function renderAccessDenied(){
  app.innerHTML='<div class="disabled-screen"><img src="/assets/ailey-sad.jpg" alt="Ailey"><h2 style="font-size:1.3rem;font-weight:700;margin-bottom:.5rem">Lernmodus nicht aktiviert</h2><p style="color:var(--text-muted);font-size:.85rem;max-width:400px;margin:0 auto">Der Lernmodus muss erst von einem Admin freigeschaltet werden.</p><a href="/chat" class="btn btn-secondary" style="margin-top:1.5rem;display:inline-block">\u2190 Zur\u00fcck zum Chat</a></div>';
}
function svgIcon(){return '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/></svg>';}
function esc(s){if(s===null||s===undefined)return '';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function md(s){
  if(s===null||s===undefined)return '';
  s=String(s);
  /* ── Phase 0: Strip AI output artefacts ── */
  /* Strip wrapping ```json ... ``` or ```markdown ... ``` if the whole string is one block */
  s=s.replace(/^\s*```(?:json|markdown|text)?\s*\n?([\s\S]*?)\n?\s*```\s*$/,'$1');
  /* Remove stray JSON wrappers sometimes returned by AI: {"lesson": "...", ...} */
  s=s.replace(/^\s*\{[\s\S]*?"(?:lesson|summary|text|content|explanation|answer)"\s*:\s*"/,'').replace(/"\s*[,}]\s*$/,'');
  /* Remove escaped newlines from JSON extraction */
  s=s.replace(/\\n/g,'\n');
  /* Remove orphan trailing JSON: ,"key":value} patterns */
  s=s.replace(/",\s*"[a-z_]+":\s*(?:"[^"]*"|\d+|true|false|null)\s*\}\s*$/gi,'');
  /* Strip leading/trailing asterisks used as markdown emphasis wrappers around entire text */
  s=s.replace(/^\*{1,3}\s+/,'').replace(/\s+\*{1,3}$/,'');

  /* ── Phase 1: Escape HTML ── */
  s=s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  /* ── Phase 2: Block elements ── */
  /* Fenced code blocks ```lang\ncode\n``` */
  s=s.replace(/```(\w*)\n([\s\S]*?)```/g,function(_,lang,code){return '<pre><code'+(lang?' data-lang="'+lang+'"':'')+'>'+code.trim()+'</code></pre>';});
  /* Inline code `code` */
  s=s.replace(/`([^`\n]+)`/g,'<code>$1</code>');
  /* Tables: |h1|h2|\n|---|---|\n|c1|c2| */
  s=s.replace(/((?:^\|.+\|$\n?)+)/gm,function(block){
    var rows=block.trim().split('\n').filter(function(r){return r.trim();});
    if(rows.length<2)return block;
    var isSep=/^\|[\s\-:|]+\|$/.test(rows[1]);if(!isSep)return block;
    var parseRow=function(r){return r.replace(/^\||\|$/g,'').split('|').map(function(c){return c.trim();});};
    var ths=parseRow(rows[0]),html='<table><thead><tr>';
    for(var i=0;i<ths.length;i++)html+='<th>'+ths[i]+'</th>';
    html+='</tr></thead><tbody>';
    for(var ri=2;ri<rows.length;ri++){var tds=parseRow(rows[ri]);html+='<tr>';for(var ci=0;ci<tds.length;ci++)html+='<td>'+tds[ci]+'</td>';html+='</tr>';}
    return html+'</tbody></table>';
  });
  /* Headers: # to #### */
  s=s.replace(/^####\s+(.+)$/gm,'<h4>$1</h4>');
  s=s.replace(/^###\s+(.+)$/gm,'<h3>$1</h3>');
  s=s.replace(/^##\s+(.+)$/gm,'<h2>$1</h2>');
  s=s.replace(/^#\s+(.+)$/gm,'<h1>$1</h1>');
  /* Horizontal rule */
  s=s.replace(/^[-*_]{3,}\s*$/gm,'<hr>');
  /* Blockquotes — merge consecutive */
  s=s.replace(/^&gt;\s?(.*)$/gm,'<blockquote>$1</blockquote>');
  s=s.replace(/<\/blockquote>\n<blockquote>/g,'\n');

  /* ── Phase 3: Inline elements ── */
  s=s.replace(/\*\*\*(.+?)\*\*\*/g,'<strong><em>$1</em></strong>');
  s=s.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  /* Italic: only match *word* not stray * at line start (which is a list marker) */
  s=s.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g,'<em>$1</em>');

  /* ── Phase 4: Lists ── */
  /* Unordered lists: - or * at line start (but not --- hr) */
  s=s.replace(/((?:^[\t ]*[-*]\s+.+$\n?)+)/gm,function(block){
    var items=block.trim().split('\n');
    var html='<ul>';
    for(var i=0;i<items.length;i++){
      var m=items[i].match(/^[\t ]*[-*]\s+(.*)/);
      if(m)html+='<li>'+m[1]+'</li>';
    }
    return html+'</ul>';
  });
  /* Ordered lists: 1. 2. etc */
  s=s.replace(/((?:^[\t ]*\d+[.)]\s+.+$\n?)+)/gm,function(block){
    var items=block.trim().split('\n');
    var html='<ol>';
    for(var i=0;i<items.length;i++){
      var m=items[i].match(/^[\t ]*\d+[.)]\s+(.*)/);
      if(m)html+='<li>'+m[1]+'</li>';
    }
    return html+'</ol>';
  });

  /* ── Phase 5: Paragraphs ── */
  s=s.replace(/\n{2,}/g,'</p><p>');
  s=s.replace(/([^>])\n([^<])/g,'$1<br>$2');
  if(!/^\s*<(?:h[1-4]|p|ul|ol|pre|blockquote|table|hr)/i.test(s))s='<p>'+s+'</p>';
  /* Clean up empty paragraphs and stray </p><p> around blocks */
  s=s.replace(/<p>\s*<\/p>/g,'');
  s=s.replace(/<p>\s*(<(?:h[1-4]|ul|ol|pre|blockquote|table|hr))/gi,'$1');
  s=s.replace(/(<\/(?:h[1-4]|ul|ol|pre|blockquote|table)>)\s*<\/p>/gi,'$1');
  return s;
}
function renderDashboard(){
  var tracks=state.dashboard?state.dashboard.tracks:[];var xp=state.dashboard?(state.dashboard.xp||0):0;var streak=state.dashboard?(state.dashboard.streak_days||0):0;
  var h='<div class="learning-header"><h1>'+svgIcon()+' A!ley Lernmodus</h1><p>Interaktive Kurse \u2022 Quizzes \u2022 KI-Erkl\u00e4rungen</p><div class="learning-stats"><div><div class="stat" style="color:var(--primary)">'+xp+' XP</div><div class="stat-label">Erfahrung</div></div><div><div class="stat">\uD83D\uDD25 '+streak+'</div><div class="stat-label">Tage Streak</div></div></div></div>';
  if(state.error)h+='<div class="error-bar">'+esc(state.error)+'</div>';
  var reviewDue=state.dashboard?(state.dashboard.review_due||0):0;
  if(reviewDue>0)h+='<div class="review-banner" onclick="LRN.startReview()"><div class="review-banner-left">\uD83D\uDD04 <strong>'+reviewDue+' Fragen</strong> zur Wiederholung f\u00e4llig</div><div class="review-banner-right">Jetzt wiederholen \u2192</div></div>';
  h+='<div class="track-grid">';
  for(var i=0;i<tracks.length;i++){var t=tracks[i];
    h+='<div class="track-card" onclick="LRN.openTrack(\''+t.id+'\')"><div class="track-card-head"><div class="track-emoji">'+(t.icon||'\uD83D\uDCDA')+'</div><button class="track-level-btn" onclick="event.stopPropagation();LRN.showLevelDialog(\''+t.id+'\','+(t.user_level||0)+')">Level '+(t.user_level||0)+'</button></div><div class="track-name">'+esc(t.name)+'</div><div class="track-meta">'+(t.completed_units||0)+'/'+(t.total_units||'?')+' Einheiten</div><div class="progress-bar"><div class="progress-fill" style="width:'+(t.progress_pct||0)+'%"></div></div><div class="progress-labels"><span>'+(t.progress_pct||0)+'%</span>'+(t.avg_quiz_score>0?'<span>\u2300 '+t.avg_quiz_score+'%</span>':'')+'</div></div>';
  }
  h+='</div>';h+=renderExamPanel();if(state.levelDialog)h+=renderLevelDialog();app.innerHTML=h;
}
function renderExamPanel(){
  var h='<div class="exam-panel"><h2 style="font-size:1.1rem;font-weight:700;margin:0 0 .25rem 0">\uD83C\uDF93 IHK Pr\u00fcfungs-Fokus</h2><p style="font-size:.7rem;color:var(--text-muted);margin:0 0 1rem 0">Pr\u00fcfungsthemen \u2014 Drill & Zusammenfassung via Ailey</p><div class="exam-input-row"><input type="text" id="exam-topic-input" placeholder="Thema eingeben..." onkeydown="if(event.key===\'Enter\')LRN.addExamTopic()"><button class="btn btn-secondary" onclick="LRN.addExamTopic()" style="white-space:nowrap">+ Hinzuf\u00fcgen</button></div>';
  if(state.examTopics.length>0){for(var i=0;i<state.examTopics.length;i++){var tp=state.examTopics[i];var safe=esc(tp).replace(/'/g,"&#39;");
    h+='<div class="exam-topic-row"><span>'+esc(tp)+'</span><button class="exam-btn exam-btn-drill" onclick="LRN.examDrill(\''+safe+'\')">\uD83D\uDCDD Drill</button><button class="exam-btn exam-btn-summary" onclick="LRN.examSummary(\''+safe+'\')">\uD83D\uDCD6 Zusammenfassung</button><button class="exam-btn-remove" onclick="LRN.removeExamTopic('+i+')">\u2715</button></div>';}}
  else h+='<p style="font-size:.75rem;color:var(--text-muted);font-style:italic">Noch keine Themen.</p>';
  var sugg=['Typografie','Farbmanagement','PDF/X','Druckverfahren','Bildbearbeitung','Kalkulation','Medienrecht','Gestaltungsgrundlagen','Datenhandling','Webentwicklung','HTML/CSS','Druckvorstufe','Bildrechte'];
  var filtered=sugg.filter(function(s){return state.examTopics.indexOf(s)===-1;});
  if(filtered.length>0){h+='<div class="exam-suggestions">';for(var si=0;si<filtered.length;si++)h+='<button class="exam-suggestion-btn" onclick="LRN.addExamTopicDirect(\''+filtered[si]+'\')">+ '+filtered[si]+'</button>';h+='</div>';}
  if(state.examDrillLoading||state.examDrill){h+='<div style="margin-top:1rem;border-top:1px solid var(--border);padding-top:.75rem"><h3 style="font-size:.9rem;font-weight:600;margin-bottom:.5rem">\uD83D\uDCDD '+esc(state.examDrillTopic)+'</h3>';
    if(state.examDrillLoading)h+='<div style="text-align:center;padding:1rem"><div class="spinner"></div></div>';
    else{var c=typeof state.examDrill==='string'?state.examDrill:JSON.stringify(state.examDrill,null,2);h+='<div class="theory-content" style="background:rgba(0,0,0,.2);border-radius:8px;padding:1rem;border:1px solid var(--border)">'+md(c)+'</div><button class="btn btn-secondary" onclick="LRN.examDrill(\''+esc(state.examDrillTopic).replace(/'/g,"&#39;")+'\')" style="margin-top:.5rem;font-size:.75rem">\uD83D\uDD04 Neu</button>';}h+='</div>';}
  if(state.examSummaryLoading||state.examSummary){h+='<div style="margin-top:1rem;border-top:1px solid var(--border);padding-top:.75rem"><h3 style="font-size:.9rem;font-weight:600;margin-bottom:.5rem">\uD83D\uDCD6 '+esc(state.examSummaryTopic)+'</h3>';
    if(state.examSummaryLoading)h+='<div style="text-align:center;padding:1rem"><div class="spinner"></div></div>';
    else h+='<div class="theory-content" style="background:rgba(0,0,0,.2);border-radius:8px;padding:1rem;border:1px solid var(--border)">'+md(state.examSummary)+'</div><button class="btn btn-secondary" onclick="LRN.examSummary(\''+esc(state.examSummaryTopic).replace(/'/g,"&#39;")+'\')" style="margin-top:.5rem;font-size:.75rem">\uD83D\uDD04 Neu</button>';h+='</div>';}
  h+='<div class="mock-exam-section"><h3 style="font-size:.95rem;font-weight:600;margin-bottom:.5rem">\uD83D\uDCC4 \u00dcbungs-Theoriepr\u00fcfung</h3><p style="font-size:.7rem;color:var(--text-muted);margin-bottom:.75rem">IHK-Format inkl. Schwerpunkt</p><div class="mock-exam-config"><label>Schwerpunkt:</label><select id="mock-exam-fr" onchange="LRN.setMockFr(this.value)"><option value="alle"'+(state.mockExamFr==='alle'?' selected':'')+'>Allgemein</option><option value="print"'+(state.mockExamFr==='print'?' selected':'')+'>Print</option><option value="digital"'+(state.mockExamFr==='digital'?' selected':'')+'>Digital</option></select><label>Fragen:</label><select onchange="LRN.setMockCount(this.value)"><option value="5"'+(state.mockExamCount===5?' selected':'')+'>5</option><option value="10"'+(state.mockExamCount===10?' selected':'')+'>10</option><option value="15"'+(state.mockExamCount===15?' selected':'')+'>15</option><option value="20"'+(state.mockExamCount===20?' selected':'')+'>20</option></select><button class="btn btn-primary" onclick="LRN.generateMockExam()" style="font-size:.8rem">\uD83C\uDF93 Erstellen</button></div>';
  if(state.mockExamLoading)h+='<div style="text-align:center;padding:1.5rem"><div class="spinner"></div></div>';
  else if(state.mockExamQuestions&&state.mockExamQuestions.length)h+=renderMockExamResult();
  h+='</div></div>';return h;
}
function renderMockExamResult(){
  var qs=state.mockExamQuestions;
  var h='<div class="mock-exam-result"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem;flex-wrap:wrap;gap:.5rem"><h4 style="font-size:.85rem;font-weight:600;margin:0">Pr\u00fcfung ('+qs.length+')</h4><div style="display:flex;gap:.35rem"><button class="btn btn-secondary" onclick="LRN.toggleAllAnswers()" style="font-size:.7rem;padding:.2rem .5rem">Alle L\u00f6sungen</button><button class="btn btn-secondary" onclick="LRN.askAileyAboutExam()" style="font-size:.7rem;padding:.2rem .5rem">\uD83D\uDC9C Ailey</button></div></div>';
  for(var i=0;i<qs.length;i++){var mq=qs[i];h+='<div class="meq"><div class="meq-num">Aufgabe '+(i+1)+(mq.bereich?' \u2022 '+esc(mq.bereich):'')+(mq.fachrichtung?' \u2022 '+esc(FR_LABELS[mq.fachrichtung]||mq.fachrichtung):'')+'</div><div class="meq-q">'+md(mq.question||mq.frage||'')+'</div>'+(mq.hint?'<div class="meq-hint">\uD83D\uDCA1 '+esc(mq.hint)+'</div>':'')+'<button class="meq-toggle" onclick="LRN.toggleAnswer(this)">L\u00f6sung anzeigen</button><div class="meq-answer" id="meq-a-'+i+'">'+md(mq.answer||mq.antwort||'')+'</div></div>';}
  h+='<button class="btn btn-primary" onclick="LRN.generateMockExam()" style="font-size:.8rem;margin-top:.5rem">\uD83D\uDD04 Neue Pr\u00fcfung</button></div>';return h;
}
function renderLevelDialog(){
  var h='<div class="level-overlay" onclick="LRN.closeLevelDialog()"><div class="level-dialog" onclick="event.stopPropagation()"><h3 style="font-weight:600;margin-bottom:.5rem">Einstiegslevel</h3><p style="font-size:.75rem;color:var(--text-muted);margin-bottom:1rem">Niedrigere Einheiten werden \u00fcbersprungen.</p>';
  for(var li=0;li<LEVEL_NAMES.length;li++)h+='<button class="level-option '+(state.levelValue===li?'active':'')+'" onclick="LRN.setLevelValue('+li+')">'+LEVEL_NAMES[li]+'</button>';
  h+='<div class="level-actions"><button class="btn btn-secondary" onclick="LRN.closeLevelDialog()">Abbrechen</button><button class="btn btn-primary" onclick="LRN.confirmLevel()">Speichern</button></div></div></div>';return h;
}
function renderTrackDetail(){
  var td=state.trackDetail;if(!td){app.innerHTML='<div style="text-align:center;padding:3rem"><div class="spinner"></div></div>';return;}
  var h='<div class="track-detail"><button class="back-btn" onclick="LRN.goBack()">\u2190 Zur\u00fcck</button><div class="track-detail-header"><div class="td-emoji">'+(td.icon||'\uD83D\uDCDA')+'</div><div><h2>'+esc(td.name)+'</h2><p>'+esc(td.description||'')+'</p></div></div>';
  var units=td.units||[];var hasFr=units.some(function(u){return u.fachrichtung&&u.fachrichtung!=='';});var hasExamArea=units.some(function(u){return u.exam_area&&u.exam_area!=='';});
  if(hasFr){var frCounts={};for(var fi=0;fi<units.length;fi++){var ufr=units[fi].fachrichtung||'';if(ufr)frCounts[ufr]=(frCounts[ufr]||0)+1;}
    h+='<div class="fr-filter"><span class="fr-filter-label">Fachrichtung:</span><button class="fr-btn'+(state.frFilter===''?' active':'')+'" onclick="LRN.setFrFilter(\'\')">Alle <span class="fr-count">('+units.length+')</span></button>';
    ['alle','print','digital'].forEach(function(k){if(frCounts[k])h+='<button class="fr-btn'+(state.frFilter===k?' active':'')+'" onclick="LRN.setFrFilter(\''+k+'\')">'+(FR_ICONS[k]||'')+' '+(FR_LABELS[k]||k)+' <span class="fr-count">('+frCounts[k]+')</span></button>';});h+='</div>';}
  var filtered=units;
  if(state.frFilter&&hasFr){if(state.frFilter==='print'||state.frFilter==='digital')filtered=units.filter(function(u){return u.fachrichtung===state.frFilter||u.fachrichtung==='alle'||!u.fachrichtung;});else filtered=units.filter(function(u){return u.fachrichtung===state.frFilter||!u.fachrichtung;});}
  if(hasExamArea&&hasFr){var groups={},groupOrder=[];for(var gi=0;gi<filtered.length;gi++){var area=filtered[gi].exam_area||'Grundlagen';if(!groups[area]){groups[area]=[];groupOrder.push(area);}groups[area].push(filtered[gi]);}
    for(var goi=0;goi<groupOrder.length;goi++){var areaName=groupOrder[goi],areaUnits=groups[areaName];var areaIcon=areaName.indexOf('konzipieren')>=0?'\uD83C\uDFA8':(areaName.indexOf('produzieren')>=0?'\u2699\uFE0F':'\uD83D\uDCD8');
    h+='<div class="exam-area-group"><div class="exam-area-header"><span>'+areaIcon+'</span><h3>'+esc(areaName)+'</h3><span class="area-count">'+areaUnits.length+' Einheiten</span></div><div class="unit-list">'+renderUnitList(areaUnits,hasFr)+'</div></div>';}}
  else h+='<div class="unit-list">'+renderUnitList(filtered,hasFr)+'</div>';
  h+=renderAiQuizSection();h+='</div>';if(state.levelDialog)h+=renderLevelDialog();app.innerHTML=h;
}
function renderUnitList(units,showFr){
  var h='';for(var ui=0;ui<units.length;ui++){var u=units[ui];var bestHtml=u.best_score!=null?'<span class="unit-best-score">\u2300 '+Math.round(u.best_score)+'%</span>':'';
    var frBadge='';if(showFr&&u.fachrichtung)frBadge='<span class="fr-badge fr-badge-'+u.fachrichtung+'">'+(FR_ICONS[u.fachrichtung]||'')+' '+(FR_LABELS[u.fachrichtung]||u.fachrichtung)+'</span>';
    h+='<div class="unit-item"><div class="unit-main" onclick="LRN.openUnit(\''+state.selectedTrack+'\',\''+u.id+'\')">'+(u.is_completed?'<div class="unit-num unit-check">\u2713</div>':'<div class="unit-num">'+(ui+1)+'</div>')+'<div class="unit-info"><div class="unit-title">'+esc(u.title)+'</div><div class="unit-meta">'+frBadge+'<span>'+(LEVEL_NAMES[u.level]||'Level '+u.level)+'</span>'+(u.quiz_count?'<span>\uD83D\uDCDD '+u.quiz_count+'</span>':'')+(u.has_exercise?'<span>\uD83D\uDCBB \u00dcbung</span>':'')+bestHtml+'</div></div><span style="color:var(--text-muted)">\u203A</span></div><div class="unit-actions">'+(u.quiz_count?'<button class="unit-action-btn quiz-btn" onclick="event.stopPropagation();LRN.openUnit(\''+state.selectedTrack+'\',\''+u.id+'\',\'quiz\')">\uD83D\uDCDD Quiz</button>':'')+'<button class="unit-action-btn" onclick="event.stopPropagation();LRN.openUnit(\''+state.selectedTrack+'\',\''+u.id+'\',\'lesson\')">\uD83D\uDC9C Frag Ailey</button></div></div>';}
  return h;
}
function renderAiQuizSection(){
  var tn=state.trackDetail?state.trackDetail.name:'';
  var h='<div class="ai-quiz-section"><h3 style="font-size:.95rem;font-weight:600;margin-bottom:.5rem">\uD83E\uDD16 KI-Quiz</h3><p style="font-size:.7rem;color:var(--text-muted);margin-bottom:.75rem">Ailey generiert ein Quiz zu \u201E'+esc(tn)+'\u201C</p><div class="ai-quiz-config"><input type="text" id="ai-quiz-topic" value="'+esc(state.aiQuizTopic)+'" placeholder="Thema..." style="flex:1;min-width:120px;padding:.4rem .6rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.8rem" oninput="state.aiQuizTopic=this.value" onkeydown="if(event.key===\'Enter\')LRN.generateAiQuiz()"><select onchange="LRN.setAiQuizCount(this.value)" style="padding:.4rem;border:1px solid var(--border);border-radius:6px;background:var(--input-bg);color:var(--text);font-size:.8rem"><option value="3"'+(state.aiQuizCount===3?' selected':'')+'>3</option><option value="5"'+(state.aiQuizCount===5?' selected':'')+'>5</option><option value="10"'+(state.aiQuizCount===10?' selected':'')+'>10</option></select><button class="btn btn-primary" onclick="LRN.generateAiQuiz()" style="font-size:.8rem;white-space:nowrap">\uD83E\uDD16 Quiz</button></div>';
  if(state.aiQuizLoading)h+='<div style="text-align:center;padding:1.5rem"><div class="spinner"></div></div>';
  else if(state.aiQuizQuestions&&state.aiQuizQuestions.length)h+=renderAiQuizQuestions();
  h+='</div>';return h;
}
function renderAiQuizQuestions(){
  var qs=state.aiQuizQuestions;var h='<div class="ai-quiz-questions">';
  for(var qi=0;qi<qs.length;qi++){var q=qs[qi],aiR=state.aiQuizResult?state.aiQuizResult[qi]:null;var cls=aiR?(aiR.correct?'correct':'incorrect'):'';
    h+='<div class="aiq quiz-question '+cls+'"><div style="display:flex;align-items:center;gap:.5rem"><span class="quiz-type-badge">KI</span><span style="font-size:.7rem;color:var(--text-muted)">Frage '+(qi+1)+'</span></div><div class="quiz-text">'+md(q.question||q.frage||'')+'</div>';
    if(q.options&&q.options.length){h+='<div class="quiz-options">';for(var oi=0;oi<q.options.length;oi++){var sel=state.aiQuizAnswers[qi]===oi;var optCls=sel?'selected':'';if(aiR&&sel)optCls+=aiR.correct?' correct-answer':' wrong-answer';h+='<button class="quiz-option '+optCls+'" '+(state.aiQuizResult?'disabled':'')+' onclick="LRN.setAiQuizAnswer('+qi+','+oi+')">'+esc(q.options[oi])+'</button>';}h+='</div>';}
    else h+='<textarea class="open-textarea" placeholder="Antwort..." '+(state.aiQuizResult?'disabled':'')+' oninput="LRN.setAiQuizAnswer('+qi+',this.value)" rows="3">'+esc(state.aiQuizAnswers[qi]||'')+'</textarea>';
    if(aiR)h+='<div class="quiz-feedback '+(aiR.correct?'correct':'incorrect')+'">'+(aiR.correct?'\u2705 Richtig!':'\u274C Nicht ganz')+(aiR.explanation?' \u2014 '+md(aiR.explanation):'')+'</div>';
    h+='</div>';}
  if(!state.aiQuizResult)h+='<button class="btn btn-primary quiz-submit-btn" onclick="LRN.submitAiQuiz()">\uD83D\uDCDD Abgeben</button>';
  else{var tc=state.aiQuizResult.filter(function(r){return r&&r.correct;}).length;var pct=Math.round(tc/qs.length*100);
    h+='<div class="quiz-result '+(pct>=60?'passed':'failed')+'"><div class="big-emoji">'+(pct>=60?'\uD83C\uDF89':'\uD83D\uDCDA')+'</div><div class="score">'+pct+'%</div><div style="font-size:.85rem;color:var(--text-muted)">'+tc+'/'+qs.length+'</div><button class="btn btn-secondary" style="margin-top:.75rem" onclick="LRN.resetAiQuiz()">\uD83D\uDD04 Neu</button></div>';}
  h+='</div>';return h;
}
function renderUnit(){
  var u=state.currentUnit;if(!u){app.innerHTML='<div style="text-align:center;padding:3rem"><div class="spinner"></div></div>';return;}
  var tabs=[{key:'theory',label:'\uD83D\uDCD6 Theorie'}];if(u.quiz&&u.quiz.length)tabs.push({key:'quiz',label:'\uD83D\uDCDD Quiz ('+u.quiz.length+')'});tabs.push({key:'lesson',label:'\uD83D\uDC9C Ailey erkl\u00e4rt'});
  var frBadge='';if(u.fachrichtung)frBadge=' <span class="fr-badge fr-badge-'+u.fachrichtung+'" style="font-size:.65rem">'+(FR_ICONS[u.fachrichtung]||'')+' '+(FR_LABELS[u.fachrichtung]||u.fachrichtung)+'</span>';
  var h='<div class="unit-view"><button class="back-btn" onclick="LRN.goBackToTrack()">\u2190 Zur\u00fcck</button><div style="margin-bottom:.5rem"><div style="font-size:.75rem;color:var(--text-muted)">'+esc(u.level_emoji||'')+' '+esc(u.level_name||'')+' \u2022 '+(u.xp_reward||0)+' XP'+frBadge+(u.is_completed?' <span style="color:#22c55e;font-weight:600">\u2713 Abgeschlossen</span>':'')+'</div><h2 style="font-size:1.5rem;font-weight:700;margin-top:.25rem">'+esc(u.title)+'</h2>'+(u.exam_area?'<div style="font-size:.7rem;color:var(--text-muted);margin-top:.15rem">'+esc(u.exam_area)+'</div>':'')+'</div><div class="unit-tabs">';
  for(var ti=0;ti<tabs.length;ti++)h+='<button class="unit-tab '+(state.activeTab===tabs[ti].key?'active':'')+'" onclick="LRN.setTab(\''+tabs[ti].key+'\')">'+tabs[ti].label+'</button>';
  h+='</div>';
  if(state.activeTab==='theory')h+=renderTheoryTab(u);else if(state.activeTab==='quiz')h+=renderQuizTab(u);else if(state.activeTab==='lesson')h+=renderLessonTab(u);
  h+='</div>';app.innerHTML=h;
}
function renderTheoryTab(u){
  var h='<div class="theory-content">'+md(u.theory||'')+'</div>';
  if(u.examples&&u.examples.length){h+='<h3 style="font-size:1.1rem;font-weight:600;margin:1.5rem 0 .75rem">\uD83D\uDCA1 Beispiele</h3>';for(var i=0;i<u.examples.length;i++){var ex=u.examples[i];h+='<div class="example-block"><div class="example-label">'+esc(ex.label||ex.title||'')+'</div><pre class="example-code">'+esc(ex.code||'')+'</pre></div>';}}
  if(u.exercise){h+='<div style="border-top:1px solid var(--border);padding-top:1.5rem;margin-top:1.5rem" class="code-exercise"><h3 style="font-size:1.1rem;font-weight:600;margin-bottom:.5rem">\uD83D\uDCBB Coding-\u00dcbung</h3><p style="font-size:.85rem;color:var(--text-muted);margin-bottom:.75rem">'+esc(u.exercise.task||'')+'</p><textarea id="code-input" placeholder="'+esc(u.exercise.starter||'Code...')+'">'+esc(state.codeText)+'</textarea><button class="btn btn-primary" style="margin-top:.75rem" onclick="LRN.submitCode()">\uD83D\uDE80 Code pr\u00fcfen</button>';if(state.codeResult)h+=renderCodeResult();h+='</div>';}
  h+=renderAskAileyBlock('theory','Ailey zu diesem Thema befragen');return h;
}
function renderAskAileyBlock(key,label){
  var isOpen=state.askAileyOpen===key;
  var h='<div class="ask-ailey-inline"><button class="ask-ailey-trigger" onclick="LRN.toggleAskAiley(\''+key+'\')">\uD83D\uDC9C '+(isOpen?'Ausblenden':esc(label))+'</button>';
  if(isOpen){h+='<div class="ask-ailey-panel"><div class="ask-row"><input type="text" id="ask-ailey-input-'+key+'" placeholder="Was m\u00f6chtest du wissen?" onkeydown="if(event.key===\'Enter\')LRN.askAileyInline(\''+key+'\')"><button class="btn btn-primary" onclick="LRN.askAileyInline(\''+key+'\')">\u2197</button></div><div style="display:flex;gap:.35rem;flex-wrap:wrap;margin-bottom:.5rem"><button class="exam-suggestion-btn" onclick="LRN.askAileyQuick(\''+key+'\',\'Erkl\u00e4re mir das einfach\')">Einfach</button><button class="exam-suggestion-btn" onclick="LRN.askAileyQuick(\''+key+'\',\'Gib mir ein Praxisbeispiel\')">Praxis</button><button class="exam-suggestion-btn" onclick="LRN.askAileyQuick(\''+key+'\',\'H\u00e4ufige Fehler?\')">Fehler</button><button class="exam-suggestion-btn" onclick="LRN.askAileyQuick(\''+key+'\',\'Wie wird das in der IHK-Pr\u00fcfung abgefragt?\')">IHK</button></div>';
    if(state.askAileyLoading)h+='<div class="ask-ailey-loading"><div class="spinner" style="width:24px;height:24px"></div><p style="margin-top:.5rem">Ailey denkt nach...</p></div>';
    if(state.askAileyResponse)h+='<div class="ask-ailey-response">'+md(state.askAileyResponse)+'</div>';h+='</div>';}
  h+='</div>';return h;
}
function renderCodeResult(){var r=state.codeResult;var h='<div class="code-result '+(r.passed?'passed':'failed')+'"><div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem"><span style="font-size:1.25rem">'+(r.passed?'\u2705':'\u26A0\uFE0F')+'</span><span style="font-weight:600">'+(r.score||0)+'/100</span></div><div style="font-size:.85rem">'+md(r.feedback||'')+'</div>';if(r.improvements&&r.improvements.length){h+='<ul style="font-size:.75rem;color:var(--text-muted);margin-top:.5rem">';for(var i=0;i<r.improvements.length;i++)h+='<li>\u2022 '+esc(r.improvements[i])+'</li>';h+='</ul>';}h+='</div>';return h;}
function renderQuizTab(u){
  var quiz=u.quiz||[];var h='';
  for(var qi=0;qi<quiz.length;qi++){var q=quiz[qi];var result=state.quizResult&&state.quizResult.results?state.quizResult.results[qi]:null;var cls=result?(result.correct?'correct':'incorrect'):'';
    h+='<div class="quiz-question '+cls+'">';var tl={mc:'Multiple Choice',tf:'Wahr/Falsch',fill:'L\u00fcckentext',match:'Zuordnung',open:'Freie Antwort',code:'Code'}[q.type]||q.type;
    h+='<div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap"><span class="quiz-type-badge">'+tl+'</span><span style="font-size:.7rem;color:var(--text-muted)">Frage '+(qi+1)+'</span></div><div class="quiz-text">'+md(q.question)+'</div>';
    if(q.type==='mc'&&q.options){h+='<div class="quiz-options">';for(var oi=0;oi<q.options.length;oi++){var sel=state.quizAnswers[qi]===oi;var oc=sel?'selected':'';if(result&&sel)oc+=result.correct?' correct-answer':' wrong-answer';h+='<button class="quiz-option '+oc+'" '+(state.quizResult?'disabled':'')+' onclick="LRN.setAnswer('+qi+','+oi+')">'+esc(q.options[oi])+'</button>';}h+='</div>';}
    else if(q.type==='tf'){h+='<div class="tf-row"><button class="quiz-option '+(state.quizAnswers[qi]===true?'selected':'')+'" '+(state.quizResult?'disabled':'')+' onclick="LRN.setAnswer('+qi+',true)">\u2713 Wahr</button><button class="quiz-option '+(state.quizAnswers[qi]===false?'selected':'')+'" '+(state.quizResult?'disabled':'')+' onclick="LRN.setAnswer('+qi+',false)">\u2717 Falsch</button></div>';}
    else if(q.type==='fill')h+='<input type="text" class="fill-input" placeholder="Antwort..." value="'+esc(state.quizAnswers[qi]||'')+'" '+(state.quizResult?'disabled':'')+' oninput="LRN.setAnswer('+qi+',this.value)">';
    else if(q.type==='match'&&q.left&&q.right){h+='<div class="match-grid">';for(var mi=0;mi<q.left.length;mi++){h+='<div class="match-row"><div class="match-left">'+esc(q.left[mi])+'</div><select class="match-select" '+(state.quizResult?'disabled':'')+' onchange="LRN.setMatchAnswer('+qi+','+mi+',this.value)"><option value="">\u2014</option>';for(var ri=0;ri<q.right.length;ri++){var seld=state.quizAnswers[qi]&&state.quizAnswers[qi][mi]===q.right[ri]?' selected':'';h+='<option value="'+esc(q.right[ri])+'"'+seld+'>'+esc(q.right[ri])+'</option>';}h+='</select></div>';}h+='</div>';}
    else if(q.type==='open'){var cv=state.quizAnswers[qi]||'';var wc=cv.trim()?cv.trim().split(/\s+/).length:0;var mw=q.min_words||10;
      h+='<div class="open-answer-wrapper"><textarea class="open-textarea" placeholder="Ausf\u00fchrlich antworten..." '+(state.quizResult?'disabled':'')+' oninput="LRN.setAnswer('+qi+',this.value);LRN.updateWordCount(this,'+mw+')" rows="5">'+esc(cv)+'</textarea><div class="open-meta"><span class="open-word-count'+(wc<mw?' low':' ok')+'">'+wc+' / min. '+mw+' W\u00f6rter</span><span class="open-hint">\uD83D\uDCA1 Schl\u00fcsselbegriffe</span></div></div>';}
    if(result){var fe='';if(result.type==='open'&&result.correct)fe=' Gut!';if(result.type==='open'&&!result.correct)fe=' Mehr Fachbegriffe!';
      h+='<div class="quiz-feedback '+(result.correct?'correct':'incorrect')+'">'+(result.correct?'\u2705 Richtig!':'\u274C Falsch')+(result.explanation?' \u2014 '+md(result.explanation):'')+fe+'</div>';}
    if(result||state.quizResult)h+=renderAskAileyBlock('q'+qi,'Ailey zu dieser Frage befragen');
    h+='</div>';}
  if(!state.quizResult){var any=state.quizAnswers.some(function(a){return a!==null&&a!==undefined&&a!=='';});h+='<button class="btn btn-primary quiz-submit-btn" '+(any?'':'disabled')+' onclick="LRN.submitQuiz()">\uD83D\uDCDD Abgeben</button>';}
  else{var r=state.quizResult;h+='<div class="quiz-result '+(r.passed?'passed':'failed')+'"><div class="big-emoji">'+(r.passed?'\uD83C\uDF89':'\uD83D\uDCDA')+'</div><div class="score">'+r.score+'%</div><div style="font-size:.85rem;color:var(--text-muted)">'+r.correct+'/'+r.total+'</div>'+(r.xp_earned>0?'<div style="color:var(--primary);font-family:monospace;margin-top:.25rem">+'+r.xp_earned+' XP</div>':'')+(!r.passed?'<p style="font-size:.75rem;color:var(--text-muted);margin-top:.5rem">60% ben\u00f6tigt</p>':'')+'<button class="btn btn-secondary" style="margin-top:.75rem" onclick="LRN.retryQuiz()">\uD83D\uDD04 Nochmal</button></div>';}
  return h;
}
function renderLessonTab(u){
  if(!state.lessonHistoryLoaded)return '<div style="text-align:center;padding:2rem"><div class="spinner"></div><p style="margin-top:.5rem;font-size:.85rem;color:var(--text-muted)">Lade Verlauf...</p></div>';
  if(state.lessonError&&!state.lessonHistory.length)return '<div class="lesson-cta"><img src="/assets/ailey-sad.jpg" alt="" style="width:64px;height:64px;border-radius:50%;object-fit:cover;margin:0 auto .5rem;display:block;box-shadow:0 4px 12px rgba(0,0,0,.3);border:2px solid rgba(168,85,247,.3)"><p style="color:#f87171;font-size:.9rem;margin-bottom:1rem">'+esc(state.lessonError)+'</p><button class="btn btn-primary" onclick="LRN.requestLesson()">\uD83D\uDD04 Nochmal</button></div>';
  var hasHistory=state.lessonHistory.length>0;
  var hasNew=state.lessonText&&state.lessonText.length>0;
  var showCTA=!hasHistory&&!hasNew&&!state.lessonLoading;
  if(showCTA)return '<div class="lesson-cta"><img src="/assets/ailey-thinking.jpg" alt="" style="width:64px;height:64px;border-radius:50%;object-fit:cover;margin:0 auto .5rem;display:block;box-shadow:0 4px 12px rgba(0,0,0,.3);border:2px solid rgba(168,85,247,.3)"><p style="color:var(--text-muted);font-size:.9rem;margin-bottom:1rem">Lass dir das von Ailey erkl\u00e4ren!</p><button class="btn btn-primary" onclick="LRN.requestLesson()">Ailey, erkl\u00e4r mir das!</button></div>';
  var h='<div class="lesson-history" style="display:flex;flex-direction:column;gap:.75rem">';
  for(var i=0;i<state.lessonHistory.length;i++){var msg=state.lessonHistory[i];
    if(msg.role==='user')h+='<div style="align-self:flex-end;max-width:85%;background:rgba(139,92,246,.12);border:1px solid rgba(139,92,246,.25);border-radius:12px 12px 4px 12px;padding:.75rem"><div style="font-size:.65rem;color:var(--text-muted);margin-bottom:.25rem">\uD83D\uDC64 Du \u2022 '+esc(msg.created_at||'').replace(/:\d{2}$/,'')+'</div><div style="font-size:.85rem">'+esc(msg.content)+'</div></div>';
    else h+='<div style="align-self:flex-start;max-width:90%;background:rgba(0,0,0,.2);border:1px solid var(--border);border-radius:12px 12px 12px 4px;padding:.75rem"><div style="font-size:.65rem;color:var(--text-muted);margin-bottom:.25rem">\uD83D\uDC9C Ailey \u2022 '+esc(msg.created_at||'').replace(/:\d{2}$/,'')+'</div><div class="theory-content" style="font-size:.85rem">'+md(msg.content)+'</div></div>';
  }
  if(hasNew)h+='<div style="align-self:flex-start;max-width:90%;background:rgba(0,0,0,.2);border:1px solid var(--border);border-radius:12px 12px 12px 4px;padding:.75rem"><div style="font-size:.65rem;color:var(--text-muted);margin-bottom:.25rem">\uD83D\uDC9C Ailey \u2022 jetzt</div><div class="theory-content" style="font-size:.85rem">'+md(state.lessonText)+'</div></div>';
  if(state.lessonLoading)h+='<div style="text-align:center;padding:1.5rem"><div class="spinner"></div><p style="margin-top:.5rem;font-size:.85rem;color:var(--text-muted)">Ailey denkt nach...</p></div>';
  h+='</div><div class="lesson-followup"><input type="text" id="lesson-q" placeholder="R\u00fcckfrage stellen..." onkeydown="if(event.key===\'Enter\')LRN.askFollowUp()"><button class="btn btn-primary" onclick="LRN.askFollowUp()">\u2197</button></div>';
  return h;
}
function renderReview(){
  if(state.reviewLoading){app.innerHTML='<div style="text-align:center;padding:3rem"><div class="spinner"></div></div>';return;}
  var items=state.reviewItems,idx=state.reviewIdx;
  var h='<div class="review-view"><button class="back-btn" onclick="LRN.goBack()">\u2190 Zur\u00fcck</button><h2 style="font-size:1.3rem;font-weight:700;margin-bottom:.25rem">\uD83D\uDD04 Wiederholung</h2><p style="font-size:.8rem;color:var(--text-muted);margin-bottom:1rem">Spaced Repetition</p>';
  if(items.length===0)h+='<div class="review-done"><div style="font-size:3rem;margin-bottom:.5rem">\uD83C\uDF89</div><h2>Alles erledigt!</h2><button class="btn btn-primary" style="margin-top:1rem" onclick="LRN.goBack()">Zur\u00fcck</button></div>';
  else if(idx>=items.length)h+='<div class="review-done"><div style="font-size:3rem;margin-bottom:.5rem">\u2705</div><h2>Session beendet!</h2><p style="color:var(--text-muted)">'+items.length+' wiederholt</p><button class="btn btn-primary" style="margin-top:1rem" onclick="LRN.goBack()">Zur\u00fcck</button></div>';
  else{var item=items[idx],q=item.question;
    h+='<div class="review-progress"><span>'+(idx+1)+'/'+items.length+'</span><div class="review-progress-bar"><div class="review-progress-fill" style="width:'+Math.round((idx/items.length)*100)+'%"></div></div><span style="font-size:.7rem">'+esc(item.unit_title||'')+'</span></div><div class="review-card"><div class="review-card-unit">\uD83D\uDCDA '+esc(item.track_id)+' \u2192 '+esc(item.unit_title||item.unit_id)+'</div>';
    if(q){h+='<div class="review-card-question">'+md(q.question)+'</div>';
      if(q.type==='mc'&&q.options){h+='<div class="quiz-options">';for(var oi=0;oi<q.options.length;oi++)h+='<button class="quiz-option '+(state.reviewAnswer===oi?'selected':'')+'" onclick="LRN.setReviewAnswer('+oi+')" '+(state.reviewResult!==null?'disabled':'')+'>'+esc(q.options[oi])+'</button>';h+='</div>';}
      else if(q.type==='tf')h+='<div class="tf-row"><button class="quiz-option '+(state.reviewAnswer===true?'selected':'')+'" onclick="LRN.setReviewAnswer(true)" '+(state.reviewResult!==null?'disabled':'')+'>Wahr</button><button class="quiz-option '+(state.reviewAnswer===false?'selected':'')+'" onclick="LRN.setReviewAnswer(false)" '+(state.reviewResult!==null?'disabled':'')+'>Falsch</button></div>';
      else if(q.type==='open')h+='<textarea class="open-textarea" placeholder="Antwort..." oninput="LRN.setReviewAnswer(this.value)" '+(state.reviewResult!==null?'disabled':'')+' rows="4">'+esc(state.reviewAnswer||'')+'</textarea>';
      else h+='<input type="text" class="fill-input" placeholder="Antwort..." oninput="LRN.setReviewAnswer(this.value)" '+(state.reviewResult!==null?'disabled':'')+' value="'+esc(state.reviewAnswer||'')+'">';}
    else h+='<div class="review-card-question">'+md(item.question_text||'N/A')+'</div>';
    if(state.reviewResult===null)h+='<div class="review-actions"><button class="btn review-wrong-btn" onclick="LRN.reviewMark(false)">\u274C Falsch</button><button class="btn review-correct-btn" onclick="LRN.reviewMark(true)" '+(state.reviewAnswer===null?'disabled':'')+  '>\u2705 Richtig</button></div>';
    else h+='<div class="quiz-feedback '+(state.reviewResult?'correct':'incorrect')+'" style="margin-top:.75rem">'+(state.reviewResult?'\u2705 Gut!':'\u274C Wird wiederholt')+'</div><button class="btn btn-primary" style="margin-top:.75rem;width:100%" onclick="LRN.reviewNext()">Weiter \u2192</button>';
    h+='</div>';}
  h+='</div>';app.innerHTML=h;
}
window.LRN={
  openTrack:async function(id){state.selectedTrack=id;state.view='track';state.trackDetail=null;state.frFilter='';state.aiQuizQuestions=null;state.aiQuizResult=null;state.aiQuizAnswers=[];render();var d=await api('learning_track',{track_id:id});if(d&&d.success&&d.track)state.trackDetail=d.track;render();},
  openUnit:async function(tid,uid,tab){state.view='unit';state.activeTab=tab||'theory';state.quizResult=null;state.lessonText='';state.lessonError='';state.codeText='';state.codeResult=null;state.currentUnit=null;state.askAileyOpen=null;state.askAileyResponse='';state.askAileyLoading=false;state.lessonHistory=[];state.lessonHistoryLoaded=false;render();var d=await api('learning_unit',{track_id:tid,unit_id:uid});if(d&&d.success&&d.unit){state.currentUnit=d.unit;state.quizAnswers=new Array(d.unit.quiz?d.unit.quiz.length:0).fill(null);}render();if(tab==='lesson'&&state.currentUnit)LRN.loadLessonHistory();},
  goBack:function(){state.view='dashboard';state.selectedTrack=null;state.trackDetail=null;loadDashboard();},
  goBackToTrack:function(){state.view='track';state.currentUnit=null;LRN.openTrack(state.selectedTrack);},
  setFrFilter:function(fr){state.frFilter=fr;render();},
  setTab:function(t){state.activeTab=t;render();if(t==='lesson'&&!state.lessonHistoryLoaded&&state.currentUnit)LRN.loadLessonHistory();},
  setAnswer:function(qi,v){state.quizAnswers[qi]=v;/* Don't re-render for text inputs — preserves focus */if(typeof v==='string')return;render();},
  setMatchAnswer:function(qi,mi,v){if(!state.quizAnswers[qi])state.quizAnswers[qi]=[];state.quizAnswers[qi][mi]=v;render();},
  submitQuiz:async function(){if(!state.currentUnit)return;var d=await api('learning_quiz_evaluate',{track_id:state.selectedTrack,unit_id:state.currentUnit.id,answers:state.quizAnswers});if(d&&d.success)state.quizResult=d;render();},
  retryQuiz:function(){state.quizResult=null;state.quizAnswers=new Array(state.currentUnit&&state.currentUnit.quiz?state.currentUnit.quiz.length:0).fill(null);state.askAileyOpen=null;state.askAileyResponse='';render();},
  loadLessonHistory:async function(){if(!state.currentUnit)return;var d=await api('learning_lesson_history',{track_id:state.selectedTrack,unit_id:state.currentUnit.id});if(d&&d.success&&d.messages){state.lessonHistory=d.messages;}state.lessonHistoryLoaded=true;render();},
  requestLesson:async function(q){if(!state.currentUnit)return;state.lessonLoading=true;state.lessonError='';state.lessonText='';render();if(q){api('learning_lesson_save',{track_id:state.selectedTrack,unit_id:state.currentUnit.id,role:'user',content:q});}var cmd=q?'lesson:'+state.selectedTrack+':'+state.currentUnit.id+':'+q:'lesson:'+state.selectedTrack+':'+state.currentUnit.id;var d=await pollerCmd(cmd,60);var txt='';if(d&&d.error){state.lessonError=d.message||d.error;}else if(d&&d.lesson){txt=d.lesson;}else if(typeof d==='string'&&d.length>0){txt=d;}else{state.lessonError='Ailey nicht erreichbar \u2014 gleich nochmal! \uD83D\uDC9C';}if(txt){state.lessonText=txt;api('learning_lesson_save',{track_id:state.selectedTrack,unit_id:state.currentUnit.id,role:'ailey',content:txt});if(q){state.lessonHistory.push({role:'user',content:q,created_at:new Date().toISOString()});state.lessonHistory.push({role:'ailey',content:txt,created_at:new Date().toISOString()});state.lessonText='';}}state.lessonLoading=false;render();},
  askFollowUp:function(){var i=document.getElementById('lesson-q');if(i&&i.value.trim()){var q=i.value.trim();i.value='';LRN.requestLesson(q);}},
  toggleAskAiley:function(k){if(state.askAileyOpen===k)state.askAileyOpen=null;else{state.askAileyOpen=k;state.askAileyResponse='';}render();},
  askAileyInline:async function(k){var i=document.getElementById('ask-ailey-input-'+k);if(!i||!i.value.trim())return;var q=i.value.trim();var ut=state.currentUnit?state.currentUnit.title:'';var ctx='Thema: '+ut;if(k.startsWith('q')&&state.currentUnit){var qI=parseInt(k.substring(1));var qO=state.currentUnit.quiz[qI];if(qO)ctx+='. Frage: "'+qO.question+'"';}state.askAileyLoading=true;state.askAileyResponse='';render();var cmd='lesson:'+state.selectedTrack+':'+(state.currentUnit?state.currentUnit.id:'general')+':'+ctx+'. '+q;var d=await pollerCmd(cmd,60);if(d&&d.lesson)state.askAileyResponse=d.lesson;else if(typeof d==='string'&&d.length>0)state.askAileyResponse=d;else state.askAileyResponse='Ailey konnte nicht antworten.';state.askAileyLoading=false;render();},
  askAileyQuick:function(k,q){var i=document.getElementById('ask-ailey-input-'+k);if(i)i.value=q;LRN.askAileyInline(k);},
  submitCode:async function(){var ta=document.getElementById('code-input');if(!ta)return;state.codeText=ta.value;var d=await pollerCmd('code_evaluate:'+state.selectedTrack+':'+state.currentUnit.id+':'+state.codeText,45);state.codeResult=d||{score:0,passed:false,feedback:'Fehlgeschlagen'};render();},
  showLevelDialog:function(t,l){state.levelDialog=t;state.levelValue=l;render();},
  closeLevelDialog:function(){state.levelDialog=null;render();},
  setLevelValue:function(v){state.levelValue=v;render();},
  confirmLevel:async function(){if(!state.levelDialog)return;await api('learning_set_level',{track_id:state.levelDialog,level:state.levelValue});state.levelDialog=null;await loadDashboard();},
  addExamTopic:function(){var i=document.getElementById('exam-topic-input');var t=i?i.value.trim():'';if(!t)return;LRN.addExamTopicDirect(t);if(i)i.value='';},
  addExamTopicDirect:async function(t){if(!t||state.examTopics.indexOf(t)!==-1)return;state.examTopics.push(t);render();await api('learning_exam_topics',{topics:state.examTopics});},
  removeExamTopic:async function(i){state.examTopics.splice(i,1);render();await api('learning_exam_topics',{topics:state.examTopics});},
  updateWordCount:function(ta,mw){var w=ta.closest('.open-answer-wrapper');if(!w)return;var c=w.querySelector('.open-word-count');if(!c)return;var n=ta.value.trim()?ta.value.trim().split(/\s+/).length:0;c.textContent=n+' / min. '+mw+' W\u00f6rter';c.className='open-word-count '+(n<mw?'low':'ok');},
  startReview:async function(){state.view='review';state.reviewItems=[];state.reviewIdx=0;state.reviewAnswer=null;state.reviewResult=null;state.reviewLoading=true;render();var d=await api('learning_review',{limit:20});if(d&&d.success){state.reviewItems=d.items||[];state.reviewStats=d.stats||null;}state.reviewLoading=false;render();},
  setReviewAnswer:function(v){state.reviewAnswer=v;/* Don't re-render for text inputs — preserves focus */if(typeof v==='string')return;render();},
  reviewMark:async function(c){var item=state.reviewItems[state.reviewIdx];if(!item)return;state.reviewResult=c;render();await api('learning_review_answer',{track_id:item.track_id,unit_id:item.unit_id,question_idx:item.question_idx,correct:c});},
  reviewNext:function(){state.reviewIdx++;state.reviewAnswer=null;state.reviewResult=null;render();},
  examDrill:async function(t){state.examDrillLoading=true;state.examDrill=null;state.examDrillTopic=t;render();var d=await pollerCmd('exam_drill:'+t+':5',60);state.examDrill=d&&d.questions?d.questions:(d||'Keine Fragen');state.examDrillLoading=false;render();},
  examSummary:async function(t){state.examSummaryLoading=true;state.examSummary='';state.examSummaryTopic=t;render();var d=await pollerCmd('exam_summary:'+t,60);state.examSummary=d&&d.summary?d.summary:(typeof d==='string'?d:'Keine Zusammenfassung');state.examSummaryLoading=false;render();},
  setMockFr:function(v){state.mockExamFr=v;},
  setMockCount:function(v){state.mockExamCount=parseInt(v);},
  generateMockExam:async function(){state.mockExamLoading=true;state.mockExamQuestions=null;render();var d=await pollerCmd('mock_exam:'+state.mockExamFr+':'+state.mockExamCount,90);if(d&&d.questions)state.mockExamQuestions=d.questions;else if(Array.isArray(d))state.mockExamQuestions=d;else if(typeof d==='string'){try{var p=JSON.parse(d);state.mockExamQuestions=p.questions||p;}catch(e){state.mockExamQuestions=[{question:d,answer:''}];}}else state.mockExamQuestions=[{question:'Fehler',answer:''}];state.mockExamLoading=false;render();},
  toggleAnswer:function(b){var a=b.nextElementSibling;if(a){a.classList.toggle('visible');b.textContent=a.classList.contains('visible')?'Verbergen':'L\u00f6sung anzeigen';}},
  toggleAllAnswers:function(){var all=document.querySelectorAll('.meq-answer');var h=false;all.forEach(function(a){if(!a.classList.contains('visible'))h=true;});all.forEach(function(a){h?a.classList.add('visible'):a.classList.remove('visible');});document.querySelectorAll('.meq-toggle').forEach(function(b){b.textContent=h?'Verbergen':'L\u00f6sung anzeigen';});},
  askAileyAboutExam:async function(){if(!state.mockExamQuestions||!state.mockExamQuestions.length)return;var ts=state.mockExamQuestions.map(function(q){return q.question||q.frage||'';}).join('; ');state.examSummaryLoading=true;state.examSummaryTopic='\u00dcbungspr\u00fcfung';state.examSummary='';render();var d=await pollerCmd('exam_summary:Meine Pr\u00fcfungsthemen: '+ts.substring(0,500),60);state.examSummary=d&&d.summary?d.summary:(typeof d==='string'?d:'N/A');state.examSummaryLoading=false;render();},
  setAiQuizCount:function(v){state.aiQuizCount=parseInt(v);},
  generateAiQuiz:async function(){var ti=document.getElementById('ai-quiz-topic');var t=ti?ti.value.trim():'';if(!t){alert('Bitte Thema eingeben.');return;}state.aiQuizTopic=t;state.aiQuizLoading=true;state.aiQuizQuestions=null;state.aiQuizResult=null;state.aiQuizAnswers=[];render();var d=await pollerCmd('ai_quiz:'+t+':'+state.aiQuizCount,90);if(d&&d.questions&&Array.isArray(d.questions)){state.aiQuizQuestions=d.questions;state.aiQuizAnswers=new Array(d.questions.length).fill(null);}else if(Array.isArray(d)){state.aiQuizQuestions=d;state.aiQuizAnswers=new Array(d.length).fill(null);}else{state.aiQuizQuestions=[{question:typeof d==='string'?d:'Fehler',options:[]}];state.aiQuizAnswers=[null];}state.aiQuizLoading=false;render();},
  setAiQuizAnswer:function(qi,v){state.aiQuizAnswers[qi]=v;/* Don't re-render for text inputs */if(typeof v==='string')return;render();},
  submitAiQuiz:function(){if(!state.aiQuizQuestions)return;var rs=[];for(var i=0;i<state.aiQuizQuestions.length;i++){var q=state.aiQuizQuestions[i],a=state.aiQuizAnswers[i];if(q.options&&q.options.length&&(q.correct!==undefined||q.correct_index!==undefined)){var ci=q.correct!==undefined?q.correct:q.correct_index;rs.push({correct:a===ci,explanation:q.explanation||''});}else rs.push({correct:a&&String(a).trim().length>5,explanation:(a&&String(a).trim().length>5)?'OK':'Ausf\u00fchrlicher!'});}state.aiQuizResult=rs;render();},
  resetAiQuiz:function(){state.aiQuizQuestions=null;state.aiQuizResult=null;state.aiQuizAnswers=[];render();}
};
loadDashboard();
})();
</script>
<?php portal_footer(); ?>