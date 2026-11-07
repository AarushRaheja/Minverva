// src/frontend/Shell.tsx
import { VectorIndexPage } from "./VectorIndexPage";
import { MetadataFilterPage } from "./MetadataFilterPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/vector_indexes">VectorIndex</a><br />
        <a href="/metadata_filters">MetadataFilter</a><br />
      </nav>
      <main>
        <VectorIndexPage />
        <MetadataFilterPage />
      </main>
    </div>
  );
}
