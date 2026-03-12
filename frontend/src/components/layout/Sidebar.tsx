import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Upload,
  Wallet,
  ArrowLeftRight,
  PieChart,
  BarChart3,
  AlertTriangle,
  Settings,
} from 'lucide-react';
import { clsx } from 'clsx';

const NAV_ITEMS = [
  { to: '/dashboard',      label: 'Dashboard',      Icon: LayoutDashboard },
  { to: '/imports',        label: 'Import',          Icon: Upload },
  { to: '/accounts',       label: 'Accounts',        Icon: Wallet },
  { to: '/transactions',   label: 'Transactions',    Icon: ArrowLeftRight },
  { to: '/holdings',       label: 'Holdings',        Icon: PieChart },
  { to: '/analytics',      label: 'Analytics',       Icon: BarChart3 },
  { to: '/reconciliation', label: 'Reconciliation',  Icon: AlertTriangle },
  { to: '/settings',       label: 'Settings',        Icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="flex w-64 flex-col border-r border-gray-200 bg-white">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2 border-b border-gray-200 px-6">
        <BarChart3 className="h-6 w-6 text-brand-600" />
        <span className="text-lg font-semibold tracking-tight">FinPort</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-brand-50 text-brand-700'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t border-gray-200 px-6 py-4">
        <p className="text-xs text-gray-400">FinPort v0.1 — Local Mode</p>
      </div>
    </aside>
  );
}
