import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client.js";

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    dob: "",
    mobile: "",
  });
  const [errors, setErrors] = useState(null);
  const [loading, setLoading] = useState(false);

  function update(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function submit(e) {
    e.preventDefault();
    setErrors(null);
    setLoading(true);
    try {
      const r = await api.post("/auth/register/", form);
      localStorage.setItem("access", r.data.access);
      localStorage.setItem("refresh", r.data.refresh);
      navigate("/");
    } catch (e) {
      setErrors(e.response?.data || { detail: "Registration failed" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 480, margin: "40px auto" }}>
      <h2>Create account</h2>
      <p style={{ color: "#6b7280", fontSize: 13 }}>
        Your name, DOB and mobile are stored encrypted at rest.
      </p>
      <form onSubmit={submit}>
        <label>Email</label>
        <input type="email" value={form.email} onChange={(e) => update("email", e.target.value)} required />
        <label>Full name</label>
        <input value={form.full_name} onChange={(e) => update("full_name", e.target.value)} required />
        <label>Date of birth</label>
        <input type="date" value={form.dob} onChange={(e) => update("dob", e.target.value)} required />
        <label>Mobile (10 digits)</label>
        <input value={form.mobile} onChange={(e) => update("mobile", e.target.value)} required />
        <label>Password (min 8 chars)</label>
        <input type="password" value={form.password} onChange={(e) => update("password", e.target.value)} required />

        {errors && (
          <div className="error">
            <ul>
              {Object.entries(errors).flatMap(([k, v]) =>
                Array.isArray(v) ? v.map((m) => <li key={k + m}>{k}: {m}</li>) : [<li key={k}>{k}: {String(v)}</li>]
              )}
            </ul>
          </div>
        )}
        <button className="primary" disabled={loading}>
          {loading ? "Creating…" : "Create account"}
        </button>
      </form>
    </div>
  );
}
