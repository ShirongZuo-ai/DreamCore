import {
  Activity,
  ClipboardCheck,
  ClipboardList,
  Database,
  UserRound,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { ConnectionStatus } from './ConnectionStatus';
import { DemoModeBadge } from './DemoModeBadge';

const links = [
  { to: '/live', label: 'Live Console', shortLabel: 'Live', icon: Activity },
  {
    to: '/datasets',
    label: 'Dataset Library',
    shortLabel: 'Data',
    icon: Database,
  },
  {
    to: '/validation',
    label: 'Signal Validation',
    shortLabel: 'Validate',
    icon: ClipboardCheck,
  },
  {
    to: '/review',
    label: 'Session Review',
    shortLabel: 'Review',
    icon: ClipboardList,
  },
  {
    to: '/subject',
    label: 'Subject View',
    shortLabel: 'Subject',
    icon: UserRound,
  },
] as const;

export function TopNavigation() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className="mx-auto flex h-16 w-full max-w-[1600px] items-center gap-3 px-4 lg:px-6">
        <NavLink
          className="mr-auto flex shrink-0 items-center gap-2 text-primary"
          to="/live"
          aria-label="DreamCore home"
        >
          <span className="grid size-8 place-items-center rounded-control border border-accent/40 bg-accent/10 font-mono text-xs font-semibold text-accent">
            DC
          </span>
          <span className="hidden text-sm font-semibold tracking-[0.08em] sm:inline">
            DreamCore
          </span>
        </NavLink>

        <nav
          aria-label="Primary navigation"
          className="order-last w-full sm:order-none sm:w-auto"
        >
          <div className="fixed inset-x-0 bottom-0 z-50 grid h-16 grid-cols-5 border-t border-line bg-surface px-2 sm:static sm:flex sm:h-auto sm:border-0 sm:bg-transparent sm:p-0">
            {links.map(({ to, label, shortLabel, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex min-w-0 items-center justify-center gap-1.5 border-t-2 px-2 text-xs font-medium sm:rounded-control sm:border-0 sm:px-3 sm:py-2 ${
                    isActive
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-transparent text-secondary hover:bg-elevated hover:text-primary'
                  }`
                }
              >
                <Icon aria-hidden="true" size={15} />
                <span className="hidden lg:inline">{label}</span>
                <span className="lg:hidden">{shortLabel}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        <div className="flex items-center gap-3 sm:border-l sm:border-line sm:pl-4">
          <DemoModeBadge />
          <ConnectionStatus />
        </div>
      </div>
    </header>
  );
}
