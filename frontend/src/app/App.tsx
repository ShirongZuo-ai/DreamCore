import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '../components/layout/AppShell';
import { LiveConsolePage } from '../pages/LiveConsolePage';
import { DatasetLibraryPage } from '../pages/DatasetLibraryPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { SessionDetailsPage } from '../pages/SessionDetailsPage';
import { SessionReviewPage } from '../pages/SessionReviewPage';
import { SubjectViewPage } from '../pages/SubjectViewPage';
import { SessionWorkspaceProvider } from './SessionWorkspaceProvider';

export function App() {
  return (
    <SessionWorkspaceProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate replace to="/live" />} />
          <Route path="live" element={<LiveConsolePage />} />
          <Route path="datasets" element={<DatasetLibraryPage />} />
          <Route
            path="datasets/:datasetId/sessions/:sessionId"
            element={<SessionDetailsPage />}
          />
          <Route path="review" element={<SessionReviewPage />} />
          <Route path="subject" element={<SubjectViewPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </SessionWorkspaceProvider>
  );
}
