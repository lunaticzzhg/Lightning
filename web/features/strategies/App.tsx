import { useEffect, useState, type FormEvent } from 'react'
import { api, connect } from '../../infra/api'
import type { Strategy, StrategyDetail, VersionDetail } from '../../infra/transport'

type Screen = 'list' | 'upload' | 'strategy' | 'version'
const message = (error: unknown) => error instanceof Error ? error.message : '操作失败，请稍后重试'
const paramType: Record<string, string> = { integer: '整数', number: '小数', boolean: '布尔值', string: '文本', enum: '枚举' }

export function App() {
  const [screen, setScreen] = useState<Screen>('list')
  const [items, setItems] = useState<Strategy[]>([])
  const [strategy, setStrategy] = useState<StrategyDetail | null>(null)
  const [version, setVersion] = useState<VersionDetail | null>(null)
  const [uploadFor, setUploadFor] = useState<string | undefined>()
  const [file, setFile] = useState<File | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedVersionId, setSavedVersionId] = useState<string | null>(null)

  async function load<T>(job: () => Promise<T>, onSuccess: (result: T) => void) {
    setError(''); setLoading(true)
    try { onSuccess(await job()) } catch (err) { setError(message(err)) } finally { setLoading(false) }
  }
  async function refreshList() { await load(async () => { await connect(); return api.list() }, data => { setItems(data); setScreen('list') }) }
  async function openStrategy(id: string) { await load(() => api.strategy(id), data => { setStrategy(data); setScreen('strategy') }) }
  async function openVersion(id: string) { await load(() => api.version(id), data => { setVersion(data); if (savedVersionId === id) setNotice(`已导入，未运行验证。生成代码版本 ${data.version.number}。`); setSavedVersionId(null); setScreen('version') }) }
  useEffect(() => { void refreshList() }, [])

  function uploadPage(id?: string) { setUploadFor(id); setFile(null); setSavedVersionId(null); setError(''); setNotice(''); setScreen('upload') }
  async function submitUpload(event: FormEvent) {
    event.preventDefault(); if (!file || saving) return
    setSaving(true); setError(''); setNotice('')
    try {
      await connect()
      const result = await api.upload(file, uploadFor)
      setFile(null)
      try {
        const detail = await api.version(result.id)
        setVersion(detail); setScreen('version')
        setNotice(`已导入，未运行验证。生成代码版本 ${result.number}。`)
      } catch (err) {
        setSavedVersionId(result.id)
        setNotice(`代码版本 ${result.number} 已保存，但详情读取失败。`)
        setError(message(err))
      }
    } catch (err) { setError(message(err)) } finally { setSaving(false) }
  }
  const selected = version?.version
  const params = selected?.manifest.parameters ?? []
  async function downloadVersion(id: string) {
    try {
      const { blob, fileName } = await api.download(id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = fileName; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) { setError(message(err)) }
  }
  const heading = { list: '策略', upload: uploadFor ? '上传新代码版本' : '上传新策略', strategy: strategy?.strategy.name ?? '策略', version: version?.strategy.name ?? '代码版本' }[screen]
  return <div className="layout"><aside><div className="brand">Lightning</div><nav><button className="nav active" onClick={refreshList}>策略</button></nav></aside><main>
    <header className="pageHead"><div><h1>{heading}</h1><p>管理策略及其代码版本</p></div><div className="actions">{screen !== 'list' && <button onClick={refreshList}>返回策略列表</button>}{screen === 'list' && <button className="primary" onClick={() => uploadPage()}>上传新策略</button>}{screen === 'version' && selected && <button className="primary" onClick={() => uploadPage(selected.strategy_id)}>上传新版本</button>}</div></header>
    {notice && <div className="message success" role="status">{notice}{savedVersionId && <> <button onClick={() => openVersion(savedVersionId)}>重试查看版本</button></>}</div>}
    {error && <div className="message error" role="alert">{error} <button onClick={() => screen === 'list' ? refreshList() : setError('')}>{screen === 'list' ? '重试' : '关闭'}</button></div>}
    {loading ? <section className="card muted" role="status">正在加载…</section> : <>
      {screen === 'list' && (items.length ? items.map(item => <article className="card item" key={item.id}><div><h2>{item.name}</h2><p>{item.version_count} 个代码版本 · 最新版本 {item.latest_version}</p></div><button onClick={() => openStrategy(item.id)}>查看策略</button></article>) : <section className="card empty"><h2>还没有策略</h2><p>上传 Python 策略包，创建第一个策略和代码版本。</p><button className="primary" onClick={() => uploadPage()}>上传新策略</button></section>)}
      {screen === 'upload' && <section className="card narrow"><p className="muted">{uploadFor ? `归属：${strategy?.strategy.name ?? version?.strategy.name ?? ''} · ${uploadFor}` : '上传后创建策略及首个代码版本'}</p><form onSubmit={submitUpload}><label htmlFor="zip">Python 策略包（ZIP） <em>*</em></label><input id="zip" type="file" accept=".zip,application/zip" onChange={e => setFile(e.target.files?.[0] ?? null)} /><p className="hint">策略名称及参数定义从包内读取；文件名不决定归属。仅静态检查，不执行代码。</p><div className="actions"><button className="primary" disabled={!file || saving}>{saving ? '上传中…' : '上传并校验'}</button><button type="button" onClick={() => uploadFor ? openStrategy(uploadFor) : refreshList()}>取消</button></div></form></section>}
      {screen === 'strategy' && strategy && <section className="card"><div className="row"><h2>代码版本</h2><button className="primary" onClick={() => uploadPage(strategy.strategy.id)}>上传新版本</button></div>{strategy.versions.length ? strategy.versions.map(v => <button className="versionRow" key={v.id} onClick={() => openVersion(v.id)}><strong>版本 {v.number}</strong><span>{new Date(v.uploaded_at).toLocaleString('zh-CN')} · {v.status}</span></button>) : <p className="muted">暂无版本</p>}</section>}
      {screen === 'version' && selected && <div className="grid"><section className="card"><h2>代码版本</h2>{strategy?.strategy.id === selected.strategy_id ? strategy.versions.map(v => <button className="versionRow" key={v.id} onClick={() => openVersion(v.id)}><strong>版本 {v.number}</strong><span>{new Date(v.uploaded_at).toLocaleString('zh-CN')}</span></button>) : <button onClick={() => openStrategy(selected.strategy_id)}>查看全部版本</button>}</section><section className="card"><div className="row"><h2>版本 {selected.number}</h2><span className="pill">{selected.status}</span></div><dl><dt>所属策略</dt><dd>{version?.strategy.name} · {selected.strategy_id}</dd><dt>上传时间</dt><dd>{new Date(selected.uploaded_at).toLocaleString('zh-CN')}</dd><dt>原始代码包</dt><dd>{selected.file_name}</dd><dt>文件校验值</dt><dd>{selected.sha256}</dd></dl><hr/><h2>参数定义</h2>{params.length ? params.map(p => <div className="param" key={p.name}><strong>{p.name}</strong><span>{paramType[p.type] ?? p.type} · {p.required ? '必填' : '选填'}{Object.hasOwn(p, 'default') ? ` · 默认 ${String(p.default)}` : ''}{(p.type === 'integer' || p.type === 'number') && p.min != null ? ` · 最小 ${p.min}` : ''}{(p.type === 'integer' || p.type === 'number') && p.max != null ? ` · 最大 ${p.max}` : ''}{p.type === 'enum' ? ` · 选项 ${p.options.join('、')}` : ''}</span></div>) : <p className="muted">该版本没有可调整参数。</p>}<hr/><button className="download" onClick={() => void downloadVersion(selected.id)}>下载原始包</button></section></div>}
    </>}
  </main></div>
}
