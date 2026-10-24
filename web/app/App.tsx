import { useState } from 'react'
import { App as Strategies } from '../features/strategies/App'
import { Page as Data } from '../features/data/Page'

export function App() {
  const [section, setSection] = useState<'strategies' | 'data'>('strategies')
  return <div className="layout"><aside><div className="brand">Lightning</div><nav>
    <button className={`nav ${section === 'strategies' ? 'active' : ''}`} onClick={() => setSection('strategies')}>策略</button>
    <button className={`nav ${section === 'data' ? 'active' : ''}`} onClick={() => setSection('data')}>历史数据</button>
  </nav></aside>{section === 'strategies' ? <Strategies /> : <Data />}</div>
}
