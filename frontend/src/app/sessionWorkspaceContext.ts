import { createContext } from 'react';

import type {
  DatasetSummary,
  DataSourceType,
  SessionLoadState,
  SessionSummary,
} from '../types';
import type { ReplaySource } from '../services/replaySource';

export type SessionCatalogState = {
  status: 'loading' | 'ready' | 'partial-error';
  datasets: DatasetSummary[];
  sessions: SessionSummary[];
  error: string | null;
};

export type SessionWorkspaceValue = {
  selectedSession: SessionSummary | null;
  loadState: SessionLoadState;
  dataSource: DataSourceType;
  catalog: SessionCatalogState;
  replaySource: ReplaySource | null;
  setDataSource: (source: DataSourceType) => void;
  selectSession: (session: SessionSummary | null) => void;
  loadSelectedSession: (sourceOverride?: DataSourceType) => Promise<boolean>;
  loadDemoSimulation: () => void;
};

export const SessionWorkspaceContext =
  createContext<SessionWorkspaceValue | null>(null);
