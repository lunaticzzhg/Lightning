import { useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { components } from '../../infra/openapi'

type Bar = components['schemas']['MarketBar']
type Warning = { key: string; kind: string; message: string }
type Slot = { key: string; label: string; bar?: Bar }
type Range = { start: number; count: number }
type Drag = Range & { mode: 'move' | 'start' | 'end'; x: number; width: number; total: number; min: number; max: number }

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value))
const minuteLabel = (value: number) => `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`

function chartSlots(bars: Bar[]): Slot[] {
  if (!bars.length) return []
  if (!bars[0].time.includes('T')) return bars.map(bar => ({ key: bar.market_time.slice(0, 10), label: bar.market_time.slice(5, 10), bar }))
  const byMinute = new Map(bars.map(bar => [bar.market_time.slice(0, 16), bar]))
  const first = bars[0].market_time.slice(0, 16)
  const last = bars[bars.length - 1].market_time.slice(0, 16)
  const date = first.slice(0, 10)
  const minuteOf = (value: string) => Number(value.slice(11, 13)) * 60 + Number(value.slice(14, 16))
  const start = minuteOf(first), end = minuteOf(last)
  if (date !== last.slice(0, 10) || end < start || end - start > 390) {
    return bars.map(bar => ({ key: bar.market_time.slice(0, 16), label: bar.market_time.slice(11, 16), bar }))
  }
  return Array.from({ length: end - start + 1 }, (_, offset) => {
    const label = minuteLabel(start + offset)
    const key = `${date}T${label}`
    return { key, label, bar: byMinute.get(key) }
  })
}

