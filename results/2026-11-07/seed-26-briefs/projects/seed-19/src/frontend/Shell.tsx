// src/frontend/Shell.tsx
import { AccountProviderPage } from "./AccountProviderPage";
import { AccountRequestPage } from "./AccountRequestPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/account_providers">AccountProvider</a><br />
        <a href="/account_requests">AccountRequest</a><br />
      </nav>
      <main>
        <AccountProviderPage />
        <AccountRequestPage />
      </main>
    </div>
  );
}
