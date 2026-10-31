#!/usr/bin/env python3
"""Local, evidence-first meeting commitment review app."""
import json
import os
import re
import secrets
import sqlite3
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("MEETING_COMMITMENTS_DATA", Path.home() / ".local/share/meeting-commitments"))
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
try:
    DATA.chmod(0o700)
except OSError:
    pass
DB = DATA / "commitments.sqlite3"
TOKEN = secrets.token_urlsafe(24)
MAX_BODY = 500_000

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, title TEXT NOT NULL, transcript TEXT NOT NULL, created TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, owner TEXT NOT NULL DEFAULT '', due TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '')")
    return db

def parse_transcript(text):
    """Parse [HH:MM:SS] Speaker: words rows, retaining exact source text."""
    rows=[]
    for idx, line in enumerate(text.splitlines(), 1):
        m=re.match(r'^\s*\[(\d{2}:\d{2}:\d{2})\]\s+([^:\n]{1,80}):\s*(.{1,2000})\s*$', line)
        if m:
            rows.append({"line":idx,"time":m.group(1),"speaker":m.group(2).strip(),"text":m.group(3)})
    return rows

def proposals(text):
    rows=parse_transcript(text)
    found=[]
    for r in rows:
        body=r["text"]
        # Conservative spoken commitment cues; proposals never become confirmed automatically.
        action=bool(re.search(r'\b(I will|we will|I’ll|we’ll|I can|we can|I am going to|we are going to|I\'ll|we\'ll)\b',body,re.I))
        decision=bool(re.search(r'\b(decided|decision is|we agreed|approved|we\'re going with)\b',body,re.I))
        if not (action or decision):
            continue
        dates=re.findall(r'\b(?:20\d{2}-\d{2}-\d{2}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*20\d{2})?|(?:today|tomorrow|next week|Friday|Monday|Tuesday|Wednesday|Thursday))\b',body,re.I)
        uncertain=bool(re.search(r'\b(maybe|possibly|tentative|might|perhaps|not sure|could|if we can|depending)\b',body,re.I))
        who= r["speaker"] if re.search(r'\b(I will|I’ll|I can|I am going to|I\'ll)\b',body,re.I) else ""
        anchors={w.lower() for w in re.findall(r"[A-Za-z]{4,}",body)}-{"will","with","from","that","this","have","need","send","review","final","date","deadline","actually","instead","maybe","next"}
        conflict=bool(dates and any(re.search(r'\b(?:20\d{2}-\d{2}-\d{2}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}|Friday|Monday|Tuesday|Wednesday|Thursday)\b',other["text"],re.I) and re.search(r'\b(by|deadline|due|date|instead|actually)\b',other["text"],re.I) and anchors & {w.lower() for w in re.findall(r"[A-Za-z]{4,}",other["text"])} for other in rows if other["line"] != r["line"]))
        reason="Tentative wording needs review" if uncertain else ("Date may conflict with another transcript reference" if conflict else ("No explicit owner in this sentence" if not who else "Review before confirming"))
        found.append({"kind":"decision" if decision else "action","text":body,"owner":who,"due":dates[0] if len(dates)==1 and not uncertain and not conflict else "","evidence":r,"status":"unresolved" if uncertain or conflict or not who else "proposed","reason":reason})
    return found

