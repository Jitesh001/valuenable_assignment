import { useEffect, useState } from "react";
import api from "../api/client.js";

const today = new Date().toISOString().slice(0, 10);

const initialForm = {
  policy_type: "ENDOW",
  dob: "1990-01-01",
  gender: "M",
  premium: "25000",
  premium_frequency: "annual",
  premium_term: 7,
  policy_term: 15,
  sum_assured: "500000",
  riders: [],
};

function fmt(n) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Number(n || 0));
}

export default function Illustration() {
  const [types, setTypes] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [save, setSave] = useState(false);

  useEffect(() => {
    api.get("/policies/types/").then((r) => setTypes(r.data)).catch(() => {});
  }, []);

  function update(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit(e) {
    e.preventDefault();
    setErrors(null);
    setResult(null);
    setLoading(true);
    try {
      if (save) {
        const r = await api.post("/policies/calculate/", form, {
          headers: { "Idempotency-Key": crypto.randomUUID() },
        });
        setResult(r.data.result);
      } else {
        const r = await api.post("/policies/illustrate/", form);
        setResult(r.data);
      }
    } catch (e) {
      setErrors(e.response?.data || { detail: "Request failed" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="card">
        <h2>Generate Benefit Illustration</h2>
        <form onSubmit={submit}>
          <div className="grid-2">
            <div>
              <label>Policy type</label>
              <select value={form.policy_type} onChange={(e) => update("policy_type", e.target.value)}>
                {types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <label>Gender</label>
              <select value={form.gender} onChange={(e) => update("gender", e.target.value)}>
                <option value="M">Male</option>
                <option value="F">Female</option>
                <option value="O">Other</option>
              </select>
            </div>
          </div>

          <div className="grid-2">
            <div>
              <label>Date of birth</label>
              <input type="date" value={form.dob} onChange={(e) => update("dob", e.target.value)} max={today} />
            </div>
            <div>
              <label>Premium frequency</label>
              <select value={form.premium_frequency} onChange={(e) => update("premium_frequency", e.target.value)}>
                <option value="annual">Annual</option>
                <option value="semi">Semi-Annual</option>
                <option value="quarterly">Quarterly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>

          <div className="grid-2">
            <div>
              <label>Annual premium (₹10,000–₹50,000)</label>
              <input value={form.premium} onChange={(e) => update("premium", e.target.value)} />
            </div>
            <div>
              <label>Sum assured (≥ max(10× premium, ₹5,00,000))</label>
              <input value={form.sum_assured} onChange={(e) => update("sum_assured", e.target.value)} />
            </div>
          </div>

          <div className="grid-2">
            <div>
              <label>Premium term (5–10 yrs)</label>
              <input type="number" min="1" value={form.premium_term} onChange={(e) => update("premium_term", Number(e.target.value))} />
            </div>
            <div>
              <label>Policy term (10–20 yrs, &gt; PPT)</label>
              <input type="number" min="1" value={form.policy_term} onChange={(e) => update("policy_term", Number(e.target.value))} />
            </div>
          </div>

          <label style={{ marginTop: 16 }}>
            <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} style={{ width: "auto", marginRight: 6 }} />
            Save this quote to history
          </label>

          {errors && (
            <div className="error">
              <strong>{errors.detail || "Error"}</strong>
              {Array.isArray(errors.errors) && (
                <ul>{errors.errors.map((m) => <li key={m}>{m}</li>)}</ul>
              )}
            </div>
          )}

          <button className="primary" disabled={loading}>
            {loading ? "Calculating…" : "Generate Illustration"}
          </button>
        </form>
      </div>

      {result && <ResultCard result={result} />}
    </div>
  );
}

function ResultCard({ result }) {
  const r = result.result || result;
  return (
    <div className="card">
      <h2>Illustration <span className="pill">Age at entry: {r.age_at_entry}</span></h2>
      <div className="summary">
        <div><span>Sum Assured</span><b>₹{fmt(r.sum_assured)}</b></div>
        <div><span>Annual Premium</span><b>₹{fmt(r.annualized_premium)}</b></div>
        <div><span>Premium Term</span><b>{r.premium_term} yrs</b></div>
        <div><span>Policy Term</span><b>{r.policy_term} yrs</b></div>
        <div><span>Lower Scenario</span><b>{(Number(r.assumed_return_lower) * 100).toFixed(0)}%</b></div>
        <div><span>Higher Scenario</span><b>{(Number(r.assumed_return_higher) * 100).toFixed(0)}%</b></div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Yr</th>
              <th>Age</th>
              <th>Premium</th>
              <th>Cum. Prem</th>
              <th>Death Benefit</th>
              <th>Bonus (4%)</th>
              <th>Bonus (8%)</th>
              <th>SV (4%)</th>
              <th>SV (8%)</th>
              <th>Maturity (4%)</th>
              <th>Maturity (8%)</th>
            </tr>
          </thead>
          <tbody>
            {r.rows.map((row) => (
              <tr key={row.policy_year}>
                <td>{row.policy_year}</td>
                <td>{row.age}</td>
                <td>{fmt(row.annualized_premium)}</td>
                <td>{fmt(row.cumulative_premium)}</td>
                <td>{fmt(row.death_benefit)}</td>
                <td>{fmt(row.accrued_bonus_lower)}</td>
                <td>{fmt(row.accrued_bonus_higher)}</td>
                <td>{fmt(row.surrender_value_lower)}</td>
                <td>{fmt(row.surrender_value_higher)}</td>
                <td>{fmt(row.maturity_benefit_lower)}</td>
                <td>{fmt(row.maturity_benefit_higher)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