export function Chart({ bars, market, warnings = [] }: { bars: Bar[]; market: string; warnings?: Warning[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<Drag | null>(null)
  const [width, setWidth] = useState(720)
  const [range, setRange] = useState<Range | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const slots = useMemo(() => chartSlots(bars), [bars])
  const warningByKey = useMemo(() => new Map(warnings.map(item => [item.key, item])), [warnings])

  useLayoutEffect(() => {
    const element = containerRef.current
    if (!element) return
    const measure = () => setWidth(Math.max(320, element.clientWidth))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [bars.length > 0])

  if (!bars.length) return <div className="marketEmpty">所选日期或时段没有保存行情。可以换日期，或补充文件。</div>

  const maxVisible = clamp(Math.floor((width - 82) / 12), 12, 60)
  const minVisible = Math.min(8, slots.length)
  const count = clamp(range?.count ?? maxVisible, minVisible, Math.min(maxVisible, slots.length))
  const start = clamp(range?.start ?? slots.length - count, 0, slots.length - count)
  const visible = slots.slice(start, start + count)
  const visibleKeys = new Set(visible.map(slot => slot.key))
  const defaultSlot = [...visible].reverse().find(slot => slot.bar)?.key ?? visible[visible.length - 1].key
  const activeKey = selected && visibleKeys.has(selected) ? selected : hovered && visibleKeys.has(hovered) ? hovered : defaultSlot
  const activeSlot = visible.find(slot => slot.key === activeKey)!
  const activeBar = activeSlot.bar
  const activeWarning = activeBar && warningByKey.get(`${activeBar.exchange}:${activeBar.symbol}|${activeBar.time}`)
  const chartBars = visible.flatMap(slot => slot.bar ? [slot.bar] : [])
  const prices = chartBars.flatMap(bar => [Number(bar.high), Number(bar.low)])
  const high = prices.length ? Math.max(...prices) : 1
  const low = prices.length ? Math.min(...prices) : 0
  const padding = Math.max((high - low) * 0.12, high * 0.004, 0.01)
  const top = high + padding, bottom = low - padding
  const volumeMax = Math.max(1, ...chartBars.map(bar => Number(bar.volume)))
  const left = 58, right = width - 22, step = (right - left) / visible.length
  const priceY = (value: number) => 32 + (top - value) / (top - bottom) * 195
  const volumeY = (value: number) => 310 - value / volumeMax * 60
  const up = market === 'US' ? '#188b68' : '#cf5546'
  const down = market === 'US' ? '#cf5546' : '#188b68'
  const activeX = left + step * (visible.findIndex(slot => slot.key === activeKey) + 0.5)
  const showRange = slots.length > maxVisible
  const hasOtherWarnings = warnings.some(item => item.key !== (activeBar ? `${activeBar.exchange}:${activeBar.symbol}|${activeBar.time}` : ''))

  const changeRange = (next: Range) => {
    const nextCount = clamp(next.count, minVisible, Math.min(maxVisible, slots.length))
    const nextStart = clamp(next.start, 0, slots.length - nextCount)
    setRange({ start: nextStart, count: nextCount })
    if (selected && !slots.slice(nextStart, nextStart + nextCount).some(slot => slot.key === selected)) setSelected(null)
    setHovered(null)
  }
  const beginDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !trackRef.current) return
    const target = event.target as HTMLElement
    const handle = target.closest('.marketRangeHandle')
    const window = target.closest('.marketRangeWindow')
    const mode = handle?.classList.contains('start') ? 'start' : handle ? 'end' : window ? 'move' : null
    event.preventDefault()
    const focusTarget = (handle ?? window) as HTMLElement | null
    focusTarget?.focus()
    if (!mode) {
      const position = (event.clientX - trackRef.current.getBoundingClientRect().left) / trackRef.current.clientWidth
      changeRange({ start: Math.round(position * slots.length - count / 2), count })
      return
    }
    dragRef.current = { mode, x: event.clientX, width: trackRef.current.clientWidth, total: slots.length, min: minVisible, max: maxVisible, start, count }
    trackRef.current.setPointerCapture(event.pointerId)
  }
  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const delta = Math.round((event.clientX - drag.x) / drag.width * drag.total)
    if (drag.mode === 'move') changeRange({ start: drag.start + delta, count: drag.count })
    if (drag.mode === 'start') {
      const end = drag.start + drag.count
      const nextStart = clamp(drag.start + delta, Math.max(0, end - drag.max), end - drag.min)
      changeRange({ start: nextStart, count: end - nextStart })
    }
    if (drag.mode === 'end') changeRange({ start: drag.start, count: clamp(drag.count + delta, drag.min, Math.min(drag.max, drag.total - drag.start)) })
  }
  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    dragRef.current = null
    if (trackRef.current?.hasPointerCapture(event.pointerId)) trackRef.current.releasePointerCapture(event.pointerId)
  }
  const rangeKey = (event: KeyboardEvent<HTMLElement>, mode: 'move' | 'start' | 'end') => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    event.stopPropagation()
    const delta = event.key === 'ArrowRight' ? 1 : -1
    if (mode === 'move') changeRange({ start: start + delta, count })
    if (mode === 'start') {
      const end = start + count
      const nextStart = clamp(start + delta, Math.max(0, end - maxVisible), end - minVisible)
      changeRange({ start: nextStart, count: end - nextStart })
    }
    if (mode === 'end') changeRange({ start, count: count + delta })
  }

  return <div ref={containerRef} className="marketChart">
    <div className="marketChartReadout" aria-live="polite"><strong>{activeSlot.key.replace('T', ' ')}</strong>
      {activeBar ? <>开 {activeBar.open}　高 {activeBar.high}　低 {activeBar.low}　收 {activeBar.close}　量 {activeBar.volume}</> : '无行情'}
      {activeWarning && <span className="marketWarning">数据异常提示：{activeWarning.message}</span>}
    </div>
    {hasOtherWarnings && <p className="marketChartWarningSummary">有数据异常提示</p>}
    <div className="marketChartFrame"><svg width={width} height="352" viewBox={`0 0 ${width} 352`} role="img" aria-label="K 线和成交量" onClick={() => { setSelected(null); setHovered(null) }} onPointerLeave={() => setHovered(null)}>
      <text x="12" y="20" className="marketChartAxis">价格</text>
      {[0, 0.5, 1].map(ratio => { const y = 32 + 195 * ratio; return <g key={ratio}><line x1="48" x2={right} y1={y} y2={y} stroke="#e8edef" /><text x="43" y={y + 4} textAnchor="end" className="marketChartAxis">{(top - (top - bottom) * ratio).toFixed(1)}</text></g> })}
      <line x1="48" x2={right} y1="310" y2="310" stroke="#cbd9de" /><text x="12" y="283" className="marketChartAxis">量</text>
      <line x1={activeX} x2={activeX} y1="28" y2="310" stroke="#496c7d" strokeDasharray="4 4" pointerEvents="none" />
      {visible.map((slot, index) => {
        const x = left + step * (index + 0.5), bar = slot.bar
        const selectedNow = slot.key === activeKey
        const showLabel = visible.length <= 12 || index % Math.ceil(visible.length / 10) === 0 || index === visible.length - 1
        const warning = bar && warningByKey.get(`${bar.exchange}:${bar.symbol}|${bar.time}`)
        const label = bar ? `${slot.key.replace('T', ' ')} 开 ${bar.open} 高 ${bar.high} 低 ${bar.low} 收 ${bar.close} 量 ${bar.volume}${warning ? '，有数据异常提示' : ''}` : `${slot.key.replace('T', ' ')} 无行情`
        return <g key={slot.key} role="button" tabIndex={selectedNow ? 0 : -1} aria-label={label} className="marketChartPoint" data-index={index}
          onPointerEnter={() => setHovered(slot.key)} onClick={event => { event.stopPropagation(); setSelected(slot.key); setHovered(null) }}
          onKeyDown={event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected(slot.key); setHovered(null) }
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
              const next = index + (event.key === 'ArrowLeft' ? -1 : 1)
              if (next >= 0 && next < visible.length) {
                event.preventDefault(); setSelected(visible[next].key); setHovered(null)
                containerRef.current?.querySelector<SVGGElement>(`[data-index="${next}"]`)?.focus()
              }
            }
          }}>
          {bar ? (() => {
            const open = Number(bar.open), close = Number(bar.close), color = close >= open ? up : down
            return <>
              <line x1={x} x2={x} y1={priceY(Number(bar.high))} y2={priceY(Number(bar.low))} stroke={color} strokeWidth="2" />
              <rect x={x - Math.min(8, step * 0.28)} y={Math.min(priceY(open), priceY(close))} width={Math.min(16, step * 0.56)} height={Math.max(3, Math.abs(priceY(open) - priceY(close)))} fill={color} stroke={selectedNow ? '#193044' : color} strokeWidth={selectedNow ? 2 : 1} />
              <rect x={x - Math.min(8, step * 0.28)} y={volumeY(Number(bar.volume))} width={Math.min(16, step * 0.56)} height={310 - volumeY(Number(bar.volume))} fill={color} opacity=".68" />
              {warning && <circle cx={x} cy="18" r="5" fill="#df9a36" />}
            </>
          })() : <rect x={x - step * 0.36} y="30" width={step * 0.72} height="280" fill={selectedNow ? '#e7eef1' : '#f8fafb'} stroke="#b8c9d2" strokeDasharray="3 3" />}
          {showLabel && <text x={x} y="338" textAnchor="middle" className="marketChartAxis">{slot.label}</text>}
          <rect x={x - step * 0.36} y="10" width={step * 0.72} height="300" fill="transparent" />
        </g>
      })}
    </svg></div>
    {showRange && <div className="marketChartRange" aria-label="显示范围">
      <div ref={trackRef} className="marketRangeTrack" onPointerDown={beginDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
        <div className="marketRangeWindow" style={{ left: `${start / slots.length * 100}%`, width: `${count / slots.length * 100}%` }} role="slider" tabIndex={0} aria-label="移动显示范围" aria-valuemin={1} aria-valuemax={slots.length - count + 1} aria-valuenow={start + 1} aria-valuetext={`${visible[0].key} 至 ${visible[visible.length - 1].key}`} title="拖动中间看前后行情" onKeyDown={event => rangeKey(event, 'move')}>
          <span className="marketRangeHandle start" role="slider" tabIndex={0} aria-label="调整范围起点" aria-valuemin={1} aria-valuemax={start + count - minVisible + 1} aria-valuenow={start + 1} title="拖动缩放" onKeyDown={event => rangeKey(event, 'start')} />
          <span className="marketRangeHandle end" role="slider" tabIndex={0} aria-label="调整范围终点" aria-valuemin={start + minVisible} aria-valuemax={Math.min(slots.length, start + maxVisible)} aria-valuenow={start + count} title="拖动缩放" onKeyDown={event => rangeKey(event, 'end')} />
        </div>
      </div>
      <div className="marketRangeDates"><span>{slots[0].key.replace('T', ' ')}</span><span>{slots[slots.length - 1].key.replace('T', ' ')}</span></div>
    </div>}
    <p className="marketChartLegend"><i style={{ background: up }} />涨或平 <i style={{ background: down }} />跌 {slots.some(slot => !slot.bar) && <><i className="missing" />无行情 </>}{warnings.length > 0 && <><i style={{ background: '#df9a36' }} />异常提示</>}</p>
  </div>
}
