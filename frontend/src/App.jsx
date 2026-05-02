import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Illustration from "./pages/Illustration.jsx";
import History from "./pages/History.jsx";

function isAuthed() {
  return !!localStorage.getItem("access");
}

function PrivateRoute({ children }) {
  return isAuthed() ? children : <Navigate to="/login" replace />;
}

function Nav() {
  const navigate = useNavigate();
  const authed = isAuthed();
  return (
    <div className="nav">
      <div>
        <Link to="/">Benefit Illustration</Link>
        {authed && <Link to="/history">History</Link>}
      </div>
      <div className="right">
        {authed ? (
          <button onClick={() => { localStorage.clear(); navigate("/login"); }}>
            Logout
          </button>
        ) : (
          <>
            <Link to="/login">Login</Link>
            <Link to="/register">Register</Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <div className="container">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={<PrivateRoute><Illustration /></PrivateRoute>}
          />
          <Route
            path="/history"
            element={<PrivateRoute><History /></PrivateRoute>}
          />
        </Routes>
      </div>
    </>
  );
}
