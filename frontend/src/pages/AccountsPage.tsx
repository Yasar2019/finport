import { useQuery } from '@tanstack/react-query';
import { getAccounts } from '@/lib/api';

export function AccountsPage() {
  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then(r => r.data),
  });

  const fmt = (n: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Accounts</h1>
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <p className="px-6 py-8 text-sm text-gray-400">Loading…</p>
        ) : accounts.length === 0 ? (
          <p className="px-6 py-8 text-sm text-gray-400">
            No accounts yet. Import a statement to get started.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                <th className="px-6 py-3 font-medium">Account</th>
                <th className="px-6 py-3 font-medium">Type</th>
                <th className="px-6 py-3 font-medium">Institution</th>
                <th className="px-6 py-3 font-medium text-right">Value</th>
              </tr>
            </thead>
            <tbody>
              {(accounts as Record<string, unknown>[]).map(a => (
                <tr key={String(a.id)} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-6 py-3 font-medium">{String(a.account_name)}</td>
                  <td className="px-6 py-3 capitalize text-gray-500">{String(a.account_type).replace('_', ' ')}</td>
                  <td className="px-6 py-3 text-gray-500">{String(a.institution_name ?? '—')}</td>
                  <td className="px-6 py-3 text-right font-mono">
                    {a.latest_value != null ? fmt(Number(a.latest_value)) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
