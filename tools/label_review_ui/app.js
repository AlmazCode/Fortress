const $ = id => document.getElementById(id);
const state = { frames: [], videos: [], questions: [], answers: {}, revision: 0, page: 0, selected: new Set(), focus: null, busy: false, nav: [] };
const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const q = () => state.questions.find(v => v.id === $('question').value);
const size = () => Number($('size').value);
const answer = (id, question = q().id) => state.answers[id]?.[question];
const time = n => `${Math.floor(n / 60)}:${(n % 60).toFixed(1).padStart(4, '0')}`;
function filtered() { return state.frames.filter(f => (!$('video').value || f.video_id === $('video').value) && ($('filter').value === 'all' || ($('filter').value === 'answered') === !!answer(f.id))); }
function visible() { return filtered().slice(state.page * size(), (state.page + 1) * size()); }
function status(text, error = false) { $('save-status').textContent = text; $('save-status').classList.toggle('error', error); }
function message(text = '') { $('message').textContent = text; $('message').hidden = !text; }
function choicesHTML(id) { return q().choices.map(([value, label], n) => `<button data-answer="${esc(value)}" ${id ? `data-frame="${esc(id)}"` : ''} class="${id && answer(id)?.value === value ? 'answer' : ''}"><kbd>${n + 1}</kbd>${esc(label)}</button>`).join(''); }
function card(frame) {
  const a = answer(frame.id); const label = q().choices.find(v => v[0] === a?.value)?.[1];
  return `<article class="card ${state.focus === frame.id ? 'focused' : ''} ${state.selected.has(frame.id) ? 'selected' : ''} ${a ? 'answered' : ''}" data-id="${esc(frame.id)}"><div class="card-top"><label><input type="checkbox" data-select="${esc(frame.id)}" ${state.selected.has(frame.id) ? 'checked' : ''} aria-label="Выбрать кадр ${esc(frame.video_id)} ${frame.timestamp_sec}"></label><b>${time(frame.timestamp_sec)}</b><span>${esc(frame.video_id.replace('video_', 'Видео '))}</span></div><button class="image-button" data-zoom="${esc(frame.id)}" aria-label="Увеличить кадр ${esc(frame.video_id)} ${frame.timestamp_sec}"><img src="/api/frame/${encodeURIComponent(frame.id)}" alt="Исходный кадр в ${frame.timestamp_sec} с" loading="lazy"></button>${a ? '<div class="card-badge">Сохранено</div>' : ''}<div class="card-footer"><div class="card-status"><span>${a ? esc(label) : 'Без ответа'}</span><button class="context-small" data-context="${esc(frame.id)}">▶ Контекст</button></div><div class="choices">${choicesHTML(frame.id)}</div></div></article>`;
}
function refreshSelection() {
  document.querySelectorAll('.card').forEach(el => { el.classList.toggle('selected', state.selected.has(el.dataset.id)); el.classList.toggle('focused', state.focus === el.dataset.id); el.querySelector('input').checked = state.selected.has(el.dataset.id); });
  const rows = visible(); $('select-all').checked = !!rows.length && rows.every(f => state.selected.has(f.id));
  $('select-all').indeterminate = !!state.selected.size && !$('select-all').checked;
  $('selected-count').textContent = state.selected.size ? `Выделено ${state.selected.size}` : 'Активный кадр';
}
function render() {
  const rows = filtered(); state.page = Math.max(0, Math.min(state.page, Math.max(0, Math.ceil(rows.length / size()) - 1)));
  const page = visible(); const ids = new Set(page.map(f => f.id)); state.selected = new Set([...state.selected].filter(id => ids.has(id)));
  if (!ids.has(state.focus)) state.focus = page[0]?.id ?? null;
  $('question-title').textContent = q().title; $('question-help').textContent = q().help;
  const scope = state.frames.filter(f => !$('video').value || f.video_id === $('video').value); const done = scope.filter(f => answer(f.id)).length;
  $('progress-text').textContent = `${done} / ${scope.length}`; $('progress').max = Math.max(1, scope.length); $('progress').value = done;
  $('overall-progress').textContent = `Всего ответов: ${Object.values(state.answers).reduce((n, a) => n + Object.keys(a).length, 0)}`;
  $('bulk-choices').innerHTML = choicesHTML(); $('grid').innerHTML = page.map(card).join(''); $('empty').hidden = !!rows.length;
  $('page-info').textContent = rows.length ? `Кадры ${state.page * size() + 1}–${Math.min(rows.length, (state.page + 1) * size())} из ${rows.length}` : 'Нет кадров';
  $('previous').disabled = !state.page; $('next').disabled = (state.page + 1) * size() >= rows.length;
  refreshSelection(); if ($('zoom').open) updateZoom();
  try { localStorage.setItem('fortress-review-position', JSON.stringify({ question: q().id, video: $('video').value, filter: $('filter').value, size: $('size').value, page: state.page, focus: state.focus })); } catch {}
}
async function api(path, payload) {
  const response = await fetch(path, payload ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {});
  if (!response.ok) { const r = await response.json().catch(() => ({})); throw new Error(r.detail ?? `HTTP ${response.status}`); }
  return response.json();
}
function setSnapshot(snapshot) { state.answers = snapshot.answers; state.revision = snapshot.revision; }
async function apply(value, frameId) {
  if (state.busy) return;
  const ids = frameId ? [frameId] : state.selected.size ? [...state.selected] : state.focus ? [state.focus] : [];
  if (!ids.length) return;
  if (ids.some(id => { const image = document.querySelector(`.card[data-id="${id}"] img`); return !image?.complete || !image.naturalWidth; })) { message('Дождитесь загрузки выбранных кадров.'); return; }
  state.busy = true; status('Сохраняем…'); message();
  const position = { page: state.page, video: $('video').value, question: q().id, filter: $('filter').value, focus: state.focus };
  const oldRows = filtered(); const last = Math.max(...ids.map(id => oldRows.findIndex(f => f.id === id))); const nextId = oldRows[last + 1]?.id;
  try {
    setSnapshot(await api('/api/answers', { revision: state.revision, changes: ids.map(id => ({ frame_id: id, question: position.question, value })) }));
    state.nav.push(position); state.selected.clear();
    if ($('auto-next').checked && nextId) { const rows = filtered(); const next = rows.findIndex(f => f.id === nextId); if (next >= 0) { state.focus = nextId; state.page = Math.floor(next / size()); } }
    status('✓ Сохранено на ПК'); render();
  } catch (error) { status('Не сохранено', true); message(`${error.message} Ваш последний выбор не записан. Повторите после проверки соединения.`); }
  finally { state.busy = false; }
}
function move(delta) {
  const rows = filtered(); const index = rows.findIndex(f => f.id === state.focus); const next = rows[Math.max(0, Math.min(rows.length - 1, index + delta))];
  if (!next) return; const oldPage = state.page; state.focus = next.id; state.page = Math.floor(rows.indexOf(next) / size());
  if (oldPage !== state.page) { state.selected.clear(); render(); } else { refreshSelection(); if ($('zoom').open) updateZoom(); }
}
function changePage(delta) { state.page += delta; state.focus = null; state.selected.clear(); render(); window.scrollTo({ top: 0, behavior: 'instant' }); }
function selectPage() { const rows = visible(); const all = rows.every(f => state.selected.has(f.id)); state.selected = all ? new Set() : new Set(rows.map(f => f.id)); refreshSelection(); }
async function undo() {
  if (state.busy) return; state.busy = true; status('Отменяем…');
  try { setSnapshot(await api('/api/undo', { revision: state.revision })); const nav = state.nav.pop(); if (nav) { $('video').value = nav.video; $('question').value = nav.question; $('filter').value = nav.filter; state.page = nav.page; state.focus = nav.focus; } state.selected.clear(); status('✓ Последний ответ отменён'); render(); }
  catch (error) { message(error.message); status('Отмена не выполнена', true); }
  finally { state.busy = false; }
}
function updateZoom() {
  const f = state.frames.find(f => f.id === state.focus); if (!f) return;
  $('zoom-title').textContent = `${f.video_id.replace('video_', 'Видео ')} · исходное время ${time(f.timestamp_sec)} · ${q().title}`;
  $('zoom-image').src = `/api/frame/${encodeURIComponent(f.id)}`; $('zoom-choices').innerHTML = choicesHTML(f.id);
  $('video-panel').hidden = true; $('context-video').pause(); $('context-video').removeAttribute('src');
}
function zoom(id, context = false) { state.focus = id; state.selected.clear(); refreshSelection(); updateZoom(); if (!$('zoom').open) $('zoom').showModal(); if (context) showContext(); }
function showContext() {
  const f = state.frames.find(f => f.id === state.focus); if (!f) return;
  const video = $('context-video'); const start = Math.max(0, f.timestamp_sec - 2.5);
  $('video-panel').hidden = false; $('source-clock').textContent = 'Готовим 5 секунд контекста…'; video.src = `/api/context/${encodeURIComponent(f.id)}`;
  video.ontimeupdate = () => { $('source-clock').textContent = `Исходное время ≈ ${time(start + video.currentTime)} · выбран кадр ${time(f.timestamp_sec)}`; };
  video.onerror = () => { $('source-clock').textContent = 'Не удалось открыть контекст. Можно продолжать по полному кадру.'; };
  video.play().catch(() => {});
}
document.addEventListener('click', event => {
  const answerButton = event.target.closest('[data-answer]'); if (answerButton) { apply(answerButton.dataset.answer, answerButton.dataset.frame); return; }
  const z = event.target.closest('[data-zoom]'); if (z) { zoom(z.dataset.zoom); return; }
  const c = event.target.closest('[data-context]'); if (c) { zoom(c.dataset.context, true); return; }
  const card = event.target.closest('.card'); if (card) { state.focus = card.dataset.id; refreshSelection(); }
});
$('grid').addEventListener('change', event => { if (event.target.dataset.select) { const id = event.target.dataset.select; if (event.target.checked) state.selected.add(id); else state.selected.delete(id); state.focus = id; refreshSelection(); } });
for (const id of ['question', 'video', 'filter', 'size']) $(id).addEventListener('change', () => { state.page = 0; state.focus = null; state.selected.clear(); render(); });
$('select-all').onclick = selectPage; $('previous').onclick = () => changePage(-1); $('next').onclick = () => changePage(1); $('undo').onclick = undo;
$('first-unanswered').onclick = () => { const rows = filtered(); const n = rows.findIndex(f => !answer(f.id)); if (n < 0) { message('В этом наборе все кадры уже имеют ответ.'); return; } state.page = Math.floor(n / size()); state.focus = rows[n].id; state.selected.clear(); render(); };
$('close-zoom').onclick = () => $('zoom').close(); $('zoom').onclose = () => $('context-video').pause(); $('context').onclick = showContext; $('zoom-previous').onclick = () => move(-1); $('zoom-next').onclick = () => move(1);
document.addEventListener('keydown', event => {
  if (event.repeat || ['SELECT', 'TEXTAREA'].includes(event.target.tagName) || (event.target.tagName === 'INPUT' && event.target.type !== 'checkbox')) return;
  if (event.target.tagName === 'INPUT' && event.code === 'Space') return;
  if ((event.ctrlKey || event.metaKey) && event.code === 'KeyZ') { event.preventDefault(); undo(); return; }
  if (event.ctrlKey || event.metaKey || event.altKey || !state.questions.length) return;
  if (/^[1-4]$/.test(event.key)) { const option = q().choices[Number(event.key) - 1]; if (option) { event.preventDefault(); apply(option[0]); } }
  else if (event.code === 'ArrowRight') { event.preventDefault(); move(1); }
  else if (event.code === 'ArrowLeft') { event.preventDefault(); move(-1); }
  else if (event.code === 'KeyA' && !$('zoom').open) { event.preventDefault(); selectPage(); }
  else if (event.code === 'Space' && !$('zoom').open) { event.preventDefault(); if (state.selected.has(state.focus)) state.selected.delete(state.focus); else if (state.focus) state.selected.add(state.focus); refreshSelection(); }
  else if (event.code === 'Enter' && state.focus && !$('zoom').open) { event.preventDefault(); zoom(state.focus); }
  else if (event.code === 'KeyV' && state.focus) { event.preventDefault(); zoom(state.focus, true); }
  else if (event.code === 'KeyN') { event.preventDefault(); $('first-unanswered').click(); }
  else if (event.code === 'PageDown' && !$('next').disabled) { event.preventDefault(); changePage(1); }
  else if (event.code === 'PageUp' && !$('previous').disabled) { event.preventDefault(); changePage(-1); }
});
try {
  let previous = null; try { previous = JSON.parse(localStorage.getItem('fortress-review-position') ?? 'null'); } catch {}
  const data = await api('/api/session'); Object.assign(state, data); state.selected = new Set();
  $('question').innerHTML = data.questions.map(q => `<option value="${esc(q.id)}">${esc(q.title)}</option>`).join('');
  $('video').innerHTML = `<option value="">Все видео · ${data.videos.length}</option>` + data.videos.map(v => `<option value="${esc(v.id)}">${esc(v.id.replace('video_', 'Видео '))} · ${time(v.duration_sec)}</option>`).join('');
  $('video').value = data.videos[0]?.id ?? '';
  if (previous) { for (const id of ['question', 'video', 'filter', 'size']) if ([...$(id).options].some(o => o.value === previous[id])) $(id).value = previous[id]; state.page = previous.page ?? 0; state.focus = previous.focus ?? null; }
  status('✓ Автосохранение включено'); render();
} catch (error) { status('Ошибка подключения', true); message(error.message); }
