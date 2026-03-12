import { useQuery } from '@tanstack/react-query';
import { getHoldings } from '@/lib/api';

export function HoldingsPage() {
  const { data = [], isLoading } = useQuery({
    queryKey: ['holdings'],
    queryFn: () => getHoldings().then(r => r.data),
  });

  const fmt = (n: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Holdings</h1>
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <p className="px-6 py-8 text-sm text-gray-400">Loading…</p>
        ) : (data as unknown[]).length === 0 ? (
          <p className="px-6 py-8 text-sm text-gray-400">No holdings yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                <th className="px-6 py-3 font-medium">Symbol</th>
                <th className="px-6 py-3 font-medium">Name</th>
                <th className="px-6 py-3 font-medium text-right">Quantity</th>
                <th className="px-6 py-3 font-medium text-right">Price</th>
                <th className="px-6 py-3 font-medium text-right">Market Value</th>
                <th className="px-6 py-3 font-medium text-right">Gain / Loss</th>
              </tr>
            </thead>
            <tbody>
              {(data as Record<string, unknown>[]).map(h => {
                const gain =
                  h.market_value != null && h.cost_basis != null
                    ? Number(h.market_value) - Number(h.cost_basis)
                    : null;
                return (
                  <tr key={String(h.id)} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-6 py-3 font-mono font-semibold">{String(h.symbol)}</td>
                    <td className="max-w-xs truncate px-6 py-3 text-gray-600">{String(h.security_name ?? '—')}</td>
                    <td className="px-6 py-3 text-right font-mono">{Number(h.quantity).toFixed(4)}</td>
                    <td className="px-6 py-3 text-right font-mono">
                      {h.price != null ? fmt(Number(h.price)) : '—'}
                    </td>
                    <td className="px-6 py-3 text-right font-mono">
                      {h.market_value != null ? fmt(Number(h.market_value)) : '—'}
                    </td>
                    <td
                      className={`px-6 py-3 text-right font-mono ${
                        gain == null ? 'text-gray-400' : gain >= 0 ? 'text-green-700' : 'text-red-600'
                      }`}
                    >
                      {gain != null ? fmt(gain) : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
