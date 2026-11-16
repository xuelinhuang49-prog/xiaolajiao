
import { useState } from 'react'
import './App.css'

const welcome = {
  role: 'assistant',
  content: '您好呀！我是小辣椒，您的贴心小伙伴。您想说啥就跟我说，我听着呢！',
}

export default function App() {
  const [messages, setMessages] = useState([welcome])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  async function sendMessage(e) {
    e?.preventDefault()
    const text = input.trim()

    if (!text || loading) return

    const next = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setInput('')
    setLoading(true)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'xiaolajiao',
          messages: next,
          stream: false,
          think: false,
        }),
      })

      if (!response.ok) {
        throw new Error(await response.text())
      }

      const data = await response.json()

      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: data.message?.content || '您慢慢说，我听着呢。',
        },
      ])
    } catch (error) {
      console.error(error)
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: '哎呀，连接暂时出了点问题。请检查 Ollama 是否正常运行。',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="app">
      <header className="header">
        <div className="logo">🌶️</div>
        <div>
          <h1>小辣椒</h1>
          <p>您的贴心 AI 陪伴伙伴</p>
        </div>
        <span className="status">本地 AI</span>
      </header>

      <section className="character">
        <div className="avatar">
          <img
            src="/xiaolajiao.png"
            alt="小辣椒"
            onError={e => {
              e.currentTarget.style.display = 'none'
            }}
          />
          <span className="avatar-fallback">🌶️</span>
        </div>
        <h2>{loading ? '我正在想呢……' : '您好呀！'}</h2>
        <p>您慢慢说，咱不着急，我听着呢。</p>
      </section>

      <section className="chat">
        <div className="messages">
          {messages.map((msg, index) => (
            <div key={index} className={`message ${msg.role}`}>
              <span className="speaker">
                {msg.role === 'assistant' ? '小辣椒' : '您'}
              </span>
              <div>{msg.content}</div>
            </div>
          ))}
          {loading && <div className="loading">小辣椒正在回答……</div>}
        </div>

        <form onSubmit={sendMessage} className="composer">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="在这里输入您想说的话……"
            aria-label="聊天内容"
          />
          <button type="submit" disabled={loading || !input.trim()}>
            {loading ? '请稍候' : '发送'}
          </button>
        </form>
        <p className="tip">目前是文字聊天版，下一步加入语音功能。</p>
      </section>
    </main>
  )
}