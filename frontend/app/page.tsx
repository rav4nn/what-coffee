"use client";

import { useState, useRef, useEffect } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

type OptionType = "experience" | "brew" | "flavor" | null;

interface Option {
  label: string;
  value: string | null; // null = focus input instead of sending
}

const OPTION_SETS: Record<Exclude<OptionType, null>, Option[]> = {
  experience: [
    { label: "Just getting started", value: "I'm just getting started with specialty coffee" },
    { label: "Casual everyday drinker", value: "I'm a casual everyday coffee drinker" },
    { label: "Gone deep into the rabbit hole", value: "I've gone deep into the coffee rabbit hole" },
  ],
  brew: [
    { label: "Espresso machine", value: "Espresso machine" },
    { label: "Pour Over / V60", value: "Pour Over / V60" },
    { label: "French Press", value: "French Press" },
    { label: "AeroPress", value: "AeroPress" },
    { label: "Moka Pot", value: "Moka Pot" },
    { label: "South Indian Filter", value: "South Indian Filter" },
    { label: "Other...", value: null },
  ],
  flavor: [
    { label: "Bright & Fruity", value: "I enjoy bright and fruity coffee — citrus, berry, floral notes" },
    { label: "Chocolatey & Rich", value: "I prefer chocolatey and rich coffee, deep and bold" },
    { label: "Balanced & Smooth", value: "I like balanced and smooth coffee, not too extreme either way" },
    { label: "Custom description...", value: null },
  ],
};

