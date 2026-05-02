import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client.js";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      const r = await api.post("/auth/login/", { email, password });
      localStorage.setItem("access", r.data.access);
      localStorage.setItem("refresh", r.data.refresh);
      navigate("/");
    } catch (e) {
      setErr(e.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
      <h2>Login</h2>
      <form onSubmit={submit}>
        <label>Email</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {err && <div className="error">{err}</div>}
        <button className="primary" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
