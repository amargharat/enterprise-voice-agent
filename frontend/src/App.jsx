// Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
// Supporting design: enterprise-voice-agent-prd-v1.md (v1), enterprise-voice-agent-journeys-sequence-diagram-v1.md (v1)
// Ticket: none
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
function money(amount) {
  const raw = String(amount ?? '0')
  const [whole = '0', fraction = '00'] = raw.split('.')
  const negative = whole.startsWith('-')
  const digits = whole.replace(/^-/, '')
  const grouped = BigInt(digits || '0').toLocaleString('en-IN')
  return `₹${negative ? '-' : ''}${grouped}.${fraction.padEnd(2, '0').slice(0, 2)}`
}
const formatDate = (date) => new Date(`${date}T00:00:00`).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || 'Something went wrong. Please try again.')
  return body
}

function websocketTurn({ sessionId, message, workflowId, channel, onDelta, onProgress }) {
  const socketUrl = `${API.replace(/^http/, 'ws')}/ws/conversations/${encodeURIComponent(sessionId)}`
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(socketUrl)
    let answer = ''
    let settled = false
    socket.onopen = () => socket.send(JSON.stringify({ type: 'turn', message, workflowId, channel }))
    socket.onmessage = (event) => {
      const frame = JSON.parse(event.data)
      if (frame.type === 'assistant.delta') {
        answer += frame.text
        onDelta?.(frame.text)
      }
      if (frame.type === 'turn.progress') onProgress?.(frame.message)
      if (frame.type === 'error') {
        settled = true
        socket.close()
        reject(new Error(frame.message || 'Conversation session unavailable.'))
      }
      if (frame.type === 'turn.completed') {
        settled = true
        socket.close()
        resolve({ ...frame, answer: answer.trim() })
      }
    }
    socket.onerror = () => {
      if (!settled) reject(new Error('The secure conversation connection closed. Please retry.'))
    }
    socket.onclose = () => {
      if (!settled) reject(new Error('The conversation ended before a response was received.'))
    }
  })
}

const welcome = {
  role: 'assistant',
  text: 'Hello, Aarav. I can explain your loan, check payments, and show how a prepayment could change your interest. Every answer includes the information and policy behind it.',
  suggestions: ['Why did my EMI change? What would ₹50,000 prepaid save?', 'Show my failed payments', 'Am I eligible for foreclosure without a penalty?'],
}

