import { useState } from 'react'
import type { components } from '../../infra/openapi'
type Bar = components['schemas']['MarketBar']
type Warning = {key: string; kind: string; message: string}
export function Chart({ bars, warnings = [] }: { bars: Bar[], warnings?: Warning[] }) {
  const [selected, setSelected] = useState<number | null>(null)
  if (!bars.length) return <div className="marketEmpty">所选日期或时段没有保存行情。可以换日期，或补充文件。</div>
  const values = bars.flatMap(b => [Number(b.high), Number(b.low)])
  const top = Math.max(...values), bottom = Math.min(...values)
  const span = Math.max(top-bottom, top*0.002, 0.01)
  const volumeMax = Math.max(...bars.map(b => Number(b.volume)), 1)
  const firstMinute = bars[0].time.includes('T') ? new Date(bars[0].time).getTime() : 0
  const firstDay = bars[0].market_time.slice(0,10)
  const businessOffset = (value: string) => {
    const cursor = new Date(`${firstDay}T12:00:00Z`)
    const end = new Date(`${value}T12:00:00Z`)
    let count = 0
    while (cursor < end) { cursor.setUTCDate(cursor.getUTCDate()+1); if (cursor.getUTCDay()!==0 && cursor.getUTCDay()!==6) count++ }
    return count
  }
  const offsets = bars.map(bar => firstMinute ? (new Date(bar.time).getTime()-firstMinute)/60000 : businessOffset(bar.market_time.slice(0,10)))
  const units = offsets[offsets.length-1]+1
  const width = Math.max(720, units*(firstMinute?13:35)+60)
  const x = (i: number) => 35 + offsets[i]*(width-65)/Math.max(units, 1)
  const y = (v: number) => 20+(top-v)/span*230
  const active = bars[Math.min(selected ?? bars.length-1, bars.length-1)]
  const warningFor = (bar: Bar) => warnings.find(w => w.key === `${bar.exchange}:${bar.symbol}|${bar.time}`)
  return <div><div className="marketChartScroll"><svg width={width} height="360" role="img" aria-label="K 线和成交量">
    <line x1="25" x2={width-25} y1="255" y2="255" stroke="#bdd0d8" />
    {bars.map((b,i) => { const up = Number(b.close) >= Number(b.open); const color = up ? '#b4463d' : '#128074'; const px=x(i); const warning=warningFor(b)
      return <g key={`${b.exchange}:${b.symbol}:${b.time}`} onClick={() => setSelected(i)} tabIndex={0} onKeyDown={e => { if (e.key==='Enter') setSelected(i) }} role="button" aria-label={`${b.market_time} 收盘 ${b.close}${warning?'，有数据变化提示':''}`} style={{cursor:'pointer'}}>
        <line x1={px} x2={px} y1={y(Number(b.high))} y2={y(Number(b.low))} stroke={color} />
        <rect x={px-4} y={Math.min(y(Number(b.open)),y(Number(b.close)))} width="8" height={Math.max(2,Math.abs(y(Number(b.close))-y(Number(b.open))))} fill={color} />
        <rect x={px-4} y={330-Number(b.volume)/volumeMax*60} width="8" height={Number(b.volume)/volumeMax*60} fill={color} opacity=".7" />
        {warning&&<circle cx={px} cy="12" r="4" fill="#d48b24" />}
        {selected===i && <circle cx={px} cy={y(Number(b.close))} r="5" fill="#193345" />}
      </g>
    })}
  </svg></div><div className="marketValues"><strong>{firstMinute ? active.market_time.replace('T',' ').slice(0,16) : active.market_time.slice(0,10)} · {active.exchange}:{active.symbol}</strong><span>开 {active.open}　高 {active.high}　低 {active.low}　收 {active.close}　量 {active.volume}</span>{warningFor(active)&&<span className="marketWarning">{warningFor(active)?.message}</span>}</div></div>
}
