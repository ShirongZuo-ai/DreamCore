import { Outlet } from 'react-router-dom';

import { ResponsivePageContainer } from './ResponsivePageContainer';
import { TopNavigation } from './TopNavigation';

export function AppShell() {
  return (
    <div className="min-h-screen min-w-0 bg-canvas">
      <TopNavigation />
      <ResponsivePageContainer>
        <Outlet />
      </ResponsivePageContainer>
    </div>
  );
}
