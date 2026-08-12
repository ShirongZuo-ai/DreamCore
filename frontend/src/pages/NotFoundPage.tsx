import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="grid min-h-[60vh] place-items-center text-center">
      <div>
        <p className="font-mono text-sm text-accent">404</p>
        <h1 className="mt-2 text-2xl font-semibold text-primary">
          Page not found
        </h1>
        <p className="mt-2 text-sm text-secondary">
          This research console route does not exist.
        </p>
        <Link
          className="mt-6 inline-flex items-center gap-2 rounded-control border border-line bg-elevated px-4 py-2.5 text-sm font-semibold text-primary hover:border-accent/50"
          to="/live"
        >
          <ArrowLeft aria-hidden="true" size={16} /> Return to Live Console
        </Link>
      </div>
    </div>
  );
}
