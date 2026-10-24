import { useEffect, useRef, useState, type FormEvent } from 'react'
import { connect, marketApi } from '../../infra/api'
import type { components } from '../../infra/openapi'
import { Chart } from './Chart'
import './style.css'

type Search = components['schemas']['MarketSearch']
type Draft = components['schemas']['MarketDraft']
type Comparison = components['schemas']['MarketComparison']
type ChartData = components['schemas']['MarketChart']
type Version = components['schemas']['MarketVersion']
type Source = components['schemas']['MarketSource']
type Publish = components['schemas']['MarketResult']
type ImportRecord = components['schemas']['MarketImportRecord']
type Screen = 'search' | 'chart' | 'upload' | 'success'
const message = (error: unknown) => error instanceof Error ? error.message : '请求失败'
const today = () => new Date(Date.now() - new Date().getTimezoneOffset()*60000).toISOString().slice(0,10)
const segments = {
  CN: ['09:30-10:00','10:00-11:30','13:00-15:00'],
  US: ['09:30-10:30','10:30-12:00','12:00-14:00','14:00-16:00'],
}

export function Page() {
  const [screen,setScreen] = useState<Screen>('search')
  const [symbol,setSymbol] = useState('')
  const [exchange,setExchange] = useState('')
  const [market,setMarket] = useState('')
  const [period,setPeriod] = useState('day')
  const [fromDate,setFromDate] = useState(today)
  const [toDate,setToDate] = useState(today)
  const [search,setSearch] = useState<Search|null>(null)
  const [submittedSearch,setSubmittedSearch] = useState('')
  const [chart,setChart] = useState<ChartData|null>(null)
  const [chartReady,setChartReady] = useState(false)
  const [versions,setVersions] = useState<Version[]>([])
  const [dataset,setDataset] = useState('')
  const [version,setVersion] = useState('')
  const [importRecord,setImportRecord] = useState<ImportRecord|null>(null)
  const importRequest = useRef(0)
  const activeImportVersion = useRef('')
  const [file,setFile] = useState<File|null>(null)
  const [draft,setDraft] = useState<Draft|null>(null)
  const [sources,setSources] = useState<Source[]>([])
  const [sourceSelection,setSourceSelection] = useState('new')
  const [provider,setProvider] = useState('')
  const [product,setProduct] = useState('')
  const [priceMode,setPriceMode] = useState('')
  const [adjustment,setAdjustment] = useState('')
  const [referenceDate,setReferenceDate] = useState('')
  const [unit,setUnit] = useState('')
  const [position,setPosition] = useState('')
  const [chosenExchange,setChosenExchange] = useState('')
  const [example,setExample] = useState('')
  const [comparison,setComparison] = useState<Comparison|null>(null)
  const [page,setPage] = useState(1)
  const [published,setPublished] = useState<Publish|null>(null)
  const [notice,setNotice] = useState('')
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const [segment,setSegment] = useState('')
  const [existingIdentity,setExistingIdentity] = useState('')
  const [targetMismatch,setTargetMismatch] = useState(false)

  useEffect(() => { void connect().catch(e => setError(message(e))) }, [])
  async function run(job: () => Promise<void>) {
    setBusy(true); setError('')
    try { await connect(); await job() }
    catch (err) { setError(message(err)) }
    finally { setBusy(false) }
  }
  const rangeEnd = period === 'minute' ? fromDate : toDate
  const inferredMarket = /^\d{6}$/.test(symbol.trim()) || /^[A-Za-z.]{1,8}$/.test(symbol.trim())
  const requestedMarket = inferredMarket ? undefined : market || undefined
  const searchKey = [symbol.trim().toUpperCase(),period,fromDate,rangeEnd,requestedMarket??''].join('|')
  async function doSearch(event?: FormEvent) {
    event?.preventDefault()
    if (fromDate > rangeEnd) { setError('开始日期不能晚于结束日期'); return }
    const query = { symbol:symbol.trim().toUpperCase(), period, fromDate, toDate:rangeEnd, market:requestedMarket, key:searchKey }
    await run(async () => {
      const found = await marketApi.search(query.symbol,query.period,query.fromDate,query.toDate,query.market)
      setSearch(found);setSubmittedSearch(query.key)
      setScreen('search')
    })
  }
  async function openChart(ds: string, id: string, selectedSymbol=symbol, selectedExchange=exchange,
      barPeriod=chart?.period??period, barMarket=chart?.market??market,
      selectedFrom=fromDate, selectedTo=toDate) {
    const options = segments[barMarket==='US'?'US':'CN']
    const selectedSegment = options.includes(segment) ? segment : options[0]
    const [start,end] = selectedSegment.split('-')
    setChartReady(false);setVersion(id);setDataset(ds)
    activeImportVersion.current = id
    if (id!==version) { importRequest.current += 1;setImportRecord(null) }
    setFromDate(selectedFrom);setToDate(selectedTo)
    if (barPeriod==='minute') setSegment(selectedSegment)
    await run(async () => {
      const [data, all] = await Promise.all([
        marketApi.chart(ds,id,selectedSymbol.trim().toUpperCase(),selectedFrom,barPeriod==='minute'?selectedFrom:selectedTo,
          selectedExchange||undefined,barPeriod==='minute'?start:undefined,barPeriod==='minute'?end:undefined),
        marketApi.versions(ds),
      ])
      setChart(data);setVersions(all);setChartReady(true)
      setSymbol(selectedSymbol);setExchange(selectedExchange);setScreen('chart')
    })
  }
  function beginUpload(target='') {
    void marketApi.sources().then(setSources).catch(e=>setError(message(e)))
    const found = search?.results.find(r=>r.dataset_id===target)
    const known = found ?? (chart?.dataset_id===target ? chart : null)
    if (known) {
      setSourceSelection('target');setProvider(known.provider);setProduct(known.product)
      setPriceMode(known.price_mode);setAdjustment(known.adjustment);setReferenceDate(known.reference_date)
    } else {
      setSourceSelection('new');setProvider('');setProduct('');setPriceMode('');setAdjustment('');setReferenceDate('')
    }
    setDataset(target);setScreen('upload');setFile(null);setDraft(null);setComparison(null);setExistingIdentity('')
    setTargetMismatch(false);setExample('');setNotice('');setError('');setUnit('');setPosition('');setChosenExchange('')
  }
  async function chooseFile(selected: File|null) {
    setFile(selected);setDraft(null);setComparison(null);setExistingIdentity('');setTargetMismatch(false);setExample('')
    if (!selected) return
    await run(async () => {
      const staged = await marketApi.stage(selected,dataset||undefined)
      setDraft(staged);setTargetMismatch(staged.target_mismatch)
    })
  }
  useEffect(() => {
    setExample('')
    if (!draft || !unit || (draft.period==='minute'&&!position) || (draft.needs_exchange&&!chosenExchange)) return
    let active=true
    void connect().then(()=>marketApi.preview(draft.draft_id,unit,position||undefined,chosenExchange||undefined))
      .then(r=>{if(active)setExample(r.examples[0]?.market_time||'')})
      .catch(e=>{if(active)setError(message(e))})
    return ()=>{active=false}
  }, [draft,unit,position,chosenExchange])
  const choice = () => ({provider,product,price_mode:priceMode,adjustment,reference_date:referenceDate,
    volume_unit:unit,exchange:chosenExchange||undefined,minute_position:position||undefined,target_dataset_id:dataset||undefined})
  function finish(result: Publish, staged: Draft) {
    if (!result.dataset_id || !result.version_id) return
    setPublished(result);setDataset(result.dataset_id);setVersion(result.version_id);setPeriod(staged.period)
    setFromDate(staged.first.slice(0,10));setToDate(staged.period==='day'?staged.last.slice(0,10):staged.first.slice(0,10))
    setSymbol(result.symbols?.length===1?result.symbols[0].split(':')[1]:'')
    setExchange(result.symbols?.length===1?result.symbols[0].split(':')[0]:'')
    setComparison(null);setScreen('success')
    setNotice(`已生成版本 ${result.version_number}：新增 ${result.added} 条，修正 ${result.changed} 条。`)
  }
  async function publishOnce(confirmation?: string) {
    if (!draft) return
    try {
      const result = await marketApi.publish(draft.draft_id,{...choice(),confirmation})
      if (result.status==='published') finish(result,draft)
      else if (result.status==='changes') {
        setComparison(await marketApi.compare(draft.draft_id,choice(),1));setPage(1)
        setNotice('版本已变化，请重新核对差异。')
      }
      else if (result.status==='unchanged') setNotice('文件内容与当前版本相同，没有生成新版本。')
    } catch (err) {
      try {
        const status = await marketApi.result(draft.draft_id)
        if (status.status==='published') { finish(status,draft);return }
      } catch { /* original error remains actionable */ }
      if (message(err).includes('期间已有新版本')) {
        setComparison(await marketApi.compare(draft.draft_id,choice(),1));setPage(1)
        setNotice('期间已有新版本，已重新比较，请核对后再确认。')
        return
      }
      throw err
    }
  }
  async function check(pageNumber=1) {
    if (!draft || targetMismatch) return
    await run(async () => {
      const compared = await marketApi.compare(draft.draft_id,choice(),pageNumber)
      setComparison(compared);setPage(pageNumber);setNotice('')
      if (compared.status==='unchanged') setNotice('文件内容与当前版本相同，没有生成新版本。')
      if (compared.status==='additions') await publishOnce()
    })
  }
  async function confirm() { await run(()=>publishOnce(comparison?.confirmation??undefined)) }
  const heading = screen==='search'?'查找历史行情':screen==='chart'?'查看行情':screen==='success'?'导入完成':'导入历史行情'
  const exchangeOptions = draft?.market==='CN' ? ['SH','SZ','BJ'] : ['NYSE','NASDAQ','AMEX']
  const existingOptions = [...new Set(draft?.symbols.map(item => item.startsWith('?:') ? `${chosenExchange}:${item.slice(2)}` : item) ?? [])]
  const selectedExisting = existingOptions.length===1 ? existingOptions[0] : existingIdentity
  const chartSegments = segments[chart?.market==='US'?'US':'CN']

  return <main>
    <header className="pageHead"><div><h1>{heading}</h1><p>按股票、周期和日期查找已保存的 A 股或美股行情</p></div><div className="actions">
      {screen!=='search'&&<button onClick={()=>setScreen('search')}>返回查找</button>}
      {screen!=='upload'&&<button className="primary" onClick={()=>beginUpload(screen==='chart'?dataset:'')}>导入文件</button>}
    </div></header>
    {notice&&<div className="message success" role="status">{notice}</div>}
    {error&&<div className="message error" role="alert">{error}</div>}
    {busy&&<p role="status">正在处理…</p>}

    {screen==='search'&&<>
      <section className="card"><form className="marketSearch" onSubmit={doSearch}>
        <label>股票代码<input required value={symbol} onChange={e=>{setSymbol(e.target.value);setSearch(null)}} placeholder="例如 600519 或 AAPL" /></label>
        <label>周期<select value={period} onChange={e=>{setPeriod(e.target.value);setSearch(null)}}><option value="day">日线</option><option value="minute">1 分钟线</option></select></label>
        <label>{period==='day'?'开始日期':'日期'}<input type="date" required value={fromDate} onChange={e=>{setFromDate(e.target.value);setSearch(null)}} /></label>
        {period==='day'&&<label>结束日期<input type="date" required value={toDate} onChange={e=>{setToDate(e.target.value);setSearch(null)}} /></label>}
        {!inferredMarket&&<label>市场<select value={market} onChange={e=>{setMarket(e.target.value);setSearch(null)}}><option value="">请选择</option><option value="CN">A 股</option><option value="US">美股</option></select></label>}
        <button className="primary" disabled={busy}>查找</button>
      </form></section>
      {search&&submittedSearch===searchKey&&<section className="card"><h2>查找结果</h2>
        {search.reason==='choose_market'?<div className="marketEmpty">无法从股票代码确定市场，请选择市场后重新查找。</div>
        :search.reason==='closed_day'?<div className="marketEmpty">所选范围只有周末，请换日期查找。</div>
        :search.reason==='never_imported'?<div className="marketEmpty">尚未导入历史行情。<button onClick={()=>beginUpload()}>导入文件</button></div>
        :search.reason==='no_source'?<div className="marketEmpty">这只股票和周期没有匹配来源。<button onClick={()=>beginUpload()}>导入文件</button></div>
        :<>{search.reason==='no_date'&&<p>所选范围没有保存行情。可以换日期或补充文件。</p>}
          {search.results.map(r=><article className="marketResult" key={r.dataset_id+':'+r.exchange}><div>
            <strong>{r.provider} · {r.product} · {r.exchange}</strong>
            <p>{r.market==='CN'?'A 股':'美股'} · {r.price_mode==='raw'?'未调整价格':'已调整价格'} · 已保存 {r.first} 至 {r.last}</p>
            <p>{r.has_bars?'所选范围有行情':'所选范围无行情'}{r.warning_count>0&&` · ${r.warning_count} 条变化提示`}</p>
          </div>{r.has_bars?<button onClick={()=>void openChart(r.dataset_id,r.version_id,symbol,r.exchange,r.period,r.market)}>查看 K 线</button>:<button onClick={()=>beginUpload(r.dataset_id)}>补充文件</button>}</article>)}
        </>}
      </section>}
    </>}

    {screen==='chart'&&chart&&<><section className="card">
      <div className="row"><h2>{chart.exchange}:{symbol} · {chart.period==='day'?'日线':'1 分钟线'}</h2>
        <label>版本<select value={version} onChange={e=>{void openChart(dataset,e.target.value,symbol,exchange,chart.period,chart.market)}}>{versions.map(v=><option value={v.id} key={v.id}>版本 {v.number}</option>)}</select></label>
      </div><div className="marketSearch">
        <label>{chart.period==='day'?'开始日期':'日期'}<input type="date" value={fromDate} onChange={e=>{setFromDate(e.target.value);setChartReady(false);setError('')}} /></label>
        {chart.period==='day'&&<label>结束日期<input type="date" value={toDate} onChange={e=>{setToDate(e.target.value);setChartReady(false);setError('')}} /></label>}
        {chart.period==='minute'&&<label>时段<select value={chartSegments.includes(segment)?segment:chartSegments[0]} onChange={e=>{setSegment(e.target.value);setChartReady(false);setError('')}}>{chartSegments.map(item=><option value={item} key={item}>{item}</option>)}</select></label>}
        <button disabled={busy} onClick={()=>void openChart(dataset,version,symbol,exchange,chart.period,chart.market)}>{chartReady?'查看':'读取行情'}</button>
      </div>{chartReady?<Chart key={version+fromDate+rangeEnd+segment} bars={chart.bars} warnings={chart.warnings as {key:string;kind:string;message:string}[]}/>:<div className="marketEmpty">{busy?'正在读取…':error?'读取失败，请重试。':'条件已变化，请点击读取行情。'}</div>}
      {chartReady&&chart.warnings.length>0&&<p>此版有 {chart.warnings.length} 条价格或成交量变化提示，点选标记查看。</p>}
    </section><details key={version} className="card" onToggle={e=>{if(e.currentTarget.open&&!importRecord&&version===activeImportVersion.current){const request=++importRequest.current;void marketApi.importRecord(version).then(value=>{if(request===importRequest.current&&version===activeImportVersion.current)setImportRecord(value)}).catch(err=>{if(request===importRequest.current&&version===activeImportVersion.current)setError(message(err))})}}}>
      <summary>导入记录</summary>{importRecord?<><p>{importRecord.provider} · {importRecord.product}</p><p>前一版本：{importRecord.previous_version_id??'无'}</p>
        {importRecord.files.map((item,index)=><p key={index}>{item.file_name} · {item.created_at}</p>)}</>:<p>正在读取…</p>}
    </details></>}

    {screen==='success'&&published&&draft&&<section className="card narrow"><h2>新版已保存</h2>
      <p>新增 {published.added} 条，修正 {published.changed} 条。影响日期：{published.affected_first} 至 {published.affected_last}</p>
      <label>选择要查看的股票<select value={exchange&&symbol?`${exchange}:${symbol}`:''} onChange={e=>{const [nextExchange,nextSymbol]=e.target.value.split(':');setExchange(nextExchange||'');setSymbol(nextSymbol||'')}}>
        <option value="">请选择</option>{published.symbols?.map(item=><option value={item} key={item}>{item}</option>)}
      </select></label><button className="primary" disabled={!symbol} onClick={()=>void openChart(published.dataset_id!,published.version_id!,symbol,exchange,draft.period,draft.market)}>查看新版 K 线</button>
    </section>}

    {screen==='upload'&&<section className="card narrow"><h2>选择 CSV 文件</h2>
      <input type="file" accept=".csv,text/csv" onChange={e=>void chooseFile(e.target.files?.[0]??null)} />
      {file&&!draft&&<p>{busy?`正在识别 ${file.name}`:'文件未通过识别，修正后请重新选择。'}</p>}
      {draft&&<><p>{draft.market==='CN'?'A 股':'美股'} · {draft.period==='day'?'日线':'1 分钟线'} · {draft.count} 行 · {draft.symbols.join('、')}</p>
        <p>文件时间：{draft.first} 至 {draft.last}</p>
        {targetMismatch&&<div className="message error">文件市场或周期与目标数据集不同。文件仍保留，可按文件另行导入。
          <button onClick={()=>{setDataset('');setTargetMismatch(false);setSourceSelection('new');setProvider('');setProduct('');setPriceMode('')}}>按文件另行导入</button>
        </div>}
        <label>数据来源<select value={sourceSelection} disabled={!!dataset} onChange={e=>{const id=e.target.value;setSourceSelection(id);const selected=sources.find(x=>x.id===id);if(selected){setProvider(selected.provider);setProduct(selected.product)}else{setProvider('');setProduct('')}}}>
          <option value="new">新来源</option>{dataset&&<option value="target">沿用目标数据集</option>}{sources.map(src=><option value={src.id} key={src.id}>{src.provider} · {src.product}</option>)}
        </select></label>
        {sourceSelection==='new'?<><label>提供方<input value={provider} onChange={e=>setProvider(e.target.value)} /></label><label>数据产品<input value={product} onChange={e=>setProduct(e.target.value)} /></label></>:<p>{provider} · {product}</p>}
        <label>价格处理<select value={priceMode} onChange={e=>setPriceMode(e.target.value)}><option value="">请选择</option><option value="raw">未调整</option><option value="adjusted">已调整</option></select></label>
        {priceMode==='adjusted'&&<><label>计算方法<input value={adjustment} onChange={e=>setAdjustment(e.target.value)} /></label><label>参照日期<input type="date" value={referenceDate} onChange={e=>setReferenceDate(e.target.value)} /></label></>}
        {draft.needs_exchange&&<label>交易所<select value={chosenExchange} onChange={e=>setChosenExchange(e.target.value)}><option value="">请选择</option>{exchangeOptions.map(item=><option value={item} key={item}>{item}</option>)}</select></label>}
        <label>成交量单位<select value={unit} onChange={e=>setUnit(e.target.value)}><option value="">请选择</option><option value="shares">股</option>{draft.market==='CN'&&<option value="lots100">手（100 股）</option>}</select></label>
        {draft.period==='minute'&&<label>文件时间表示<select value={position} onChange={e=>setPosition(e.target.value)}><option value="">请选择</option><option value="start">这一分钟开始</option><option value="end">这一分钟结束</option></select></label>}
        {draft.period==='minute'&&example&&<p>保存后的市场时间示例：{example.replace('T',' ').slice(0,16)}</p>}
        {comparison?.status==='unchanged'&&comparison.dataset_id&&comparison.version_id&&<>
          {existingOptions.length>1&&<label>选择要查看的股票<select value={existingIdentity} onChange={e=>setExistingIdentity(e.target.value)}><option value="">请选择</option>{existingOptions.map(item=><option value={item} key={item}>{item}</option>)}</select></label>}
          <button disabled={!selectedExisting} onClick={()=>{const [chosen,code]=selectedExisting.split(':');void openChart(comparison.dataset_id!,comparison.version_id!,code,chosen,draft.period,draft.market,draft.first.slice(0,10),draft.last.slice(0,10))}}>查看已有 K 线</button>
        </>}
        {comparison?.status==='changes'&&<><h2>将修正 {comparison.changed} 条旧值</h2><p>新增 {comparison.added} 条；影响日期 {comparison.affected_first} 至 {comparison.affected_last}。</p>
          <table><thead><tr><th>时点</th><th>原开高低收 / 量</th><th>新开高低收 / 量</th></tr></thead><tbody>
            {comparison.differences.map(d=><tr key={d.key}><td>{d.key}</td><td>{[d.old.open,d.old.high,d.old.low,d.old.close,d.old.volume].join(' / ')}</td><td>{[d.new.open,d.new.high,d.new.low,d.new.close,d.new.volume].join(' / ')}</td></tr>)}
          </tbody></table><div className="actions"><button disabled={page<=1||busy} onClick={()=>void check(page-1)}>上一页</button><span>{page} / {comparison.pages}</span><button disabled={page>=comparison.pages||busy} onClick={()=>void check(page+1)}>下一页</button></div>
          <button className="primary" disabled={busy} onClick={()=>void confirm()}>确认修正并生成新版</button>
        </>}
        {comparison?.status==='additions'&&<p>仅新增记录，发布未完成。可重新检查并导入。</p>}
        {comparison?.status!=='unchanged'&&<button disabled={busy||targetMismatch||!provider||!product||!priceMode||!unit||(draft.needs_exchange&&!chosenExchange)||(draft.period==='minute'&&!position)} onClick={()=>void check()}>重新检查并导入</button>}
      </>}
    </section>}
  </main>
}
