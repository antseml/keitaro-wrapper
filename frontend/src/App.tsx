import { useEffect, useId, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api, type Campaign, type Meta, type Offer, type Option, type Stream, type StreamList } from './api'

type View = 'create' | 'edit'

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Не удалось выполнить действие'
}

function OfferPicker({ value, onChange, disabled = false, exclude = [] }: {
  value: Option | null
  onChange: (offer: Option | null) => void
  disabled?: boolean
  exclude?: number[]
}) {
  const id = useId()
  const [query, setQuery] = useState(value ? `${value.id} · ${value.name}` : '')
  const [results, setResults] = useState<Option[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (value) setQuery(`${value.id} · ${value.name}`)
    else if (!open) setQuery('')
  }, [value])

  useEffect(() => {
    if (!open) return
    let current = true
    const timer = window.setTimeout(() => {
      setLoading(true)
      api.offers(value ? '' : query.trim())
        .then(items => { if (current) { setResults(items.filter(item => !exclude.includes(item.id)).slice(0, 40)); setActive(-1) } })
        .catch(() => { if (current) setResults([]) })
        .finally(() => { if (current) setLoading(false) })
    }, 180)
    return () => { current = false; window.clearTimeout(timer) }
  }, [query, open, value, exclude.join(',')])

  function choose(item: Option) {
    onChange(item)
    setQuery(`${item.id} · ${item.name}`)
    setOpen(false)
    setActive(-1)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') { setOpen(false); setActive(-1); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) setOpen(true)
      setActive(index => event.key === 'ArrowDown'
        ? Math.min(index + 1, results.length - 1)
        : Math.max(index - 1, 0))
    }
    if (event.key === 'Enter' && open && active >= 0 && results[active]) {
      event.preventDefault()
      choose(results[active])
    }
  }

  return <div className="offer-picker">
    <label htmlFor={`${id}-input`}>Оффер</label>
    <input id={`${id}-input`} type="search" role="combobox" aria-autocomplete="list"
      aria-expanded={open} aria-controls={`${id}-list`}
      aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined}
      autoComplete="off" placeholder="ID или название" disabled={disabled}
      value={query} onFocus={() => setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 100)}
      onChange={event => { setQuery(event.target.value); onChange(null); setOpen(true) }}
      onKeyDown={onKeyDown} />
    {open && <ul id={`${id}-list`} role="listbox" className="offer-results">
      {loading && <li className="result-message" role="presentation">Поиск офферов</li>}
      {!loading && results.length === 0 && <li className="result-message" role="presentation">Офферы не найдены</li>}
      {!loading && results.map((item, index) =>
        <li key={item.id} id={`${id}-option-${index}`} role="option" aria-selected={index === active}
          className={index === active ? 'active' : ''}
          onMouseDown={event => event.preventDefault()} onClick={() => choose(item)}>
          <span className="mono">#{item.id}</span><span>{item.name}</span>
        </li>)}
    </ul>}
  </div>
}

