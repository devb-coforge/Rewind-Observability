import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { SearchPage } from "./pages/SearchPage";
import { SessionDetailPage } from "./pages/SessionDetailPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SourcesPage } from "./pages/SourcesPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <SessionsPage /> },
      { path: "sessions/:sessionId", element: <SessionDetailPage /> },
      { path: "analytics", element: <AnalyticsPage /> },
      { path: "search", element: <SearchPage /> },
      { path: "benchmark", element: <BenchmarkPage /> },
      { path: "sources", element: <SourcesPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
