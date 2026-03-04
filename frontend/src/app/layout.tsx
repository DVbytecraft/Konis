import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import { AuthProvider } from "@/contexts/auth-context";
import "./globals.css";

const poppins = Poppins({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  display: "swap",
  variable: "--font-poppins",
});

export const metadata: Metadata = {
  title: "KONIS – Gestion provenderie",
  description: "Application de gestion KONIS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr" className="overflow-x-hidden">
      <body
        className={`${poppins.variable} min-h-screen bg-background font-sans antialiased text-base`}
      >
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