function App() {
  const [sessionId, setSessionId] = useState(localStorage.getItem('horizon-session') || '')
  const [customerId, setCustomerId] = useState(localStorage.getItem('horizon-customer') || '')
  const [workflow, setWorkflow] = useState('loan-servicing')
  const [account, setAccount] = useState(null)
  const [messages, setMessages] = useState([welcome])
  const [input, setInput] = useState('')
  const [otp, setOtp] = useState('246810')
  const [customerEntry, setCustomerEntry] = useState('CU-2291')
  const [loading, setLoading] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  const [progressText, setProgressText] = useState('Checking your account securely…')
  const [metrics, setMetrics] = useState(null)
  const [failureOn, setFailureOn] = useState(false)
  const [voiceMode, setVoiceMode] = useState(false)
  const [serverVoice, setServerVoice] = useState(false)
  const [listening, setListening] = useState(false)
  const [selectedEvidence, setSelectedEvidence] = useState(null)
  const [copied, setCopied] = useState(false)
  const inputRef = useRef(null)
  const recognitionRef = useRef(null)
  const voiceSocketRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const voiceAnswerRef = useRef('')
  const nextAudioMimeRef = useRef('audio/mpeg')
  const serverAudioRef = useRef(false)
  const audioPlaybackRef = useRef([])
  const bottomRef = useRef(null)

  const verified = Boolean(sessionId && customerId)
  const isCard = workflow === 'credit-card'
  const activeAssistant = useMemo(() => [...messages].reverse().find((item) => item.role === 'assistant' && item.evidence?.length), [messages])

  const refreshAccount = useCallback(async (sid = sessionId, wf = workflow) => {
    if (!sid || !localStorage.getItem('horizon-customer')) return
    try {
      const data = await api(`/api/account?sessionId=${encodeURIComponent(sid)}&workflowId=${encodeURIComponent(wf)}`)
      setAccount(data)
    } catch (err) {
      if (err.message.toLowerCase().includes('session')) {
        localStorage.removeItem('horizon-session')
        localStorage.removeItem('horizon-customer')
        setSessionId('')
        setCustomerId('')
        setAccount(null)
      }
    }
  }, [sessionId, workflow])

  const refreshMetrics = useCallback(async () => {
    try { setMetrics(await api('/api/metrics')) } catch { /* dashboard is optional while the API starts */ }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function start() {
      if (sessionId) {
        if (customerId) {
          try {
            await api(`/api/account?sessionId=${encodeURIComponent(sessionId)}&workflowId=${workflow}`)
            if (!cancelled) {
              await refreshAccount(sessionId, workflow)
              await refreshMetrics()
            }
            return
          } catch {
            localStorage.removeItem('horizon-session')
            localStorage.removeItem('horizon-customer')
            if (!cancelled) { setSessionId(''); setCustomerId(''); setAccount(null) }
          }
        } else {
          localStorage.removeItem('horizon-session')
          if (!cancelled) setSessionId('')
        }
      }
      try {
        const result = await api('/api/session/start', { method: 'POST', body: JSON.stringify({ workflowId: workflow }) })
        if (!cancelled) { setSessionId(result.sessionId); localStorage.setItem('horizon-session', result.sessionId) }
      } catch (err) { if (!cancelled) setError(`Could not connect to the local service: ${err.message}`) }
    }
    start()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    api('/api/voice/status').then((status) => setServerVoice(status.serverSttConfigured)).catch(() => setServerVoice(false))
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, loading])
  useEffect(() => { if (verified) refreshAccount(sessionId, workflow) }, [workflow, verified, sessionId, refreshAccount])

  async function verify(event) {
    event.preventDefault()
    setError('')
    setVerifying(true)
    try {
      const result = await api('/api/session/verify', { method: 'POST', body: JSON.stringify({ sessionId, customerId: customerEntry, otp }) })
      setCustomerId(result.customerId)
      localStorage.setItem('horizon-customer', result.customerId)
      setCustomerEntry(result.customerId)
      const data = await api(`/api/account?sessionId=${encodeURIComponent(sessionId)}&workflowId=${workflow}`)
      setAccount(data)
      setMessages([{ ...welcome, text: `Welcome back, ${result.name}. I’m ready to help with your ${isCard ? 'card' : 'loan'} account. Your personal account information stays protected in this demo.` }])
      await refreshMetrics()
    } catch (err) { setError(err.message) }
    finally { setVerifying(false) }
  }

  async function sendMessage(text = input, channel = 'TEXT') {
    const value = text.trim()
    if (!value || loading || !verified) return
    setError('')
    setInput('')
    setProgressText('Preparing your response…')
    setMessages((current) => [...current, { role: 'user', text: value, channel }, { role: 'assistant', text: '', streaming: true, channel }])
    setLoading(true)
    try {
      const result = await websocketTurn({
        sessionId, message: value, workflowId: workflow, channel,
        onDelta: (delta) => setMessages((current) => current.map((item, index) => index === current.length - 1 && item.streaming ? { ...item, text: item.text + delta } : item)),
        onProgress: (message) => setProgressText(message),
      })
      const assistant = { role: 'assistant', text: result.answer, evidence: result.evidence, action: result.action, suggestions: result.suggestions, latencyMs: result.latencyMs, turnId: result.turnId, channel }
      setMessages((current) => current.map((item, index) => index === current.length - 1 && item.streaming ? assistant : item))
      setSelectedEvidence(assistant)
      setProgressText('Checking your account securely…')
      if (channel === 'VOICE' && window.speechSynthesis) {
        window.speechSynthesis.cancel()
        const utterance = new SpeechSynthesisUtterance(result.answer.replace(/[₹]/g, 'rupees '))
        utterance.lang = 'en-IN'
        utterance.rate = 1.02
        window.speechSynthesis.speak(utterance)
      }
      await Promise.all([refreshAccount(sessionId, workflow), refreshMetrics()])
    } catch (err) {
      setError(err.message)
      setProgressText('Checking your account securely…')
      setMessages((current) => current.map((item, index) => index === current.length - 1 && item.streaming ? { ...item, text: `I couldn't complete that request. ${err.message}`, error: true, streaming: false } : item))
    } finally { setLoading(false); inputRef.current?.focus() }
  }

  async function startServerVoice() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('This browser cannot stream microphone audio. Use the browser speech input or type instead.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const socketUrl = `${API.replace(/^http/, 'ws')}/ws/conversations/${encodeURIComponent(sessionId)}`
      let socket = voiceSocketRef.current
      const newSocket = !socket || socket.readyState === WebSocket.CLOSED
      if (newSocket) {
        socket = new WebSocket(socketUrl)
        socket.binaryType = 'arraybuffer'
        voiceSocketRef.current = socket
      }
      mediaRecorderRef.current = recorder
      mediaStreamRef.current = stream
      voiceAnswerRef.current = ''
      serverAudioRef.current = false
      const beginRecording = () => {
        socket.send(JSON.stringify({ type: 'voice.audio.start', mimeType: recorder.mimeType || 'audio/webm', workflowId: workflow }))
        recorder.start(250)
        setListening(true)
        setVoiceMode(true)
      }
      if (newSocket) socket.onopen = beginRecording
      else if (socket.readyState === WebSocket.OPEN) beginRecording()
      recorder.ondataavailable = (event) => {
        if (event.data.size && socket.readyState === WebSocket.OPEN) event.data.arrayBuffer().then((buffer) => socket.send(buffer))
      }
      recorder.onstop = () => {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'voice.audio.end' }))
        stream.getTracks().forEach((track) => track.stop())
        mediaStreamRef.current = null
      }
      if (newSocket) socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          const clip = new Audio(URL.createObjectURL(new Blob([event.data], { type: nextAudioMimeRef.current })))
          serverAudioRef.current = true
          audioPlaybackRef.current.push(clip)
          clip.onended = () => URL.revokeObjectURL(clip.src)
          clip.play().catch(() => setError('Allow audio playback in your browser to hear the assistant.'))
          return
        }
        if (frame.type === 'turn.cancelled') {
          window.speechSynthesis?.cancel()
          audioPlaybackRef.current.forEach((clip) => { clip.pause(); clip.currentTime = 0 })
          audioPlaybackRef.current = []
          setMessages((current) => current.map((item, index) => index === current.length - 1 && item.streaming ? { ...item, text: item.text || 'I stopped that response to handle your interruption.', streaming: false } : item))
        }
        const frame = JSON.parse(event.data)
        if (frame.type === 'voice.audio.chunk') nextAudioMimeRef.current = frame.mimeType || 'audio/mpeg'
        if (frame.type === 'voice.transcript') {
          voiceAnswerRef.current = ''
          setMessages((current) => [...current, { role: 'user', text: frame.text, channel: 'VOICE' }, { role: 'assistant', text: '', streaming: true, channel: 'VOICE' }])
        }
        if (frame.type === 'assistant.delta') {
          voiceAnswerRef.current += frame.text
          setMessages((current) => current.map((item, index) => index === current.length - 1 && item.streaming ? { ...item, text: item.text + frame.text } : item))
        }
        if (frame.type === 'turn.completed') {
          const assistant = { role: 'assistant', text: voiceAnswerRef.current.trim(), evidence: frame.evidence, action: frame.action, suggestions: frame.suggestions, latencyMs: frame.latencyMs, turnId: frame.turnId, channel: 'VOICE' }
          setMessages((current) => current.map((item, index) => index === current.length - 1 && item.streaming ? assistant : item))
          setSelectedEvidence(assistant)
          setProgressText('Checking your account securely…')
          if (!serverAudioRef.current && window.speechSynthesis) {
            const utterance = new SpeechSynthesisUtterance(assistant.text.replace(/[₹]/g, 'rupees '))
            utterance.lang = 'en-IN'
            window.speechSynthesis.speak(utterance)
          }
          refreshAccount(sessionId, workflow)
          refreshMetrics()
          setLoading(false)
        }
        if (frame.type === 'turn.progress') setProgressText(frame.message)
        if (frame.type === 'voice.unavailable' || frame.type === 'voice.error' || frame.type === 'error') setError(frame.message || 'Voice processing is unavailable. You can type your message instead.')
      }
      if (newSocket) socket.onerror = () => setError('The voice connection stopped. You can continue by typing.')
      if (newSocket) socket.onclose = () => {
        setListening(false)
        setLoading(false)
        mediaStreamRef.current?.getTracks().forEach((track) => track.stop())
        if (voiceSocketRef.current === socket) voiceSocketRef.current = null
      }
    } catch (err) {
      setError(err.name === 'NotAllowedError' ? 'Allow microphone access to use voice.' : 'The microphone could not be started. Please try again.')
      setListening(false)
    }
  }

  function toggleVoice() {
    if (serverVoice) {
      if (listening) {
        mediaRecorderRef.current?.stop()
        setListening(false)
        setLoading(true)
      } else {
        startServerVoice()
      }
      return
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setError('Voice input is not available in this browser. Try Chrome or use the text box instead.')
      return
    }
    setError('')
    const recognition = new SpeechRecognition()
    recognition.lang = 'en-IN'
    recognition.interimResults = false
    recognition.continuous = false
    recognition.onstart = () => setListening(true)
    recognition.onend = () => setListening(false)
    recognition.onerror = (event) => { setListening(false); setError(event.error === 'not-allowed' ? 'Allow microphone access to use voice.' : 'Voice input stopped. You can continue by typing.') }
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript
      setInput(transcript)
      setVoiceMode(true)
      sendMessage(transcript, 'VOICE')
    }
    recognitionRef.current = recognition
    try { recognition.start() } catch { setError('The microphone could not be started. Please try again.') }
  }

  async function confirmAction(messageIndex) {
    const item = messages[messageIndex]
    if (!item?.action || item.action.completed) return
    setError('')
    try {
      const result = await api('/api/actions/confirm', { method: 'POST', body: JSON.stringify({ sessionId, token: item.action.token }) })
      const updated = { ...item, action: { ...item.action, completed: true, result } }
      setMessages((current) => current.map((message, index) => index === messageIndex ? updated : message))
      setSelectedEvidence(updated)
      await refreshAccount(sessionId, workflow)
      await refreshMetrics()
    } catch (err) {
      setError(err.message)
      const retryable = /outcome|retry|temporar/i.test(err.message)
      setMessages((current) => current.map((message, index) => index === messageIndex ? { ...message, action: { ...message.action, failed: !retryable, retryable } } : message))
    }
  }

  async function toggleFailure() {
    try {
      const result = await api('/api/demo/failures', { method: 'POST', body: JSON.stringify({ system: 'payments', enabled: !failureOn }) })
      setFailureOn(result.enabled)
      await refreshMetrics()
    } catch (err) { setError(err.message) }
  }

  async function changeWorkflow(value) {
    setWorkflow(value)
    setError('')
    if (verified) {
      setMessages([{ role: 'assistant', text: value === 'credit-card' ? 'The credit-card workflow uses the same verified session, tool gateway, evidence trail, and confirmed-action flow. What would you like to check?' : 'You’re back in personal-loan servicing. What can I help you understand?', suggestions: value === 'credit-card' ? ['Show my statement', 'What is my minimum due?', 'Dispute a card transaction'] : ['Why did my EMI change?', 'Show failed payments'] }])
    }
  }

  async function copyEvidence() {
    const payload = selectedEvidence?.evidence || activeAssistant?.evidence || []
    await navigator.clipboard?.writeText(JSON.stringify(payload, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const evidenceItem = selectedEvidence || activeAssistant

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Horizon home"><span className="brand-mark">h</span><span>horizon<span className="brand-light">/</span></span></a>
        <div className="topbar-center"><span className="crumb-muted">Customer experience</span><span className="crumb-slash">/</span><span>Service studio</span></div>
        <div className="topbar-actions"><span className="sandbox-pill"><span className="green-dot" /> Synthetic data sandbox</span><button className="avatar-button" aria-label="Account profile">{customerId ? customerId.slice(-2) : '—'}</button></div>
      </header>

      <main className="workspace" id="top">
        <section className="page-heading">
          <div><div className="eyebrow"><span className="eyebrow-line" /> CUSTOMER SERVICE · ASSISTANT</div><h1>Good {new Date().getHours() < 12 ? 'morning' : 'afternoon'}{account?.customer?.name ? `, ${account.customer.name.split(' ')[0]}` : ''}.</h1><p>One conversation for the questions that matter.</p></div>
          <label className="workflow-select"><span>WORKFLOW</span><select value={workflow} onChange={(event) => changeWorkflow(event.target.value)} aria-label="Choose servicing workflow"><option value="loan-servicing">Personal loan</option><option value="credit-card">Credit card</option></select><span className="select-chevron">⌄</span></label>
        </section>

        <div className="content-grid">
          <aside className="account-column">
            <section className="panel identity-panel">
              <div className="panel-label-row"><span className="overline">YOUR ACCOUNT</span>{verified && <span className="verified-badge"><span>✓</span> Verified</span>}</div>
              {!verified ? (
                <form className="verify-form" onSubmit={verify}>
                  <div className="verify-icon">⌑</div><h2>Secure sign in</h2><p>Verify your identity to see your synthetic demo account.</p>
                  <label>Customer ID<input value={customerEntry} onChange={(event) => setCustomerEntry(event.target.value)} autoComplete="off" /></label>
                  <label>One-time code<input value={otp} onChange={(event) => setOtp(event.target.value)} inputMode="numeric" autoComplete="one-time-code" /></label>
                  <div className="demo-hint"><span>i</span> Demo IDs: CU-2291 or CU-3140 · code 246810</div>
                  <button className="primary-button full-button" disabled={verifying || !sessionId}>{verifying ? 'Verifying…' : 'Verify and continue'} <span>↗</span></button>
                </form>
              ) : isCard ? <CardSummary account={account} /> : <LoanSummary account={account} />}
            </section>

            {account?.warnings?.length > 0 && <div className="account-warning" role="status">{account.warnings.join(' ')}</div>}
            {verified && <section className="panel payment-panel">
              <div className="panel-label-row"><span className="overline">RECENT ACTIVITY</span><button className="text-button" onClick={() => sendMessage(isCard ? 'Show my statement' : 'Show my failed payments')}>View all <span>↗</span></button></div>
              {account?.recentPayments?.length ? account.recentPayments.slice(0, 3).map((payment) => <div className="activity-row" key={payment.paymentId}><span className={`activity-icon ${payment.status === 'FAILED' ? 'danger' : ''}`}>{payment.status === 'FAILED' ? '!' : '↙'}</span><div className="activity-info"><strong>{payment.status === 'FAILED' ? 'Payment failed' : 'EMI payment'}</strong><small>{formatDate(payment.dueDate || payment.date)} · {payment.paymentId}</small></div><div className="activity-amount"><strong>{money(payment.amount)}</strong><small className={payment.status === 'FAILED' ? 'status-failed' : 'status-paid'}>{payment.status === 'FAILED' ? 'Needs attention' : 'Completed'}</small></div></div>) : <div className="empty-activity">{account?.warnings?.length ? 'Recent activity is temporarily unavailable.' : 'Your recent activity will appear here.'}</div>}
              {account?.requests?.length > 0 && <div className="request-preview"><span className="overline">OPEN REQUEST</span><div><strong>{account.requests[0].reference}</strong><span className="request-status">{account.requests[0].status}</span></div><small>{account.requests[0].summary}</small></div>}
            </section>}
            <div className="privacy-note"><span className="lock-icon">◇</span><p><strong>Your details stay private.</strong><br />This demo uses synthetic customer data. No real financial accounts are connected.</p></div>
          </aside>

          <section className="chat-panel panel" aria-label="Assistant conversation">
            <div className="chat-header"><div className="assistant-avatar"><span>h</span><i /></div><div className="chat-heading-copy"><strong>Horizon assistant</strong><small><span className="green-dot" /> {verified ? 'Online · secure session' : 'Identity verification required'}</small></div><div className="chat-header-right"><span className="channel-pill">{voiceMode ? '◖ Voice ready' : '▤ Text + voice'}</span><button className="icon-button" title="New conversation" onClick={() => setMessages([welcome])}>↻</button></div></div>
            {!verified ? <div className="locked-state"><div className="lock-large">⌑</div><strong>Your assistant is ready when you are.</strong><span>Verify your demo identity to start a secure conversation.</span></div> : <>
              <div className="messages" aria-live="polite">
                <div className="date-divider"><span /> TODAY <span /></div>
                {messages.map((message, index) => <article key={`${index}-${message.turnId || message.text.slice(0, 12)}`} className={`message-row ${message.role}`}>
                  {message.role === 'assistant' && <div className="message-avatar">h</div>}
                  <div className="message-content"><div className={`message-bubble ${message.error ? 'error-bubble' : ''}`}>{message.text.split('\n').map((line, lineIndex) => <span className="message-line" key={lineIndex}>{line || '\u00a0'}</span>)}
                    {message.action && <div className={`confirmation-card ${message.action.completed ? 'confirmed' : ''}`}><div className="confirm-top"><span className="confirm-icon">{message.action.completed ? '✓' : '↗'}</span><div><strong>{message.action.completed ? 'Request submitted' : 'Please confirm this request'}</strong><small>{message.action.completed ? 'A reference has been created for you.' : 'Nothing is sent until you approve below.'}</small></div></div><div className="confirm-summary">{message.action.completed ? <><span>Reference</span><strong>{message.action.result?.reference}</strong><span>Status</span><strong className="open-status">{message.action.result?.status || 'OPEN'}</strong></> : <><span>Action</span><strong>{message.action.summary}</strong><span>Expires</span><strong>In 5 minutes</strong></>}</div>{!message.action.completed && <button className="confirm-button" disabled={message.action.failed} onClick={() => confirmAction(index)}>{message.action.failed ? 'Confirmation unavailable' : message.action.retryable ? 'Retry confirmation' : 'Confirm request'} <span>→</span></button>}{message.action.completed && <div className="success-footnote">✓ Confirmed · Your reference is saved to recent requests</div>}</div>}
                  </div>
                  </div>
                  <div className="message-meta">{message.role === 'user' ? <><span>{message.channel === 'VOICE' ? '◖ Voice' : 'You'}</span></> : <><span>{message.latencyMs ? `${message.latencyMs} ms` : 'Horizon'}</span>{message.evidence?.length > 0 && <button className="evidence-link" onClick={() => setSelectedEvidence(message)}>◈ Evidence</button>}</>}</div>
                  {message.suggestions?.length > 0 && index === messages.length - 1 && <div className="suggestions">{message.suggestions.map((suggestion) => <button key={suggestion} onClick={() => sendMessage(suggestion)}>{suggestion}<span>↗</span></button>)}</div>}
                </article>)}
                {loading && <div className="typing-row"><div className="message-avatar">h</div><div className="typing-bubble"><i /><i /><i /><span>{progressText}</span></div></div>}
                <div ref={bottomRef} />
              </div>
              {error && <div className="inline-error" role="alert"><span>!</span>{error}<button onClick={() => setError('')} aria-label="Dismiss">×</button></div>}
              <div className="composer-wrap"><form className={`composer ${listening ? 'is-listening' : ''}`} onSubmit={(event) => { event.preventDefault(); sendMessage() }}><input ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} placeholder={listening ? 'Listening… speak naturally' : `Ask about your ${isCard ? 'card' : 'loan'}…`} aria-label="Message Horizon assistant" disabled={loading} /><button type="button" className={`mic-button ${listening ? 'active' : ''}`} onClick={toggleVoice} title={listening ? 'Stop listening' : 'Speak a message'} aria-label={listening ? 'Stop voice input' : 'Start voice input'}>{listening ? '■' : '◖'}</button><button type="submit" className="send-button" disabled={!input.trim() || loading} aria-label="Send message">↑</button></form><div className="composer-foot"><span>AI can make mistakes. Check important details before acting.</span><span className="secure-caption"><span className="tiny-lock">◇</span> Secure conversation</span></div></div>
            </>}
          </section>

          <aside className="insight-column">
            <section className="panel evidence-panel"><div className="panel-label-row"><span className="overline">ANSWER TRANSPARENCY</span><span className="evidence-mark">◈</span></div><h2>Show your work.</h2><p className="subtle-copy">Answers are grounded in account data, policy, and deterministic calculations.</p>
              {evidenceItem?.evidence?.length ? <><div className="evidence-list">{evidenceItem.evidence.map((item, index) => <div className="evidence-source" key={`${item.requestId || item.type || item.tool}-${index}`}><span className={`source-mark ${item.status === 'ERROR' ? 'source-error' : ''}`}>{item.status === 'ERROR' ? '!' : '✓'}</span><div><strong>{evidenceTitle(item)}</strong><small>{evidenceDescription(item)}</small></div><span className="source-time">{item.latencyMs} ms</span></div>)}</div><div className="correlation-line"><span>TURN ID</span><code>{evidenceItem.turnId || '—'}</code></div><button className="copy-button" onClick={copyEvidence}>{copied ? 'Copied evidence' : 'Copy evidence'} <span>{copied ? '✓' : '▣'}</span></button></> : <div className="evidence-empty"><div className="empty-orbit">◈</div><strong>Evidence appears here</strong><span>Ask a question and open its evidence trail to see which systems and rules informed the answer.</span></div>}
            </section>
            <section className="panel performance-panel"><div className="panel-label-row"><span className="overline">LIVE PERFORMANCE</span><button className="refresh-button" onClick={refreshMetrics} title="Refresh metrics">↻</button></div><div className="metric-main"><span>Tool calls</span><strong>{metrics?.toolCalls ?? 0}</strong></div><div className="latency-metrics"><div><span>p50</span><strong>{metrics?.toolLatencyMs?.p50 ?? '—'}<small> ms</small></strong></div><div><span>p95</span><strong>{metrics?.toolLatencyMs?.p95 ?? '—'}<small> ms</small></strong></div><div><span>p99</span><strong>{metrics?.toolLatencyMs?.p99 ?? '—'}<small> ms</small></strong></div></div><div className="performance-foot"><span><i className="green-dot" /> Instrumented locally</span><span>{metrics?.turnsRecorded ?? 0} turns</span></div></section>
            <section className="panel demo-panel"><div className="panel-label-row"><span className="overline">DEMO CONTROLS</span><span className="demo-flask">⚙</span></div><div className="failure-control"><div><strong>Payments outage</strong><small>Test honest fallback behavior</small></div><button className={`toggle ${failureOn ? 'enabled' : ''}`} onClick={toggleFailure} role="switch" aria-checked={failureOn} aria-label="Inject payment service outage"><span /></button></div>{failureOn && <div className="failure-on"><span className="failure-dot" /> Failure injected · next payment lookup will be unavailable</div>}<div className="demo-divider" /><div className="action-stats"><span>Actions submitted</span><strong>{metrics?.actionsCreated ?? 0}</strong></div><small className="demo-caption">Synthetic services · local measurement only</small></section>
            <div className="voice-note"><span>◖</span><p><strong>{serverVoice ? 'Streaming voice gateway' : 'Browser voice fallback'}</strong> {serverVoice ? 'uses the configured server STT/TTS adapters over WebSocket.' : 'uses your browser speech API; configure STT/TTS provider endpoints for server-side audio streaming.'}</p></div>
          </aside>
        </div>
        <footer className="footer"><span>HORIZON SERVICE STUDIO <i>·</i> POC</span><span>Designed for clarity, built for trust.</span><a href="https://www.rbi.org.in/" target="_blank" rel="noreferrer">Support & policies ↗</a></footer>
      </main>
    </div>
  )
}

