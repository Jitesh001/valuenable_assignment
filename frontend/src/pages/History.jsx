import { useEffect, useState } from "react";
import api from "../api/client.js";

function fmt(n) {
  return new Intl.NumberFormat("en-IN").format(Number(n || 0));
}

export default function History() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    api.get("/policies/quotes/").then((r) => setItems(r.data.results || r.data)).catch(() => {});
  }, []);

  return (
    <div className="card">
      <h2>Saved quotes</h2>
      {items.length === 0 ? (
        <p>No saved quotes yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Age</th>
              <th>Premium</th>
              <th>SA</th>
              <th>PPT</th>
              <th>PT</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {items.map((q) => (
              <tr key={q.id}>
                <td>{q.id}</td>
                <td>{q.policy_type}</td>
                <td>{q.age_at_entry}</td>
                <td>{fmt(q.premium)}</td>
                <td>{fmt(q.sum_assured)}</td>
                <td>{q.premium_term}</td>
                <td>{q.policy_term}</td>
                <td>{new Date(q.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
