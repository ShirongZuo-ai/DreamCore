import { createContext } from 'react';

import type {
  DataSourceType,
  SessionLoadState,
  SessionSummary,
} from '../types';

export type SessionWorkspaceValue = {
  selectedSession: SessionSummary | null;
  loadState: SessionLoadState;
  dataSource: DataSourceType;
  setDataSource: (source: DataSourceType) => void;
  selectSession: (session: SessionSummary | null) => void;
  loadSelectedSession: (sourceOverride?: DataSourceType) => Promise<boolean>;
  loadDemoSimulation: () => void;
};

export const SessionWorkspaceContext =
  createContext<SessionWorkspaceValue | null>(null);