function Creator({ onCreated }: { onCreated: (campaign: Campaign) => void }) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [name, setName] = useState('')
  const [geo, setGeo] = useState('')
  const [offer, setOffer] = useState<Option | null>(null)
  const [domain, setDomain] = useState('')
  const [group, setGroup] = useState('')
  const [source, setSource] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.meta().then(data => {
      setMeta(data)
      setDomain(String(data.domains[0]?.id ?? ''))
      setGroup(String(data.groups.find(item => item.name === 'FORTESTS')?.id ?? data.groups[0]?.id ?? ''))
      setSource(String(data.sources.find(item => item.name === 'FORTESTS')?.id ?? data.sources[0]?.id ?? ''))
    }).catch(error => setError(errorText(error)))
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!offer) { setError('Выберите оффер из результатов поиска'); return }
    setBusy(true); setError('')
    try {
      const campaign = await api.create({
        name: name.trim(), geo: geo.toUpperCase(), offer_id: offer.id,
        domain_id: Number(domain), group_id: Number(group), source_id: Number(source),
      })
      onCreated(campaign)
    } catch (failure) { setError(errorText(failure)) }
    finally { setBusy(false) }
  }

  return <div className="content">
    <div className="page-heading"><div><p className="eyebrow">Новая кампания</p><h1>Маршрут трафика</h1>
      <p className="subheading">Один адрес для страны, второй для остальных посетителей</p></div></div>
    <div className="create-layout">
      <form className="panel creator" onSubmit={submit}>
        <div className="section-title"><span className="step">01</span><h2>Параметры кампании</h2></div>
        <div className="field"><label htmlFor="campaign-name">Название</label>
          <div className="prefix-field"><span>test_antipov_</span><input id="campaign-name" required maxLength={140}
            value={name} onChange={event => setName(event.target.value.replace(/^test_antipov_/i, ''))} placeholder="campaign1" /></div>
          <small>Префикс добавится автоматически</small></div>
        <div className="field-row"><div className="field"><label htmlFor="geo">Гео-код страны</label>
          <input id="geo" required type="text" inputMode="text" autoComplete="off" maxLength={2}
            pattern="[a-zA-Z]{2}" title="Две латинские буквы, например AU"
            value={geo} onChange={event => setGeo(event.target.value.replace(/[^a-zA-Z]/g, '').toUpperCase())}
            placeholder="AU" /><small>Две латинские буквы</small></div>
          <OfferPicker value={offer} onChange={setOffer} disabled={busy} /></div>
        <div className="field-row assets">
          <div className="field"><label htmlFor="domain">Домен</label><select id="domain" required value={domain} onChange={event => setDomain(event.target.value)} disabled={!meta || busy}>
            <option value="">Выберите домен</option>{meta?.domains.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></div>
          <div className="field"><label htmlFor="group">Группа</label><select id="group" required value={group} onChange={event => setGroup(event.target.value)} disabled={!meta || busy}>
            <option value="">Выберите группу</option>{meta?.groups.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></div>
          <div className="field"><label htmlFor="source">Источник</label><select id="source" required value={source} onChange={event => setSource(event.target.value)} disabled={!meta || busy}>
            <option value="">Выберите источник</option>{meta?.sources.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></div>
        </div>
        {error && <p className="alert" role="alert">{error}</p>}
        <div className="form-footer"><button className="primary" type="submit" disabled={busy || !meta}>{busy ? 'Создание' : 'Создать кампанию'}</button></div>
      </form>
      <aside className="panel route-panel" aria-label="Схема маршрутизации">
        <div className="section-title"><span className="step">02</span><h2>Как пойдёт трафик</h2></div>
        <div className="route"><span className="route-index">1</span><div><span className="route-rule">Страна {geo || 'AU'}</span><strong>Google</strong><small>Прямой редирект</small></div></div>
        <div className="route-connector" aria-hidden="true" />
        <div className="route"><span className="route-index">2</span><div><span className="route-rule">Остальные страны</span><strong>{offer?.name || 'Выбранный оффер'}</strong><small>Доля 100%</small></div></div>
        <p className="route-note">Потоки проверяются по порядку. Посетитель попадает в первый подходящий поток.</p>
      </aside>
    </div>
  </div>
}

function PinControl({ offer, busy, onPin }: { offer: Offer; busy: boolean; onPin: (pinned: boolean, share: number) => Promise<boolean> }) {
  const [share, setShare] = useState(String(offer.share))
  useEffect(() => setShare(String(offer.share)), [offer.share])
  async function save() {
    const value = Number(share)
    if (offer.pinned && Number.isInteger(value) && value >= 0 && value <= 100 && value !== offer.share) {
      const success = await onPin(true, value)
      if (!success) setShare(String(offer.share))
    } else setShare(String(offer.share))
  }
  return <div className="weight-cell">
    <input className="weight-input mono" aria-label={`Доля оффера ${offer.id}, %`} type="number" min={0} max={100} step={1}
      value={share} disabled={!offer.pinned || offer.removed || busy}
      onChange={event => setShare(event.target.value)} onBlur={() => void save()}
      onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); event.currentTarget.blur() } }} />
    <span>%</span><label className="pin-label"><input type="checkbox" checked={offer.pinned} disabled={offer.removed || busy}
      onChange={event => { void onPin(event.target.checked, offer.share) }} /> Закрепить</label>
  </div>
}

