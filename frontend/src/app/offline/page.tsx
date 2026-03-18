"use client";

export default function OfflinePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-muted/30 px-4 text-center">
      <div className="text-4xl">📡</div>
      <h1 className="text-2xl font-bold text-foreground">Hors ligne</h1>
      <p className="text-sm text-muted-foreground max-w-xs">
        Vous êtes hors connexion. Reconnectez-vous à Internet pour accéder à KONIS.
      </p>
      <button
        className="mt-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
        onClick={() => window.location.reload()}
      >
        Réessayer
      </button>
    </div>
  );
}