function LoanSummary({ account }) {
  const loan = account?.loan
  if (!loan) return <div className="summary-loading">Loan details are temporarily unavailable.</div>
  return <><div className="account-name"><div className="person-avatar">{account.customer.name.split(' ').map((part) => part[0]).slice(0, 2).join('')}</div><div><strong>{account.customer.name}</strong><small>Customer ID · {account.customer.customerId}</small></div></div><div className="product-card loan-card"><div className="product-card-top"><span className="product-label">PERSONAL LOAN</span><span className="active-state"><i /> {loan.status}</span></div><div className="balance-label">Outstanding principal</div><div className="balance-value">{money(loan.outstandingPrincipal)}</div><div className="product-divider" /><div className="account-stat-grid"><div><span>Monthly EMI</span><strong>{money(loan.emi)}</strong></div><div><span>Next due date</span><strong>{formatDate(loan.nextDueDate)}</strong></div></div><div className="loan-meta"><span>{loan.annualRatePercent}% {loan.rateType === 'FLOATING' ? 'floating' : 'fixed'} rate</span><span>{loan.tenureRemainingMonths} months left</span></div></div><div className="account-link-row"><span>▤</span><div><strong>Loan account</strong><small>{loan.loanId} · {loan.product}</small></div><span className="link-arrow">↗</span></div></>
}

