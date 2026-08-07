import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { demoSessionManifest } from '../mocks/sessionFixtures';
import { sessionCatalogService } from '../services/sessionCatalogService';
import type {
  DataSourceType,
  LoadedSession,
  SessionLoadState,
  SessionSummary,
} from '../types';
import {
  SessionWorkspaceContext,
  type SessionWorkspaceValue,
} from './sessionWorkspaceContext';

const demoLoadedSession: LoadedSession = {
  dataSource: 'demo-simulation',
  manifest: demoSessionManifest,
  fixture: false,
};

export function SessionWorkspaceProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [selectedSession, selectSession] = useState<SessionSummary | null>(
    null,
  );
  const [dataSource, setDataSource] =
    useState<DataSourceType>('demo-simulation');
  const [loadState, setLoadState] = useState<SessionLoadState>({
    status: 'ready',
    session: demoLoadedSession,
    error: null,
  });

  const value = useMemo<SessionWorkspaceValue>(
    () => ({
      selectedSession,
      loadState,
      dataSource,
      setDataSource,
      selectSession,
      loadSelectedSession: async (sourceOverride) => {
        const requestedSource = sourceOverride ?? dataSource;
        if (requestedSource === 'demo-simulation') {
          setLoadState({
            status: 'ready',
            session: demoLoadedSession,
            error: null,
          });
          return true;
        }
        if (requestedSource === 'live-device') {
          setLoadState({
            status: 'error',
            session: loadState.session,
            error: 'Live Device is unavailable in Phase 2A',
          });
          return false;
        }
        if (!selectedSession) {
          setLoadState({
            status: 'error',
            session: loadState.session,
            error: 'Select a TEST FIXTURE session before loading',
          });
          return false;
        }
        setLoadState({
          status: 'loading',
          session: loadState.session,
          error: null,
        });
        try {
          const manifest = await sessionCatalogService.loadSession(
            selectedSession.dataset.id,
            selectedSession.sessionId,
          );
          setLoadState({
            status: 'ready',
            session: {
              dataSource: 'offline-replay',
              manifest,
              fixture: true,
            },
            error: null,
          });
          return true;
        } catch (error) {
          setLoadState({
            status: 'error',
            session: loadState.session,
            error:
              error instanceof Error ? error.message : 'Unable to load session',
          });
          return false;
        }
      },
      loadDemoSimulation: () => {
        setDataSource('demo-simulation');
        setLoadState({
          status: 'ready',
          session: demoLoadedSession,
          error: null,
        });
      },
    }),
    [dataSource, loadState, selectedSession],
  );

  return (
    <SessionWorkspaceContext.Provider value={value}>
      {children}
    </SessionWorkspaceContext.Provider>
  );
}
