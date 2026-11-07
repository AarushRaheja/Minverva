// src/frontend/Shell.tsx
import { CepTaskPage } from "./CepTaskPage";
import { PartitionDefinitionPage } from "./PartitionDefinitionPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/cep_tasks">CepTask</a><br />
        <a href="/partition_definitions">PartitionDefinition</a><br />
      </nav>
      <main>
        <CepTaskPage />
        <PartitionDefinitionPage />
      </main>
    </div>
  );
}
