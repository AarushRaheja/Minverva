// src/frontend/Shell.tsx
import { AgentPage } from "./AgentPage";
import { EscalationPage } from "./EscalationPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/agents">Agent</a><br />
        <a href="/escalations">Escalation</a><br />
      </nav>
      <main>
        <AgentPage />
        <EscalationPage />
      </main>
    </div>
  );
}
