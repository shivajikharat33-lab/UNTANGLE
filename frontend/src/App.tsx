import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { Spinner } from "./components/Spinner";
import { DashboardPage } from "./pages/DashboardPage";
import { LandingPage } from "./pages/LandingPage";
import { NewProjectPage } from "./pages/NewProjectPage";
import { EditPage } from "./pages/EditPage";
import { ExportPage } from "./pages/ExportPage";
import { HistoryPage } from "./pages/HistoryPage";
import { FindingsPage } from "./pages/FindingsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SketchPage } from "./pages/SketchPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { ResultsPage } from "./pages/ResultsPage";
import { SettingsPage } from "./pages/SettingsPage";

const StageFixturePage = import.meta.env.DEV
  ? lazy(() => import("./pages/StageFixturePage").then((module) => ({ default: module.StageFixturePage })))
  : null;

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/app" element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="new" element={<NewProjectPage />} />
          <Route path="projects/:id/processing" element={<ProcessingPage />} />
          <Route path="projects/:id/findings" element={<FindingsPage />} />
          <Route path="projects/:id/sketch" element={<SketchPage />} />
          <Route path="projects/:id/results" element={<ResultsPage />} />
          <Route path="projects/:id/reports" element={<ReportsPage />} />
          <Route path="projects/:id/export" element={<ExportPage />} />
          <Route path="projects/:id/edit" element={<EditPage />} />
          <Route path="projects/:id/versions" element={<HistoryPage />} />
          {StageFixturePage ? (
            <Route
              path="dev/stages"
              element={
                <Suspense fallback={<Spinner label="Loading fixture" />}>
                  <StageFixturePage />
                </Suspense>
              }
            />
          ) : null}
          <Route path="results" element={<ResultsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="edit" element={<EditPage />} />
          <Route path="versions" element={<HistoryPage />} />
          <Route path="export" element={<ExportPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
