import React from "react";

export default function ChatMessage({ sender, text }) {
  const isUser = sender === "user";

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}
    >
      <div
        className={`max-w-[70%] p-3 rounded-2xl shadow-md ${
          isUser
            ? "bg-blue-600 text-white rounded-br-none"
            : "bg-gray-100 text-gray-900 rounded-bl-none"
        }`}
      >
        {text}
      </div>
    </div>
  );
}
