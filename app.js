const $ = (s) => document.querySelector(s);
let meeting = null, items = [], meetings = [], toastTimer;

async function api(path, method = 'GET', body) {
  const options = { method, headers: { 'X-Local-Action': TOKEN_PLACEHOLDER } };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (!response.ok) throw new Error((await response.json()).error || 'Request failed.');
  return response.status === 204 ? null : response.json();
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function flash(message) {
  const toast = $('#toast'); toast.textContent = message; toast.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 2400);
}

async function load(id) {
  const data = await api('/api/state' + (id ? '?id=' + encodeURIComponent(id) : ''));
  meeting = data.meeting; items = data.items; meetings = data.meetings; render();
}

function render() {
  const select = $('#meetingSelect');
  select.innerHTML = meetings.map((entry) => `<option value="${esc(entry.id)}" ${meeting && entry.id === meeting.id ? 'selected' : ''}>${esc(entry.title)}</option>`).join('');
  if (!meeting) {
    $('#meetingTitle').textContent = 'No meeting selected';
    $('#transcript').innerHTML = '<p class="small-muted">Import a transcript to begin.</p>';
    $('#items').innerHTML = '<p class="small-muted">No commitments to review.</p>';
    $('#count').textContent = '0 items'; $('#exportBtn').disabled = true;
    return;
  }
  $('#meetingTitle').textContent = meeting.title;
  const turns = meeting.transcript.split('\n').map((line, index) => {
    const match = line.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+([^:]+):\s*(.*)$/);
    return match ? `<div class="turn" id="line-${index + 1}"><span class="time">${esc(match[1])}</span><span class="speaker">${esc(match[2])}</span><p>${esc(match[3])}</p></div>` : `<div class="turn"><span class="time">Line ${index + 1}</span><span class="speaker">Text</span><p>${esc(line)}</p></div>`;
  }).join('');
  $('#transcript').innerHTML = turns || '<p class="small-muted">No transcript text.</p>';
  $('#items').innerHTML = items.map((item, index) => `<article class="item" style="animation-delay:${Math.min(index * 55, 300)}ms">
    <div class="item-head"><span class="kind">${esc(item.kind.toUpperCase())}</span><span class="status ${item.status === 'unresolved' ? 'unresolved' : ''}">${item.status === 'confirmed' ? 'Confirmed' : item.status === 'unresolved' ? 'Needs review' : 'Proposed'}</span></div>
    <p class="item-text">${esc(item.text)}</p><div class="fields">
    <div class="field"><label for="owner-${esc(item.id)}">Owner</label><input id="owner-${esc(item.id)}" value="${esc(item.owner)}" maxlength="80" aria-label="Owner"></div>
    <div class="field"><label for="due-${esc(item.id)}">Due date</label><input id="due-${esc(item.id)}" value="${esc(item.due)}" maxlength="80" aria-label="Due date"></div></div>
    <button class="evidence" data-line="${item.evidence.line}" title="Show source in transcript"><span class="ref">${esc(item.evidence.time)} · ${esc(item.evidence.speaker)}</span><span>${esc(item.evidence.text)}</span></button>
    <div class="actions"><button class="confirm" data-id="${esc(item.id)}" ${item.status === 'unresolved' ? 'disabled' : ''}>Confirm</button><button class="edit" data-id="${esc(item.id)}">Save edits</button><button class="leave" data-id="${esc(item.id)}">Leave unresolved</button></div>
    <p class="small-muted" style="margin:10px 0 0">${esc(item.reason)}</p></article>`).join('') || '<p class="small-muted">No commitment proposals found. Import a transcript with speaker and time references.</p>';
  $('#count').textContent = `${items.length} ${items.length === 1 ? 'item' : 'items'}`;
  $('#exportBtn').disabled = !items.some((item) => item.status === 'confirmed');
}

async function patchItem(item, changes) { await api(`/api/items/${encodeURIComponent(item.id)}`, 'PATCH', changes); await load(meeting.id); }
async function saveItem(item, status) {
  await patchItem(item, { owner: $(`#owner-${CSS.escape(item.id)}`).value.trim(), due: $(`#due-${CSS.escape(item.id)}`).value.trim(), status, resolved: true });
}

$('#meetingSelect').addEventListener('change', (event) => load(event.target.value).catch((error) => flash(error.message)));
$('#items').addEventListener('click', async (event) => {
  const evidence = event.target.closest('.evidence');
  if (evidence) {
    const row = document.querySelector(`#line-${CSS.escape(evidence.dataset.line)}`);
    row?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' });
    row?.classList.add('highlight'); setTimeout(() => row?.classList.remove('highlight'), 1700); return;
  }
  const id = event.target.dataset.id; if (!id) return;
  const item = items.find((entry) => entry.id === id); if (!item) return;
  if (event.target.classList.contains('confirm')) { await saveItem(item, 'confirmed'); flash('Commitment confirmed.'); }
  else if (event.target.classList.contains('edit')) {
    await patchItem(item, { owner: $(`#owner-${CSS.escape(id)}`).value.trim(), due: $(`#due-${CSS.escape(id)}`).value.trim(), status: 'proposed', resolved: true });
    flash('Edits saved. Confirm when ready.');
  } else if (event.target.classList.contains('leave')) { await saveItem(item, 'unresolved'); flash('Left unresolved.'); }
});

$('#importBtn').onclick = () => $('#importDialog').showModal();
$('#saveMeeting').onclick = async (event) => {
  event.preventDefault(); const title = $('#titleInput').value.trim(), transcript = $('#transcriptInput').value;
  if (!title || !transcript.trim()) { flash('Add a meeting name and transcript.'); return; }
  try { const result = await api('/api/meetings', 'POST', { title, transcript }); $('#importDialog').close(); $('#transcriptInput').value = ''; await load(result.id); flash('Transcript imported. Review each proposal.'); }
  catch (error) { flash(error.message); }
};
$('#editTranscript').onclick = () => { $('#editText').value = meeting?.transcript || ''; $('#editDialog').showModal(); };
$('#saveEdit').onclick = async (event) => {
  event.preventDefault(); try { await api(`/api/meetings/${encodeURIComponent(meeting.id)}`, 'PUT', { transcript: $('#editText').value }); $('#editDialog').close(); await load(meeting.id); flash('Transcript updated. Proposals reset for review.'); }
  catch (error) { flash(error.message); }
};
$('#exportBtn').onclick = async () => {
  try { const data = await api(`/api/meetings/${encodeURIComponent(meeting.id)}/export`); const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }); const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(blob); anchor.download = 'confirmed-meeting-actions.json'; anchor.click(); URL.revokeObjectURL(anchor.href); flash('Confirmed commitments exported.'); }
  catch (error) { flash(error.message); }
};
function settings(on) { $('#room').hidden = on; $('#settings').hidden = !on; $('#settingsTab').classList.toggle('active', on); $('#libraryTab').classList.toggle('active', !on); }
$('#settingsTab').onclick = () => settings(true); $('#libraryTab').onclick = () => settings(false); $('#backBtn').onclick = () => settings(false);
$('#wipeBtn').onclick = async () => { if (!confirm('Delete all meeting transcripts and commitment reviews from this app?')) return; await api('/api/data', 'DELETE'); await load(); settings(false); flash('Local app data deleted.'); };
load().catch((error) => flash('Could not load local data: ' + error.message));
