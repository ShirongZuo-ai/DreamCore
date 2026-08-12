import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { demoSessionManifest } from '../mocks/sessionFixtures';
import {
  FixtureReplaySource,
  HttpReplaySource,
} from '../services/replaySource';
import type { ReplaySource } from '../services/replaySource';
import {
  httpSessionCatalogService,
  sessionCatalogService,
} from '../services/sessionCatalogService';
import type {
  DataSourceType,
  LoadedSession,
  SessionLoadState,
  SessionSummary,
} from '../types';
import {
  SessionWorkspaceContext,
  type SessionCatalogState,
  type SessionWorkspaceValue,
} from './sessionWorkspaceContext';

const demoLoadedSession: LoadedSession = {
  dataSource: 'demo-simulation',
  manifest: demoSessionManifest,
  fixture: false,
  realPublicData: false,
};
const fixtureDatasets = sessionCatalogService.listDatasets();
const fixtureSessions = sessionCatalogService.listSessions();

function sourceForSession(session: SessionSummary): DataSourceType {
  return session.catalogTransport === 'http'
    ? 'real-public-dataset'
    : 'test-fixture';
}

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
  const [replaySource, setReplaySource] = useState<ReplaySource | null>(null);
  const [catalog, setCatalog] = useState<SessionCatalogState>({
    status: 'loading',
    datasets: fixtureDatasets,
    sessions: fixtureSessions,
    error: null,
  });
  const [loadState, setLoadState] = useState<SessionLoadState>({
    status: 'ready',
    session: demoLoadedSession,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const datasets = await httpSessionCatalogService.listDatasets(
          controller.signal,
        );
        const sessions = (
          await Promise.all(
            datasets.map((dataset) =>
              httpSessionCatalogService.listSessions(
                dataset.id,
                controller.signal,
              ),
            ),
          )
        ).flat();
        setCatalog({
          status: 'ready',
          datasets: [...fixtureDatasets, ...datasets],
          sessions: [...fixtureSessions, ...sessions],
          error: null,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setCatalog({
          status: 'partial-error',
          datasets: fixtureDatasets,
          sessions: fixtureSessions,
          error:
            error instanceof Error
              ? error.message
              : 'Real dataset API unavailable',
        });
      }
    })();
    return () => controller.abort();
  }, []);

  const value = useMemo<SessionWorkspaceValue>(
    () => ({
      selectedSession,
      loadState,
      dataSource,
      catalog,
      replaySource,
      setDataSource,
      selectSession: (session) => {
        selectSession(session);
        if (session) setDataSource(sourceForSession(session));
      },
      loadSelectedSession: async (sourceOverride) => {
        const requestedSource = sourceOverride ?? dataSource;
        if (requestedSource === 'demo-simulation') {
          setReplaySource(null);
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
            error: 'Live Device is unavailable in Phase A2',
          });
          return false;
        }
        if (!selectedSession) {
          setLoadState({
            status: 'error',
            session: loadState.session,
            error:
              'Select a Test Fixture or Real Public Dataset session before loading',
          });
          return false;
        }
        setLoadState({
          status: 'loading',
          session: loadState.session,
          error: null,
        });
        try {
          const isHttp = selectedSession.catalogTransport === 'http';
          const manifest = isHttp
            ? await httpSessionCatalogService.loadSession(
                selectedSession.dataset.id,
                selectedSession.sessionId,
              )
            : await sessionCatalogService.loadSession(
                selectedSession.dataset.id,
                selectedSession.sessionId,
              );
          const source = isHttp
            ? new HttpReplaySource(manifest)
            : new FixtureReplaySource(manifest);
          setReplaySource(source);
          setDataSource(sourceForSession(selectedSession));
          setLoadState({
            status: 'ready',
            session: {
              dataSource: sourceForSession(selectedSession),
              manifest,
              fixture: !isHttp,
              realPublicData: isHttp,
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
        setReplaySource(null);
        setLoadState({
          status: 'ready',
          session: demoLoadedSession,
          error: null,
        });
      },
    }),
    [catalog, dataSource, loadState, replaySource, selectedSession],
  );

  return (
    <SessionWorkspaceContext.Provider value={value}>
      {children}
    </SessionWorkspaceContext.Provider>
  );
}
