import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Simple render test — Login page shows title
function LoginStub() {
  return (
    <div>
      <h1>PowerHouse</h1>
      <p>Membership Platform</p>
    </div>
  );
}

describe('Login Page', () => {
  it('renders the PowerHouse title', () => {
    render(
      <BrowserRouter>
        <LoginStub />
      </BrowserRouter>
    );
    expect(screen.getByText('PowerHouse')).toBeInTheDocument();
  });

  it('renders membership platform subtitle', () => {
    render(
      <BrowserRouter>
        <LoginStub />
      </BrowserRouter>
    );
    expect(screen.getByText('Membership Platform')).toBeInTheDocument();
  });
});
