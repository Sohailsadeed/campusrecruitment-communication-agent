import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Layout from "./components/Layout/Layout";
import HomePage from "./pages/HomePage";
import RecordingPage from "./pages/RecordingPage";
import AnalysisPage from "./pages/AnalysisPage";
import DashboardPage from "./pages/DashboardPage";
import SettingsPage from "./pages/SettingsPage";
import TechnicalStudio from "./pages/technical/TechnicalStudio";
import TechnicalReport from "./pages/technical/TechnicalReport";
import GuesstimateStudio from "./pages/guesstimate/GuesstimateStudio";
import GuesstimateReport from "./pages/guesstimate/GuesstimateReport";
import HRStudio from "./pages/hr/HRStudio";
import HRReport from "./pages/hr/HRReport";
import AuthPage from "./pages/AuthPage";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AuthModal from "./components/Auth/AuthModal";

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-10 h-10 rounded-full border-2 border-secondary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <AuthModal />
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<HomePage />} />
          <Route path="/record" element={<RecordingPage />} />
          <Route path="/technical" element={<TechnicalStudio />} />
          <Route path="/technical/:sessionId" element={<TechnicalStudio />} />
          <Route path="/technical/report/:sessionId" element={<TechnicalReport />} />
          <Route path="/guesstimate" element={<GuesstimateStudio />} />
          <Route path="/guesstimate/:sessionId" element={<GuesstimateStudio />} />
          <Route path="/guesstimate/report/:sessionId" element={<GuesstimateReport />} />
          <Route path="/hr" element={<HRStudio />} />
          <Route path="/hr/:sessionId" element={<HRStudio />} />
          <Route path="/hr/report/:sessionId" element={<HRReport />} />
          <Route path="/analysis/:sessionId" element={<AnalysisPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
