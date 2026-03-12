import { BrowserRouter, Route, Routes, Navigate } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { DashboardPage }     from '@/pages/DashboardPage';
import { ImportsPage }       from '@/pages/ImportsPage';
import { AccountsPage }      from '@/pages/AccountsPage';
import { TransactionsPage }  from '@/pages/TransactionsPage';
import { HoldingsPage }      from '@/pages/HoldingsPage';
import { AnalyticsPage }     from '@/pages/AnalyticsPage';
import { ReconciliationPage } from '@/pages/ReconciliationPage';
import { SettingsPage }      from '@/pages/SettingsPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"      element={<DashboardPage />} />
          <Route path="/imports"        element={<ImportsPage />} />
          <Route path="/accounts"       element={<AccountsPage />} />
          <Route path="/transactions"   element={<TransactionsPage />} />
          <Route path="/holdings"       element={<HoldingsPage />} />
          <Route path="/analytics"      element={<AnalyticsPage />} />
          <Route path="/reconciliation" element={<ReconciliationPage />} />
          <Route path="/settings"       element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
