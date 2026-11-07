// src/frontend/Shell.tsx
import { BucketPage } from "./BucketPage";
import { RaftLogPage } from "./RaftLogPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/buckets">Bucket</a><br />
        <a href="/raft_logs">RaftLog</a><br />
      </nav>
      <main>
        <BucketPage />
        <RaftLogPage />
      </main>
    </div>
  );
}
