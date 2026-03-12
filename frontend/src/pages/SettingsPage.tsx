import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAccounts, updateAccount } from '@/lib/api';

type CostBasisMethod = 'fifo' | 'lifo' | 'average_cost' | 'specific_id';

const COST_BASIS_OPTIONS: {
  value: CostBasisMethod;
  label: string;
  description: string;
  disabled?: boolean;
}[] = [
  { value: 'fifo', label: 'FIFO', description: 'First In, First Out — oldest shares sold first' },
  { value: 'lifo', label: 'LIFO', description: 'Last In, First Out — newest shares sold first' },
  {
    value: 'average_cost',
    label: 'Average Cost',
    description: 'Uses the average cost of all shares in the position',
  },
  {
    value: 'specific_id',
    label: 'Specific ID',
    description: 'Manually identify which lots to sell — Phase 3 feature',
    disabled: true,
  },
];

const ACCOUNT_TYPES = [
  'brokerage',
  'retirement_traditional',
  'retirement_roth',
  'checking',
  'savings',
  'crypto',
  'credit_card',
  'other',
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-6 py-4">
        <h2 className="font-medium">{title}</h2>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
}

type Account = {
  id: string;
  account_name: string;
  account_type: string;
  institution_name: string | null;
};

export function SettingsPage() {
  const [costBasis, setCostBasis] = useState<CostBasisMethod>('fifo');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editType, setEditType] = useState('');
  const qc = useQueryClient();

  const { data: accountsData, isLoading: accountsLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then(r => r.data),
  });

  const accounts: Account[] = accountsData?.items ?? accountsData ?? [];

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      updateAccount(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] });
      setEditingId(null);
    },
  });

  const startEdit = (a: Account) => {
    setEditingId(a.id);
    setEditName(a.account_name);
    setEditType(a.account_type);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      {/* Cost Basis Method */}
      <Section title="Cost Basis Method">
        <p className="mb-4 text-sm text-gray-500">
          Determines how realized gains are calculated when shares are sold. Applies globally
          across all accounts.
        </p>
        <fieldset className="space-y-3">
          {COST_BASIS_OPTIONS.map(opt => (
            <label
              key={opt.value}
              className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors ${
                costBasis === opt.value
                  ? 'border-gray-900 bg-gray-50'
                  : 'border-gray-200 hover:border-gray-300'
              } ${opt.disabled ? 'cursor-not-allowed opacity-50' : ''}`}
            >
              <input
                type="radio"
                name="costBasis"
                value={opt.value}
                checked={costBasis === opt.value}
                disabled={opt.disabled}
                onChange={() => setCostBasis(opt.value)}
                className="mt-0.5 accent-gray-900"
              />
              <div>
                <p className="text-sm font-medium">{opt.label}</p>
                <p className="text-xs text-gray-500">{opt.description}</p>
              </div>
            </label>
          ))}
        </fieldset>
        <p className="mt-4 text-xs text-gray-400">
          Cost basis calculation is a Phase 3 feature. This preference will be applied once tax
          lot tracking is implemented.
        </p>
      </Section>

      {/* Account Management */}
      <Section title="Accounts">
        {accountsLoading ? (
          <div className="h-24 animate-pulse rounded bg-gray-100" />
        ) : accounts.length === 0 ? (
          <p className="text-sm text-gray-400">
            No accounts yet. Import a statement to get started.
          </p>
        ) : (
          <div className="divide-y divide-gray-100">
            {accounts.map(acc => (
              <div key={acc.id} className="py-3">
                {editingId === acc.id ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      value={editName}
                      onChange={e => setEditName(e.target.value)}
                      className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                      placeholder="Account name"
                    />
                    <select
                      value={editType}
                      onChange={e => setEditType(e.target.value)}
                      className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                    >
                      {ACCOUNT_TYPES.map(t => (
                        <option key={t} value={t}>
                          {t.replace(/_/g, ' ')}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() =>
                        updateMutation.mutate({
                          id: acc.id,
                          data: { account_name: editName, account_type: editType },
                        })
                      }
                      disabled={updateMutation.isPending}
                      className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                    >
                      {updateMutation.isPending ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-gray-400"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{acc.account_name}</p>
                      <p className="text-xs text-gray-400">
                        {acc.institution_name ?? 'Unknown institution'} ·{' '}
                        {acc.account_type.replace(/_/g, ' ')}
                      </p>
                    </div>
                    <button
                      onClick={() => startEdit(acc)}
                      className="text-xs text-gray-400 hover:text-gray-700"
                    >
                      Edit
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Data Export */}
      <Section title="Data Export">
        <p className="mb-4 text-sm text-gray-500">
          Export your normalised data as CSV for use in spreadsheets or other tools.
        </p>
        <div className="flex flex-wrap gap-3">
          <a
            href="/api/v1/transactions?format=csv"
            download="transactions.csv"
            className="inline-flex items-center gap-2 rounded-md border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-gray-400"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            Export Transactions (CSV)
          </a>
          <a
            href="/api/v1/holdings?format=csv"
            download="holdings.csv"
            className="inline-flex items-center gap-2 rounded-md border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-gray-400"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            Export Holdings (CSV)
          </a>
        </div>
      </Section>

      {/* About */}
      <Section title="About">
        <dl className="space-y-2 text-sm">
          <div className="flex gap-4">
            <dt className="w-32 text-gray-500">Version</dt>
            <dd className="font-medium">0.1.0 — Phase 1</dd>
          </div>
          <div className="flex gap-4">
            <dt className="w-32 text-gray-500">API Docs</dt>
            <dd>
              <a
                href="/api/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                /api/docs
              </a>
            </dd>
          </div>
          <div className="flex gap-4">
            <dt className="w-32 text-gray-500">Stack</dt>
            <dd className="text-gray-600">FastAPI · SQLAlchemy 2 · Celery · React 18 · Vite</dd>
          </div>
        </dl>
      </Section>
    </div>
  );
}