function StreamCard({ stream, action, busy }: {
  stream: Stream
  action: (streamId: number, operation: () => Promise<Stream>) => Promise<boolean>
  busy: boolean
}) {
  const [picked, setPicked] = useState<Option | null>(null)
  const active = stream.offers.filter(offer => !offer.removed)
  const excluded = stream.offers.map(offer => offer.id)

  return <section className={`panel stream ${stream.dirty ? 'stream-dirty' : ''}`} aria-label={stream.name}>
    <div className="stream-heading"><div className="stream-title"><span className={`state-dot ${stream.dirty ? 'pending' : ''}`} />
      <div><h2>{stream.name}</h2><span className="stream-meta">ID {stream.id} · {stream.type}</span></div></div>
      <span className={`status ${stream.dirty ? 'pending' : ''}`}>{stream.dirty ? 'Черновик' : 'В Keitaro'}</span></div>
    {stream.editable ? <>
      <div className="table-scroll"><table><thead><tr><th>Оффер</th><th>Доля</th><th>Состояние</th><th><span className="sr-only">Действие</span></th></tr></thead>
        <tbody>{stream.offers.map(offer => <tr key={offer.id} className={offer.removed ? 'removed' : ''}>
          <td><span className="offer-id mono">#{offer.id}</span><span className="offer-name">{offer.name}</span></td>
          <td><PinControl offer={offer} busy={busy} onPin={(pinned, share) =>
            action(stream.id, () => api.pin(stream.id, offer.id, pinned, share))} /></td>
          <td><span className={`offer-state ${offer.removed ? 'archived' : ''}`}>{offer.removed ? 'Удалён' : 'Активен'}</span></td>
          <td className="actions">{offer.removed
            ? <button className="text-button" disabled={busy} onClick={() => void action(stream.id, () => api.restore(stream.id, offer.id))}>Вернуть</button>
            : <button className="text-button danger" disabled={busy || active.length <= 1}
                title={active.length <= 1 ? 'Нельзя удалить последний активный оффер' : undefined}
                onClick={() => void action(stream.id, () => api.remove(stream.id, offer.id))}>Убрать</button>}</td>
        </tr>)}</tbody></table></div>
      <div className="stream-bottom"><div className="add-offer"><OfferPicker value={picked} onChange={setPicked} disabled={busy} exclude={excluded} />
        <button className="secondary" disabled={!picked || busy} onClick={() => {
          if (!picked) return
          void action(stream.id, () => api.add(stream.id, picked.id)).then(success => { if (success) setPicked(null) })
        }}>Добавить</button></div>
        <div className="stream-actions"><button className="secondary" disabled={!stream.dirty || busy}
          onClick={() => void action(stream.id, () => api.cancel(stream.id))}>Отменить</button>
          <button className="primary" disabled={!stream.dirty || busy}
            onClick={() => void action(stream.id, () => api.publish(stream.id))}>Отправить в Keitaro</button></div></div>
    </> : <p className="empty-stream">В потоке нет офферов. Его правила и адрес назначения сохраняются в Keitaro.</p>}
  </section>
}

