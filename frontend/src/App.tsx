import { useState } from "react";

const API = "http://localhost:8000/api";

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [videoId, setVideoId] = useState("");
  const [instructions, setInstructions] = useState("Find exciting moments and keep 8 seconds before and 5 seconds after each one.");
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("15");
  const [clipUrl, setClipUrl] = useState("");
  const [suggestions, setSuggestions] = useState<Array<{ start: number; end: number; title: string; reason: string; clip_url?: string }>>([]);
  const [progress, setProgress] = useState(0);
  const [eta, setEta] = useState<number | null>(null);
  const [status, setStatus] = useState("Upload a video to begin.");

  async function upload() {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setStatus("Uploading video...");
    const response = await fetch(`${API}/videos`, { method: "POST", body: form });
    const data = await response.json();
    setVideoId(data.video_id);
    setStatus("Uploaded. Choose timestamps or run analysis when the AI selector is connected.");
  }

  async function analyze() {
    if (!videoId) return setStatus("Upload a video first.");
    setProgress(0);
    setEta(null);
    setStatus("Starting analysis...");
    const response = await fetch(`${API}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ video_id: videoId, instructions }) });
    const data = await response.json();
    if (!response.ok) return setStatus(data.detail ?? "Analysis failed.");
    let done = false;
    while (!done) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const jobResponse = await fetch(`${API}/jobs/${data.job_id}`);
      const job = await jobResponse.json();
      setProgress(job.progress ?? 0);
      setEta(job.eta_seconds ?? null);
      setStatus(job.message ?? "Processing...");
      done = job.status === "complete" || job.status === "failed";
      setSuggestions(job.status === "complete" ? (job.suggestions ?? []) : (job.ideas ?? []));
    }
  }

  async function makeClip() {
    if (!videoId) return setStatus("Upload a video first.");
    const response = await fetch(`${API}/clips`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ video_id: videoId, start: Number(start), end: Number(end), title: "Manual test clip" }) });
    const data = await response.json();
    if (!response.ok) return setStatus(data.detail ?? "Could not create clip.");
    setClipUrl(`http://localhost:8000${data.url}`);
    setStatus("Clip created.");
  }

  return <main>
    <header><p className="eyebrow">CLIPFORGE MVP</p><h1>Turn long videos into usable Shorts.</h1><p className="sub">Upload a video, describe what you want, and let the pipeline find the moments worth clipping.</p></header>
    <section className="card">
      <label>1. Choose a video<input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
      <button onClick={upload} disabled={!file}>Upload video</button>
      <label>2. Clipping instructions<textarea value={instructions} onChange={e => setInstructions(e.target.value)} /></label>
      <button className="secondary" onClick={analyze}>Analyze with AI</button>
      {progress > 0 && <div className="progress-wrap"><div className="progress-label"><span>Processing: {Math.round(progress)}%</span><span>{eta === null ? "Estimating time..." : `${Math.floor(eta / 60)}m ${eta % 60}s remaining`}</span></div><div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div></div>}
    </section>
    <section className="card">
      <h2>Manual clip tester</h2><p className="muted">This proves the video-cutting portion works before we add transcription and AI selection.</p>
      <div className="row"><label>Start seconds<input value={start} onChange={e => setStart(e.target.value)} /></label><label>End seconds<input value={end} onChange={e => setEnd(e.target.value)} /></label></div>
      <button onClick={makeClip}>Create clip</button>
      {clipUrl && <video className="preview" controls src={clipUrl} />}
    </section>
    {suggestions.length > 0 && <section className="card"><h2>Suggested clips</h2>{suggestions.map((suggestion, index) => <article className="suggestion" key={`${suggestion.start}-${index}`}><div><h3>{suggestion.title}</h3><p className="muted">{suggestion.reason}</p><small>{suggestion.start}s – {suggestion.end}s</small></div>{suggestion.clip_url && <video controls src={`http://localhost:8000${suggestion.clip_url}`} />}</article>)}</section>}
    <p className="status">{status}</p>
  </main>;
}
