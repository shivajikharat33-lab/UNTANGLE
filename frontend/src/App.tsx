import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { Spinner } from "./components/Spinner";
import { DashboardPage } from "./pages/DashboardPage";
import { LandingPage } from "./pages/LandingPage";
import { NewProjectPage } from "./pages/NewProjectPage";
import { NotBuiltPage } from "./pages/NotBuiltPage";
import { ProcessingPage } from "./pages/ProcessingPage";
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
          <Route
            path="results"
            element={
              <NotBuiltPage
                title="Results"
                description="The simplified sketch will appear here. There is no sketch to show."
              />
            }
          />
          <Route
            path="reports"
            element={
              <NotBuiltPage
                title="Reports"
                description="The Tag Check Report and the Connection Report will be listed here. No report has been produced."
              />
            }
          />
          <Route
            path="edit"
            element={
              <NotBuiltPage
                title="Edit"
                description="Delete, add, reverse, and recolor will live here. Those tools are not built yet."
              />
            }
          />
          <Route
            path="versions"
            element={
              <NotBuiltPage
                title="Versions"
                description="Version 0 will stay the original. Version history is not built yet, so there is nothing to compare."
              />
            }
          />
          <Route
            path="export"
            element={
              <NotBuiltPage
                title="Export"
                description="SVG, PDF, PNG, JSON, and Excel downloads will be offered here. There is no file to download."
              />
            }
          />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
