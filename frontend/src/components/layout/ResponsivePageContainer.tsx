import type { ReactNode } from 'react';

export function ResponsivePageContainer({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto min-h-[calc(100vh-4rem)] w-full min-w-0 max-w-[1600px] px-4 py-5 pb-24 sm:px-5 sm:pb-8 lg:px-6 lg:py-6">
      {children}
    </main>
  );
}
