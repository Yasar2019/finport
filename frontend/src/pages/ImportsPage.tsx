import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Upload, FileText, CheckCircle, XCircle, Clock, RefreshCw } from 'lucide-react';
import { clsx } from 'clsx';
import { uploadStatement, getImportSessions, reprocessSession } from '@/lib/api';

const STATUS_ICON: Record<string, React.ReactNode> = {
  pending:      <Clock className="h-4 w-4 text-yellow-500" />,
  processing:   <RefreshCw className="h-4 w-4 animate-spin text-blue-500" />,
  completed:    <CheckCircle className="h-4 w-4 text-green-600" />,
  failed:       <XCircle className="h-4 w-4 text-red-500" />,
  needs_review: <Clock className="h-4 w-4 text-orange-500" />,
};

export function ImportsPage() {
  const qc = useQueryClient();
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['import-sessions'],
    queryFn: () => getImportSessions().then(r => r.data.items ?? r.data),
    refetchInterval: 5000,  // poll while processing
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadStatement(file),
    onSuccess: () => {
      setUploadError(null);
      qc.invalidateQueries({ queryKey: ['import-sessions'] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Upload failed';
      setUploadError(msg);
    },
  });

  const onDrop = useCallback(
    (files: File[]) => {
      files.forEach(f => uploadMutation.mutate(f));
    },
    [uploadMutation],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    },
    maxSize: 50 * 1024 * 1024,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Import Statements</h1>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={clsx(
          'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 transition-colors',
          isDragActive ? 'border-brand-500 bg-brand-50' : 'border-gray-300 bg-white hover:border-brand-400',
        )}
      >
        <input {...getInputProps()} />
        <Upload className="mb-3 h-10 w-10 text-gray-400" />
        <p className="text-sm font-medium text-gray-700">
          {isDragActive ? 'Drop files here…' : 'Drag & drop PDF, CSV, or XLSX files'}
        </p>
        <p className="mt-1 text-xs text-gray-400">or click to browse · max 50 MB each</p>
      </div>

      {uploadError && (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{uploadError}</p>
      )}

      {/* Sessions table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-medium">Recent Imports</h2>
        </div>
        {isLoading ? (
          <p className="px-6 py-8 text-sm text-gray-400">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="px-6 py-8 text-sm text-gray-400">No imports yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                <th className="px-6 py-3 font-medium">File</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Institution</th>
                <th className="px-6 py-3 font-medium">Uploaded</th>
                <th className="px-6 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s: Record<string, string>) => (
                <tr key={s.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-6 py-3 font-medium">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-gray-400" />
                      {s.original_filename}
                    </div>
                  </td>
                  <td className="px-6 py-3">
                    <span className="flex items-center gap-1.5 capitalize">
                      {STATUS_ICON[s.status] ?? null}
                      {s.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-gray-500">{s.institution_name ?? '—'}</td>
                  <td className="px-6 py-3 text-gray-400">
                    {new Date(s.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-3">
                    {['failed', 'needs_review'].includes(s.status) && (
                      <button
                        onClick={() => reprocessSession(s.id).then(() =>
                          qc.invalidateQueries({ queryKey: ['import-sessions'] }),
                        )}
                        className="text-xs text-brand-600 hover:underline"
                      >
                        Reprocess
                      </button>
                    )}
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
