import axios from "axios";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

export default api;

// ── Import / Ingestion ──────────────────────────────────────────────────────

export const uploadStatement = (file: File, accountId?: string) => {
  const form = new FormData();
  form.append("file", file);
  if (accountId) form.append("account_id", accountId);
  return api.post("/imports/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const getImportSessions = () => api.get("/imports");
export const getImportSession = (id: string) =>
  api.get(`/imports/${id}/status`);
export const reprocessSession = (id: string) =>
  api.post(`/imports/${id}/reprocess`);

// ── Accounts ─────────────────────────────────────────────────────────────────

export const getAccounts = () => api.get("/accounts");
export const getAccount = (id: string) => api.get(`/accounts/${id}`);
export const createAccount = (data: Record<string, unknown>) =>
  api.post("/accounts", data);
export const updateAccount = (id: string, data: Record<string, unknown>) =>
  api.patch(`/accounts/${id}`, data);

// ── Transactions ─────────────────────────────────────────────────────────────

export const getTransactions = (params?: Record<string, unknown>) =>
  api.get("/transactions", { params });

// ── Holdings ─────────────────────────────────────────────────────────────────

export const getHoldings = (params?: Record<string, unknown>) =>
  api.get("/holdings", { params });

// ── Analytics ────────────────────────────────────────────────────────────────

export const getNetWorth = (asOfDate?: string) =>
  api.get("/analytics/net-worth", { params: { as_of_date: asOfDate } });
export const getAllocation = (asOfDate?: string) =>
  api.get("/analytics/allocation", { params: { as_of_date: asOfDate } });
export const getGains = (params?: { date_from?: string; date_to?: string }) =>
  api.get("/analytics/performance", { params });

// ── Reconciliation ────────────────────────────────────────────────────────────

export const getReconciliationIssues = (params?: Record<string, unknown>) =>
  api.get("/reconciliation/issues", { params });
export const resolveIssue = (id: string, note: string) =>
  api.post(`/reconciliation/issues/${id}/resolve`, { resolution_note: note });
export const dismissIssue = (id: string) =>
  api.post(`/reconciliation/issues/${id}/dismiss`);
