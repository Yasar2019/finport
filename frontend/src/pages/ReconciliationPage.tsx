import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { getReconciliationIssues, resolveIssue, dismissIssue } from '@/lib/api';

const SEVERITY_COLOUR: Record<string, string> = {
  error:   'text-red-600 bg-red-50',
  warning: 'text-yellow-700 bg-yellow-50',
  info:    'text-blue-600 bg-blue-50',
};

export function ReconciliationPage() {
  const qc = useQueryClient();

  const { data: issues = [], isLoading } = useQuery({
    queryKey: ['reconciliation-issues'],
    queryFn: () => getReconciliationIssues({ status: 'open' }).then(r => r.data),
  });

  const resolveMut = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => resolveIssue(id, note),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reconciliation-issues'] }),
  });

  const dismissMut = useMutation({
    mutationFn: (id: string) => dismissIssue(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reconciliation-issues'] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">Reconciliation</h1>
        {(issues as unknown[]).length > 0 && (
          <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
            {(issues as unknown[]).length} open
          </span>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (issues as unknown[]).length === 0 ? (
        <div className="flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 px-6 py-5">
          <AlertTriangle className="h-5 w-5 text-green-600" />
          <p className="text-sm font-medium text-green-800">All clear — no open reconciliation issues.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {(issues as Record<string, unknown>[]).map(issue => (
            <li
              key={String(issue.id)}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
                      SEVERITY_COLOUR[String(issue.severity)] ?? ''
                    }`}
                  >
                    {String(issue.severity)}
                  </span>
                  <span className="ml-2 text-xs text-gray-400 capitalize">
                    {String(issue.issue_type).replace(/_/g, ' ')}
                  </span>
                  <p className="mt-2 text-sm text-gray-800">{String(issue.description)}</p>
                  {issue.suggested_action != null && (
                    <p className="mt-1 text-xs text-gray-500">
                      Suggestion: {String(issue.suggested_action)}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => dismissMut.mutate(String(issue.id))}
                    className="rounded border border-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
                  >
                    Dismiss
                  </button>
                  <button
                    onClick={() =>
                      resolveMut.mutate({ id: String(issue.id), note: 'Manually resolved' })
                    }
                    className="rounded bg-brand-600 px-3 py-1 text-xs text-white hover:bg-brand-700"
                  >
                    Resolve
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
