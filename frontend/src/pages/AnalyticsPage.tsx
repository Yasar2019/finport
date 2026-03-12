import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAllocation, getGains } from '@/lib/api';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

type AllocTab = 'asset_class' | 'account_type' | 'sector';

const COLORS = [
  '#22c55e', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316',
];

const fmt = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
const fmtPct = (n: number) => `${n.toFixed(1)}%`;

const TAB_LABELS: Record<AllocTab, string> = {
  asset_class: 'Asset Class',
  account_type: 'Account Type',
  sector: 'Sector',
};

export function AnalyticsPage() {
  const [allocTab, setAllocTab] = useState<AllocTab>('asset_class');

  const { data: allocData, isLoading: allocLoading } = useQuery({
    queryKey: ['allocation'],
    queryFn: () => getAllocation().then(r => r.data),
  });

  const { data: gainsData, isLoading: gainsLoading } = useQuery({
    queryKey: ['gains'],
    queryFn: () => getGains().then(r => r.data),
  });

  type AllocItem = { label: string; value: number; pct: number };
  const allocItems: AllocItem[] =
    allocTab === 'asset_class' ? (allocData?.by_asset_class ?? []) :
    allocTab === 'account_type' ? (allocData?.by_account_type ?? []) :
    (allocData?.by_sector ?? []);

  type UnrealizedGain = {
    symbol: string;
    security_name: string;
    cost_basis: number;
    market_value: number;
    unrealized_gain: number;
    unrealized_gain_pct: number;
  };
  const unrealizedGains: UnrealizedGain[] = gainsData?.unrealized_gains ?? [];
  const totalUnrealized: number = gainsData?.total_unrealized_gain ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Analytics</h1>

      {/* Gains summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-gray-500">Total Unrealized Gain / Loss</p>
          {gainsLoading ? (
            <div className="mt-1 h-8 w-40 animate-pulse rounded bg-gray-100" />
          ) : (
            <p
              className={`mt-1 text-3xl font-bold ${
                totalUnrealized >= 0 ? 'text-green-600' : 'text-red-500'
              }`}
            >
              {totalUnrealized >= 0 ? '+' : ''}{fmt(totalUnrealized)}
            </p>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-gray-500">Realized Gain / Loss (YTD)</p>
          {gainsLoading ? (
            <div className="mt-1 h-8 w-40 animate-pulse rounded bg-gray-100" />
          ) : (
            <p className="mt-1 text-3xl font-bold text-gray-400">
              {gainsData?.total_realized_gain != null
                ? fmt(gainsData.total_realized_gain)
                : '—'}
            </p>
          )}
          {!gainsLoading && gainsData?.note && (
            <p className="mt-1 text-xs text-gray-400">{gainsData.note}</p>
          )}
        </div>
      </div>

      {/* Allocation bar chart with tab switcher */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-medium">Portfolio Allocation</h2>
          <div className="flex gap-1 rounded-lg border border-gray-200 p-1">
            {(Object.keys(TAB_LABELS) as AllocTab[]).map(tab => (
              <button
                key={tab}
                onClick={() => setAllocTab(tab)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  allocTab === tab
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {TAB_LABELS[tab]}
              </button>
            ))}
          </div>
        </div>

        {allocLoading ? (
          <div className="h-48 animate-pulse rounded bg-gray-100" />
        ) : allocItems.length === 0 ? (
          <p className="text-sm text-gray-400">
            No holdings data yet. Import a statement to see allocation.
          </p>
        ) : (
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart
                data={allocItems}
                margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 12 }}
                  tickFormatter={v => String(v).replace(/_/g, ' ')}
                />
                <YAxis
                  tickFormatter={v => `$${(Number(v) / 1000).toFixed(0)}k`}
                  tick={{ fontSize: 11 }}
                  width={55}
                />
                <Tooltip
                  formatter={(v: number) => [fmt(v), 'Value']}
                  labelFormatter={l => String(l).replace(/_/g, ' ')}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {allocItems.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            <ul className="min-w-[160px] shrink-0 space-y-2 text-sm lg:w-44">
              {allocItems.map((item, i) => (
                <li key={item.label} className="flex items-center gap-2">
                  <span
                    className="inline-block h-3 w-3 shrink-0 rounded-full"
                    style={{ background: COLORS[i % COLORS.length] }}
                  />
                  <span className="flex-1 capitalize text-gray-700">
                    {item.label.replace(/_/g, ' ')}
                  </span>
                  <span className="font-medium text-gray-500">{fmtPct(item.pct)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Unrealized gains table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-medium">Unrealized Gains / Losses by Holding</h2>
        </div>
        {gainsLoading ? (
          <div className="p-6">
            <div className="h-32 animate-pulse rounded bg-gray-100" />
          </div>
        ) : unrealizedGains.length === 0 ? (
          <p className="px-6 py-4 text-sm text-gray-400">
            No holdings with cost basis data yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-gray-100 bg-gray-50 text-xs text-gray-500">
                <tr>
                  {['Symbol', 'Name', 'Cost Basis', 'Market Value', 'Gain / Loss', '%'].map(
                    h => (
                      <th key={h} className="px-4 py-3 text-left font-medium">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {unrealizedGains.map(g => (
                  <tr key={g.symbol} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{g.symbol}</td>
                    <td className="max-w-[200px] truncate px-4 py-3 text-gray-600">
                      {g.security_name}
                    </td>
                    <td className="px-4 py-3">{fmt(g.cost_basis)}</td>
                    <td className="px-4 py-3">{fmt(g.market_value)}</td>
                    <td
                      className={`px-4 py-3 font-medium ${
                        g.unrealized_gain >= 0 ? 'text-green-600' : 'text-red-500'
                      }`}
                    >
                      {g.unrealized_gain >= 0 ? '+' : ''}{fmt(g.unrealized_gain)}
                    </td>
                    <td
                      className={`px-4 py-3 font-medium ${
                        g.unrealized_gain_pct >= 0 ? 'text-green-600' : 'text-red-500'
                      }`}
                    >
                      {g.unrealized_gain_pct >= 0 ? '+' : ''}{fmtPct(g.unrealized_gain_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
