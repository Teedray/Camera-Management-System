import React from 'react';
import ReactDOM from 'react-dom/client';
import {
  BrowserRouter,
  Routes,
  Route
} from "react-router-dom";
import { CookiesProvider } from 'react-cookie'
import './index.css';
import { ThemeProvider, CssBaseline } from '@mui/material';
import theme from './theme';
import App from './App';
import DashboardPage from './pages/DashboardPage';
import CloudPage from './pages/CloudPage';
import StoragePage from './pages/StoragePage';
import AuditPage from './pages/AuditPage';
import MergePage from './pages/MergePage';
import VideoList from "./pages/VideoList";
import SearchPage from "./pages/SearchPage";
import IncidentsPage from "./pages/IncidentsPage";
import ExportsPage from "./pages/ExportsPage";
import StatusPage from "./pages/StatusPage";
import AdminPage from "./pages/AdminPage";
import Login from "./pages/Login";
import Register from "./pages/Register";

const root = ReactDOM.createRoot(document.getElementById('root')); 
root.render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
    <CssBaseline />
    <CookiesProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="stream" element={<App />} />
          <Route path="cloud" element={<CloudPage />} />
          <Route path="storage" element={<StoragePage />} />
          <Route path="activity" element={<AuditPage />} />
          <Route path="merge" element={<MergePage />} />
          <Route path="videos" element={<VideoList />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="exports" element={<ExportsPage />} />
          <Route path="status" element={<StatusPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="register" element={<Register />} />
        </Routes>
      </BrowserRouter>
    </CookiesProvider>
    </ThemeProvider>
  </React.StrictMode>
);
