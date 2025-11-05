import React, { useState } from "react";
import api from "../api/axios";

export default function FileUpload({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => setFile(e.target.files[0]);

  const handleUpload = async () => {
    if (!file) return alert("Please select a file!");
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await api.post("/upload-pdf", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      onUploadSuccess(res.data);
      alert("✅ PDF uploaded successfully!");
    } catch (err) {
      console.error(err);
      alert("❌ Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex gap-2 items-center">
      <input
        type="file"
        accept="application/pdf"
        onChange={handleFileChange}
        className="border border-gray-300 rounded-lg p-2 text-sm"
      />
      <button
        onClick={handleUpload}
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition"
      >
        {loading ? "Uploading..." : "Upload PDF"}
      </button>
    </div>
  );
}
