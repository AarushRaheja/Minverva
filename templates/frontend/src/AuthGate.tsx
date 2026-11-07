import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { currentUser, signIn, signUp } from "./api";

// Written by the integrator, not a model. The generated UI only ever renders for a signed-in user.
export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "signed-in" | "signed-out">("loading");
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    currentUser()
      .then((user) => setState(user ? "signed-in" : "signed-out"))
      .catch(() => setState("signed-out"));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await (mode === "sign-in" ? signIn : signUp)(email, password);
      setState("signed-in");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Something went wrong");
    }
  }

  if (state === "loading") return <main className="p-8 text-slate-900">Loading…</main>;
  if (state === "signed-in") return <>{children}</>;
  return (
    <main className="mx-auto max-w-sm p-6 text-slate-900">
      <h1 className="mb-6 text-2xl font-semibold">{mode === "sign-in" ? "Sign in" : "Create account"}</h1>
      <form data-testid="auth-form" onSubmit={submit} className="space-y-4">
        <label className="block text-sm font-medium">
          Email
          <input data-testid="auth-email" type="email" required value={email} autoComplete="email"
            onChange={(e) => setEmail(e.target.value)} className="mt-1 block w-full rounded border border-slate-500 px-3 py-2" />
        </label>
        <label className="block text-sm font-medium">
          Password
          <input data-testid="auth-password" type="password" required minLength={8} value={password}
            autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
            onChange={(e) => setPassword(e.target.value)} className="mt-1 block w-full rounded border border-slate-500 px-3 py-2" />
        </label>
        {error && <p role="alert" data-testid="auth-error" className="text-sm text-red-800">{error}</p>}
        <button data-testid="auth-submit" type="submit" className="w-full rounded bg-blue-700 px-4 py-2 font-medium text-white">
          {mode === "sign-in" ? "Sign in" : "Create account"}
        </button>
      </form>
      <button data-testid="auth-mode" type="button" onClick={() => { setMode(mode === "sign-in" ? "sign-up" : "sign-in"); setError(""); }}
        className="mt-4 min-h-6 text-sm text-blue-800 underline">
        {mode === "sign-in" ? "Need an account? Create one" : "Have an account? Sign in"}
      </button>
    </main>
  );
}
