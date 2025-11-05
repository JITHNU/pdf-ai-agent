import React, { useState, useEffect, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import { FiSend, FiTrash2, FiPlus, FiUser, FiCpu } from "react-icons/fi";
import "./App.css";

export default function App() {
  const [conversations, setConversations] = useState(
    JSON.parse(localStorage.getItem("conversations")) || []
  );
  const [activeChat, setActiveChat] = useState(() => uuidv4());
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef();
  const [uploadedPdf, setUploadedPdf] = useState("");

  useEffect(() => {
    localStorage.setItem("conversations", JSON.stringify(conversations));
  }, [conversations]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Send message
  const handleSend = async () => {
    if (!query.trim()) return;
    const userMsg = { role: "user", text: query };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setQuery("");
    setLoading(true);
    setError("");

    try {
      const res = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, session_id: activeChat }),
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      const botMsg = { role: "assistant", text: data.answer };
      const newMsgs = [...updatedMessages, botMsg];
      setMessages(newMsgs);

      // Update conversation history (first user message as summary)
      const summary =
        newMsgs.find((m) => m.role === "user")?.text?.slice(0, 40) || "New chat";
      setConversations((prev) => [
        ...prev.filter((c) => c.id !== activeChat),
        { id: activeChat, summary, messages: newMsgs },
      ]);
    } catch (err) {
      console.error(err);
      setError("Unable to get response. ❌ ");
    } finally {
      setLoading(false);
    }
  };

  // Start a new chat
  const handleNewChat = () => {
    const newId = uuidv4();
    setActiveChat(newId);
    setMessages([]);
  };

  // Clear all history
  const handleClear = () => {
    setConversations([]);
    setMessages([]);
    setActiveChat(uuidv4());
    localStorage.clear();
  };

  // Switch between conversations
  const openChat = (chatId) => {
    const chat = conversations.find((c) => c.id === chatId);
    if (chat) {
      setActiveChat(chat.id);
      setMessages(chat.messages);
    }
  };

  // PDF upload handler
  const handlePdfUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.type !== "application/pdf") {
      alert("Please upload a valid PDF file.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("session_id", activeChat);

    try {
      const res = await fetch("http://127.0.0.1:8000/upload_pdf", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setUploadedPdf(file.name);
        alert(data.message || "PDF uploaded successfully!");
      } else {
        alert(data.error || "Failed to process PDF.");
      }
    } catch (err) {
      console.error(err);
      alert("Failed to upload PDF.");
    }
  };

  // Markdown link rendering
  const renderMessageText = (text) => {
    const markdownLinkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
    const urlRegex = /(https?:\/\/[^\s]+)/g;

    let parts = [];
    let lastIndex = 0;
    let match;
    while ((match = markdownLinkRegex.exec(text)) !== null) {
      const [full, label, url] = match;
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      parts.push(
        <a
          key={url}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="chat-link"
        >
          {label}
        </a>
      );
      lastIndex = match.index + full.length;
    }
    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }

    return parts.flatMap((part, i) => {
      if (typeof part !== "string") return part;
      const urlParts = [];
      let last = 0;
      let urlMatch;
      while ((urlMatch = urlRegex.exec(part)) !== null) {
        if (urlMatch.index > last) {
          urlParts.push(part.slice(last, urlMatch.index));
        }
        const url = urlMatch[0];
        urlParts.push(
          <a
            key={`${url}-${i}`}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="chat-link"
          >
            {url}
          </a>
        );
        last = urlMatch.index + url.length;
      }
      if (last < part.length) {
        urlParts.push(part.slice(last));
      }
      return urlParts;
    });
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <h2 className="sidebar-title">JithBot 🤖</h2>
        <button className="new-chat" onClick={handleNewChat}>
          <FiPlus /> New Chat
        </button>
        <button className="clear-btn" onClick={handleClear}>
          <FiTrash2 /> Clear All
        </button>

        {/* PDF Upload */}
        <div className="pdf-upload-container">
          <label htmlFor="pdf-upload" className="pdf-upload-label">
            📄 Upload PDF
          </label>
          <input
            id="pdf-upload"
            type="file"
            accept="application/pdf"
            onChange={handlePdfUpload}
            className="pdf-upload-input"
          />
        </div>
        {uploadedPdf && (
          <div className="pdf-status">
            <strong>{uploadedPdf}</strong> loaded. ✅
          </div>
        )}

        <div className="history">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`history-item ${c.id === activeChat ? "active" : ""}`}
              onClick={() => openChat(c.id)}
            >
              💬 {c.summary}
            </div>
          ))}
        </div>
      </aside>

      {/* Chat Area */}
      <main className="chat-area">
        <div className="messages">
          <div className="messages">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`message ${msg.role} ${
                  msg.role === "user" ? "justify-end text-right" : "justify-start text-left"
                }`}
              >
                {msg.role === "assistant" && (
                  <div className="icon mr-2">
                    <FiCpu className="text-green-400 w-6 h-6" />
                  </div>
                )}
                <div className="bubble">{renderMessageText(msg.text)}</div>
                {msg.role === "user" && (
                  <div className="icon ml-2">
                    <FiUser className="text-blue-400 w-6 h-6" />
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="message assistant">
                <div className="icon">
                  <FiCpu className="text-green-400 w-6 h-6" />
                </div>
                <div className="bubble typing">...</div>
              </div>
            )}
            {error && <div className="error">{error}</div>}
            <div ref={scrollRef}></div>
          </div>
          {error && <div className="error">{error}</div>}
          <div ref={scrollRef}></div>
        </div>

        {/* Input */}
        {/* Chat Disclaimer */}
        <div className="disclaimer">
          <strong>JithBot can make mistakes. ⚠️</strong> Always verify important information or Upload PDF and ask from it.
        </div>
        <div className="input-area">
          <input
            type="text"
            placeholder={
              uploadedPdf
                ? `Ask something from ${uploadedPdf}...`
                : "Type your message..."
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
          />
          <button onClick={handleSend} disabled={loading}>
            <FiSend />
          </button>
        </div>
      </main>
    </div>
  );
}
