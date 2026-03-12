import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTransactions } from '@/lib/api';

export function TransactionsPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ['transactions', page],
    queryFn: () => getTransactions({ page, limit: 50 }).then(r => r.data),
  });

  const items: Record<string, unknown>[] = data?.items ?? [];
  const total: number = data?.total ?? 0;

  const fmt = (n: number, currency = 'USD') =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Transactions</h1>
        <p className="text-sm text-gray-400">{total.toLocaleString()} total</p>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <p className="px-6 py-8 text-sm text-gray-400">Loading…</p>
        ) : items.length === 0 ? (
          <p className="px-6 py-8 text-sm text-gray-400">No transactions yet.</p>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="px-6 py-3 font-medium">Date</th>
                  <th className="px-6 py-3 font-medium">Description</th>
                  <th className="px-6 py-3 font-medium">Type</th>
                  <th className="px-6 py-3 font-medium">Symbol</th>
                  <th className="px-6 py-3 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {items.map(tx => (
                  <tr key={String(tx.id)} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-6 py-3 font-mono text-xs">{String(tx.transaction_date)}</td>
                    <td className="max-w-xs truncate px-6 py-3 text-gray-700">
                      {String(tx.description_raw)}
                    </td>
                    <td className="px-6 py-3 capitalize text-gray-500">
                      {String(tx.transaction_type).replace('_', ' ')}
                    </td>
                    <td className="px-6 py-3 font-mono text-gray-500">
                      {String(tx.symbol ?? '—')}
                    </td>
                    <td
                      className={`px-6 py-3 text-right font-mono ${
                        Number(tx.amount) < 0 ? 'text-red-600' : 'text-green-700'
                      }`}
                    >
                      {fmt(Number(tx.amount))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-6 py-3">
              <button
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                className="rounded px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs text-gray-400">Page {page}</span>
              <button
                disabled={items.length < 50}
                onClick={() => setPage(p => p + 1)}
                className="rounded px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
