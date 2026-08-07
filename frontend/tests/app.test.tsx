import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { App } from '../src/app/App';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('application routing and core safety boundaries', () => {
  it('redirects the root path to the Live Console', async () => {
    renderAt('/');
    expect(await screen.findByTestId('live-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Live Console' }),
    ).toBeInTheDocument();
  });

  it.each([
    ['/live', 'live-page'],
    ['/review', 'review-page'],
    ['/subject', 'subject-page'],
  ])('renders %s', (path, testId) => {
    renderAt(path);
    expect(screen.getByTestId(testId)).toBeInTheDocument();
  });

  it('shows all six configured EEG channels', () => {
    renderAt('/live');
    const channelList = screen.getByTestId('eeg-channel-list');

    for (const channel of ['Fp1', 'Fp2', 'F3', 'F4', 'F7', 'F8']) {
      expect(within(channelList).getByText(channel)).toBeInTheDocument();
    }
  });

  it('keeps Emergency Stop visible and changes only local demo state', () => {
    renderAt('/live');
    const stopButton = screen.getByRole('button', { name: /Emergency Stop/i });
    expect(stopButton).toBeVisible();

    fireEvent.click(stopButton);

    expect(screen.getByRole('status')).toHaveTextContent(
      'Local demo stop is active',
    );
    expect(screen.getByText(/No command was sent/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Reset local demo/i }),
    ).toBeVisible();
  });

  it('does not expose blinded condition labels in Subject View', () => {
    renderAt('/subject');
    const page = screen.getByTestId('subject-page');
    expect(page).not.toHaveTextContent(/\bActive\b/i);
    expect(page).not.toHaveTextContent(/\bSham\b/i);
  });

  it('shows the Demo Mode badge globally', () => {
    renderAt('/review');
    expect(
      screen.getByLabelText(/Demo Mode: simulated data only/i),
    ).toBeInTheDocument();
  });
});
