import { useQuery } from '@tanstack/react-query';
import { getNetWorth, getAllocation } from '@/lib/api';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

const COLORS = ['#22c55e','#3b82f6','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6'];

export function DashboardPage() {
  const { data: nwData, isLoading: nwLoading } = useQuery({
    queryKey: ['net-worth'],
    queryFn: () => getNetWorth().then(r => r.data),
  });

  const { data: allocData, isLoading: allocLoading } = useQuery({
    queryKey: ['allocation'],
    queryFn: () => getAllocation().then(r => r.data),
  });

  const netWorth: number = nwData?.total_net_worth ?? 0;
  const accounts: { account_name: string; value: number }[] = nwData?.accounts ?? [];
  const byAssetClass: { label: string; value: number; pct: number }[] =
    allocData?.by_asset_class ?? [];

  const fmt = (n: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      {/* Net Worth Card */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <p className="text-sm text-gray-500">Total Net Worth</p>
        {nwLoading ? (
          <p className="mt-1 h-9 w-48 animate-pulse rounded bg-gray-100" />
        ) : (
          <p className="mt-1 text-4xl font-bold tracking-tight">{fmt(netWorth)}</p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Accounts breakdown */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 font-medium">Accounts</h2>
          {nwLoading ? (
            <p className="text-sm text-gray-400">Loading…</p>
          ) : (
            <ul className="space-y-2">
              {accounts.map(a => (
                <li key={a.account_name} className="flex justify-between text-sm">
                  <span className="text-gray-700">{a.account_name}</span>
                  <span className="font-medium">{fmt(a.value)}</span>
                </li>
              ))}
              {accounts.length === 0 && (
                <li className="text-sm text-gray-400">No accounts yet — import a statement.</li>
              )}
            </ul>
          )}
        </div>

        {/* Asset allocation pie */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 font-medium">Asset Allocation</h2>
          {allocLoading ? (
            <p className="text-sm text-gray-400">Loading…</p>
          ) : byAssetClass.length === 0 ? (
            <p className="text-sm text-gray-400">No holdings yet.</p>
          ) : (
            <div className="flex items-center gap-6">
              <ResponsiveContainer width={160} height={160}>
                <PieChart>
                  <Pie data={byAssetClass} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={70}>
                    {byAssetClass.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => fmt(v)} />
                </PieChart>
              </ResponsiveContainer>
              <ul className="space-y-1 text-sm">
                {byAssetClass.map((item, i) => (
                  <li key={item.label} className="flex items-center gap-2">
                    <span
                      className="inline-block h-3 w-3 rounded-full"
                      style={{ background: COLORS[i % COLORS.length] }}
                    />
                    <span className="text-gray-700 capitalize">{item.label}</span>
                    <span className="text-gray-400">{item.pct}%</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