function CardSummary({ account }) {
  const card = account?.card
  if (!card) return <div className="summary-loading">Card details are temporarily unavailable.</div>
  return <><div className="account-name"><div className="person-avatar">{account.customer.name.split(' ').map((part) => part[0]).slice(0, 2).join('')}</div><div><strong>{account.customer.name}</strong><small>Customer ID · {account.customer.customerId}</small></div></div><div className="product-card card-visual"><div className="card-topline"><span>HORIZON</span><span>◈</span></div><div className="card-chip">▦</div><div className="card-number">•••• &nbsp;•••• &nbsp;•••• &nbsp;{card.lastFour}</div><div className="card-bottom"><span>{card.product.toUpperCase()}</span><span>VISA</span></div></div><div className="card-balance-row"><div><span>Outstanding balance</span><strong>{money(card.outstanding)}</strong></div><div className="limit-chip">{money(card.availableLimit)} available</div></div><div className="card-due-row"><span>Statement due {formatDate(card.dueDate)}</span><strong>Minimum {money(card.minimumDue)}</strong></div><div className="reward-note"><span>✦</span> {card.rewardPoints.toLocaleString('en-IN')} reward points available</div></>
}

function systemLabel(system) {
  return ({ CRM: 'Customer profile', LOAN: 'Loan management', PAYMENTS: 'Payments', POLICY: 'Policy knowledge', SERVICE_OPS: 'Service operations' })[system] || system
}

function evidenceTitle(item) {
  if (item.type === 'policy') return `Policy rule · ${item.clauseId}`
  if (item.type === 'calculation') return 'Deterministic calculator'
  if (item.type === 'verification') return 'Answer verifier'
  return systemLabel(item.system)
}

function evidenceDescription(item) {
  if (item.type === 'policy') return `${item.applies ? 'Applied' : 'Not applicable'} · ${item.clauseText}`
  if (item.type === 'calculation') return `${money(item.inputs?.prepayment)} prepaid · saves ${money(item.result?.interest_saved)}`
  if (item.type === 'verification') return item.outcome || 'Figures and clause IDs checked against evidence'
  return String(item.operation || '').replace('GET ', '')
}

export default App
