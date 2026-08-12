import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { App } from '../src/app/App';
import { fixtureSessionManifests } from '../src/mocks/sessionFixtures';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('Dataset Library and session loading', () => {
  it('parses the shared canonical fixtures and renders the session list', () => {
    expect(fixtureSessionManifests).toHaveLength(3);
    expect(
      fixtureSessionManifests.every(
        (manifest) => manifest.schema_version === 'dreamcore.session.v1',
      ),
    ).toBe(true);

    renderAt('/datasets');
    expect(screen.getByTestId('datasets-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Dataset Library' }),
    ).toBeVisible();
    expect(screen.getByTestId('session-row-fixture-a')).toBeInTheDocument();
    expect(screen.getByTestId('session-row-fixture-b')).toBeInTheDocument();
    expect(screen.getByTestId('session-row-fixture-c')).toBeInTheDocument();
  });

  it('searches the metadata-only session catalog', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');

    await user.type(screen.getByLabelText('Search sessions'), 'TEST-SUBJECT-C');

    expect(screen.getByTestId('session-row-fixture-c')).toBeInTheDocument();
    expect(
      screen.queryByTestId('session-row-fixture-a'),
    ).not.toBeInTheDocument();
  });

  it('updates valid-session results with capability filters', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');
    expect(screen.getByTestId('valid-session-count')).toHaveTextContent('2');

    await user.click(screen.getByRole('button', { name: 'Phase estimation' }));

    expect(screen.getByTestId('valid-session-count')).toHaveTextContent('1');
  });

  it('selects a session without immediately loading it', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');

    await user.click(screen.getByTestId('session-row-fixture-b'));

    const selected = screen.getByRole('region', { name: 'Selected session' });
    expect(within(selected).getByText('fixture-b')).toBeVisible();
    expect(within(selected).getByText(/No replay has started/i)).toBeVisible();
  });

  it('uses Random Session to select from current candidates', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');

    await user.click(screen.getByRole('button', { name: /^Random Session$/ }));

    expect(screen.getByRole('status')).toHaveTextContent(/Random selection:/i);
    expect(
      screen.getByRole('region', { name: 'Selected session' }),
    ).not.toHaveTextContent('Select a catalog row');
  });

  it('uses Random Valid Session to respect the current eligibility filter', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');

    await user.click(
      screen.getByRole('button', { name: /^Random Valid Session$/ }),
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      /Random valid selection:/i,
    );
    const selected = screen.getByRole('region', { name: 'Selected session' });
    expect(selected).not.toHaveTextContent('fixture-c');
  });

  it('loads an offline fixture and adapts missing capability rendering', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');

    await user.click(screen.getByTestId('session-row-fixture-b'));
    await user.click(screen.getByRole('button', { name: 'Load Session' }));

    expect(
      await screen.findByRole('heading', { name: 'Live Console' }),
    ).toBeVisible();
    expect(
      screen.getAllByText('fixture-b', { exact: true }).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    expect(
      screen.getAllByText('Unavailable in this session').length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText('62 bpm')).not.toBeInTheDocument();
    expect(screen.queryByText('98%')).not.toBeInTheDocument();
  });

  it('shows available phase output only for a capable session', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');

    await user.click(screen.getByTestId('session-row-fixture-a'));
    await user.click(screen.getByRole('button', { name: 'Load Session' }));

    expect(
      await screen.findByRole('heading', { name: 'Live Console' }),
    ).toBeVisible();
    const decisionPanel = screen.getByRole('complementary', {
      name: 'AI decision panel',
    });
    expect(
      within(decisionPanel).getAllByText('Available').length,
    ).toBeGreaterThan(0);
  });

  it('keeps Live Device disabled', () => {
    renderAt('/live');
    const source = screen.getByLabelText('Data Source');
    const liveOption = within(source).getByRole('option', {
      name: 'Live Device · Unavailable',
    });
    expect(liveOption).toBeDisabled();
  });

  it('persists selected session during in-app navigation', async () => {
    const user = userEvent.setup();
    renderAt('/datasets');

    await user.click(screen.getByTestId('session-row-fixture-a'));
    await user.click(screen.getByRole('link', { name: /Live Console/ }));
    await user.click(screen.getByRole('link', { name: /Dataset Library/ }));

    const selected = screen.getByRole('region', { name: 'Selected session' });
    expect(within(selected).getByText('fixture-a')).toBeVisible();
  });
});
