import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout/Layout";
import HomePage from "./pages/HomePage";
import RecordingPage from "./pages/RecordingPage";
import AnalysisPage from "./pages/AnalysisPage";
import DashboardPage from "./pages/DashboardPage";
import SettingsPage from "./pages/SettingsPage";
import TechnicalStudio from "./pages/technical/TechnicalStudio";
import TechnicalReport from "./pages/technical/TechnicalReport";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/record" element={<RecordingPage />} />
        <Route path="/technical" element={<TechnicalStudio />} />
        <Route path="/technical/report/:sessionId" element={<TechnicalReport />} />
        <Route path="/analysis/:sessionId" element={<AnalysisPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
