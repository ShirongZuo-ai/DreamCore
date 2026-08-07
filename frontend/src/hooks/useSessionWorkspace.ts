import { useContext } from 'react';

import { SessionWorkspaceContext } from '../app/sessionWorkspaceContext';

export function useSessionWorkspace() {
  const context = useContext(SessionWorkspaceContext);
  if (!context) {
    throw new Error(
      'useSessionWorkspace must be used within SessionWorkspaceProvider',
    );
  }
  return context;
}