function Editor({ initialCampaign, onSelect }: { initialCampaign: Campaign | null; onSelect: (campaign: Campaign) => void }) {
  const [query, setQuery] = useState('')
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selected, setSelected] = useState<Campaign | null>(initialCampaign)
  const [streams, setStreams] = useState<Stream[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let current = true
    const timer = window.setTimeout(() => {
      api.campaigns(query).then(items => { if (current) setCampaigns(items) })
        .catch(failure => { if (current) setError(errorText(failure)) })
    }, 200)
    return () => { current = false; window.clearTimeout(timer) }
  }, [query])

  useEffect(() => {
    if (!selected) { setStreams([]); return }
    let current = true
    setStreams([])
    setBusy(true); setError(''); setNotice('')
    api.streams(selected.id).then(data => { if (current) setStreams(data.streams) })
      .catch(failure => { if (current) setError(errorText(failure)) })
      .finally(() => { if (current) setBusy(false) })
    return () => { current = false }
  }, [selected?.id])

  async function sync() {
    if (!selected) return
    setBusy(true); setError(''); setNotice('')
    try { const data: StreamList = await api.sync(selected.id); setStreams(data.streams); setNotice('Потоки обновлены из Keitaro') }
    catch (failure) { setError(errorText(failure)) }
    finally { setBusy(false) }
  }

  async function action(streamId: number, operation: () => Promise<Stream>): Promise<boolean> {
    setBusy(true); setError(''); setNotice('')
    try {
      const next = await operation()
      setStreams(current => current.map(stream => stream.id === streamId ? next : stream))
      if (!next.dirty) setNotice('Поток синхронизирован')
      return true
    } catch (failure) { setError(errorText(failure)); return false }
    finally { setBusy(false) }
  }

  const dirty = streams.filter(stream => stream.dirty).length
  return <div className="content editor-layout">
    <aside className="campaign-sidebar"><div className="sidebar-top"><p className="eyebrow">Редактор</p><h1>Кампании</h1>
      <label className="sr-only" htmlFor="campaign-search">Поиск по названию или ID</label>
      <input id="campaign-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Название или ID" /></div>
      <div className="campaign-list">{campaigns.map(campaign => <button key={campaign.id}
        className={`campaign-item ${campaign.id === selected?.id ? 'selected' : ''}`}
        onClick={() => { setStreams([]); setSelected(campaign); onSelect(campaign) }}>
        <span>{campaign.name}</span><span className="mono">#{campaign.id}</span></button>)}
        {!campaigns.length && <p className="sidebar-empty">Кампании не найдены</p>}</div></aside>
    <main className="workspace"><div className="workspace-header"><div><p className="eyebrow">Потоки и офферы</p>
      <h1>{selected?.name || 'Выберите кампанию'}</h1>
      {selected && <span className="workspace-id mono">ID {selected.id} · {selected.alias}</span>}</div>
      {selected && <button className="secondary" disabled={busy || dirty > 0} title={dirty ? 'Сначала опубликуйте или отмените черновики' : undefined}
        onClick={() => void sync()}>Загрузить потоки</button>}</div>
      {selected?.url && <a className="campaign-url" href={selected.url} target="_blank" rel="noreferrer">{selected.url}</a>}
      {dirty > 0 && <p className="draft-notice" role="status">Не опубликовано потоков: {dirty}. Изменения пока видны только здесь.</p>}
      {notice && <p className="success" role="status">{notice}</p>}
      {error && <p className="alert" role="alert">{error}</p>}
      {!selected && <div className="panel blank-state"><div className="route-symbol">↗</div><h2>Откройте кампанию</h2>
        <p>Выберите кампанию слева, чтобы увидеть её потоки и распределение офферов</p></div>}
      {selected && streams.length === 0 && !busy && <div className="panel blank-state"><h2>Потоки не найдены</h2>
        <p>Загрузите данные из Keitaro или проверьте настройки кампании</p></div>}
      <div className="stream-list">{streams.map(stream => <StreamCard key={stream.id} stream={stream} busy={busy} action={action} />)}</div>
    </main>
  </div>
}

export default function App() {
  const [view, setView] = useState<View>('create')
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  return <div className="app-shell"><header className="app-header"><div className="wordmark"><span className="mark" aria-hidden="true">↗</span><span>Keitaro <span className="wordmark-light">/ Кампании</span></span></div>
    <nav aria-label="Разделы"><button className={view === 'create' ? 'current' : ''} aria-current={view === 'create' ? 'page' : undefined}
      onClick={() => setView('create')}>Создать</button><button className={view === 'edit' ? 'current' : ''}
      aria-current={view === 'edit' ? 'page' : undefined} onClick={() => setView('edit')}>Редактор</button></nav>
    <span className="environment">Тестовый трекер</span></header>
    {view === 'create'
      ? <Creator onCreated={created => { setCampaign(created); setView('edit') }} />
      : <Editor initialCampaign={campaign} onSelect={setCampaign} />}
  </div>
}