function detectOptionType(text: string): OptionType {
  if (!text.includes("?")) return null;
  const lower = text.toLowerCase();
  if (
    lower.includes("rabbit hole") ||
    lower.includes("getting started") ||
    lower.includes("casual everyday") ||
    (lower.includes("experience") && (lower.includes("casual") || lower.includes("beginner") || lower.includes("enthusiast")))
  ) return "experience";
  if (
    lower.includes("brew with") ||
    lower.includes("equipment") ||
    lower.includes("how do you brew") ||
    lower.includes("how do you make") ||
    lower.includes("what do you use to brew") ||
    (lower.includes("brew") && (lower.includes("espresso") || lower.includes("pour over") || lower.includes("aeropress") || lower.includes("french press")))
  ) return "brew";
  if (
    lower.includes("flavors do you enjoy") ||
    lower.includes("flavours do you enjoy") ||
    lower.includes("what flavors") ||
    lower.includes("what flavours") ||
    (lower.includes("flavor") && lower.includes("?")) ||
    (lower.includes("flavour") && lower.includes("?"))
  ) return "flavor";
  return null;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [activeOptions, setActiveOptions] = useState<OptionType>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Reliable auto-focus whenever loading stops
  useEffect(() => {
    if (!isLoading && started) {
      inputRef.current?.focus();
    }
  }, [isLoading, started]);

  const startChat = async () => {
    setStarted(true);
    await sendMessage("Hello, I'm looking for a coffee recommendation.");
  };

  const sendMessage = async (messageText?: string) => {
    const text = messageText || input.trim();
    if (!text || isLoading) return;

    if (!messageText) setInput("");
    setActiveOptions(null);

    const userMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
        }),
      });

      if (!response.ok) throw new Error("API error");

      const newSessionId = response.headers.get("X-Session-Id");
      if (newSessionId) setSessionId(newSessionId);

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = "";

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          assistantMessage += chunk;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: assistantMessage,
            };
            return updated;
          });
        }
        // Detect if the completed response is asking a question we have options for
        setActiveOptions(detectOptionType(assistantMessage));
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I couldn't connect to the server. Make sure the backend is running.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOptionClick = (option: Option) => {
    if (option.value === null) {
      // "Other..." or "Custom description..." — just focus the input
      setActiveOptions(null);
      inputRef.current?.focus();
    } else {
      sendMessage(option.value);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatMessage = (content: string) => {
    return content
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br/>");
  };

  return (
    <main className="app">
      <div className="bg-texture" />

      <header className="header">
        <div className="logo-wrap">
          <span className="logo-icon">☕</span>
          <div>
            <h1 className="logo-title">What Coffee</h1>
            <p className="logo-sub">Indian Specialty Coffee Guide</p>
          </div>
        </div>
        <div className="header-tag">AI Powered</div>
      </header>

      <div className="chat-wrap">
        {!started ? (
          <div className="welcome">
            <div className="welcome-bean">☕</div>
            <h2 className="welcome-title">Find your perfect cup</h2>
            <p className="welcome-body">
              Tell me about your coffee preferences and I'll recommend the best
              Indian specialty coffees — sourced from roasters across the country.
            </p>
            <button className="start-btn" onClick={startChat}>
              Start exploring →
            </button>
            <div className="roaster-strip">
              <span>Blue Tokai</span>
              <span className="dot">·</span>
              <span>Subko</span>
              <span className="dot">·</span>
              <span>Corridor Seven</span>
              <span className="dot">·</span>
              <span>Black Baza</span>
              <span className="dot">·</span>
              <span>Araku</span>
              <span className="dot">·</span>
              <span>& more</span>
            </div>
          </div>
        ) : (
          <div className="messages">
            {messages.map((msg, i) => (
              <div key={i} className={`msg-row ${msg.role}`}>
                {msg.role === "assistant" && (
                  <div className="avatar">☕</div>
                )}
                <div
                  className={`bubble ${msg.role}`}
                  dangerouslySetInnerHTML={{
                    __html: formatMessage(msg.content) || (isLoading && i === messages.length - 1 ? '<span class="typing-dot">●</span>' : ""),
                  }}
                />
                {msg.role === "user" && (
                  <div className="avatar user-avatar">you</div>
                )}
              </div>
            ))}
            {isLoading && messages[messages.length - 1]?.role !== "assistant" && (
              <div className="msg-row assistant">
                <div className="avatar">☕</div>
                <div className="bubble assistant typing">
                  <span className="dot-1">●</span>
                  <span className="dot-2">●</span>
                  <span className="dot-3">●</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {started && (
        <div className="input-bar">
          {activeOptions && (
            <div className="options-row">
              {OPTION_SETS[activeOptions].map((opt) => (
                <button
                  key={opt.label}
                  className={`option-chip ${opt.value === null ? "option-chip-other" : ""}`}
                  onClick={() => handleOptionClick(opt)}
                  disabled={isLoading}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
          <div className="input-wrap">
            <textarea
              ref={inputRef}
              className="input"
              placeholder="Tell me about your coffee preferences..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isLoading}
            />
            <button
              className="send-btn"
              onClick={() => sendMessage()}
              disabled={isLoading || !input.trim()}
            >
              →
            </button>
          </div>
          <p className="input-hint">Press Enter to send · Shift+Enter for new line</p>
        </div>
      )}

      <style jsx global>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;1,400&family=DM+Sans:wght@300;400;500&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
          --espresso:   #1a0f0a;
          --roast:      #2d1a0e;
          --mahogany:   #4a2518;
          --caramel:    #8b5e3c;
          --latte:      #c4956a;
          --cream:      #f5ead8;
          --parchment:  #fdf6ec;
          --white:      #ffffff;
          --accent:     #c17f3a;
        }

        html, body {
          height: 100%;
          background: var(--espresso);
          color: var(--cream);
          font-family: 'DM Sans', sans-serif;
          font-weight: 300;
        }

        .app {
          display: flex;
          flex-direction: column;
          height: 100vh;
          max-width: 780px;
          margin: 0 auto;
          position: relative;
        }

        .bg-texture {
          position: fixed;
          inset: 0;
          background-image:
            radial-gradient(ellipse at 20% 50%, rgba(74,37,24,0.4) 0%, transparent 60%),
            radial-gradient(ellipse at 80% 20%, rgba(139,94,60,0.15) 0%, transparent 50%);
          pointer-events: none;
          z-index: 0;
        }

        /* ── Header ── */
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 20px 28px;
          border-bottom: 1px solid rgba(196,149,106,0.15);
          position: relative;
          z-index: 10;
          background: rgba(26,15,10,0.8);
          backdrop-filter: blur(12px);
        }

        .logo-wrap {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .logo-icon {
          font-size: 28px;
          filter: drop-shadow(0 0 8px rgba(193,127,58,0.5));
        }

        .logo-title {
          font-family: 'Playfair Display', serif;
          font-size: 22px;
          font-weight: 600;
          color: var(--cream);
          line-height: 1;
        }

        .logo-sub {
          font-size: 11px;
          color: var(--caramel);
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-top: 3px;
        }

        .header-tag {
          font-size: 10px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--accent);
          border: 1px solid rgba(193,127,58,0.3);
          padding: 4px 10px;
          border-radius: 20px;
        }

        /* ── Chat wrap ── */
        .chat-wrap {
          flex: 1;
          overflow-y: auto;
          position: relative;
          z-index: 5;
          scroll-behavior: smooth;
        }

        .chat-wrap::-webkit-scrollbar { width: 4px; }
        .chat-wrap::-webkit-scrollbar-track { background: transparent; }
        .chat-wrap::-webkit-scrollbar-thumb { background: var(--mahogany); border-radius: 4px; }

        /* ── Welcome screen ── */
        .welcome {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100%;
          padding: 40px 28px;
          text-align: center;
          animation: fadeUp 0.6s ease both;
        }

        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        .welcome-bean {
          font-size: 56px;
          margin-bottom: 24px;
          filter: drop-shadow(0 0 20px rgba(193,127,58,0.4));
          animation: float 3s ease-in-out infinite;
        }

        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50%       { transform: translateY(-8px); }
        }

        .welcome-title {
          font-family: 'Playfair Display', serif;
          font-size: 38px;
          font-weight: 600;
          color: var(--cream);
          margin-bottom: 16px;
          line-height: 1.2;
        }

        .welcome-body {
          font-size: 16px;
          color: var(--latte);
          line-height: 1.7;
          max-width: 460px;
          margin-bottom: 36px;
        }

        .start-btn {
          background: var(--accent);
          color: var(--espresso);
          border: none;
          padding: 14px 32px;
          border-radius: 40px;
          font-family: 'DM Sans', sans-serif;
          font-size: 15px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          letter-spacing: 0.02em;
          margin-bottom: 40px;
        }

        .start-btn:hover {
          background: var(--latte);
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(193,127,58,0.3);
        }

        .roaster-strip {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          justify-content: center;
          font-size: 12px;
          color: var(--caramel);
          letter-spacing: 0.04em;
        }

        .roaster-strip .dot { color: var(--mahogany); }

        /* ── Messages ── */
        .messages {
          padding: 28px 24px;
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .msg-row {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          animation: fadeUp 0.3s ease both;
        }

        .msg-row.user { flex-direction: row-reverse; }

        .avatar {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: var(--mahogany);
          border: 1px solid rgba(196,149,106,0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
          flex-shrink: 0;
        }

        .user-avatar {
          font-size: 11px;
          font-weight: 500;
          color: var(--caramel);
          letter-spacing: 0.04em;
          background: rgba(74,37,24,0.5);
        }

        .bubble {
          max-width: 75%;
          padding: 14px 18px;
          border-radius: 18px;
          font-size: 15px;
          line-height: 1.65;
        }

        .bubble.assistant {
          background: var(--roast);
          border: 1px solid rgba(196,149,106,0.12);
          color: var(--cream);
          border-bottom-left-radius: 4px;
        }

        .bubble.user {
          background: var(--accent);
          color: var(--espresso);
          border-bottom-right-radius: 4px;
          font-weight: 400;
        }

        .bubble strong { color: var(--latte); font-weight: 500; }
        .bubble.user strong { color: var(--espresso); }

        /* Typing indicator */
        .bubble.typing {
          display: flex;
          gap: 6px;
          align-items: center;
          padding: 16px 20px;
        }

        .dot-1, .dot-2, .dot-3 {
          font-size: 10px;
          color: var(--caramel);
          animation: blink 1.2s infinite;
        }
        .dot-2 { animation-delay: 0.2s; }
        .dot-3 { animation-delay: 0.4s; }

        @keyframes blink {
          0%, 80%, 100% { opacity: 0.2; }
          40%            { opacity: 1; }
        }

        /* ── Option chips ── */
        .options-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          padding: 0 0 12px 0;
          animation: fadeUp 0.25s ease both;
        }

        .option-chip {
          background: rgba(74,37,24,0.7);
          border: 1px solid rgba(193,127,58,0.35);
          color: var(--cream);
          font-family: 'DM Sans', sans-serif;
          font-size: 13px;
          font-weight: 400;
          padding: 7px 14px;
          border-radius: 20px;
          cursor: pointer;
          transition: all 0.15s ease;
          white-space: nowrap;
        }

        .option-chip:hover:not(:disabled) {
          background: var(--accent);
          color: var(--espresso);
          border-color: var(--accent);
          transform: translateY(-1px);
        }

        .option-chip:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .option-chip-other {
          background: transparent;
          border-style: dashed;
          color: var(--caramel);
        }

        .option-chip-other:hover:not(:disabled) {
          background: rgba(74,37,24,0.5);
          color: var(--cream);
          border-color: var(--latte);
          border-style: solid;
        }

        /* ── Input bar ── */
        .input-bar {
          padding: 16px 24px 20px;
          border-top: 1px solid rgba(196,149,106,0.1);
          background: rgba(26,15,10,0.9);
          backdrop-filter: blur(12px);
          position: relative;
          z-index: 10;
        }

        .input-wrap {
          display: flex;
          gap: 10px;
          align-items: flex-end;
          background: var(--roast);
          border: 1px solid rgba(196,149,106,0.2);
          border-radius: 16px;
          padding: 10px 10px 10px 16px;
          transition: border-color 0.2s;
        }

        .input-wrap:focus-within {
          border-color: rgba(193,127,58,0.5);
        }

        .input {
          flex: 1;
          background: transparent;
          border: none;
          outline: none;
          color: var(--cream);
          font-family: 'DM Sans', sans-serif;
          font-size: 15px;
          font-weight: 300;
          resize: none;
          line-height: 1.5;
          max-height: 120px;
        }

        .input::placeholder { color: var(--caramel); opacity: 0.6; }

        .send-btn {
          width: 38px;
          height: 38px;
          border-radius: 10px;
          background: var(--accent);
          border: none;
          color: var(--espresso);
          font-size: 18px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
          flex-shrink: 0;
          font-weight: 700;
        }

        .send-btn:hover:not(:disabled) {
          background: var(--latte);
          transform: translateY(-1px);
        }

        .send-btn:disabled {
          opacity: 0.35;
          cursor: not-allowed;
        }

        .input-hint {
          font-size: 11px;
          color: var(--caramel);
          opacity: 0.5;
          margin-top: 8px;
          text-align: center;
          letter-spacing: 0.03em;
        }

        /* ── Responsive ── */
        @media (max-width: 600px) {
          .welcome-title { font-size: 28px; }
          .bubble { max-width: 88%; }
          .header { padding: 16px 20px; }
          .messages { padding: 20px 16px; }
          .input-bar { padding: 12px 16px 16px; }
          .option-chip { font-size: 12px; padding: 6px 12px; }
        }
      `}</style>
    </main>
  );
}
