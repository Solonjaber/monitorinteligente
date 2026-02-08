import { useState } from "react";
import axios from "axios";
import "./App.css";

const API = "http://localhost:8000";

const TYPES = [
  { value: "movimento", label: "Movimento" },
  { value: "parado", label: "Parado" },
  { value: "queda", label: "Queda" },
  { value: "inatividade_prolongada", label: "Inatividade Prolongada" },
  { value: "invasao_perimetro", label: "Invasao Perimetro" },
];

function App() {
  const [camId, setCamId] = useState("");
  const [type, setType] = useState("movimento");
  const [ts, setTs] = useState(() => String(Date.now()));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // axios direto aqui por ser teste rapido, em prod usaria React Query
  // pra gerenciar cache e estados de request
  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const { data } = await axios.post(`${API}/event`, {
        camera_id: camId,
        event_type: type,
        timestamp: Number(ts),
      });
      setResult(data);
    } catch (err) {
      const msg =
        err.response?.data?.detail?.[0]?.msg ||
        err.response?.data?.detail ||
        "Falha ao enviar. A API esta rodando?";
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <h1>Monitoramento Inteligente</h1>
      <p className="subtitle">Painel de eventos em tempo real</p>

      <form className="event-form" onSubmit={submit}>
        <div className="form-group">
          <label>Camera ID</label>
          <input
            type="text"
            placeholder="CAM-001"
            value={camId}
            onChange={(e) => setCamId(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label>Tipo de Evento</label>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Timestamp</label>
          <input
            type="number"
            value={ts}
            onChange={(e) => setTs(e.target.value)}
            required
          />
        </div>

        <button className="btn-submit" type="submit" disabled={loading}>
          {loading ? "Enviando..." : "Enviar"}
        </button>
      </form>

      {error && <div className="error-msg">{error}</div>}

      {result && (
        <div className={`result-card ${result.alert ? "alert" : "safe"}`}>
          <div className="card-label">
            {result.alert ? "ALERTA GERADO" : "Sem Alerta"}
          </div>
          <div>{result.alert ? "Evento critico detectado" : "Evento registrado"}</div>
          <div className="card-details">
            {result.camera_id} &middot; {result.event_type}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
