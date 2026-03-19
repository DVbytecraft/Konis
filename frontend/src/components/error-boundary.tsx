"use client";

import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

/**
 * ErrorBoundary global : capture les erreurs React non gérées et affiche
 * un écran de récupération au lieu de planter silencieusement.
 *
 * Les Error Boundaries doivent être des class components (contrainte React).
 * Utilisation dans layout.tsx : <ErrorBoundary>{children}</ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // En production, envoyer à un service de monitoring (Sentry, etc.)
    console.error("[ErrorBoundary] Erreur capturée :", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex min-h-screen items-center justify-center p-4 bg-background">
          <div className="max-w-md w-full text-center space-y-4">
            <div className="text-4xl">⚠️</div>
            <h1 className="text-xl font-semibold tracking-tight">
              Une erreur inattendue est survenue
            </h1>
            <p className="text-sm text-muted-foreground">
              {process.env.NODE_ENV === "development"
                ? (this.state.error?.message || "Erreur inconnue")
                : "Une erreur interne est survenue. Veuillez recharger la page."}
            </p>
            <div className="flex gap-2 justify-center">
              <button
                onClick={() => this.setState({ hasError: false, error: undefined })}
                className="px-4 py-2 rounded-md border text-sm hover:bg-muted transition-colors"
              >
                Réessayer
              </button>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors"
              >
                Recharger la page
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
