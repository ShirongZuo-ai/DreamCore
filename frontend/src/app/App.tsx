import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '../components/layout/AppShell';
import { LiveConsolePage } from '../pages/LiveConsolePage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { SessionReviewPage } from '../pages/SessionReviewPage';
import { SubjectViewPage } from '../pages/SubjectViewPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate replace to="/live" />} />
        <Route path="live" element={<LiveConsolePage />} />
        <Route path="review" element={<SessionReviewPage />} />
        <Route path="subject" element={<SubjectViewPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
