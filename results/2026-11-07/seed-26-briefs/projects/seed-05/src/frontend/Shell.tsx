// src/frontend/Shell.tsx
import { AccountPage } from "./AccountPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/accounts">Account</a><br />
      </nav>
      <main>
        <AccountPage />
      </main>
    </div>
  );
}