def seed():
    db=connect()
    if db.execute("SELECT 1 FROM meetings LIMIT 1").fetchone():
        db.close(); return
    transcript=("[00:00:04] Maya: We decided to send the revised outline to the group.\n"
                "[00:00:18] Leo: I will share the first draft by Friday.\n"
                "[00:00:33] Maya: Maybe we can finish the review by May 14, but I need to check with the team.\n"
                "[00:00:49] Leo: I heard May 16 for the final review, not May 14.\n"
                "[00:01:02] Maya: The owner for the final review is still unclear.")
    mid=secrets.token_hex(8)
    db.execute("INSERT INTO meetings VALUES (?,?,?,datetime('now'))",(mid,"Sample · Fictional project check-in",transcript))
    for p in proposals(transcript):
        db.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)",(secrets.token_hex(8),mid,p["kind"],p["text"],p["owner"],p["due"],json.dumps(p["evidence"]),p["status"],p["reason"]))
    db.commit(); db.close()

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#090b0f"><title>Meeting Commitments</title><link rel="stylesheet" href="/style.css"></head><body>
<header><a class="brand" href="/" aria-label="Meeting Commitments home"><span class="mark">M</span><span>Meeting<br>Commitments</span></a><nav><button id="libraryTab" class="nav active">Review room</button><button id="settingsTab" class="nav">Settings</button></nav><span class="local"><i></i> Saved on this device</span></header>
<main id="app"><section id="room">
<div class="topline"><div><p class="eyebrow">THE REVIEW ROOM</p><h1>Keep the receipts.</h1><p class="intro">Turn meeting words into commitments you can stand behind.</p></div><button id="importBtn" class="primary">Import transcript <span>+</span></button></div>
<section class="workbench"><div class="transcript-pane"><div class="pane-head"><div><span class="label">TRANSCRIPT</span><h2 id="meetingTitle">Loading meeting…</h2></div><span class="synthetic">SAMPLE MEETING</span></div><div id="transcript" class="transcript"></div><div class="transcript-foot"><span>Each proposal points to its source line.</span><button id="editTranscript" class="text-button">Edit transcript</button></div></div>
<div class="commit-pane"><div class="pane-head"><div><span class="label">COMMITMENTS</span><h2>Review each one</h2></div><span id="count" class="count">0 items</span></div><div id="items" class="items"></div><div class="export-row"><span id="exportHint">Only confirmed items are included.</span><button id="exportBtn" class="export">Export confirmed</button></div></div></section>
<div class="bottom-note"><span class="pulse"></span> Nothing leaves this device. Confirmed items only.</div></section>
<section id="settings" hidden><button id="backBtn" class="text-button">← Back to review</button><h1>Settings</h1><p class="intro">This app stores transcripts and commitments in a local database.</p><div class="settings-block"><h2>Local storage</h2><p>Data path is set by <code>MEETING_COMMITMENTS_DATA</code>, or defaults to your user data folder. No account or connection is configured.</p><button id="wipeBtn" class="danger">Delete all local data</button></div><p class="small-muted">Transcript files remain wherever you keep them. Delete removes imported meeting text and reviewed items from this app.</p></section>
<dialog id="importDialog"><form method="dialog" id="importForm"><div class="dialog-head"><h2 id="dialogTitle">Import transcript</h2><button class="close" value="cancel" aria-label="Close">×</button></div><label for="titleInput">Meeting name</label><input id="titleInput" maxlength="120" value="Meeting notes"><label for="transcriptInput">Transcript with speaker and time references</label><textarea id="transcriptInput" rows="10" placeholder="[00:00:12] Alex: I will send the draft by Friday."></textarea><p class="small-muted">Use one line per turn: [HH:MM:SS] Speaker: words. Text is stored locally.</p><div class="dialog-actions"><button class="secondary" value="cancel">Cancel</button><button id="saveMeeting" class="primary" value="default">Import and review</button></div></form></dialog>
<dialog id="editDialog"><form method="dialog" id="editForm"><div class="dialog-head"><h2>Edit transcript</h2><button class="close" value="cancel" aria-label="Close">×</button></div><label for="editText">Transcript</label><textarea id="editText" rows="12"></textarea><p class="small-muted">Re-importing the edited transcript replaces its proposals. Review them again.</p><div class="dialog-actions"><button class="secondary" value="cancel">Cancel</button><button id="saveEdit" class="primary" value="default">Save transcript</button></div></form></dialog><div id="toast" role="status" aria-live="polite"></div></main><script src="/app.js" defer></script></body></html>'''

CSS = r'''
:root{color-scheme:dark;--bg:#090b0f;--surface:#11151b;--surface2:#171c23;--line:#272e37;--text:#f2f4f6;--muted:#a0a8b2;--dim:#77818d;--mint:#b5f3d0;--mint-ink:#092217;--amber:#f2c879;--red:#ff9d95;--font: 'DM Sans',-apple-system,sans-serif;--display:Manrope,'DM Sans',sans-serif}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse 70% 40% at 50% -12%,#26312a 0,transparent 72%),var(--bg);color:var(--text);font:16px/1.5 var(--font);min-height:100vh}button,input,textarea{font:inherit}button{cursor:pointer}header{height:76px;border-bottom:1px solid #ffffff12;display:flex;align-items:center;padding:0 max(28px,calc((100vw - 1440px)/2));gap:54px}.brand{color:var(--text);display:flex;align-items:center;gap:11px;text-decoration:none;font:700 13px/1.05 var(--display);letter-spacing:-.03em}.mark{height:32px;width:32px;display:grid;place-items:center;border:1px solid #709c83;border-radius:11px;color:var(--mint);font:700 16px var(--display)}nav{display:flex;gap:8px;height:100%;align-items:center}.nav{height:42px;border:0;background:none;color:var(--muted);padding:0 15px;border-radius:9px;font-size:14px}.nav:hover,.nav.active{color:var(--text);background:#ffffff0b}.local{margin-left:auto;color:var(--muted);font-size:12px;display:flex;gap:9px;align-items:center}.local i,.pulse{width:7px;height:7px;border-radius:9px;background:#8ee2ae;box-shadow:0 0 12px #8ee2ae88}main{max-width:1380px;margin:auto;padding:56px 38px 40px}.topline{display:flex;justify-content:space-between;align-items:end;margin:0 0 34px}.eyebrow,.label{font-size:10px;letter-spacing:.16em;font-weight:700;color:#a6c9b3}.eyebrow{margin:0 0 12px}h1,h2,p{margin-top:0}h1{font:700 clamp(36px,4.5vw,62px)/1.03 var(--display);letter-spacing:-.055em;margin:0 0 13px}.intro{color:#aab1ba;max-width:44ch;margin-bottom:0;font-size:16px}.primary,.export,.secondary,.danger{min-height:45px;border-radius:10px;padding:0 17px;border:1px solid transparent;font-weight:700;font-size:14px;transition:transform .24s cubic-bezier(.16,1,.3,1),background .2s,border .2s}.primary{background:var(--mint);color:var(--mint-ink)}.primary:hover{background:#d1f9e1;transform:translateY(-2px)}.primary span{font-size:19px;margin-left:9px;vertical-align:-1px}.workbench{display:grid;grid-template-columns:minmax(0,1fr) minmax(420px,.94fr);min-height:590px;border:1px solid #29313a;border-radius:18px;background:#0f1318;overflow:hidden;box-shadow:0 28px 70px #0005}.transcript-pane,.commit-pane{min-width:0;padding:28px 30px}.transcript-pane{border-right:1px solid var(--line);background:linear-gradient(140deg,#12181d,#0e1217)}.pane-head{display:flex;align-items:start;justify-content:space-between;gap:12px;padding-bottom:20px;border-bottom:1px solid #ffffff10}.pane-head h2{font:600 19px var(--display);letter-spacing:-.035em;margin:6px 0 0}.label{color:#828e99;font-size:9px}.synthetic{border:1px solid #485c4f;border-radius:20px;padding:4px 9px;color:#bddac7;font-size:9px;letter-spacing:.09em;white-space:nowrap}.transcript{padding:14px 0;max-height:435px;overflow:auto}.turn{display:grid;grid-template-columns:66px 74px 1fr;gap:10px;padding:12px 8px;border-radius:10px;color:#c1c7ce;transition:background .3s,transform .35s cubic-bezier(.16,1,.3,1);font-size:14px}.turn .time{font-variant-numeric:tabular-nums;color:#7f8a95;font-size:12px;padding-top:2px}.turn .speaker{font-size:12px;font-weight:700;color:#d4e1d8}.turn p{margin:0}.turn.highlight{background:#b5f3d013;outline:1px solid #b5f3d02a;transform:translateX(3px)}.transcript-foot{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #ffffff10;padding-top:15px;color:#7f8993;font-size:11px}.text-button{border:0;background:none;color:#b9e8ca;text-decoration:underline;text-underline-offset:3px;padding:4px}.items{display:flex;flex-direction:column;gap:11px;padding-top:16px;max-height:424px;overflow:auto}.item{border:1px solid #29313a;border-radius:12px;background:#141920;padding:15px 15px 13px;animation:rise .55s cubic-bezier(.16,1,.3,1) both;transition:border-color .2s,transform .2s}.item:hover{border-color:#45564c;transform:translateY(-1px)}@keyframes rise{from{opacity:0;transform:translateY(12px);filter:blur(4px)}to{opacity:1;transform:translateY(0);filter:blur(0)}}.item-head{display:flex;gap:10px;align-items:center;margin-bottom:9px}.kind{font-size:9px;letter-spacing:.12em;color:#aab6ad;font-weight:700}.status{font-size:10px;border-radius:20px;padding:3px 8px;background:#262c32;color:#ddd}.status.unresolved{color:#ffd891;background:#403520}.item-text{font-size:14px;line-height:1.5;color:#edf0f2;margin:0 0 11px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:11px}.field label,.dialog label{display:block;color:#a0a8b0;font-size:11px;margin-bottom:5px}.field input{width:100%;background:#0b0f13;border:1px solid #303943;color:#f1f3f5;border-radius:8px;padding:8px 9px;font-size:12px}.evidence{display:flex;align-items:center;gap:7px;color:#9ecdae;background:#17221c;border:1px solid #294032;border-radius:8px;padding:7px 9px;width:100%;text-align:left;font-size:11px}.evidence:hover{background:#1d2c23}.evidence .ref{font-variant-numeric:tabular-nums;color:#d0e4d5;white-space:nowrap}.evidence span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.actions{display:flex;align-items:center;gap:7px;margin-top:12px}.actions button{border-radius:7px;min-height:32px;padding:0 11px;font-size:11px;font-weight:700}.confirm{border:1px solid #8bd8aa;background:#aeecc6;color:#102117}.confirm:disabled{opacity:.45;cursor:not-allowed}.edit{border:1px solid #3b444d;background:#1e252c;color:#e1e5e8}.leave{margin-left:auto;border:0;background:none;color:#9ca6ae;text-decoration:underline;text-underline-offset:3px}.export-row{display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid #ffffff10;margin-top:14px;padding-top:15px;color:#8f989f;font-size:11px}.export{color:#14251a;background:#a7e7bc}.export:hover{background:#c6f3d3}.export:disabled{opacity:.42;cursor:not-allowed}.count{font-size:11px;color:#919ba5}.bottom-note{padding:19px 4px;color:#929ba3;font-size:12px;display:flex;gap:10px;align-items:center}.pulse{width:6px;height:6px}#settings{max-width:780px;margin:0 auto;min-height:70vh;padding-top:18px}#settings h1{margin-top:48px}.settings-block{border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:26px 0;margin-top:34px}.settings-block h2{font:600 19px var(--display)}.settings-block p,.small-muted{color:#9ba4ad;font-size:13px;max-width:65ch}.danger{background:#2b1718;border-color:#573031;color:#ffb4ad}.danger:hover{background:#3a1d1e}code{color:#d7eddf}.dialog-head{display:flex;justify-content:space-between;align-items:center}.dialog-head h2{font:700 23px var(--display);letter-spacing:-.035em}.close{background:none;border:0;color:#c2c9ce;font-size:25px}dialog{width:min(640px,calc(100vw - 24px));border-radius:17px;background:#151a20;color:var(--text);border:1px solid #404a54;padding:27px;box-shadow:0 25px 90px #000b}dialog::backdrop{background:#020406bd;backdrop-filter:blur(6px)}dialog label{margin-top:17px}dialog input,dialog textarea{width:100%;border-radius:9px;border:1px solid #353e47;background:#0b0f13;color:white;padding:11px;resize:vertical}dialog textarea{font-size:13px;line-height:1.6}.dialog-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}.secondary{border-color:#414a53;background:#20262d;color:#e9ecef}#toast{position:fixed;bottom:24px;left:50%;transform:translate(-50%,12px);opacity:0;background:#e2f8e9;color:#102117;padding:10px 16px;border-radius:9px;pointer-events:none;transition:.24s}#toast.show{opacity:1;transform:translate(-50%,0)}:focus-visible{outline:3px solid #b5f3d0!important;outline-offset:3px}::selection{background:#b5f3d0;color:#102217}*{scrollbar-color:#48544c #101419;scrollbar-width:thin}@media(max-width:900px){main{padding:40px 24px}.workbench{grid-template-columns:1fr}.transcript-pane{border-right:0;border-bottom:1px solid var(--line)}.transcript{max-height:320px}.items{max-height:none}}@media(max-width:560px){header{height:66px;padding:0 17px;gap:15px}.brand span:last-child{display:none}nav{gap:0}.nav{padding:0 11px;font-size:12px}.local{font-size:0;gap:0}.local i{width:8px;height:8px}main{padding:32px 14px}.topline{display:block;margin-bottom:23px}.topline h1{font-size:42px}.topline .primary{margin-top:20px;width:100%}.workbench{border-radius:14px}.transcript-pane,.commit-pane{padding:20px 16px}.turn{grid-template-columns:56px 62px 1fr;gap:7px;padding:11px 4px;font-size:13px}.turn .time{font-size:11px}.fields{grid-template-columns:1fr 1fr}.export-row{align-items:flex-start;flex-direction:column}.export{width:100%}.pane-head h2{font-size:17px}.synthetic{font-size:8px}.transcript-foot{align-items:start;font-size:10px}#settings{padding-top:0}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}'''

JS = r'''const $=s=>document.querySelector(s);let meeting=null,items=[],toastTimer;
async function api(path,method='GET',body){const o={method,headers:{'X-Local-Action':TOKEN_PLACEHOLDER}};if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}const r=await fetch(path,o);if(!r.ok)throw Error(await r.text());return r.status===204?null:r.json()}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function flash(s){const t=$('#toast');t.textContent=s;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),2400)}
async function load(){const data=await api('/api/state');meeting=data.meeting;items=data.items;render()}
function render(){if(!meeting){$('#meetingTitle').textContent='No meeting selected';return}$('#meetingTitle').textContent=meeting.title;const rows=meeting.transcript.split('\n').map((line,i)=>{const m=line.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+([^:]+):\s*(.*)$/);return m?`<div class="turn" id="line-${i+1}"><span class="time">${esc(m[1])}</span><span class="speaker">${esc(m[2])}</span><p>${esc(m[3])}</p></div>`:`<div class="turn"><span class="time">Line ${i+1}</span><span class="speaker">Text</span><p>${esc(line)}</p></div>`}).join('');$('#transcript').innerHTML=rows||'<p class="small-muted">No transcript text.</p>';$('#items').innerHTML=items.map((it,i)=>`<article class="item" style="animation-delay:${Math.min(i*55,300)}ms"><div class="item-head"><span class="kind">${esc(it.kind.toUpperCase())}</span><span class="status ${it.status==='unresolved'?'unresolved':''}">${it.status==='confirmed'?'Confirmed':it.status==='unresolved'?'Needs review':'Proposed'}</span></div><p class="item-text">${esc(it.text)}</p><div class="fields"><div class="field"><label for="owner-${esc(it.id)}">Owner</label><input id="owner-${esc(it.id)}" value="${esc(it.owner)}" maxlength="80" aria-label="Owner"></div><div class="field"><label for="due-${esc(it.id)}">Due date</label><input id="due-${esc(it.id)}" value="${esc(it.due)}" maxlength="80" aria-label="Due date"></div></div><button class="evidence" data-line="${it.evidence.line}" title="Show source in transcript"><span class="ref">${esc(it.evidence.time)} · ${esc(it.evidence.speaker)}</span><span>${esc(it.evidence.text)}</span></button><div class="actions"><button class="confirm" data-id="${esc(it.id)}" ${it.status==='unresolved'?'disabled':''}>Confirm</button><button class="edit" data-id="${esc(it.id)}">Save edits</button><button class="leave" data-id="${esc(it.id)}">Leave unresolved</button></div><p class="small-muted" style="margin:10px 0 0">${esc(it.reason)}</p></article>`).join('')||'<p class="small-muted">No commitment proposals found. Import a transcript with speaker and time references.</p>';$('#count').textContent=`${items.length} ${items.length===1?'item':'items'}`;$('#exportBtn').disabled=!items.some(x=>x.status==='confirmed')}
$('#items').addEventListener('click',async e=>{const ev=e.target.closest('.evidence');if(ev){const row=document.querySelector(`#line-${CSS.escape(ev.dataset.line)}`);row?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});row?.classList.add('highlight');setTimeout(()=>row?.classList.remove('highlight'),1700);return}const id=e.target.dataset.id;if(!id)return;const it=items.find(x=>x.id===id);if(e.target.classList.contains('confirm')){await saveItem(it,'confirmed');flash('Commitment confirmed.')}else if(e.target.classList.contains('edit')){const owner=$(`#owner-${CSS.escape(id)}`).value.trim(),due=$(`#due-${CSS.escape(id)}`).value.trim();await patchItem(it,{owner,due,status:'proposed'});flash('Edits saved. Confirm when ready.')}else if(e.target.classList.contains('leave')){await saveItem(it,'unresolved');flash('Left unresolved.')}});
async function patchItem(it,changes){await api(`/api/items/${encodeURIComponent(it.id)}`,'PATCH',changes);await load()}async function saveItem(it,status){await patchItem(it,{owner:$(`#owner-${CSS.escape(it.id)}`).value.trim(),due:$(`#due-${CSS.escape(it.id)}`).value.trim(),status,resolved:true})}
$('#importBtn').onclick=()=>$('#importDialog').showModal();$('#saveMeeting').onclick=async e=>{e.preventDefault();const title=$('#titleInput').value.trim(),transcript=$('#transcriptInput').value;if(!title||!transcript.trim()){flash('Add a meeting name and transcript.');return}try{await api('/api/meetings','POST',{title,transcript});$('#importDialog').close();$('#transcriptInput').value='';await load();flash('Transcript imported. Review each proposal.')}catch(err){flash(err.message)}};
$('#editTranscript').onclick=()=>{$('#editText').value=meeting?.transcript||'';$('#editDialog').showModal()};$('#saveEdit').onclick=async e=>{e.preventDefault();try{await api(`/api/meetings/${encodeURIComponent(meeting.id)}`,'PUT',{transcript:$('#editText').value});$('#editDialog').close();await load();flash('Transcript updated. Proposals reset for review.')}catch(err){flash(err.message)}};
$('#exportBtn').onclick=async()=>{const data=await api(`/api/meetings/${encodeURIComponent(meeting.id)}/export`);const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='confirmed-commitments.json';a.click();URL.revokeObjectURL(a.href);flash('Confirmed commitments exported.')};
function settings(on){$('#room').hidden=on;$('#settings').hidden=!on;$('#settingsTab').classList.toggle('active',on);$('#libraryTab').classList.toggle('active',!on)}$('#settingsTab').onclick=()=>settings(true);$('#libraryTab').onclick=()=>settings(false);$('#backBtn').onclick=()=>settings(false);$('#wipeBtn').onclick=async()=>{if(!confirm('Delete all meeting transcripts and commitment reviews from this app?'))return;await api('/api/data','DELETE');await load();settings(false);flash('Local app data deleted.')};load().catch(e=>flash('Could not load local data: '+e.message));'''

JS = (ROOT / "app.js").read_text(encoding="utf-8")

class Handler(BaseHTTPRequestHandler):
    server_version="MeetingCommitments/1.0"
    def log_message(self,fmt,*args):
        # No request bodies or transcript content in logs.
        super().log_message(fmt,*args)
    def safe(self):
        host=self.headers.get('Host','')
        return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def send(self,status,body=b'',ctype='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def json(self,status,obj):self.send(status,json.dumps(obj,ensure_ascii=False).encode())
    def body(self):
        n=int(self.headers.get('Content-Length','0'))
        if n<1 or n>MAX_BODY:raise ValueError('Request body is empty or too large.')
        return json.loads(self.rfile.read(n))
    def do_GET(self):
        if not self.safe():return self.send(403,b'Forbidden','text/plain')
        path=urlparse(self.path).path
        if path=='/':
            page=HTML.replace('Keep the receipts.','Meeting Commitments').replace('Turn meeting words into commitments you can stand behind.','Review actions and decisions against the words in each meeting transcript.').replace('<h2 id="meetingTitle">Loading meeting…</h2>','<h2 id="meetingTitle">Loading meeting…</h2><select id="meetingSelect" aria-label="Choose a meeting"></select>').replace('SAMPLE MEETING','LOCAL TRANSCRIPT')
            return self.send(200,page.encode(),'text/html; charset=utf-8')
        if path=='/style.css':return self.send(200,CSS.replace(':root{', '#meetingSelect{display:block;max-width:260px;margin-top:8px;background:#0b0f13;color:#e8eee9;border:1px solid #39463f;border-radius:7px;padding:5px 8px;font-size:12px}:root{',1).encode(),'text/css; charset=utf-8')
        if path=='/app.js':return self.send(200,JS.replace('TOKEN_PLACEHOLDER',json.dumps(TOKEN)).encode(),'application/javascript; charset=utf-8')
        if path=='/api/state':
            from urllib.parse import parse_qs
            db=connect();meetings=db.execute('SELECT id,title,created FROM meetings ORDER BY rowid DESC').fetchall();wanted=parse_qs(urlparse(self.path).query).get('id',[None])[0];m=db.execute('SELECT * FROM meetings WHERE id=?',(wanted,)).fetchone() if wanted else (db.execute('SELECT * FROM meetings ORDER BY rowid DESC LIMIT 1').fetchone());its=db.execute('SELECT * FROM items WHERE meeting_id=? ORDER BY rowid',(m['id'],)).fetchall() if m else [];db.close()
            return self.json(200,{'meeting':dict(m) if m else None,'meetings':[dict(x) for x in meetings],'items':[dict(x)|{'evidence':json.loads(x['evidence'])} for x in its]})
        parts=path.split('/')
        if len(parts)==5 and parts[:3]==['','api','meetings'] and parts[4]=='export':
            db=connect();rows=db.execute("SELECT kind,text,owner,due,evidence FROM items WHERE meeting_id=? AND status='confirmed'",(parts[3],)).fetchall();m=db.execute('SELECT title FROM meetings WHERE id=?',(parts[3],)).fetchone();db.close()
            if not m:return self.json(404,{'error':'Meeting not found.'})
            return self.json(200,{'meeting':m['title'],'items':[dict(r)|{'evidence':json.loads(r['evidence'])} for r in rows]})
        return self.send(404,b'Not found','text/plain')
    def mutation_ok(self):
        origin=self.headers.get('Origin')
        allowed=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
        return self.safe() and self.headers.get('X-Local-Action')==TOKEN and (origin is None or origin in allowed)
    def do_POST(self):
        if not self.mutation_ok():return self.send(403,b'Forbidden','text/plain')
        try:
            if urlparse(self.path).path!='/api/meetings':return self.send(404,b'Not found','text/plain')
            obj=self.body()
            if not isinstance(obj,dict) or not isinstance(obj.get('title',''),str) or not isinstance(obj.get('transcript',''),str):raise ValueError('Meeting name and transcript must be text.')
            title=obj.get('title','').strip();transcript=obj.get('transcript','')
            if len(title)>120 or len(transcript)>400000:raise ValueError('Meeting name or transcript is too long.')
            rows=parse_transcript(transcript)
            if not rows:raise ValueError('No timed speaker lines found. Use [HH:MM:SS] Speaker: words.')
            mid=secrets.token_hex(8);db=connect();db.execute('INSERT INTO meetings VALUES (?,?,?,datetime(\'now\'))',(mid,title or 'Untitled meeting',transcript))
            for p in proposals(transcript):db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)',(secrets.token_hex(8),mid,p['kind'],p['text'],p['owner'],p['due'],json.dumps(p['evidence']),p['status'],p['reason']))
            db.commit();db.close();return self.json(201,{'id':mid})
        except (ValueError,TypeError,json.JSONDecodeError) as e:return self.json(400,{'error':str(e)})
    def do_PATCH(self):
        if not self.mutation_ok():return self.send(403,b'Forbidden','text/plain')
        try:
            if not re.fullmatch(r'/api/items/[a-f0-9]{16}',urlparse(self.path).path):return self.send(404,b'Not found','text/plain')
            obj=self.body()
            if not isinstance(obj,dict):raise ValueError('Expected a JSON object.')
            status=obj.get('status')
            if status not in ('proposed','confirmed','unresolved'):raise ValueError('Invalid review status.')
            if status=='confirmed' and obj.get('resolved') is not True:raise ValueError('Edit and save an unresolved proposal before confirming it.')
            if not isinstance(obj.get('owner',''),str) or not isinstance(obj.get('due',''),str):raise ValueError('Owner and due date must be text.')
            owner=obj.get('owner','').strip()[:80];due=obj.get('due','').strip()[:80]
            # Confirmation requires an explicit owner and evidence-backed proposal. Date may remain blank.
            if status=='confirmed' and not owner:raise ValueError('Add an owner before confirming this item.')
            iid=urlparse(self.path).path.rsplit('/',1)[-1]
            db=connect();current=db.execute('SELECT status FROM items WHERE id=?',(iid,)).fetchone()
            if current and current['status']=='unresolved' and status=='confirmed':db.close();return self.json(400,{'error':'Save edits on this unresolved proposal before confirming it.'})
            cur=db.execute('UPDATE items SET owner=?,due=?,status=?,reason=CASE WHEN ? THEN ? ELSE reason END WHERE id=?',(owner,due,status,1 if obj.get('resolved') is True else 0,'Reviewed by user',iid));db.commit();db.close()
            if not cur.rowcount:db.close();return self.json(404,{'error':'Commitment not found.'})
            db.close()
            return self.json(200,{'updated':cur.rowcount})
        except (ValueError,TypeError,json.JSONDecodeError) as e:return self.json(400,{'error':str(e)})
    def do_PUT(self):
        if not self.mutation_ok():return self.send(403,b'Forbidden','text/plain')
        try:
            mid=urlparse(self.path).path.rsplit('/',1)[-1];db=connect()
            if not re.fullmatch(r'[a-f0-9]{16}',mid) or not db.execute('SELECT 1 FROM meetings WHERE id=?',(mid,)).fetchone():db.close();return self.json(404,{'error':'Meeting not found.'})
            obj=self.body()
            if not isinstance(obj,dict) or not isinstance(obj.get('transcript'),str):raise ValueError('Expected a transcript text field.')
            transcript=obj['transcript']
            if not parse_transcript(transcript):raise ValueError('No timed speaker lines found.')
            db.execute('UPDATE meetings SET transcript=? WHERE id=?',(transcript,mid));db.execute('DELETE FROM items WHERE meeting_id=?',(mid,))
            for p in proposals(transcript):db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)',(secrets.token_hex(8),mid,p['kind'],p['text'],p['owner'],p['due'],json.dumps(p['evidence']),p['status'],p['reason']))
            db.commit();db.close();return self.json(200,{'saved':True})
        except (ValueError,TypeError,json.JSONDecodeError) as e:return self.json(400,{'error':str(e)})
    def do_DELETE(self):
        if not self.mutation_ok():return self.send(403,b'Forbidden','text/plain')
        path=urlparse(self.path).path;db=connect()
        if path=='/api/data':db.execute('DELETE FROM items');db.execute('DELETE FROM meetings');db.commit();db.close();return self.send(204)
        db.close();return self.send(404)

def run(port=8344):
    seed();server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    print(f'Meeting Commitments listening at http://127.0.0.1:{port}',flush=True);server.serve_forever()
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8344);a=p.parse_args();run(a.port)
